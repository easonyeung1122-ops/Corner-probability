#!/usr/bin/env python3
"""predict.py — Predict corner probabilities for upcoming EPL fixtures.

Usage:
    python predict.py --models cache/models/ --features cache/features.csv --matches cache/upcoming.csv
    python predict.py --models cache/models/ --features cache/features.csv --matches cache/upcoming.csv --format tsv
    python predict.py --models cache/models/ --features cache/features.csv --matches cache/upcoming.csv --format markdown

Default output format is TSV (tab-separated, copy-paste ready for Excel).
Use --format markdown for the original Markdown table output.
"""

import argparse
import csv
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from build_features import (
    safe_float, rolling_mean, rolling_mean_home_away,
    avg_corners_for_season,
)

FEATURE_COLS = [
    "H_CornersFor_N", "H_CornersAgainst_N", "H_CornersFor_S",
    "H_Shots_N", "H_ShotsOnTarget_N", "H_Goals_N", "H_Fouls_N",
    "H_PPG_N", "H_HomeCornersFor_N",
    "A_CornersFor_N", "A_CornersAgainst_N", "A_CornersFor_S",
    "A_Shots_N", "A_ShotsOnTarget_N", "A_Goals_N", "A_Fouls_N",
    "A_PPG_N", "A_AwayCornersFor_N",
    "TotalShots_N",
]

LINES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]


