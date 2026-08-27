#!/usr/bin/env python3
"""train_models.py — Train one independent RF classifier per corner line (7.5 to 13.5).

Usage:
    python train_models.py --features cache/features.csv --output cache/models/
"""

import argparse
import json
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

FEATURE_COLS = [
    "H_CornersFor_N", "H_CornersAgainst_N", "H_CornersFor_S",
    "H_Shots_N", "H_ShotsOnTarget_N", "H_Goals_N", "H_Fouls_N",
    "H_PPG_N", "H_HomeCornersFor_N",
    "A_CornersFor_N", "A_CornersAgainst_N", "A_CornersFor_S",
    "A_Shots_N", "A_ShotsOnTarget_N", "A_Goals_N", "A_Fouls_N",
    "A_PPG_N", "A_AwayCornersFor_N",
    "TotalShots_N",
]

LINES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5]


def target_col(line: float) -> str:
    return f"Target_{str(line).replace('.', '_')}"


def load_training_data(features_path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Load features CSV, return (X, targets_dict)."""
    import csv
    rows = []
    with open(features_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    X_rows = []
    y_dict = {f"Target_{str(line).replace('.', '_')}": [] for line in LINES}

    for row in rows:
        # Only use rows that have all targets (completed matches)
        target_vals = [row.get(target_col(line), "") for line in LINES]
        if "" in target_vals or None in target_vals:
            continue

        features = []
        valid = True
        for col in FEATURE_COLS:
            val = row.get(col, "")
            if val == "" or val is None:
                features.append(np.nan)
            else:
                try:
                    features.append(float(val))
                except (ValueError, TypeError):
                    features.append(np.nan)
        X_rows.append(features)

        for line in LINES:
            try:
                y_dict[target_col(line)].append(int(row[target_col(line)]))
            except (ValueError, KeyError):
                y_dict[target_col(line)].append(0)

    X = np.array(X_rows, dtype=np.float64)
    for k in y_dict:
        y_dict[k] = np.array(y_dict[k], dtype=np.int32)

    return X, y_dict


def train_models(X: np.ndarray, y_dict: dict[str, np.ndarray],
                 n_estimators: int, max_depth: int, min_samples_leaf: int,
                 random_state: int) -> dict:
    """Train six independent RF classifiers with shared preprocessing."""
    imputer = SimpleImputer(strategy="mean")
    X_imputed = imputer.fit_transform(X)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_imputed)

    models = {}
    for line in LINES:
        tc = target_col(line)
        y = y_dict[tc]
        pos_ratio = y.mean()
        print(f"  Training model for Over {line}... (pos ratio: {pos_ratio:.3f})")

        model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            n_jobs=-1,
            class_weight=None,  # Let user override if needed
        )
        model.fit(X_scaled, y)

        train_score = model.score(X_scaled, y)
        print(f"    In-sample accuracy: {train_score:.4f}")

        models[line] = model

    return models, imputer, scaler


def save_models(models: dict, imputer, scaler, output_dir: Path):
    """Save all models + preprocessors to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for line, model in models.items():
        line_str = str(line).replace(".", "_")
        with open(output_dir / f"model_{line_str}.pkl", "wb") as f:
            pickle.dump(model, f)

    with open(output_dir / "imputer.pkl", "wb") as f:
        pickle.dump(imputer, f)

    with open(output_dir / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    # Save feature column order
    with open(output_dir / "feature_cols.json", "w", encoding="utf-8") as f:
        json.dump(FEATURE_COLS, f)

    # Save metadata
    meta = {
        "trained_at": datetime.now().isoformat(),
        "n_estimators": models[list(models.keys())[0]].n_estimators if models else 0,
        "features": FEATURE_COLS,
        "lines": LINES,
    }
    with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Train RF corner classifiers (one per line)")
    parser.add_argument("--features", type=str, required=True, help="Path to features CSV")
    parser.add_argument("--output", type=str, required=True, help="Output model directory")
    parser.add_argument("--n-estimators", type=int, default=500, help="RF trees")
    parser.add_argument("--max-depth", type=int, default=7, help="RF max depth")
    parser.add_argument("--min-samples-leaf", type=int, default=8, help="RF min samples leaf")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    features_path = Path(args.features)
    if not features_path.exists():
        print(f"ERROR: {features_path} not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading features from {features_path}...")
    X, y_dict = load_training_data(features_path)
    print(f"  Training samples: {X.shape[0]}, Features: {X.shape[1]}")
    print(f"  Features: {', '.join(FEATURE_COLS)}")
    print()

    print("Training models...")
    models, imputer, scaler = train_models(
        X, y_dict,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_leaf=args.min_samples_leaf,
        random_state=args.random_state,
    )

    output_dir = Path(args.output)
    save_models(models, imputer, scaler, output_dir)
    print(f"\nModels saved to {output_dir.resolve()}")
    print(f"  Files: " + ", ".join(f"model_{str(l).replace('.', '_')}.pkl" for l in LINES))
    print(f"         imputer.pkl, scaler.pkl, feature_cols.json, meta.json")


if __name__ == "__main__":
    main()
