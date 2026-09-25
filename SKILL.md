---
name: epl-corner-probability
description: "This skill should be used when the user wants to forecast EPL corner probability distributions for upcoming matchweeks. Triggers: 预测英超角球概率, EPL corners prediction, 英超角球盘口概率, 英超角球 edge. Pulls data from football-data.co.uk, builds walk-forward rolling features, trains seven independent RF classifiers (one per line: 7.5 to 13.5), outputs P(Over) for each fixture, then automatically pulls live Polymarket total-corner prices and reports model-vs-market edge with Kelly sizing. EPL only."
---

# EPL Corner Probability Forecasting

## Purpose

Forecast corner probability distributions for every upcoming EPL matchweek.
Seven independent RandomForest classifiers, one per corner line (7.5 to 13.5 in 1.0 steps),
trained on walk-forward features built from football-data.co.uk historical data.

Two output layers:

1. **Probability layer (always)** — a structured probability table. No commentary.
2. **Edge layer (automatic, optional)** — live Polymarket total-corner prices pulled from the
   Gamma + CLOB APIs, compared line-by-line against the model, with edge, EV% and
   Kelly-sized stake in both USDC and shares. Skipped automatically when Polymarket has no
   open corner market for the fixture (see "Polymarket Edge Module").

## Trigger Rules

Invoke this skill when the user makes any of these requests:
- "预测本周英超角球概率"
- "EPL corners 概率分布"
- "给我这轮英超角球盘口概率"
- "更新模型并跑下周赛程"
- "英超角球预测"
- "英超角球 edge / 角球盘口有没有价值"
- Any query combining EPL + corner + probability/forecast/edge

If the user requests other leagues (Serie A, La Liga, etc.), live in-play betting,
goals, cards, or any non-corner market, respond: "本 skill 仅支持英超角球赛前概率预测，
其他联赛 / 盘口 / 滚球场景不适用。"

Note: the edge layer compares against Polymarket only. If the user asks about bookmaker
(e.g. Bet365 / Pinnacle) prices, state that only Polymarket is wired in and offer to
compare manually against numbers the user supplies.

---

## Core Architecture

### Seven Independent Classifiers

| Model | Target (binary) |
|-------|----------------|
| `model_7_5`  | `TotalCorners > 7.5`  |
| `model_8_5`  | `TotalCorners > 8.5`  |
| `model_9_5`  | `TotalCorners > 9.5`  |
| `model_10_5` | `TotalCorners > 10.5` |
| `model_11_5` | `TotalCorners > 11.5` |
| `model_12_5` | `TotalCorners > 12.5` |
| `model_13_5` | `TotalCorners > 13.5` |

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

After obtaining seven independent probabilities per fixture, enforce:
```
P(>7.5) >= P(>8.5) >= P(>9.5) >= P(>10.5) >= P(>11.5) >= P(>12.5) >= P(>13.5)
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

### Step 4: Train Seven Models

Run `scripts/train_models.py`:
```bash
python scripts/train_models.py --features cache/features.csv --output cache/models/
```

Trains all seven RF classifiers, saves each as `model_{line}.pkl` plus `scaler.pkl` and `imputer.pkl`.

### Step 5: Predict Upcoming Fixtures

Run `scripts/predict.py`:
```bash
python scripts/predict.py --models cache/models/ --features cache/features.csv \
    --matches cache/epl_merged.csv --pred-out cache/predictions.json --output -
```

Builds features for the next matchweek fixtures (from the current season CSV where `HC` is NaN),
applies the seven models, enforces monotonicity, prints the probability table, and writes
`cache/predictions.json` for the edge layer.

If `upcoming fixtures: 0` is reported, the season CSV has no unplayed rows — stop and tell the
user the fixtures are missing. Do not fabricate a fixture list.

### Step 6: Fetch Polymarket Corner Odds

Run `scripts/pm_odds.py`:
```bash
python scripts/pm_odds.py --fixtures cache/epl_merged.csv --out cache/pm_odds.json
```

For every upcoming fixture, finds the matching Polymarket event
(`epl-{home3}-{away3}-{YYYY-MM-DD}-total-corners`) and pulls the executable price for both
sides of all seven full-time total-corner lines straight from the CLOB order book.
Skip with `--no-book` to fetch metadata only (faster, no live prices).

### Step 7: Edge Report

Run `scripts/pm_edge.py`:
```bash
python scripts/pm_edge.py --predictions cache/predictions.json --pm cache/pm_odds.json \
    --bankroll 1000 --kelly-frac 0.35 --min-edge 0.03
