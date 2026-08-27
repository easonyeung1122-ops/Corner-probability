#!/usr/bin/env python3
"""build_features.py — Build walk-forward rolling features with no data leakage.

Usage:
    python build_features.py --input cache/epl_merged.csv --output cache/features.csv --n-recent 5
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

# Required raw columns from the merged data
REQUIRED_COLS = ["Date", "HomeTeam", "AwayTeam", "HC", "AC", "HS", "AS",
                 "HST", "AST", "FTHG", "FTAG", "HF", "AF"]

# Feature columns output
FEATURE_COLS = [
    "H_CornersFor_N", "H_CornersAgainst_N", "H_CornersFor_S",
    "H_Shots_N", "H_ShotsOnTarget_N", "H_Goals_N", "H_Fouls_N",
    "H_PPG_N", "H_HomeCornersFor_N",
    "A_CornersFor_N", "A_CornersAgainst_N", "A_CornersFor_S",
    "A_Shots_N", "A_ShotsOnTarget_N", "A_Goals_N", "A_Fouls_N",
    "A_PPG_N", "A_AwayCornersFor_N",
    "TotalShots_N",
]

# Corner lines to predict (Over targets)
LINES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5]

# Target columns (one per corner line)
TARGET_COLS = [f"Target_{str(line).replace('.', '_')}" for line in LINES]


def safe_float(val) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return np.nan


def rolling_mean(recent: list[dict], key: str) -> float:
    """Compute mean of key across recent matches, ignoring NaN."""
    vals = [safe_float(m.get(key)) for m in recent]
    vals = [v for v in vals if not np.isnan(v)]
    if not vals:
        return np.nan
    return sum(vals) / len(vals)


def rolling_mean_home_away(recent: list[dict], team: str, key: str, is_home: bool) -> float:
    """Compute mean of key only for home or away matches."""
    if is_home:
        vals = [safe_float(m.get(key)) for m in recent if m.get("_venue") == "H"]
    else:
        vals = [safe_float(m.get(key)) for m in recent if m.get("_venue") == "A"]
    vals = [v for v in vals if not np.isnan(v)]
    if not vals:
        return np.nan
    return sum(vals) / len(vals)


def avg_corners_for_season(team_stats: dict, team: str) -> float:
    """Season-to-date average corners for."""
    info = team_stats.get(team, {})
    games = info.get("games", 0)
    if games == 0:
        return np.nan
    return info.get("corners_for_total", 0) / games


def load_matches(input_path: Path) -> list[dict]:
    """Load and validate raw match data."""
    rows = []
    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Validate required columns
            missing = [c for c in REQUIRED_COLS if c not in row]
            if missing:
                continue
            rows.append(row)
    if not rows:
        print("ERROR: No valid match rows found.", file=sys.stderr)
        sys.exit(1)
    return rows


def build_features(rows: list[dict], n_recent: int = 5) -> tuple[list[dict], dict]:
    """Build walk-forward features.

    Walk-forward: for each match, compute rolling stats from matches played
    BEFORE this match, then update stats WITH this match. No data leakage.

    Returns (feature_rows, summary_stats).
    """
    # Per-team rolling history (most recent N matches, newest last)
    team_history: dict[str, list[dict]] = defaultdict(list)

    # Per-team season-to-date accumulators
    team_season: dict[str, dict] = defaultdict(lambda: {
        "games": 0, "corners_for_total": 0, "corners_against_total": 0,
        "goals_for": 0, "goals_against": 0,
    })

    # Season tracking – reset when a new season year boundary is crossed
    last_season_id: str | None = None

    feature_rows = []
    stats = {"total_matches": len(rows), "valid_rows": 0, "cold_start_count": 0}

    for row in rows:
        home = row["HomeTeam"]
        away = row["AwayTeam"]

        # Detect season boundary
        try:
            date_str = row["Date"]
            # football-data.co.uk dates are dd/mm/yyyy or dd/mm/yy
            parts = date_str.split("/")
            if len(parts) == 3:
                yr = int(parts[2])
                if yr < 100:
                    yr += 2000
                season_id = f"{yr}/{yr + 1}"
                if last_season_id is None:
                    last_season_id = season_id
                elif season_id != last_season_id:
                    # New season → reset all accumulators
                    team_season.clear()
                    last_season_id = season_id
            else:
                season_id = last_season_id or "?"
        except (ValueError, IndexError):
            season_id = last_season_id or "?"

        # --- Compute features from pre-match history ---
        h_recent = team_history[home][-n_recent:] if team_history[home] else []
        a_recent = team_history[away][-n_recent:] if team_history[away] else []

        if len(h_recent) < n_recent or len(a_recent) < n_recent:
            stats["cold_start_count"] += 1

        features = {}

        # Home features
        features["H_CornersFor_N"] = rolling_mean(h_recent, "_corner_home" if home else "_corner_away")
        features["H_CornersAgainst_N"] = rolling_mean(h_recent, "_corner_against")
        features["H_CornersFor_S"] = avg_corners_for_season(team_season, home)
        features["H_Shots_N"] = rolling_mean(h_recent, "_shots")
        features["H_ShotsOnTarget_N"] = rolling_mean(h_recent, "_shots_on_target")
        features["H_Goals_N"] = rolling_mean(h_recent, "_goals")
        features["H_Fouls_N"] = rolling_mean(h_recent, "_fouls")
        features["H_PPG_N"] = rolling_mean(h_recent, "_points")

        # Home corners at home (venue-specific)
        home_matches = [m for m in h_recent if m.get("_venue") == "H"]
        if home_matches:
            features["H_HomeCornersFor_N"] = rolling_mean(home_matches[-n_recent:], "_corner_home")
        else:
            features["H_HomeCornersFor_N"] = np.nan

        # Away features
        features["A_CornersFor_N"] = rolling_mean(a_recent, "_corner_away")
        features["A_CornersAgainst_N"] = rolling_mean(a_recent, "_corner_against")
        features["A_CornersFor_S"] = avg_corners_for_season(team_season, away)
        features["A_Shots_N"] = rolling_mean(a_recent, "_shots")
        features["A_ShotsOnTarget_N"] = rolling_mean(a_recent, "_shots_on_target")
        features["A_Goals_N"] = rolling_mean(a_recent, "_goals")
        features["A_Fouls_N"] = rolling_mean(a_recent, "_fouls")
        features["A_PPG_N"] = rolling_mean(a_recent, "_points")

        # Away corners away (venue-specific)
        away_matches = [m for m in a_recent if m.get("_venue") == "A"]
        if away_matches:
            features["A_AwayCornersFor_N"] = rolling_mean(away_matches[-n_recent:], "_corner_away")
        else:
            features["A_AwayCornersFor_N"] = np.nan

        # Combined
        h_shots = features.get("H_Shots_N", np.nan)
        a_shots = features.get("A_Shots_N", np.nan)
        if not np.isnan(h_shots) and not np.isnan(a_shots):
            features["TotalShots_N"] = h_shots + a_shots
        else:
            features["TotalShots_N"] = np.nan

        # --- Compute targets ---
        hc = safe_float(row.get("HC"))
        ac = safe_float(row.get("AC"))
        if not np.isnan(hc) and not np.isnan(ac):
            total = hc + ac
            for line in LINES:
                features[f"Target_{str(line).replace('.', '_')}"] = 1 if total > line else 0
            stats["valid_rows"] += 1
        else:
            for line in LINES:
                features[f"Target_{str(line).replace('.', '_')}"] = ""

        # Metadata
        features["Date"] = row.get("Date", "")
        features["HomeTeam"] = home
        features["AwayTeam"] = away

        feature_rows.append(features)

        # --- Update team history AFTER computing features ---
        # Build a history record for this match
        hr = safe_float(row.get("HS"))
        ar = safe_float(row.get("AS"))
        hst = safe_float(row.get("HST"))
        ast = safe_float(row.get("AST"))
        hg = safe_float(row.get("FTHG"))
        ag = safe_float(row.get("FTAG"))
        hf = safe_float(row.get("HF"))
        af = safe_float(row.get("AF"))

        home_record = {
            "_venue": "H",
            "_corner_home": hc,
            "_corner_away": ac,
            "_corner_against": ac,
            "_shots": hr,
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
            "_shots": ar,
            "_shots_on_target": ast,
            "_goals": ag,
            "_fouls": af,
            "_points": (3 if ag > hg else 1 if ag == hg else 0) if not (np.isnan(hg) or np.isnan(ag)) else np.nan,
        }

        team_history[home].append(home_record)
        team_history[away].append(away_record)

        # Update season accumulators
        for team, rec in [(home, home_record), (away, away_record)]:
            ts = team_season[team]
            ts["games"] += 1
            if not np.isnan(rec.get("_corner_home", np.nan)):
                ts["corners_for_total"] += rec["_corner_home"]
            if not np.isnan(rec.get("_corner_against", np.nan)):
                ts["corners_against_total"] += rec["_corner_against"]

    return feature_rows, stats


def write_features(rows: list[dict], output_path: Path):
    """Write feature rows to CSV."""
    meta_cols = ["Date", "HomeTeam", "AwayTeam"]
    all_cols = meta_cols + FEATURE_COLS + TARGET_COLS
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} feature rows to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Build walk-forward features")
    parser.add_argument("--input", type=str, required=True, help="Path to epl_merged.csv")
    parser.add_argument("--output", type=str, required=True, help="Output features CSV")
    parser.add_argument("--n-recent", type=int, default=5, help="Rolling window size")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    rows = load_matches(input_path)
    print(f"Loaded {len(rows)} matches")
    feature_rows, stats = build_features(rows, args.n_recent)
    write_features(feature_rows, Path(args.output))

    print(f"\nStats: {stats['valid_rows']} valid rows, {stats['cold_start_count']} cold-start rows")
    if stats["cold_start_count"] > 0:
        print(f"  [WARN] {stats['cold_start_count']} rows had insufficient rolling window (< {args.n_recent})")


if __name__ == "__main__":
    main()