def load_models(model_dir: Path) -> tuple[dict, object, object]:
    """Load all six models + preprocessors."""
    models = {}
    for line in LINES:
        line_str = str(line).replace(".", "_")
        path = model_dir / f"model_{line_str}.pkl"
        if not path.exists():
            print(f"ERROR: Model file missing: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, "rb") as f:
            models[line] = pickle.load(f)

    imputer_path = model_dir / "imputer.pkl"
    scaler_path = model_dir / "scaler.pkl"
    with open(imputer_path, "rb") as f:
        imputer = pickle.load(f)
    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    return models, imputer, scaler


def load_history(raw_matches_path: Path) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Reconstruct team history from RAW matches CSV (actual HC/AC values).

    Reads only completed matches (HC + AC present), builds per-team
    rolling history with actual match outcomes. Uses the same record
    structure as build_features.py for consistent feature computation.

    Returns (team_history, team_season).
    """
    team_history: dict[str, list[dict]] = defaultdict(list)
    team_season: dict[str, dict] = defaultdict(lambda: {
        "games": 0, "corners_for_total": 0, "corners_against_total": 0,
    })

    rows = []
    with open(raw_matches_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Sort by date for correct chronological order
    rows = sorted(rows, key=lambda r: r.get("Date", ""))

    for row in rows:
        home = row.get("HomeTeam", "")
        away = row.get("AwayTeam", "")
        hc = safe_float(row.get("HC", np.nan))
        ac = safe_float(row.get("AC", np.nan))
        hs = safe_float(row.get("HS", np.nan))
        as_ = safe_float(row.get("AS", np.nan))
        hst = safe_float(row.get("HST", np.nan))
        ast = safe_float(row.get("AST", np.nan))
        hg = safe_float(row.get("FTHG", np.nan))
        ag = safe_float(row.get("FTAG", np.nan))
        hf = safe_float(row.get("HF", np.nan))
        af = safe_float(row.get("AF", np.nan))

        # Skip upcoming fixtures (no HC/AC)
        if np.isnan(hc) or np.isnan(ac):
            continue

        home_record = {
            "_venue": "H",
            "_corner_home": hc,
            "_corner_away": ac,
            "_corner_against": ac,
            "_shots": hs,
            "_shots_on_target": hst,
            "_goals": hg,
            "_fouls": hf,
            "_points": (3 if hg > ag else 1 if hg == ag else 0) if not (np.isnan(hg) or np.isnan(ag)) else np.nan,
        }
        away_record = {
            "_venue": "A",
            "_corner_home": ac,
            "_corner_away": hc,
            "_corner_against": hc,
            "_shots": as_,
            "_shots_on_target": ast,
            "_goals": ag,
            "_fouls": af,
            "_points": (3 if ag > hg else 1 if ag == hg else 0) if not (np.isnan(hg) or np.isnan(ag)) else np.nan,
        }

        team_history[home].append(home_record)
        team_history[away].append(away_record)

        for team in [home, away]:
            team_season[team]["games"] += 1
            # Track corners for season
            if team == home:
                team_season[team]["corners_for_total"] += hc
                team_season[team]["corners_against_total"] += ac
            else:
                team_season[team]["corners_for_total"] += ac
                team_season[team]["corners_against_total"] += hc

    return team_history, team_season


def build_fixture_features(fixture: dict, team_history: dict[str, list[dict]],
                           team_season: dict, n_recent: int = 5) -> dict | None:
    """Build features for a single upcoming fixture — no look-ahead."""
    home = fixture["HomeTeam"]
    away = fixture["AwayTeam"]

    h_recent = team_history[home][-n_recent:] if team_history[home] else []
    a_recent = team_history[away][-n_recent:] if team_history[away] else []

    features = {}
    features["H_CornersFor_N"] = rolling_mean(h_recent, "_corner_home")
    features["H_CornersAgainst_N"] = rolling_mean(h_recent, "_corner_against")
    features["H_CornersFor_S"] = avg_corners_for_season(team_season, home)
    features["H_Shots_N"] = rolling_mean(h_recent, "_shots")
    features["H_ShotsOnTarget_N"] = rolling_mean(h_recent, "_shots_on_target")
    features["H_Goals_N"] = rolling_mean(h_recent, "_goals")
    features["H_Fouls_N"] = rolling_mean(h_recent, "_fouls")
    features["H_PPG_N"] = rolling_mean(h_recent, "_points")

    home_matches = [m for m in h_recent if m.get("_venue") == "H"]
    features["H_HomeCornersFor_N"] = rolling_mean(home_matches[-n_recent:], "_corner_home") if home_matches else np.nan

    features["A_CornersFor_N"] = rolling_mean(a_recent, "_corner_away")
    features["A_CornersAgainst_N"] = rolling_mean(a_recent, "_corner_against")
    features["A_CornersFor_S"] = avg_corners_for_season(team_season, away)
    features["A_Shots_N"] = rolling_mean(a_recent, "_shots")
    features["A_ShotsOnTarget_N"] = rolling_mean(a_recent, "_shots_on_target")
    features["A_Goals_N"] = rolling_mean(a_recent, "_goals")
    features["A_Fouls_N"] = rolling_mean(a_recent, "_fouls")
    features["A_PPG_N"] = rolling_mean(a_recent, "_points")

    away_matches = [m for m in a_recent if m.get("_venue") == "A"]
    features["A_AwayCornersFor_N"] = rolling_mean(away_matches[-n_recent:], "_corner_away") if away_matches else np.nan

    h_shots = features.get("H_Shots_N", np.nan)
    a_shots = features.get("A_Shots_N", np.nan)
    if not np.isnan(h_shots) and not np.isnan(a_shots):
        features["TotalShots_N"] = h_shots + a_shots
    else:
        features["TotalShots_N"] = np.nan

    return features


def predict_probs(fixture: dict, features: dict, models: dict,
                  imputer, scaler) -> dict:
    """Run the fixture through all six models, return probability dict."""
    # Build feature array
    X = np.array([[safe_float(features.get(col, np.nan)) for col in FEATURE_COLS]], dtype=np.float64)
    X_imputed = imputer.transform(X)
    X_scaled = scaler.transform(X_imputed)

    probs = {}
    for line in LINES:
        p = models[line].predict_proba(X_scaled)[0, 1]
        probs[line] = round(float(p), 4)

    return probs


def enforce_monotonicity(probs: dict) -> tuple[dict, bool]:
    """Ensure P(>7.5) >= P(>8.5) >= ... >= P(>12.5).

    Returns (corrected_probs, was_corrected).
    """
    lines = LINES
    values = np.array([probs[line] for line in lines])
    corrected = np.minimum.accumulate(values)  # monotonic decreasing
    was_corrected = not np.allclose(values, corrected, atol=1e-4)

    result = {line: round(float(corrected[i]), 4) for i, line in enumerate(lines)}
    return result, was_corrected


def load_upcoming_fixtures(matches_path: Path, features_path: Path) -> list[dict]:
    """Extract upcoming fixtures from the merged data (rows without HC/AC)."""
    fixtures = []
    with open(matches_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hc = row.get("HC", "").strip()
            ac = row.get("AC", "").strip()
            if not hc or not ac:
                home = row.get("HomeTeam", "").strip()
                away = row.get("AwayTeam", "").strip()
                date_str = row.get("Date", "").strip()
                if home and away:
                    fixtures.append({"Date": date_str, "HomeTeam": home, "AwayTeam": away})

    # Deduplicate by (HomeTeam, AwayTeam)
    seen = set()
    unique = []
    for f in fixtures:
        key = (f["HomeTeam"], f["AwayTeam"])
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def key_drivers(features: dict, probs: dict, n: int = 3) -> str:
    """Generate 2-3 key driver descriptions based on feature values."""
    drivers = []
    threshold = 1.5  # standard deviation multiplier

    # Check high home corners for
    hcf = features.get("H_CornersFor_N", 0) or 0
    aca = features.get("A_CornersAgainst_N", 0) or 0
    if hcf > 6.5:
        drivers.append(f"{_short_team(features)} 高近N场角球 ({hcf:.1f})")
    if aca > 6.5:
        drivers.append(f"客队高客场角球失球 ({aca:.1f})")

    # Check total shots
    ts = features.get("TotalShots_N", 0) or 0
    if ts > 28:
        drivers.append(f"两队高射门量 ({ts:.1f})")
    elif ts < 20 and ts > 0:
        drivers.append(f"两队低射门量 ({ts:.1f})")

    # Top probability lines
    top_lines = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    if top_lines[0][1] > 0.6:
        drivers.append(f"高概率 Over {top_lines[0][0]}")

    if len(drivers) < 2:
        # Fallback with PPG
        h_ppg = features.get("H_PPG_N", 0) or 0
        a_ppg = features.get("A_PPG_N", 0) or 0
        if h_ppg > 2.0:
            drivers.append("主队近期强势")
        if a_ppg < 1.0:
            drivers.append("客队近期低迷")

    return "; ".join(drivers[:3]) if drivers else "—"


_team_short = {}
def _short_team(features: dict) -> str:
    return "主队"  # Simplified; context-dependent


def output_results_markdown(fixtures: list, all_probs: list, all_features: list,
                            all_corrected: list, model_dir: Path):
    """Print formatted results table in Markdown format."""
    meta_path = model_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    else:
        meta = {"trained_at": "unknown"}

    lines_out = []
    lines_out.append(f"# EPL Corner Probability Forecast")
    lines_out.append(f"六模型就绪 · 训练于 {meta.get('trained_at', 'unknown')[:19]}")
    lines_out.append(f"{len(fixtures)} fixtures to evaluate")
    lines_out.append("")

    header = "| # | Date | Home | Away | P(>7.5) | P(>8.5) | P(>9.5) | P(>10.5) | P(>11.5) | P(>12.5) | Key Drivers |"
    sep = "|---|------|------|------|---------|---------|---------|----------|----------|----------|-------------|"
    lines_out.append(header)
    lines_out.append(sep)

    any_corrected = False
    for i, (fixture, probs, features, corrected) in enumerate(
        zip(fixtures, all_probs, all_features, all_corrected)):
        any_corrected = any_corrected or corrected
        mark = "*" if corrected else ""
        date = fixture.get("Date", "?")
        probs_str = " | ".join(
            f"{probs.get(line, 0):.3f}" for line in LINES
        )
        drivers = key_drivers(features, probs)
        line = f"| {mark}#{i+1} | {date} | {fixture['HomeTeam']} | {fixture['AwayTeam']} | {probs_str} | {drivers} |"
        lines_out.append(line)

    if any_corrected:
        lines_out.append("")
        lines_out.append("* 已做单调性修正")

    lines_out.append("")
    lines_out.append("---")
    lines_out.append("数据来源: football-data.co.uk | 模型: RandomForest × 6 | 概率仅供参考，不构成任何建议")

    print("\n".join(lines_out))


def output_results_tsv(fixtures: list, all_probs: list, all_features: list,
                       all_corrected: list, model_dir: Path, output_path: str = None):
    """Print results as TSV table — copy-paste ready for Excel."""
    meta_path = model_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    else:
        meta = {"trained_at": "unknown"}

    lines_out = []

    # Meta-info header lines (prefixed with # so they paste as comments)
    n_matches = meta.get("n_matches", "?")
    lines_out.append(f"# EPL Corner Probability Forecast — 训练于 {meta.get('trained_at', 'unknown')[:19]} — {n_matches} 场历史")
    lines_out.append(f"# 注：* 标记表示该场概率经单调性修正 | 数据来源: football-data.co.uk | 仅供参考")
    lines_out.append("")

    # TSV Header row
    col_names = [
        "#", "日期", "主队", "客队",
        "P(>7.5)", "P(>8.5)", "P(>9.5)",
        "P(>10.5)", "P(>11.5)", "P(>12.5)",
        "关键驱动因素", "修正"
    ]
    lines_out.append("\t".join(col_names))

    any_corrected = False
    for i, (fixture, probs, features, corrected) in enumerate(
        zip(fixtures, all_probs, all_features, all_corrected)):
        any_corrected = any_corrected or corrected
        date = fixture.get("Date", "?")
        drivers = key_drivers(features, probs)
        corrected_flag = "是" if corrected else ""
        col_values = [
            str(i + 1),
            date,
            fixture['HomeTeam'],
            fixture['AwayTeam'],
            f"{probs.get(7.5, 0):.1%}",
            f"{probs.get(8.5, 0):.1%}",
            f"{probs.get(9.5, 0):.1%}",
            f"{probs.get(10.5, 0):.1%}",
            f"{probs.get(11.5, 0):.1%}",
            f"{probs.get(12.5, 0):.1%}",
            drivers,
            corrected_flag,
        ]
        lines_out.append("\t".join(col_values))

    if any_corrected:
        lines_out.append("")
        lines_out.append("# * 部分场次概率经单调性修正（P(>7.5) >= P(>8.5) >= ... >= P(>12.5) 约束）")

    result = "\n".join(lines_out)

    if output_path and output_path != "-":
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(result)
        print(f"TSV results saved to {output_path}", file=sys.stderr)
    else:
        print(result)


def output_results(fixtures: list, all_probs: list, all_features: list,
                   all_corrected: list, model_dir: Path, output_path: str = None,
                   fmt: str = "markdown"):
    """Dispatch to the correct output formatter."""
    if fmt == "tsv":
        output_results_tsv(fixtures, all_probs, all_features, all_corrected,
                           model_dir, output_path)
    else:
        output_results_markdown(fixtures, all_probs, all_features, all_corrected,
                                model_dir)


def main():
    parser = argparse.ArgumentParser(description="Predict corner probabilities")
    parser.add_argument("--models", type=str, required=True, help="Model directory")
    parser.add_argument("--features", type=str, required=True, help="Features CSV (for history)")
    parser.add_argument("--matches", type=str, required=True, help="Merged CSV with upcoming fixtures")
    parser.add_argument("--n-recent", type=int, default=5, help="Rolling window")
    parser.add_argument("--output", type=str, default="-", help="Output file or '-' for stdout")
    parser.add_argument("--format", type=str, default="tsv", choices=["markdown", "tsv"],
                        help="Output format: markdown or tsv (Excel-ready)")
    args = parser.parse_args()

    model_dir = Path(args.models)
    features_path = Path(args.features)
    matches_path = Path(args.matches)

    for p in [model_dir, features_path, matches_path]:
        if not p.exists():
            print(f"ERROR: {p} not found.", file=sys.stderr)
            sys.exit(1)

    # Load models
    models, imputer, scaler = load_models(model_dir)
    print(f"Loaded {len(models)} models", file=sys.stderr)

    # Reconstruct team history from raw match data (needs actual HC/AC values)
    team_history, team_season = load_history(matches_path)
    print(f"  Teams in history: {len(team_history)}", file=sys.stderr)

    # Load upcoming fixtures
    fixtures = load_upcoming_fixtures(matches_path, features_path)
    print(f"  Upcoming fixtures: {len(fixtures)}", file=sys.stderr)

    if not fixtures:
        print("\n[WARN] 未检测到 upcoming fixtures。当前赛季 CSV 中可能没有未赛场次。", file=sys.stderr)
        print("如果当前赛季已结束，下一个赛季 fixtures 尚未公布，请手动提供赛程。")
        return

    # Predict
    all_probs = []
    all_features = []
    all_corrected = []

    for fixture in fixtures:
        feats = build_fixture_features(fixture, team_history, team_season, args.n_recent)
        if feats is None:
            print(f"  SKIP: cannot build features for {fixture['HomeTeam']} vs {fixture['AwayTeam']}", file=sys.stderr)
            continue

        probs = predict_probs(fixture, feats, models, imputer, scaler)
        probs, was_corrected = enforce_monotonicity(probs)

        all_probs.append(probs)
        all_features.append(feats)
        all_corrected.append(was_corrected)

    # Output
    output_results(fixtures, all_probs, all_features, all_corrected, model_dir,
                   args.output, fmt=args.format)


if __name__ == "__main__":
    main()
