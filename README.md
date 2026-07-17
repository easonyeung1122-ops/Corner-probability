# EPL Corner Probability Forecasting

Predict corner probability distributions for every upcoming EPL matchweek using walk-forward Random Forest classifiers.

## Overview

Six independent RandomForest classifiers, one per corner line (7.5 to 12.5 in 1.0 steps), trained on walk-forward features built from [football-data.co.uk](https://www.football-data.co.uk) historical data.

| Model | Target |
|-------|--------|
| `model_7_5`  | TotalCorners > 7.5  |
| `model_8_5`  | TotalCorners > 8.5  |
| `model_9_5`  | TotalCorners > 9.5  |
| `model_10_5` | TotalCorners > 10.5 |
| `model_11_5` | TotalCorners > 11.5 |
| `model_12_5` | TotalCorners > 12.5 |

## Quick Start

```bash
# Install dependencies
pip install pandas numpy scikit-learn requests

# Run full pipeline
python scripts/run_pipeline.py
```

## Pipeline Steps

1. **Fetch Data** — Pull EPL CSV data from football-data.co.uk
2. **Build Features** — Walk-forward rolling features (no data leakage)
3. **Train Models** — Six independent RF classifiers
4. **Predict** — Forecast upcoming fixtures with monotonicity enforcement

## Data Source

[football-data.co.uk](https://www.football-data.co.uk) — EPL historical match data.

## Disclaimer

This tool outputs probability distributions only. It does not provide betting advice or wagering recommendations.