```

Produces the TSV edge table + ranked actionable summary (see "Polymarket Edge Module" below).
Steps 6–7 are non-fatal: if Polymarket has no open market or the network is down, report
"无盘口" / skip the section and still deliver the probability table.

### Step 8: Output

Present results in three sections (see Output Format below):
1. Probability table (always)
2. Polymarket edge table + actionable list (when odds were fetched)
3. Caveats

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

#	日期	主队	客队	P(>7.5)	P(>8.5)	P(>9.5)	P(>10.5)	P(>11.5)	P(>12.5)	P(>13.5)	关键驱动因素	修正
1	2026-07-12	Arsenal	Liverpool	68.0%	52.0%	38.0%	24.0%	14.0%	6.0%	3.0%	主队高近N场角球 (7.2); 两队高射门量 (29.3)	
2	2026-07-13	Chelsea	Man City	71.0%	65.0%	59.0%	42.0%	28.0%	15.0%	9.0%	两队高射门量 (31.5); 客队高客场角球失球 (6.8)	是
```

- Each row is one fixture, columns separated by Tab
- Probabilities displayed as percentages (e.g. `68.0%`)
- `修正` column: `是` = monotonicity was enforced for this fixture
- Lines starting with `#` are meta-info comments

### Format: `markdown` (legacy)

Use `--format markdown` for the original Markdown table output:

```
| Date | Home | Away | P(>7.5) | P(>8.5) | P(>9.5) | P(>10.5) | P(>11.5) | P(>12.5) | P(>13.5) | Key Drivers |
|------|------|------|---------|---------|---------|----------|----------|----------|----------|-------------|
| Jul 12 | Arsenal | Liverpool | 0.68 | 0.52 | 0.38 | 0.24 | 0.14 | 0.06 | 0.03 | TeamA high CF5 + TeamB high away corners conceded |
| *Jul 13 | Chelsea | Man City | 0.71 | 0.65 | 0.59 | 0.42 | 0.28 | 0.15 | 0.09 | Both teams high recent shot volume |
```

### Format: edge report (Polymarket, TSV)

Emitted by `pm_edge.py` after the probability table. Same TSV convention — `#` lines are
meta/comments, one fixture-line per row, with a ranked block underneath.

```
# Polymarket Edge Report — 盘口抓取于 2026-09-25T01:05:10
# 本金 1,000 USDC · 35% Kelly · 单笔上限 5.0% · Edge 阈值 3.0% · 方向 both
# Edge = 模型概率 − 可成交价(ask)；EV% = Edge / ask；仅供参考

日期	主队	客队	线	方向	模型P	ask	bid	mid	Edge	EV%	建议金额	份数	深度(份)	备注
27/09/2026	Arsenal	Chelsea	9.5	Over	44.0%	0.360	0.350	0.355	+8.0%	+22.2%	44	122	800
27/09/2026	Arsenal	Chelsea	10.5	Over	30.0%	0.135	0.125	0.130	+16.5%	+122.2%	50	370	800

# ——— 可交易 Edge（≥3.0%，共 2 条）———
# Arsenal vs Chelsea | >10.5 Over @ 0.135 | 模型 30.0% | Edge +16.5% | 建议 $50 / 370 份
# Arsenal vs Chelsea | >9.5 Over @ 0.360 | 模型 44.0% | Edge +8.0% | 建议 $44 / 122 份

# ——— 市场自洽性检查（P(>7.5) ≥ … ≥ P(>13.5)）———
# 未发现市场报价违反单调性。
```

- `建议金额` / `份数` are blank (`—`) unless the row is actionable
- `深度(份)` is the size resting at the best ask — the practical fill ceiling
- When nothing clears the threshold: `# 无。模型与市场无显著分歧，或盘口未开 / 无深度。`

### Usage

```bash
# Full pipeline incl. Polymarket edge (default)
python scripts/run_pipeline.py

# Model only, no market lookup
python scripts/run_pipeline.py --no-polymarket

# Sizing / threshold overrides
python scripts/run_pipeline.py --bankroll 2000 --kelly-frac 0.25 --min-edge 0.05

# Standalone edge refresh against cached models + predictions
python scripts/pm_odds.py --fixtures cache/epl_merged.csv --out cache/pm_odds.json
python scripts/pm_edge.py --predictions cache/predictions.json --pm cache/pm_odds.json

# List every EPL corner event Polymarket currently exposes
python scripts/pm_odds.py --list
```

Pipeline argument reference: `--no-polymarket`, `--bankroll`, `--kelly-frac`,
`--max-stake-pct`, `--min-edge`, `--edge-output`, `--no-book`.

### Cold Start Warning

If current season < 5 matches completed:
```
⚠ 冷启动警告：当前赛季已完成场次 < 5 场，rolling features 依赖上赛季末数据，预测稳定性降低。
```

---

## Polymarket Edge Module

