#!/usr/bin/env python3
"""run_pipeline.py — End-to-end pipeline: fetch → features → train → predict.

Usage:
    python run_pipeline.py [--start 2021] [--n-recent 5] [--cache-dir cache/]
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def current_season_start() -> int:
    dt = datetime.now()
    return dt.year if dt.month >= 8 else dt.year - 1


def run(cmd: list[str], description: str) -> bool:
    print(f"\n{'=' * 60}")
    print(f"  Step: {description}")
    print(f"{'=' * 60}")
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    if result.returncode != 0:
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
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    models_dir = Path(args.models_dir) if args.models_dir else cache_dir / "models"

    current_start = current_season_start()
    print(f"EPL Corner Probability Pipeline")
    print(f"  Current season: {current_start}-{str(current_start + 1)[-2:]}")
    print(f"  Historical from: {args.start}-{str(args.start + 1)[-2:]}")
    print(f"  Rolling window:  {args.n_recent}")
    print(f"  Cache dir:       {cache_dir.resolve()}")
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
    if not run(train_cmd, "Train six RF models"):
        sys.exit(1)

    # Step 4: Predict
    predict_cmd = [
        sys.executable, str(SCRIPT_DIR / "predict.py"),
        "--models", str(models_dir),
        "--features", str(features_path),
        "--matches", str(merged_path),
        "--n-recent", str(args.n_recent),
        "--format", args.format,
        "--output", "-",
    ]
    if not run(predict_cmd, "Predict upcoming fixtures"):
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete.")
    print(f"{'=' * 60}")


# Determine script directory for subprocess calls
SCRIPT_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    main()
