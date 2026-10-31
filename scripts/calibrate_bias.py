#!/usr/bin/env python3
"""Measure the live models' per-line probability bias on the current season.

Why this exists
---------------
A RandomForest trained on 2021-2026 averages over five seasons whose mean total
corners is ~10.3. When the current season runs cold (2026-27 measured 9.43 after
80 matches), every model keeps emitting probabilities anchored to the training
distribution and every line reads several points too high. On 2026-10-31 that
bias measured +6.4pp to +15.1pp, which was larger than the entire "edge" the
Polymarket report was quoting — the edge was an artefact of the bias.

The fix is to measure the bias on realised results and subtract it before
scoring edge, rather than trusting the raw output.

Output: cache/bias.json

    {
      "measured_at": "...", "season": "2026-27", "n_matches": 80,
      "bias": {"7.5": 0.0641, "8.5": 0.1508, ...},
      "method": "in-sample mean(pred) - mean(actual)"
    }

Usage:
    python scripts/calibrate_bias.py --features cache/features.csv \
        --merged cache/epl_merged.csv --models cache/models --output cache/bias.json

Then pass it to the edge report:
    python scripts/pm_edge.py ... --bias cache/bias.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

LINES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5]

FEATURE_COLS = [
    "H_CornersFor_N", "H_CornersAgainst_N", "H_CornersFor_S",
    "H_Shots_N", "H_ShotsOnTarget_N", "H_Goals_N", "H_Fouls_N",
    "H_PPG_N", "H_HomeCornersFor_N",
    "A_CornersFor_N", "A_CornersAgainst_N", "A_CornersFor_S",
    "A_Shots_N", "A_ShotsOnTarget_N", "A_Goals_N", "A_Fouls_N",
    "A_PPG_N", "A_AwayCornersFor_N",
    "TotalShots_N",
]


def season_start(today: datetime | None = None) -> str:
    """First day of the current EPL season."""
    today = today or datetime.now()
    year = today.year if today.month >= 8 else today.year - 1
    return f"{year}-08-01"


def season_label(start: str) -> str:
    y = int(start[:4])
    return f"{y}-{str(y + 1)[2:]}"


def load_frame(features: Path, merged: Path) -> pd.DataFrame:
    f = pd.read_csv(features)
    m = pd.read_csv(merged)
    m = m[m["HC"].notna()].copy()
    m["TotalCorners"] = m["HC"] + m["AC"]
    m = m[["Date", "HomeTeam", "AwayTeam", "TotalCorners"]].drop_duplicates(
        ["Date", "HomeTeam", "AwayTeam"])
    f = f.merge(m, on=["Date", "HomeTeam", "AwayTeam"], how="left")
    f["dt"] = pd.to_datetime(f["Date"], format="%d/%m/%Y", errors="coerce")
    return f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--features", default="cache/features.csv")
    ap.add_argument("--merged", default="cache/epl_merged.csv")
    ap.add_argument("--models", default="cache/models")
    ap.add_argument("--output", default="cache/bias.json")
    ap.add_argument("--min-matches", type=int, default=30,
                    help="本季已赛场次下限，低于此值不输出校准")
    args = ap.parse_args()

    f = load_frame(Path(args.features), Path(args.merged))
    start = season_start()
    cur = f[(f["dt"] >= start) & f["TotalCorners"].notna()].copy()
    n = len(cur)
    print(f"season {season_label(start)} | 本季已赛 {n} 场 (起始 {start})")

    if n < args.min_matches:
        print(f"[skip] 场次 < {args.min_matches}，本季样本不足，不写校准文件")
        Path(args.output).write_text(json.dumps(
            {"measured_at": datetime.now().isoformat(timespec="seconds"),
             "season": season_label(start), "n_matches": n, "bias": {},
             "reason": "insufficient current-season sample"}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return 0

    models_dir = Path(args.models)
    imp = joblib.load(models_dir / "imputer.pkl")
    sc = joblib.load(models_dir / "scaler.pkl")
    X = sc.transform(imp.transform(cur[FEATURE_COLS].values))

    bias: dict[str, float] = {}
    print(f"\n{'线':<7}{'模型均值':>9}{'实际':>9}{'偏差':>9}{'n':>6}")
    for line in LINES:
        path = models_dir / f"model_{str(line).replace('.', '_')}.pkl"
        if not path.exists():
            print(f"  [warn] 缺少 {path.name}，跳过 >{line}")
            continue
        mdl = joblib.load(path)
        p = mdl.predict_proba(X)[:, 1]
        y = (cur["TotalCorners"] > line).astype(int).values
        delta = float(p.mean() - y.mean())
        bias[str(line)] = round(delta, 4)
        print(f">{line:<6}{p.mean()*100:8.1f}%{y.mean()*100:8.1f}%{delta*100:+8.1f}pp{n:6d}")

    med = float(np.median(list(bias.values()))) if bias else 0.0
    print(f"\n偏差中位数 {med*100:+.1f}pp | 平均绝对偏差 "
          f"{np.mean([abs(v) for v in bias.values()])*100:.1f}pp")

    payload = {
        "measured_at": datetime.now().isoformat(timespec="seconds"),
        "season": season_label(start),
        "n_matches": n,
        "bias": bias,
        "bias_median": round(med, 4),
        "method": "in-sample mean(pred) - mean(actual) on current-season matches",
        "note": ("Positive value = model over-predicts Over. Subtracted from the "
                 "model probability before edge scoring."),
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