### What Polymarket offers

Polymarket auto-generates one event per EPL match, slug pattern
`epl-{home3}-{away3}-{YYYY-MM-DD}-total-corners`, containing 23 binary markets:

| Group | Lines |
|-------|-------|
| `Total Corners: O/U` | 7.5 / 8.5 / 9.5 / 10.5 / 11.5 / 12.5 / 13.5 |
| `1st Half Total Corners: O/U` | 3.5 / 4.5 / 5.5 |
| `2nd Half Total Corners: O/U` | 3.5 / 4.5 / 5.5 |
| `{Home} Corners: O/U` | 2.5 / 3.5 / 4.5 / 5.5 |
| `{Away} Corners: O/U` | 2.5 / 3.5 / 4.5 / 5.5 |
| `Total Corners: Odd or Even` | — |
| `Team to Take First Corner` | — |

The first group is the only one the seven models cover — that is what the edge layer scores.
The halves / per-team lines are **not** modelled; do not compute edge on them.

### Endpoints (both keyless)

| Purpose | Endpoint |
|---------|----------|
| Event + market metadata | `https://gamma-api.polymarket.com/events?slug=<slug>` |
| Series scan (EPL = id `10188`) | `.../events?series_id=10188&closed=false` |
| Tag scan | `.../events?tag_slug=epl&closed=false` |
| Live order book | `https://clob.polymarket.com/book?token_id=<clobTokenIds[i]>` |
| Mid price | `https://clob.polymarket.com/midpoint?token_id=<...>` |

`clobTokenIds[0]` = Over token, `clobTokenIds[1]` = Under token.

### Edge and sizing definitions

```
ask      = 最低卖价 (best ask)  →  taker 实际可成交价
mid      = (best_bid + best_ask) / 2
edge     = P_model − ask             (买 Over 用 P(>L)；买 Under 用 1 − P(>L))
EV%      = edge / ask
f*       = (p − ask) / (1 − ask)      全 Kelly
stake    = bankroll × kelly_frac × f*  →  上限 bankroll × max_stake_pct
shares   = stake / ask
```

Defaults: `bankroll = 1000` USDC, `kelly_frac = 0.35`, `max_stake_pct = 0.05`, `min_edge = 0.03`.
These mirror `hk-weather-edge` so position sizing is stated identically across projects.

A row is **actionable** only when all hold: `edge >= min_edge`, `acceptingOrders == true`,
`closed == false`, and the best-ask level has non-zero size.

### ⚠ Sizing gate — read before quoting any stake

A walk-forward audit on 2026-09-25 (1,889 matches, 2021-08 → 2026-08; 1,039 out-of-sample)
measured **no out-of-sample predictive power** in the current model and feature set:

| Metric | Measured | Required to bet |
|---|---|---|
| AUC (7 lines) | 0.465 – 0.528 (6 of 7 within ±2σ of 0.50) | ≥ 0.55 |
| Brier skill vs climatology | −0.022 … −0.002 (all negative) | > 0 |
| Calibration slope on logit | −0.12 … +0.11 (theory = 1) | 0.7 – 1.3 |
| Reliability monotone by decile | fails (10.5 line runs inverse) | monotone |
| Edge capture rate (realized / claimed) | −0.88 … +0.51, median negative | ≥ 0.5 |

At the 0.35 Kelly default this prices to **−0.45% … +0.30% log growth per bet** before
spread. Root cause is upstream: the 19 team-form features correlate with total corners at
only +0.02 … +0.07. Full audit: `references/kelly_audit_2026-09-25.md`.

**Therefore:**

1. **Do not quote a non-zero stake for this model until the gate above is passed.** Report
   the probabilities and the edge table, then state plainly that the model has no measured
   out-of-sample edge and that no position is recommended. Never present a Kelly figure
   without this caveat.
2. If the gate is passed, use `--kelly-frac 0.25` and `--min-edge 0.05`, not the 0.35 / 0.03
   defaults. Derivation: `λ* = σ²/(σ²+s²)` with measured `s ≈ 3.5–5.0pp`.
3. **Always compute a per-match aggregate exposure** and cap it at 6% of bankroll. The 7
   full-time lines are nested (`>7.5 ⊃ >8.5 ⊃ … ⊃ >13.5`, pairwise outcome correlation
   0.39–0.80), so they are one payoff ladder on one event, not 7 independent bets. At the
   current defaults they sum to **27.6% of bankroll on a single match** (P&L sd 22.9%,
   P(loss) 52%).
4. Prefer the zero-forecast path where available: the `market_monotonicity()` check flags
   cross-line arbitrage that requires no predictive skill. If `P(>8.5) < P(>9.5)` is quoted,
   buying `Under 9.5` + `Over 8.5` costs < 1 and pays ≥ 1 in every state.

