---
name: epl-corner-probability
description: "This skill should be used when the user wants to forecast EPL corner probability distributions for upcoming matchweeks. Triggers: 预测英超角球概率, EPL corners prediction, 英超角球盘口概率. Pulls data from football-data.co.uk, builds walk-forward rolling features, trains six independent RF classifiers (one per line: 7.5 to 12.5), outputs P(Over) for each fixture. EPL only."
---

# EPL Corner Probability Forecasting

## Purpose

Forecast corner probability distributions for every upcoming EPL matchweek.
Six independent RandomForest classifiers, one per corner line (7.5 to 12.5 in 1.0 steps),
trained on walk-forward features built from football-data.co.uk historical data.
Output is a structured probability table — no betting advice, no commentary.

## Trigger Rules

Invoke this skill when the user makes any of these requests:
- "预测本周英超角球概率"
- "EPL corners 概率分布"
- "给我这轮英超角球盘口概率"
- "更新模型并跑下周赛程"
- "英超角球预测"
- Any query combining EPL + corner + probability/forecast

If the user requests other leagues (Serie A, La Liga, etc.), live in-play betting,
goals, cards, or any non-corner market, respond: "本 skill 仅支持英超角球赛前概率预测，
其他联赛 / 盘口 / 滚球场景不适用。"

---

## Core Architecture

### Six Independent Classifiers

| Model | Target (binary) |
|-------|----------------|
| `model_7_5`  | `TotalCorners > 7.5`  |
| `model_8_5`  | `TotalCorners > 8.5`  |
| `model_9_5`  | `TotalCorners > 9.5`  |
| `model_10_5` | `TotalCorners > 10.5` |
| `model_11_5` | `TotalCorners > 11.5` |
| `model_12_5` | `TotalCorners > 12.5` |

Each model uses the same 19-feature set, same preprocessing pipeline, but is fit independently.

### Default Hyperparameters

- `n_estimators = 500`
- `max_depth = 7`
- `min_samples_leaf = 8`
- `random_state = 42`

### Preprocessing Pipeline

1. `SimpleImputer(strategy='mean')` — handle missing values
2. `StandardScaler()` — standardize features

### Monotonicity Enforcement (Post-Processing)

After obtaining six independent probabilities per fixture, enforce:
```
P(>7.5) >= P(>8.5) >= P(>9.5) >= P(>10.5) >= P(>11.5) >= P(>12.5)
```
If violated, apply `np.minimum.accumulate` from the top down. Mark fixtures
where monotonicity was enforced with `*` in the output table.

---

## Execution Workflow

### Step 1: Detect Current Season

Compute current season based on today's date:
- If month >= 8: current season = `(current_year)-(current_year+1)`
- If month < 8: current season = `(current_year-1)-current_year`

Example: July 2026 → season 2025-26; August 2026 → season 2026-27.

### Step 2: Fetch Historical Data

Run `scripts/fetch_data.py`:
```bash
python scripts/fetch_data.py --start 2021 --output cache/
```

The script:
1. Generates season codes from `start_season` (default 2020-21) to current season
2. For each: `https://www.football-data.co.uk/mmz4281/{YY(YY+1)}/E0.csv`
3. Historical seasons → read from cache if available
4. Current season → always re-fetch (includes latest completed matches)
5. Excludes future fixtures (rows where `Date` is in the future or `HC` is missing)
6. Saves merged CSV to `cache/epl_merged.csv`

### Step 3: Build Walk-Forward Features

Run `scripts/build_features.py`:
```bash
python scripts/build_features.py --input cache/epl_merged.csv --output cache/features.csv --n-recent 5
```

Critical: Walk-forward logic prevents data leakage. For each match row:
1. Compute rolling stats from matches played strictly before this match
2. After computing features for this row, update rolling stats with this match's outcome
3. Never include a match's own HC/AC/result in its own feature row

### Step 4: Train Six Models

Run `scripts/train_models.py`:
```bash
python scripts/train_models.py --features cache/features.csv --output cache/models/
```

Trains all six RF classifiers, saves each as `model_{line}.pkl` plus `scaler.pkl` and `imputer.pkl`.

### Step 5: Predict Upcoming Fixtures

Run `scripts/predict.py`:
```bash
python scripts/predict.py --models cache/models/ --features cache/features.csv --output -
```

Builds features for the next matchweek fixtures (from the current season CSV where `HC` is NaN),
applies the six models, enforces monotonicity, and prints the probability table.

### Step 6: Output

Present results in two sections (see Output Format below).

---

## Feature Specification (19 Features)

### Home Team Features (9)
| Feature | Description |
|---------|-------------|
| `H_CornersFor_N` | Home team avg corners won, last N matches |
| `H_CornersAgainst_N` | Home team avg corners conceded, last N matches |
| `H_CornersFor_S` | Home team avg corners won, season to date |
| `H_Shots_N` | Home team avg shots, last N matches |
| `H_ShotsOnTarget_N` | Home team avg shots on target, last N matches |
| `H_Goals_N` | Home team avg goals, last N matches |
| `H_Fouls_N` | Home team avg fouls, last N matches |
| `H_PPG_N` | Home team avg points per game, last N matches |
| `H_HomeCornersFor_N` | Home team avg corners won at home, last N home matches |

