#!/usr/bin/env python3
"""run_pipeline.py — End-to-end pipeline: fetch → features → train → predict → edge.

Usage:
    python run_pipeline.py [--start 2021] [--n-recent 5] [--cache-dir cache/]
    python run_pipeline.py --no-polymarket          # 只跑模型，不抓盘口
    python run_pipeline.py --bankroll 2000 --min-edge 0.04

Steps
    1. fetch_data.py      历史 + 当季 CSV
    2. build_features.py  walk-forward 特征
    3. train_models.py    7 个 RF 分类器
    4. predict.py         赛程概率 + cache/predictions.json
    5. pm_odds.py         Polymarket 角球盘口（实时 bid/ask）      [非致命]
    6. pm_edge.py         模型 vs 市场 edge + Kelly 仓位建议        [非致命]
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def current_season_start() -> int:
    dt = datetime.now()
    return dt.year if dt.month >= 8 else dt.year - 1


def run(cmd: list[str], description: str, soft: bool = False) -> bool:
    print(f"\n{'=' * 60}")
    print(f"  Step: {description}")
    print(f"{'=' * 60}")
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    if result.returncode != 0:
        if soft:
            print(f"\n[SKIPPED] {description} (exit code {result.returncode}) — "
                  f"非致命，继续执行")
            return False
        print(f"\n[FAILED] {description} (exit code {result.returncode})")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="EPL Corner Probability Pipeline")
    parser.add_argument("--start", type=int, default=2021, help="Start season (e.g. 2021 = 2021-22)")
    parser.add_argument("--n-recent", type=int, default=5, help="Rolling window size")
    parser.add_argument("--cache-dir", type=str, default="cache/",
                        help="Cache/output directory")
    parser.add_argument("--n-estimators", type=int, default=500, help="RF trees")
    parser.add_argument("--max-depth", type=int, default=7, help="RF max depth")
    parser.add_argument("--min-samples-leaf", type=int, default=8, help="RF min leaf samples")
    parser.add_argument("--no-cache-data", action="store_true", help="Force re-fetch all data")
    parser.add_argument("--models-dir", type=str, default=None,
                        help="Model subdirectory (default: cache_dir/models/)")
    parser.add_argument("--format", type=str, default="tsv", choices=["markdown", "tsv"],
                        help="Output format: markdown or tsv (Excel-ready)")
    # --- Polymarket edge module ---
    parser.add_argument("--no-polymarket", action="store_true",
                        help="Skip Polymarket odds fetch + edge report")
    parser.add_argument("--bankroll", type=float, default=1000.0,
                        help="本金 (USDC)，用于 Kelly 建议金额")
    parser.add_argument("--kelly-frac", type=float, default=0.35,
                        help="Kelly 折扣系数（默认 35%%）")
    parser.add_argument("--max-stake-pct", type=float, default=0.05,
                        help="单笔上限占本金比例")
    parser.add_argument("--min-edge", type=float, default=0.03,
                        help="计入可交易的最小 Edge")
    parser.add_argument("--edge-output", type=str, default=None,
                        help="Edge report 输出路径（默认打印到 stdout）")
    parser.add_argument("--no-book", action="store_true",
                        help="Polymarket 只取元数据，不拉 CLOB 订单簿")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    models_dir = Path(args.models_dir) if args.models_dir else cache_dir / "models"

    current_start = current_season_start()
    print(f"EPL Corner Probability Pipeline")
    print(f"  Current season: {current_start}-{str(current_start + 1)[-2:]}")
    print(f"  Historical from: {args.start}-{str(args.start + 1)[-2:]}")
    print(f"  Rolling window:  {args.n_recent}")
    print(f"  Cache dir:       {cache_dir.resolve()}")
    if args.no_polymarket:
        print(f"  Polymarket:      disabled")
    else:
        print(f"  Polymarket:      enabled  (bankroll {args.bankroll:,.0f} USDC, "
              f"{args.kelly_frac:.0%} Kelly, min edge {args.min_edge:.1%})")
    print()

    merged_path = cache_dir / "epl_merged.csv"
    features_path = cache_dir / "features.csv"

    # Step 1: Fetch data
    fetch_cmd = [
        sys.executable, str(SCRIPT_DIR / "fetch_data.py"),
        "--start", str(args.start),
        "--output", str(cache_dir),
    ]
    if args.no_cache_data:
        fetch_cmd.append("--no-cache")
    if not run(fetch_cmd, "Fetch EPL data"):
        sys.exit(1)

    # Step 2: Build features
    build_cmd = [
        sys.executable, str(SCRIPT_DIR / "build_features.py"),
        "--input", str(merged_path),
        "--output", str(features_path),
        "--n-recent", str(args.n_recent),
    ]
    if not run(build_cmd, "Build walk-forward features"):
        sys.exit(1)

    # Step 3: Train models
    train_cmd = [
        sys.executable, str(SCRIPT_DIR / "train_models.py"),
        "--features", str(features_path),
        "--output", str(models_dir),
        "--n-estimators", str(args.n_estimators),
        "--max-depth", str(args.max_depth),
        "--min-samples-leaf", str(args.min_samples_leaf),
    ]
    if not run(train_cmd, "Train seven RF models"):
        sys.exit(1)

    # Step 4: Predict
    predictions_path = cache_dir / "predictions.json"
    predict_cmd = [
        sys.executable, str(SCRIPT_DIR / "predict.py"),
        "--models", str(models_dir),
        "--features", str(features_path),
        "--matches", str(merged_path),
        "--n-recent", str(args.n_recent),
        "--format", args.format,
        "--output", "-",
        "--pred-out", str(predictions_path),
    ]
    if not run(predict_cmd, "Predict upcoming fixtures"):
        sys.exit(1)

    # --- Step 5/6: Polymarket edge (optional, non-fatal) ---
    if not args.no_polymarket:
        pm_path = cache_dir / "pm_odds.json"
        odds_ok = False

        if not predictions_path.exists():
            print("\n[SKIP] 本阶段没有 upcoming fixtures（未生成 predictions.json），"
                  "跳过 Polymarket edge 对比。")
        else:
            odds_cmd = [
                sys.executable, str(SCRIPT_DIR / "pm_odds.py"),
                "--fixtures", str(merged_path),
                "--out", str(pm_path),
            ]
            if args.no_book:
                odds_cmd.append("--no-book")
            odds_ok = run(odds_cmd, "Fetch Polymarket total-corner odds", soft=True)
            if not odds_ok:
                print("\n[SKIP] Polymarket 盘口抓取失败（网络或无市场），跳过 edge 对比。")

        if odds_ok:
            edge_cmd = [
                sys.executable, str(SCRIPT_DIR / "pm_edge.py"),
                "--predictions", str(predictions_path),
                "--pm", str(pm_path),
                "--bankroll", str(args.bankroll),
                "--kelly-frac", str(args.kelly_frac),
                "--max-stake-pct", str(args.max_stake_pct),
                "--min-edge", str(args.min_edge),
                "--format", "tsv",
                "--output", args.edge_output or "-",
            ]
            run(edge_cmd, "Polymarket edge report", soft=True)

    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete.")
    print(f"{'=' * 60}")


# Determine script directory for subprocess calls
SCRIPT_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    main()
