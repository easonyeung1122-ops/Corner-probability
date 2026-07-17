# EPL Corner Probability Forecasting / 英超角球概率预测

[English](#english) | [中文](#中文)

---

## English

### Overview

A machine learning pipeline that forecasts corner probability distributions for every upcoming English Premier League (EPL) matchweek. Six independent **Random Forest classifiers** — one per corner line from 7.5 to 12.5 — are trained on walk-forward features built from historical match data.

**Data Source**: [football-data.co.uk](https://www.football-data.co.uk) — open, freely available EPL match statistics.

### How It Works

| Model | Target (Binary Classification) |
|-------|-------------------------------|
| `model_7_5`  | Total Corners > 7.5  |
| `model_8_5`  | Total Corners > 8.5  |
| `model_9_5`  | Total Corners > 9.5  |
| `model_10_5` | Total Corners > 10.5 |
| `model_11_5` | Total Corners > 11.5 |
| `model_12_5` | Total Corners > 12.5 |

Each model uses the same **19 features** but is trained independently. After prediction, **monotonicity** is enforced: P(>7.5) ≥ P(>8.5) ≥ ... ≥ P(>12.5). Fixtures where correction was applied are flagged in the output.

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
│ (football-  │    │ (walk-forward,  │    │ (6× RF, 500   │    │ (upcoming  │
│  data.co.uk)│    │  no leakage)    │    │  trees each)  │    │  fixtures) │
└─────────────┘    └────────────────┘    └──────────────┘    └────────────┘
```

#### Walk-Forward Feature Engineering

Features are built using **strict walk-forward logic** to prevent data leakage:
1. For each match, compute rolling statistics from matches played **strictly before** this match
2. After computing features, update team history **with** this match's outcomes
3. A match's own HC/AC/result is **never** included in its own feature row

### Quick Start

```bash
# 1. Install dependencies
pip install pandas numpy scikit-learn

# 2. Run the full pipeline (fetch → features → train → predict)
python scripts/run_pipeline.py

# 3. Output is TSV by default (copy-paste ready for Excel)
#    Use --format markdown for Markdown table output
```

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

### Individual Script Usage

Each pipeline step can also be run independently:

```bash
# Step 1: Fetch historical EPL data
python scripts/fetch_data.py --start 2021 --output cache/

# Step 2: Build walk-forward features
python scripts/build_features.py --input cache/epl_merged.csv --output cache/features.csv --n-recent 5

# Step 3: Train six Random Forest classifiers
python scripts/train_models.py --features cache/features.csv --output cache/models/

# Step 4: Predict upcoming fixtures
python scripts/predict.py --models cache/models/ --features cache/features.csv --matches cache/epl_merged.csv
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
│   ├── train_models.py        # Train 6 independent RF classifiers
│   ├── predict.py             # Predict probabilities for upcoming fixtures
│   └── temp_build_fixtures.py # Fixture builder utility
├── references/
│   ├── data_columns.md        # Data column reference
│   └── feature_spec.md        # Feature specification
└── cache/                     # (gitignored) Cached data & trained models
```

### Limitations & Scope

- **EPL only** — Does not support other leagues (Serie A, La Liga, Bundesliga, etc.)
- **Pre-match only** — No in-play/live predictions
- **Corners only** — Does not predict goals, cards, or other markets
- **Probability output only** — No betting advice, no Kelly criterion, no wagering recommendations

### License

This project is for educational and research purposes. Use at your own discretion.

---

## 中文

### 概述

一个机器学习流水线，用于预测每轮英超 (English Premier League) 比赛的角球概率分布。六个独立的**随机森林分类器**——每条角球线（7.5 至 12.5）一个——基于历史比赛数据构建的 Walk-Forward 特征进行训练。

**数据来源**: [football-data.co.uk](https://www.football-data.co.uk) —— 开放、免费的英超比赛统计数据。

### 工作原理

| 模型 | 预测目标（二分类） |
|------|-------------------|
| `model_7_5`  | 总角球数 > 7.5  |
| `model_8_5`  | 总角球数 > 8.5  |
| `model_9_5`  | 总角球数 > 9.5  |
| `model_10_5` | 总角球数 > 10.5 |
| `model_11_5` | 总角球数 > 11.5 |
| `model_12_5` | 总角球数 > 12.5 |

每个模型使用相同的 **19 个特征**，但独立训练。预测后强制执行**单调性约束**：P(>7.5) ≥ P(>8.5) ≥ ... ≥ P(>12.5)。被修正的场次会在输出中标记。

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
│ (football │    │ (Walk-Forward│    │ (6× 随机森林│    │ (未来赛程) │
│  -data)   │    │  无数据泄露)  │    │  各500棵树) │    │           │
└──────────┘    └──────────────┘    └────────────┘    └──────────┘
```

#### Walk-Forward 特征工程

采用**严格的 Walk-Forward 逻辑**防止数据泄露：
1. 对每场比赛，从**该场比赛之前**的比赛计算滚动统计量
2. 计算完特征后，再用**本场**结果更新球队历史
3. 一场比赛自身的角球/结果数据**绝不会**出现在其特征行中

### 快速开始

```bash
# 1. 安装依赖
pip install pandas numpy scikit-learn

# 2. 运行完整流水线（抓取 → 特征 → 训练 → 预测）
python scripts/run_pipeline.py

# 3. 默认输出 TSV 格式（可直接粘贴到 Excel）
#    使用 --format markdown 输出 Markdown 表格
```

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

### 单独运行各步骤

流水线的每个步骤也可以独立运行：

```bash
# 步骤 1：抓取英超历史数据
python scripts/fetch_data.py --start 2021 --output cache/

# 步骤 2：构建 Walk-Forward 特征
python scripts/build_features.py --input cache/epl_merged.csv --output cache/features.csv --n-recent 5

# 步骤 3：训练六个随机森林分类器
python scripts/train_models.py --features cache/features.csv --output cache/models/

# 步骤 4：预测未来赛程
python scripts/predict.py --models cache/models/ --features cache/features.csv --matches cache/epl_merged.csv
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
│   ├── train_models.py        # 训练 6 个独立随机森林分类器
│   ├── predict.py             # 预测未来赛程概率
│   └── temp_build_fixtures.py # 赛程构建工具
├── references/
│   ├── data_columns.md        # 数据列参考
│   └── feature_spec.md        # 特征规格说明
└── cache/                     # (gitignored) 缓存数据和训练好的模型
```

### 限制与适用范围

- **仅限英超** — 不支持其他联赛（意甲、西甲、德甲等）
- **仅限赛前** — 不支持滚球/实时预测
- **仅限角球** — 不预测进球、红黄牌等其他盘口
- **仅输出概率** — 不提供投注建议、凯利准则或下注推荐

### 许可

本项目仅供学习和研究用途，请自行斟酌使用。