### Away Team Features (9)
| Feature | Description |
|---------|-------------|
| `A_CornersFor_N` | Away team avg corners won, last N matches |
| `A_CornersAgainst_N` | Away team avg corners conceded, last N matches |
| `A_CornersFor_S` | Away team avg corners won, season to date |
| `A_Shots_N` | Away team avg shots, last N matches |
| `A_ShotsOnTarget_N` | Away team avg shots on target, last N matches |
| `A_Goals_N` | Away team avg goals, last N matches |
| `A_Fouls_N` | Away team avg fouls, last N matches |
| `A_PPG_N` | Away team avg points per game, last N matches |
| `A_AwayCornersFor_N` | Away team avg corners won away, last N away matches |

### Combined Feature (1)
| Feature | Description |
|---------|-------------|
| `TotalShots_N` | `H_Shots_N + A_Shots_N` |

### Missing Value Handling

Use training set mean via `SimpleImputer`. If rolling window is insufficient
(early-season matches with < N prior games), flag prediction confidence as lower.

---

## Output Format

Default output is **TSV (Tab-Separated Values)** — ready for copy-paste into Excel.

### Format: `tsv` (default, Excel-ready)

Output is a tab-separated table. Copy the entire output and paste directly into Excel —
columns will auto-separate into cells.

```
# EPL Corner Probability Forecast — 训练于 2026-07-07T12:00:00 — 380 场历史
# 注：* 标记表示该场概率经单调性修正 | 数据来源: football-data.co.uk | 仅供参考

#	日期	主队	客队	P(>7.5)	P(>8.5)	P(>9.5)	P(>10.5)	P(>11.5)	P(>12.5)	关键驱动因素	修正
1	2026-07-12	Arsenal	Liverpool	68.0%	52.0%	38.0%	24.0%	14.0%	6.0%	主队高近N场角球 (7.2); 两队高射门量 (29.3)	
2	2026-07-13	Chelsea	Man City	71.0%	65.0%	59.0%	42.0%	28.0%	15.0%	两队高射门量 (31.5); 客队高客场角球失球 (6.8)	是
```

- Each row is one fixture, columns separated by Tab
- Probabilities displayed as percentages (e.g. `68.0%`)
- `修正` column: `是` = monotonicity was enforced for this fixture
- Lines starting with `#` are meta-info comments

### Format: `markdown` (legacy)

Use `--format markdown` for the original Markdown table output:

```
| Date | Home | Away | P(>7.5) | P(>8.5) | P(>9.5) | P(>10.5) | P(>11.5) | P(>12.5) | Key Drivers |
|------|------|------|---------|---------|---------|----------|----------|----------|-------------|
| Jul 12 | Arsenal | Liverpool | 0.68 | 0.52 | 0.38 | 0.24 | 0.14 | 0.06 | TeamA high CF5 + TeamB high away corners conceded |
| *Jul 13 | Chelsea | Man City | 0.71 | 0.65 | 0.59 | 0.42 | 0.28 | 0.15 | Both teams high recent shot volume |
```

### Usage

```bash
# Default: TSV (Excel-ready)
python scripts/run_pipeline.py

# Or explicitly
python scripts/run_pipeline.py --format tsv

# Legacy Markdown
python scripts/run_pipeline.py --format markdown
```

### Cold Start Warning

If current season < 5 matches completed:
```
⚠ 冷启动警告：当前赛季已完成场次 < 5 场，rolling features 依赖上赛季末数据，预测稳定性降低。
```

---

## Data Source

`https://www.football-data.co.uk/mmz4281/{season_code}/E0.csv`

Season code: season `YYYY-(YY+1)` → code `YY(YY+1)`.
Example: 2025-26 → `2526`, 2026-27 → `2627`.

Key columns used (see `references/data_columns.md` for full mapping):
- `Date`, `HomeTeam`, `AwayTeam`, `HC` (home corners), `AC` (away corners)
- `HS` (home shots), `AS` (away shots)
- `HST` (home shots on target), `AST` (away shots on target)
- `FTHG`, `FTAG` (goals), `HF`, `AF` (fouls)
- `FTR` (result: H/D/A)

---

## User-Configurable Parameters

Allow user to override (otherwise use defaults, do not ask repeatedly):
| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_recent` | 5 | Rolling window size |
| `start_season` | 2020-21 | Earliest historical season |
| `n_estimators` | 500 | RF trees |
| `max_depth` | 7 | RF max depth |
| `min_samples_leaf` | 8 | RF min samples per leaf |

---

## Prohibitions

- Do NOT fabricate upcoming fixtures — use only what exists in current season CSV
- Do NOT mix data from other leagues
- Do NOT leak post-match data into pre-match features
- Do NOT output betting odds, Kelly criterion, or wagering recommendations
- Do NOT hardcode season lists — always compute dynamically from current date
- Do NOT use language like "稳胆", "必出大角", "铁定", or any certainty-implying phrasing
- Do NOT write football commentary or narrative summaries

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/fetch_data.py` | Fetch and merge EPL CSV data from football-data.co.uk |
| `scripts/build_features.py` | Build walk-forward features with no data leakage |
| `scripts/train_models.py` | Train six independent RF classifiers per corner line |
| `scripts/predict.py` | Predict probabilities for upcoming fixtures with monotonicity fix |
| `scripts/run_pipeline.py` | Orchestrate all steps end-to-end |

Run the full pipeline:
```bash
python scripts/run_pipeline.py --cache-dir cache/ [--n-recent 5] [--start-season 2021] [--rf-params ...]
```

---

## One-Liner Mission

Turn "weekly EPL corner pre-match prediction" into a stable, reproducible six-line
independent probability output pipeline. Output probabilities only, no advice.
