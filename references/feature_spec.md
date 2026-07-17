# Feature Engineering Specification

## Walk-Forward 数据划分规则

### 原则

所有特征必须是 match kickoff 之前已知的信息。训练集必须使用 walk-forward 逻辑：
1. 先提取该场比赛特征（基于已打完的历史）
2. 再用该场比赛结果更新 team stats
3. 绝不能把一场比赛的 HC / AC / result 泄漏回它自己的 feature row

### 实现

```python
for match in sorted_matches:
    features = compute_from_history(team_history[match.home][-N:],
                                     team_history[match.away][-N:],
                                     team_season)
    save(features)
    update_history(match)  # <- AFTER feature computation
```

### 赛季边界

当检测到跨赛季（Date 从 5 月跳到 8 月），清空所有 per-team season accumulators。
Rolling history 不清空（新赛季前几场依赖上赛季末数据，标注冷启动）。

---

## 19 特征详述

### Rolling N Mean（N 默认 5）

Per-team rolling 使用该队最近 N 场（不限主客）比赛数据计算算术均值。

#### 主队

| Feature | 公式 | NaN 处理 |
|---------|------|----------|
| `H_CornersFor_N` | mean(HC of last N matches for home team) | 训练集均值 |
| `H_CornersAgainst_N` | mean(AC of last N matches for home team) | 训练集均值 |
| `H_Shots_N` | mean(HS of last N matches for home team) | 训练集均值 |
| `H_ShotsOnTarget_N` | mean(HST of last N matches for home team) | 训练集均值 |
| `H_Goals_N` | mean(FTHG of last N matches for home team) | 训练集均值 |
| `H_Fouls_N` | mean(HF of last N matches for home team) | 训练集均值 |
| `H_PPG_N` | mean(points per game of last N matches) | 训练集均值 |

#### 客队

| Feature | 公式 | NaN 处理 |
|---------|------|----------|
| `A_CornersFor_N` | mean(AC of last N matches for away team) | 训练集均值 |
| `A_CornersAgainst_N` | mean(HC of last N matches for away team) | 训练集均值 |
| `A_Shots_N` | mean(AS of last N matches for away team) | 训练集均值 |
| `A_ShotsOnTarget_N` | mean(AST of last N matches for away team) | 训练集均值 |
| `A_Goals_N` | mean(FTAG of last N matches for away team) | 训练集均值 |
| `A_Fouls_N` | mean(AF of last N matches for away team) | 训练集均值 |
| `A_PPG_N` | mean(points per game of last N matches) | 训练集均值 |

### Venue-Specific Rolling（仅该方场地）

| Feature | 公式 | NaN 处理 |
|---------|------|----------|
| `H_HomeCornersFor_N` | mean(HC of last N **home** matches for home team) | 训练集均值 |
| `A_AwayCornersFor_N` | mean(AC of last N **away** matches for away team) | 训练集均值 |

### Season-to-Date

| Feature | 公式 | NaN 处理 |
|---------|------|----------|
| `H_CornersFor_S` | sum(HC this season) / games played this season | 训练集均值 |
| `A_CornersFor_S` | sum(AC this season) / games played this season | 训练集均值 |

### Combined

| Feature | 公式 | NaN 处理 |
|---------|------|----------|
| `TotalShots_N` | H_Shots_N + A_Shots_N | 训练集均值 |

---

## 目标变量

对每条盘口 line ∈ {7.5, 8.5, 9.5, 10.5, 11.5, 12.5}：

```
Target_{line} = 1 if (HC + AC) > line else 0
```

六条盘口各自独立建模，不共享参数。

---

## 冷启动标注

当某场比赛的 rolling window 不足 N 场时（赛季初期或升班马），
在输出中标注预测稳定性较差。判断条件：`len(h_recent) < n_recent or len(a_recent) < n_recent`。

---

## 数据完整性检查

训练前必须验证：
1. 每场比赛都有 HC 和 AC（否则排除出训练集）
2. 至少 500 场训练样本（否则提示数据不足）
3. 每条盘口的正样本比例均在 5%-95%（否则提示类别不平衡）

---

## Feature Importance 参考（可选的辅助输出）

训练完成后，可以针对每个模型输出 Top 5 feature importances，
帮助理解每条盘口的关键驱动维度。不作为必选输出。