### Reporting rules

- Always give **both the USDC amount and the share count** — e.g. `$44 / 122 份`. Never one alone.
- If `ask` size < required shares, flag `深度不足，仅可成交 N 份` and cap the reported stake.
- When Polymarket has no event for a fixture, print `无盘口` — never guess or substitute a
  bookmaker price.
- Note the **asymmetry by design**: Polymarket corner books are thin ($1k–$150k lifetime volume
  per match). Headline fixtures (top-6 vs top-6) can absorb a few hundred shares; lower-profile
  fixtures often quote only 7.5–11.5 and carry no size at all.
- The market-monotonicity check (P(>7.5) ≥ … ≥ P(>13.5)) is a **data-quality signal**, not a
  trade. Report it as-is; it usually means stale quotes on illiquid tail lines.

### Known pitfalls

- **Gamma `closed` defaults to `true`.** Omitting the parameter silently returns only closed
  events — always pass `closed=false` explicitly when hunting live markets. `pm_odds.py`
  requests both values and filters locally.
- **Stale open events.** Events whose match has already been played can linger at
  `closed=false` while every sub-market inside is closed. Check the per-market
  `acceptingOrders` flag, not the event-level flag.
- **Cadence gap.** Corner events are generated roughly 5–13 days before kickoff. Between
  matchweeks there may be no open EPL corner market at all — this is normal, not a bug.
- **Series pagination.** `series_id=10188` with `limit=100` only returns the newest 100 events
  of the series, most of which are player props. The tag scan is the reliable path for corners.

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
| `bankroll` | 1000 | 本金 (USDC)，Kelly 建议金额的基数 |
| `kelly_frac` | 0.35 | Kelly 折扣系数。**过门禁前不可引用 — 见 ⚠ Sizing gate；过门禁后用 0.25** |
| `max_stake_pct` | 0.05 | 单笔上限占本金比例 |
| `min_edge` | 0.03 | 计入可交易的最小 Edge。**过门禁后用 0.05** |
| `max_match_pct` | 6% (待实现) | 同场次全部线合计上限。7 条线是一个事件，必须聚合限仓 |
| `polymarket` | on | `--no-polymarket` 可关闭盘口对比 |

---

## Prohibitions

- Do NOT fabricate upcoming fixtures — use only what exists in current season CSV
- Do NOT mix data from other leagues
- Do NOT leak post-match data into pre-match features
- Do NOT hardcode season lists — always compute dynamically from current date
- Do NOT use language like "稳胆", "必出大角", "铁定", or any certainty-implying phrasing
- Do NOT write football commentary or narrative summaries

Applies to the Polymarket edge layer specifically:

- Do NOT fabricate a market price. If `pm_odds.json` has no quote for a fixture, the row is `无盘口`
- Do NOT substitute bookmaker or model-implied "fair odds" for a missing market price
- Do NOT compute edge on the half-time or per-team corner lines — only the seven full-time lines
  are modelled and only those may be scored
- Do NOT state a position without **both** the USDC amount and the share count
- Do NOT present edge as a win expectation — it is a model-vs-price divergence, and the market
  may simply be right
- Do NOT size off the full Kelly value; the reported stake is always `kelly_frac × f*`, capped
  by `max_stake_pct`

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/fetch_data.py` | Fetch and merge EPL CSV data from football-data.co.uk |
| `scripts/build_features.py` | Build walk-forward features with no data leakage |
| `scripts/train_models.py` | Train seven independent RF classifiers per corner line |
| `scripts/predict.py` | Predict probabilities for upcoming fixtures with monotonicity fix |
| `scripts/pm_odds.py` | Fetch live Polymarket total-corner odds (Gamma + CLOB) |
| `scripts/pm_edge.py` | Model-vs-market edge, EV%, Kelly stake in USDC + shares |
| `scripts/run_pipeline.py` | Orchestrate all steps end-to-end |

Run the full pipeline:
```bash
python scripts/run_pipeline.py --cache-dir cache/ [--n-recent 5] [--start-season 2021] \
    [--rf-params ...] [--bankroll 1000] [--min-edge 0.03] [--no-polymarket]
```

Intermediates written to `cache/`:
- `epl_merged.csv` — raw merged match data
- `features.csv` — walk-forward feature matrix
- `predictions.json` — model probabilities per fixture (input to `pm_edge.py`)
- `pm_odds.json` — Polymarket live quotes per fixture (input to `pm_edge.py`)

---

## One-Liner Mission

Turn "weekly EPL corner pre-match prediction" into a stable, reproducible seven-line
independent probability output pipeline, automatically cross-checked against live Polymarket
prices so the user sees where the model and the market disagree.
