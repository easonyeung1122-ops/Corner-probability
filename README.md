# EPL Corner Probability Forecasting / 英超角球概率预测

[English](#english) | [中文](#中文)

---

## English

> **Status — audited 2026-09-25: the current model has no measurable out-of-sample edge.**
> Walk-forward over 1,889 matches (2021-08 → 2026-08; 1,039 out-of-sample) measured AUC
> 0.465–0.528 per line, **negative** Brier skill on all seven lines, and a calibration slope of
> ≈ 0. The probabilities do not carry information beyond the base rate. **No non-zero position
> is recommended until the sizing gate is passed** — see [Kelly Audit](#kelly-audit-2026-09-25).
> The Polymarket integration and the probability pipeline are unaffected and fully functional.

### Overview

A machine learning pipeline that forecasts corner probability distributions for every upcoming English Premier League (EPL) matchweek. Seven independent **Random Forest classifiers** — one per corner line from 7.5 to 13.5 — are trained on walk-forward features built from historical match data.

**Data Sources**: [football-data.co.uk](https://www.football-data.co.uk) (historical match stats) + [Polymarket](https://polymarket.com) Gamma / CLOB APIs (live corner prices, keyless).

**Two output layers**:
1. **Probability** — P(Over) for each of the seven lines, per fixture
2. **Edge** — model vs. live Polymarket price, EV%, and Kelly-sized stake (USDC + shares), auto-fetched on every run

### How It Works

| Model | Target (Binary Classification) |
|-------|-------------------------------|
| `model_7_5`  | Total Corners > 7.5  |
| `model_8_5`  | Total Corners > 8.5  |
| `model_9_5`  | Total Corners > 9.5  |
| `model_10_5` | Total Corners > 10.5 |
| `model_11_5` | Total Corners > 11.5 |
| `model_12_5` | Total Corners > 12.5 |
| `model_13_5` | Total Corners > 13.5 |

Each model uses the same **19 features** but is trained independently. After prediction, **monotonicity** is enforced: P(>7.5) ≥ P(>8.5) ≥ ... ≥ P(>13.5). Fixtures where correction was applied are flagged in the output.

### Features (19 total)

**Home Team (9 features)**:
| Feature | Description |
|---------|-------------|
| `H_CornersFor_N` | Avg corners won, last N matches |
| `H_CornersAgainst_N` | Avg corners conceded, last N matches |
| `H_CornersFor_S` | Avg corners won, season to date |
| `H_Shots_N` | Avg shots, last N matches |
| `H_ShotsOnTarget_N` | Avg shots on target, last N matches |
| `H_Goals_N` | Avg goals, last N matches |
| `H_Fouls_N` | Avg fouls, last N matches |
| `H_PPG_N` | Avg points per game, last N matches |
| `H_HomeCornersFor_N` | Avg corners won at home, last N home matches |

**Away Team (9 features)**: Mirror of the above for the away team.

**Combined (1 feature)**: `TotalShots_N` = H_Shots_N + A_Shots_N

### Pipeline Architecture

```
┌─────────────┐    ┌────────────────┐    ┌──────────────┐    ┌────────────┐
│  Fetch Data │ → │ Build Features  │ → │ Train Models │ → │  Predict   │
│ (football-  │    │ (walk-forward,  │    │ (7× RF, 500   │    │ (upcoming  │
│  data.co.uk)│    │  no leakage)    │    │  trees each)  │    │  fixtures) │
└─────────────┘    └────────────────┘    └──────────────┘    └─────┬──────┘
                                                                  │
                          ┌───────────────────────────────────────┘
                          ▼
              ┌────────────────────┐    ┌──────────────────────┐
              │ Polymarket Odds    │ → │  Edge Report         │
              │ (Gamma + CLOB,     │    │ (edge, EV%, Kelly     │
              │  live bid/ask)     │    │  stake in $ + shares) │
              └────────────────────┘    └──────────────────────┘
```

The last two stages are best-effort: if Polymarket has no open corner market for the
matchweek (a normal gap between matchweeks), they are skipped and the probability table is
still delivered.

#### Walk-Forward Feature Engineering

Features are built using **strict walk-forward logic** to prevent data leakage:
1. For each match, compute rolling statistics from matches played **strictly before** this match
2. After computing features, update team history **with** this match's outcomes
3. A match's own HC/AC/result is **never** included in its own feature row

### Quick Start

```bash
# 1. Install dependencies
pip install pandas numpy scikit-learn

# 2. Run the full pipeline (fetch → features → train → predict → Polymarket edge)
python scripts/run_pipeline.py

# 3. Output is TSV by default (copy-paste ready for Excel)
#    Use --format markdown for Markdown table output
#    Use --no-polymarket to skip the market lookup
```

### Polymarket Edge Layer

Polymarket auto-generates one event per EPL match
(`epl-{home3}-{away3}-{YYYY-MM-DD}-total-corners`) containing 23 binary markets. The seven
full-time total-corner lines match the seven models 1:1 and are the only lines scored.

| Concept | Definition |
|---------|------------|
| `ask` | best ask — the executable taker price |
| `edge` | `P_model − ask` (Over side) or `(1 − P_model) − ask` (Under side) |
| `EV%` | `edge / ask` |
| `f*` | full Kelly = `(p − ask) / (1 − ask)` |
| `stake` | `bankroll × kelly_frac × f*`, capped at `bankroll × max_stake_pct` |
| `shares` | `stake / ask` |

Defaults: `bankroll = 1000` USDC, `kelly_frac = 0.35`, `max_stake_pct = 0.05`,
`min_edge = 0.03`. A row is actionable only when `edge ≥ min_edge`, the market
`acceptingOrders`, not closed, and the best-ask level carries non-zero size.

> **These defaults are not currently usable as-is.** The model fails its out-of-sample gate, so
> the reported stake should not be acted on. The numbers below supersede them once the gate
> passes: `kelly_frac = 0.25`, `min_edge = 0.05`, plus a 6% per-match aggregate cap. See
> [Kelly Audit](#kelly-audit-2026-09-25).

Stakes are always reported as **both USDC and share count** (e.g. `$50 / 370 份`).

```
# ——— 可交易 Edge（≥3.0%，共 2 条）———
# Arsenal vs Chelsea | >10.5 Over @ 0.135 | 模型 30.0% | Edge +16.5% | 建议 $50 / 370 份
# Arsenal vs Chelsea | >9.5 Over @ 0.360  | 模型 44.0% | Edge +8.0%  | 建议 $44 / 122 份

# ——— 市场自洽性检查（P(>7.5) ≥ … ≥ P(>13.5)）———
# 未发现市场报价违反单调性。
```

Note: Polymarket corner books are thin — lifetime volume per match typically $1k–$150k, and
only the 9.5–11.5 lines usually carry meaningful size. The `深度(份)` column reports the
shares resting at the best ask.

### Kelly Audit (2026-09-25)

Out-of-sample behaviour was measured over 1,889 usable matches (2021-08-13 → 2026-08-24), with
the last 55% held out in six expanding-window folds of 173 matches (1,039 out-of-sample).

| Metric | Measured (7 lines) | Required to bet |
|--------|--------------------|-----------------|
| AUC | 0.465 – 0.528 — 6 of 7 within ±2σ of 0.50 (σ ≈ 0.019) | ≥ 0.55 |
| Brier skill vs climatology | −0.022 … −0.002 — **all negative** | > 0 |
| Calibration slope (logit) | −0.12 … +0.11 (theory = 1) | 0.7 – 1.3 |
| Reliability by prediction decile | non-monotone; the 10.5 line runs inverse | monotone |
| Edge capture (realized ÷ claimed) | −0.88 … +0.51, median negative | ≥ 0.5 |

A negative Brier skill means predicting the historical base rate outperforms the model. Label
integrity was verified first — `Target_L = (HC + AC > L)` matched on all 13,370 cells — so the
pipeline is sound. The root cause is upstream: the 19 team-form features correlate with total
corners at only **+0.023** (corners won) and **+0.068** (corners conceded), against a
distribution of 10.32 ± 3.39. Team-level corner tendency barely persists, which caps any model
built on these features at roughly AUC 0.53.

At the 0.35 Kelly default this prices to **−0.45% … +0.30% log growth per bet**, before spread.

**Consequences for sizing:**

1. **Quote no non-zero stake until the gate above is passed.** Report probabilities and the edge
   table, then state plainly that the model shows no measured out-of-sample edge and that no
   position is recommended.
2. Once passed, use `--kelly-frac 0.25` and `--min-edge 0.05`. Derivation: `λ* = σ²/(σ²+s²)`,
   with the measured edge-estimation error `s ≈ 3.5–5.0pp`.
3. **Always aggregate exposure per match and cap it at 6% of bankroll.** The seven full-time
   lines are nested (`>7.5 ⊃ >8.5 ⊃ … ⊃ >13.5`; pairwise outcome correlation 0.39–0.80), so they
   are one payoff ladder on one event, not seven independent bets. At the shipped defaults they
   sum to **27.6% of bankroll on a single match** (P&L sd 22.9%, P(loss) 52%).
4. Where available, prefer the zero-forecast path. The monotonicity check flags cross-line
   arbitrage that needs no predictive skill: if `P(>8.5) < P(>9.5)` is quoted, buying
   `Under 9.5` + `Over 8.5` costs < 1 and pays ≥ 1 in every state.

Full methodology, per-line tables and caveats:
[`references/kelly_audit_2026-09-25.md`](references/kelly_audit_2026-09-25.md).

### Configuration

All parameters have sensible defaults. Override as needed:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--start` | `2021` | Earliest historical season (e.g., 2021 = 2021-22) |
| `--n-recent` | `5` | Rolling window size for recent-form features |
| `--n-estimators` | `500` | Number of trees per Random Forest |
| `--max-depth` | `7` | Maximum tree depth |
| `--min-samples-leaf` | `8` | Minimum samples per leaf |
| `--cache-dir` | `cache/` | Directory for cached data and models |
| `--no-cache-data` | `false` | Force re-fetch all historical data |
| `--format` | `tsv` | Output format: `tsv` (Excel-ready) or `markdown` |
| `--no-polymarket` | `false` | Skip the Polymarket odds fetch + edge report |
| `--bankroll` | `1000` | Bankroll in USDC, base for Kelly staking |
| `--kelly-frac` | `0.35` | Kelly discount factor — **use `0.25` once the sizing gate passes** |
| `--max-stake-pct` | `0.05` | Per-bet cap as a share of bankroll |
| `--min-edge` | `0.03` | Minimum edge for a row to count as actionable — **use `0.05` once the gate passes** |
| `--edge-output` | `stdout` | Write the edge report to a file |
| `--no-book` | `false` | Fetch Polymarket metadata only, skip the CLOB order book |

There is currently **no per-match aggregate cap** — see
[Kelly Audit](#kelly-audit-2026-09-25) item 3 for why one is required.

### Individual Script Usage

Each pipeline step can also be run independently:

```bash
# Step 1: Fetch historical EPL data
python scripts/fetch_data.py --start 2021 --output cache/

# Step 2: Build walk-forward features
python scripts/build_features.py --input cache/epl_merged.csv --output cache/features.csv --n-recent 5

# Step 3: Train seven Random Forest classifiers
python scripts/train_models.py --features cache/features.csv --output cache/models/

# Step 4: Predict upcoming fixtures (also writes cache/predictions.json)
python scripts/predict.py --models cache/models/ --features cache/features.csv \
    --matches cache/epl_merged.csv --pred-out cache/predictions.json

# Step 5: Fetch live Polymarket corner odds
python scripts/pm_odds.py --fixtures cache/epl_merged.csv --out cache/pm_odds.json
python scripts/pm_odds.py --list          # just list available EPL corner events

# Step 6: Compute edge + Kelly sizing
# Note: 0.35 / 0.03 are the shipped defaults but are NOT usable until the sizing
# gate passes — see "Kelly Audit (2026-09-25)". Post-gate values are shown here.
python scripts/pm_edge.py --predictions cache/predictions.json --pm cache/pm_odds.json \
    --bankroll 1000 --kelly-frac 0.25 --min-edge 0.05
```

### Model Details

| Hyperparameter | Value |
|----------------|-------|
| Algorithm | Random Forest (scikit-learn) |
| Trees per model | 500 |
| Max depth | 7 |
| Min samples per leaf | 8 |
| Random seed | 42 |
| Preprocessing | `SimpleImputer` (mean) → `StandardScaler` |

### Output Format

**TSV (default)** — Tab-separated, paste directly into Excel:

```
# EPL Corner Probability Forecast — Trained on 2026-07-17 — 380 matches
# * = monotonicity corrected | Source: football-data.co.uk | For reference only

#    Date        Home         Away        P(>7.5)  P(>8.5)  P(>9.5)  P(>10.5) P(>11.5) P(>12.5) Key Drivers           Fixed
1    2026-08-15  Arsenal      Liverpool   68.0%    52.0%    38.0%    24.0%    14.0%    6.0%     Home high corners; ...  
2    2026-08-15  Chelsea      Man City    71.0%    65.0%    59.0%    42.0%    28.0%    15.0%    Both high shot volume  Yes
```

**Markdown** — Use `--format markdown` for a formatted table.

### Cold Start Warning

When the current season has fewer than 5 completed matches, rolling features rely on last season's data, and prediction stability is reduced. A warning will be displayed.

### Project Structure

```
epl-corner-probability/
├── README.md                  # This file
├── SKILL.md                   # Skill definition (for AI agent integration)
├── scripts/
│   ├── run_pipeline.py        # End-to-end pipeline orchestrator
│   ├── fetch_data.py          # Fetch EPL CSV from football-data.co.uk
│   ├── build_features.py      # Walk-forward feature engineering
│   ├── train_models.py        # Train 7 independent RF classifiers
│   ├── predict.py             # Predict probabilities for upcoming fixtures
│   ├── pm_odds.py             # Fetch live Polymarket total-corner odds
│   ├── pm_edge.py             # Model-vs-market edge + Kelly sizing
│   └── temp_build_fixtures.py # Fixture builder utility
├── references/
│   ├── data_columns.md        # Data column reference
│   ├── feature_spec.md        # Feature specification
│   └── kelly_audit_2026-09-25.md  # Out-of-sample audit + sizing gate derivation
└── cache/                     # (gitignored) Cached data, models, odds
    ├── epl_merged.csv         # Raw merged match data
    ├── features.csv           # Walk-forward feature matrix
    ├── predictions.json       # Model probabilities per fixture
    └── pm_odds.json           # Live Polymarket quotes per fixture
```

### Limitations & Scope

- **No measured out-of-sample edge** — see [Kelly Audit](#kelly-audit-2026-09-25). The model is
  fine as a structured probability pipeline but is not currently a basis for position sizing
- **EPL only** — Does not support other leagues (Serie A, La Liga, Bundesliga, etc.)
- **Pre-match only** — No in-play/live predictions
- **Full-time total corners only** — the half-time and per-team corner markets Polymarket
  offers are not modelled and are never scored
- **Polymarket only** — no bookmaker feeds are wired in
- **Thin books** — Polymarket corner liquidity is limited; treat `深度(份)` as the real ceiling
  and expect no market at all between matchweeks
- **Edge ≠ edge** — a divergence between model and price, not a statement that the market is
  wrong. Probability outputs are for research; sizing is provided for the user's own judgement

### License

This project is for educational and research purposes. Use at your own discretion.

---

## 中文

> **状态 —— 2026-09-25 审计：当前模型样本外无可测 edge。**
> Walk-forward 实测 1,889 场（2021-08 → 2026-08，其中 1,039 场为样本外）：AUC 0.465–0.528，
> 七条线 Brier Skill **全部为负**，校准斜率 ≈ 0。模型概率不含基准率之外的任何信息。
> **在通过下注门禁之前，不建议任何非零仓位** —— 详见 [Kelly 审计](#kelly-审计-2026-09-25)。
> Polymarket 对接与概率流水线本身不受影响，功能完整。

### 概述

一个机器学习流水线，用于预测每轮英超 (English Premier League) 比赛的角球概率分布。七个独立的**随机森林分类器**——每条角球线（7.5 至 13.5）一个——基于历史比赛数据构建的 Walk-Forward 特征进行训练。

**数据来源**：[football-data.co.uk](https://www.football-data.co.uk)（历史比赛数据）+ [Polymarket](https://polymarket.com) Gamma / CLOB API（实时角球盘口，免密钥）。

**两层输出**：
1. **概率层** —— 每场七条线的 P(Over)
2. **Edge 层** —— 模型 vs Polymarket 实时价、EV%、Kelly 建议仓位（同时给 USDC 金额与份数），每次运行自动抓取

### 工作原理

| 模型 | 预测目标（二分类） |
|------|-------------------|
| `model_7_5`  | 总角球数 > 7.5  |
| `model_8_5`  | 总角球数 > 8.5  |
| `model_9_5`  | 总角球数 > 9.5  |
| `model_10_5` | 总角球数 > 10.5 |
| `model_11_5` | 总角球数 > 11.5 |
| `model_12_5` | 总角球数 > 12.5 |
| `model_13_5` | 总角球数 > 13.5 |

每个模型使用相同的 **19 个特征**，但独立训练。预测后强制执行**单调性约束**：P(>7.5) ≥ P(>8.5) ≥ ... ≥ P(>13.5)。被修正的场次会在输出中标记。

### 特征工程（19 个特征）

**主队特征（9 个）**：
| 特征 | 含义 |
|------|------|
| `H_CornersFor_N` | 近 N 场场均获得角球 |
| `H_CornersAgainst_N` | 近 N 场场均被获得角球 |
| `H_CornersFor_S` | 本赛季场均获得角球 |
| `H_Shots_N` | 近 N 场场均射门 |
| `H_ShotsOnTarget_N` | 近 N 场场均射正 |
| `H_Goals_N` | 近 N 场场均进球 |
| `H_Fouls_N` | 近 N 场场均犯规 |
| `H_PPG_N` | 近 N 场场均积分 |
| `H_HomeCornersFor_N` | 近 N 个主场场均获得角球 |

**客队特征（9 个）**：与主队对称。

**组合特征（1 个）**：`TotalShots_N` = 主队射门 + 客队射门。

### 流水线架构

```
┌──────────┐    ┌──────────────┐    ┌────────────┐    ┌──────────┐
│  数据抓取 │ → │   特征工程    │ → │  模型训练   │ → │  概率预测  │
│ (football │    │ (Walk-Forward│    │ (7× 随机森林│    │ (未来赛程) │
│  -data)   │    │  无数据泄露)  │    │  各500棵树) │    │           │
└──────────┘    └──────────────┘    └────────────┘    └────┬─────┘
                                                           │
                            ┌──────────────────────────────┘
                            ▼
                  ┌──────────────────┐    ┌────────────────────┐
                  │ Polymarket 盘口   │ → │  Edge 报告          │
                  │ (Gamma + CLOB    │    │ (edge / EV% / Kelly │
                  │  实时 bid/ask)   │    │  金额 + 份数)        │
                  └──────────────────┘    └────────────────────┘
```

后两步是尽力而为：若 Polymarket 本轮没有开放角球盘（matchweek 之间属正常情况），
自动跳过并仍交付概率表。

#### Walk-Forward 特征工程

采用**严格的 Walk-Forward 逻辑**防止数据泄露：
1. 对每场比赛，从**该场比赛之前**的比赛计算滚动统计量
2. 计算完特征后，再用**本场**结果更新球队历史
3. 一场比赛自身的角球/结果数据**绝不会**出现在其特征行中

### 快速开始

```bash
# 1. 安装依赖
pip install pandas numpy scikit-learn

# 2. 运行完整流水线（抓取 → 特征 → 训练 → 预测 → Polymarket edge）
python scripts/run_pipeline.py

# 3. 默认输出 TSV 格式（可直接粘贴到 Excel）
#    使用 --format markdown 输出 Markdown 表格
#    使用 --no-polymarket 跳过盘口对比
```

### Polymarket Edge 层

Polymarket 为每场英超比赛自动生成一个事件
（`epl-{主队3字母}-{客队3字母}-{YYYY-MM-DD}-total-corners`），内含 23 个二值盘口。
其中全场大小 7 条线与七个模型 1:1 对应，是唯一参与评分的一组。

| 概念 | 定义 |
|------|------|
| `ask` | 最低卖价，taker 实际可成交价 |
| `edge` | `模型P − ask`（买 Over）或 `(1 − 模型P) − ask`（买 Under） |
| `EV%` | `edge / ask` |
| `f*` | 全 Kelly = `(p − ask) / (1 − ask)` |
| `stake` | `本金 × kelly_frac × f*`，上限 `本金 × max_stake_pct` |
| `shares` | `stake / ask` |

默认：本金 1000 USDC、`kelly_frac = 0.35`、`max_stake_pct = 0.05`、`min_edge = 0.03`。
仅当 `edge ≥ min_edge`、市场在接单、未关闭、且最优卖价档位有挂单量时，该行才视为可交易。

> **以上默认值当前不可直接使用。** 模型未通过样本外门禁，报告出的仓位不应被执行。
> 门禁通过后改用：`kelly_frac = 0.25`、`min_edge = 0.05`，并另加同场次 6% 总仓位上限。
> 详见 [Kelly 审计](#kelly-审计-2026-09-25)。

仓位始终**同时**给出 USDC 金额与份数（如 `$50 / 370 份`）。

```
# ——— 可交易 Edge（≥3.0%，共 2 条）———
# Arsenal vs Chelsea | >10.5 Over @ 0.135 | 模型 30.0% | Edge +16.5% | 建议 $50 / 370 份
# Arsenal vs Chelsea | >9.5 Over @ 0.360  | 模型 44.0% | Edge +8.0%  | 建议 $44 / 122 份

# ——— 市场自洽性检查（P(>7.5) ≥ … ≥ P(>13.5)）———
# 未发现市场报价违反单调性。
```

注意：Polymarket 角球盘口深度有限 —— 单场历史成交额约 $1k–$150k，通常只有 9.5–11.5
三条线有实质挂单量。`深度(份)` 列即最优卖价上的可成交量。

### Kelly 审计 2026-09-25

样本外表现实测于 1,889 场可用比赛（2021-08-13 → 2026-08-24），后 55%（1,039 场）作为
留出集，按 6 个 expanding-window 折各 173 场推进。

| 指标 | 实测（7 条线） | 下注门槛 |
|------|---------------|---------|
| AUC | 0.465 – 0.528 —— 7 条中 6 条落在 0.50 的 ±2σ 内（σ ≈ 0.019） | ≥ 0.55 |
| Brier Skill（对基准率） | −0.022 … −0.002 —— **全部为负** | > 0 |
| 校准斜率（logit） | −0.12 … +0.11（理论值 = 1） | 0.7 – 1.3 |
| 分档可靠性 | 非单调；10.5 线反向 | 单调 |
| Edge 捕获率（真实 ÷ 声称） | −0.88 … +0.51，中位数为负 | ≥ 0.5 |

Brier Skill 为负意味着**直接预测历史基准率比模型更准**。审计第一步先核对了标签完整性——
`Target_L = (HC + AC > L)` 在全部 13,370 个单元格上零 mismatch——所以流水线本身没有问题。
根源在上游：19 个球队状态特征与总角球的相关性只有 **+0.023**（角球获得）与 **+0.068**
（角球被获得），而总角球分布为 10.32 ± 3.39。球队级角球倾向几乎没有持续性，任何建立在这组
特征上的模型，AUC 上限约 0.53。

按默认 35% Kelly 折算，期望对数增长为 **−0.45% … +0.30%/注**（尚未计入买卖价差）。

**对仓位的结论：**

1. **在通过上表门禁之前，不报任何非零仓位。** 照常给出概率与 edge 表，然后明确说明模型
   未测出样本外 edge、不建议任何仓位。
2. 门禁通过后改用 `--kelly-frac 0.25` 与 `--min-edge 0.05`。推导：`λ* = σ²/(σ²+s²)`，
   其中 edge 估计误差实测 `s ≈ 3.5–5.0pp`。
3. **必须按场次聚合敞口，上限为本金 6%。** 七条全场线是嵌套的
   （`>7.5 ⊃ >8.5 ⊃ … ⊃ >13.5`，成对结果相关性 0.39–0.80），它们是同一事件的一个支付阶梯，
   不是 7 个独立下注。按当前默认参数逐线计算，会**在同一场比赛上押上 27.6% 本金**
   （P&L 标准差 22.9%，亏损概率 52%）。
4. 有条件时优先走零预测路径。单调性检查能发现无需任何预测能力的跨线套利：
   若市场报出 `P(>8.5) < P(>9.5)`，买入 `Under 9.5` + `Over 8.5` 成本 < 1，
   而任意结果均支付 ≥ 1。

完整方法学、逐线数据表与局限性说明：
[`references/kelly_audit_2026-09-25.md`](references/kelly_audit_2026-09-25.md)。

### 参数配置

所有参数都有合理默认值，可按需覆盖：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start` | `2021` | 最早历史赛季（如 2021 = 2021-22 赛季） |
| `--n-recent` | `5` | 近期状态特征的滚动窗口大小 |
| `--n-estimators` | `500` | 每个随机森林的决策树数量 |
| `--max-depth` | `7` | 树的最大深度 |
| `--min-samples-leaf` | `8` | 叶节点最少样本数 |
| `--cache-dir` | `cache/` | 缓存数据和模型目录 |
| `--no-cache-data` | `false` | 强制重新抓取所有历史数据 |
| `--format` | `tsv` | 输出格式：`tsv`（可粘贴到Excel）或 `markdown` |
| `--no-polymarket` | `false` | 跳过 Polymarket 盘口抓取与 edge 报告 |
| `--bankroll` | `1000` | 本金（USDC），Kelly 建议金额的基数 |
| `--kelly-frac` | `0.35` | Kelly 折扣系数 —— **门禁通过后改用 `0.25`** |
| `--max-stake-pct` | `0.05` | 单笔上限占本金比例 |
| `--min-edge` | `0.03` | 计入可交易的最小 Edge —— **门禁通过后改用 `0.05`** |
| `--edge-output` | `stdout` | Edge 报告输出路径 |
| `--no-book` | `false` | 只取 Polymarket 元数据，不拉 CLOB 订单簿 |

当前**没有同场次总仓位上限** —— 为什么必须有，见
[Kelly 审计](#kelly-审计-2026-09-25)第 3 条。

### 单独运行各步骤

流水线的每个步骤也可以独立运行：

```bash
# 步骤 1：抓取英超历史数据
python scripts/fetch_data.py --start 2021 --output cache/

# 步骤 2：构建 Walk-Forward 特征
python scripts/build_features.py --input cache/epl_merged.csv --output cache/features.csv --n-recent 5

# 步骤 3：训练七个随机森林分类器
python scripts/train_models.py --features cache/features.csv --output cache/models/

# 步骤 4：预测未来赛程（同时写出 cache/predictions.json）
python scripts/predict.py --models cache/models/ --features cache/features.csv \
    --matches cache/epl_merged.csv --pred-out cache/predictions.json

# 步骤 5：抓取 Polymarket 实时角球盘口
python scripts/pm_odds.py --fixtures cache/epl_merged.csv --out cache/pm_odds.json
python scripts/pm_odds.py --list          # 仅列出当前可用的英超角球事件

# 步骤 6：计算 edge 与 Kelly 仓位
# 注：0.35 / 0.03 是出厂默认值，但门禁通过前不可使用 —— 见「Kelly 审计（2026-09-25）」。
#     此处展示的是过门禁后的取值。
python scripts/pm_edge.py --predictions cache/predictions.json --pm cache/pm_odds.json \
    --bankroll 1000 --kelly-frac 0.25 --min-edge 0.05
```

### 模型详情

| 超参数 | 值 |
|--------|-----|
| 算法 | 随机森林 (scikit-learn) |
| 每模型树数量 | 500 |
| 最大深度 | 7 |
| 叶节点最少样本 | 8 |
| 随机种子 | 42 |
| 预处理 | `SimpleImputer` (均值填充) → `StandardScaler` (标准化) |

### 输出格式

**TSV 格式（默认）**——Tab 分隔，可直接粘贴到 Excel：

```
# EPL 角球概率预测 — 训练于 2026-07-17 — 380 场历史
# 注：* 标记表示该场概率经单调性修正 | 数据来源: football-data.co.uk | 仅供参考

#    日期        主队        客队       P(>7.5)  P(>8.5)  P(>9.5)  P(>10.5) P(>11.5) P(>12.5) 关键驱动因素           修正
1    2026-08-15  Arsenal     Liverpool  68.0%    52.0%    38.0%    24.0%    14.0%    6.0%     主队高近N场角球; ...   
2    2026-08-15  Chelsea     Man City   71.0%    65.0%    59.0%    42.0%    28.0%    15.0%    两队高射门量             是
```

**Markdown 格式**——使用 `--format markdown` 输出格式化表格。

### 冷启动警告

当当前赛季已完成场次少于 5 场时，滚动特征依赖上赛季末数据，预测稳定性降低。此时会显示警告提示。

### 项目结构

```
epl-corner-probability/
├── README.md                  # 本文件
├── SKILL.md                   # Skill 定义（用于 AI Agent 集成）
├── scripts/
│   ├── run_pipeline.py        # 端到端流水线编排
│   ├── fetch_data.py          # 从 football-data.co.uk 抓取英超 CSV
│   ├── build_features.py      # Walk-Forward 特征工程
│   ├── train_models.py        # 训练 7 个独立随机森林分类器
│   ├── predict.py             # 预测未来赛程概率
│   ├── pm_odds.py             # 抓取 Polymarket 实时角球盘口
│   ├── pm_edge.py             # 模型 vs 市场 edge + Kelly 仓位
│   └── temp_build_fixtures.py # 赛程构建工具
├── references/
│   ├── data_columns.md        # 数据列参考
│   ├── feature_spec.md        # 特征规格说明
│   └── kelly_audit_2026-09-25.md  # 样本外审计 + 仓位门禁推导
└── cache/                     # (gitignored) 缓存数据、模型、盘口
    ├── epl_merged.csv         # 原始合并比赛数据
    ├── features.csv           # Walk-Forward 特征矩阵
    ├── predictions.json       # 每场模型概率
    └── pm_odds.json           # 每场 Polymarket 实时报价
```

### 限制与适用范围

- **未测出样本外 edge** —— 详见 [Kelly 审计](#kelly-审计-2026-09-25)。模型作为结构化概率
  流水线是完整的，但当前不构成仓位管理的依据
- **仅限英超** — 不支持其他联赛（意甲、西甲、德甲等）
- **仅限赛前** — 不支持滚球/实时预测
- **仅限全场总角球** — Polymarket 提供的半场与单队角球盘口不在建模范围内，也不参与评分
- **仅对接 Polymarket** — 未接入任何博彩公司数据源
- **盘口深度有限** — Polymarket 角球流动性薄，请以 `深度(份)` 为实际成交上限；
  matchweek 之间可能完全没有开放盘口
- **edge 不等于必赢** — 它只是模型与市场价的偏离，市场也可能是对的。概率输出供研究参考，
  仓位建议仅供用户自行判断

### 许可

本项目仅供学习和研究用途，请自行斟酌使用。
