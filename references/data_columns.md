# football-data.co.uk E0.csv 列说明

## 核心列（本 skill 使用）

| CSV 列名 | 含义 | 类型 | 备注 |
|----------|------|------|------|
| `Date` | 比赛日期 | `dd/mm/yyyy` | 用于排序和时间序列构建 |
| `HomeTeam` | 主队名称 | `string` | 完整队名，如 "Arsenal" |
| `AwayTeam` | 客队名称 | `string` | |
| `FTHG` | 全场主队进球 | `int` | Full Time Home Goals |
| `FTAG` | 全场客队进球 | `int` | Full Time Away Goals |
| `FTR` | 全场结果 | `H / D / A` | Home win / Draw / Away win |
| `HTHG` | 半场主队进球 | `int` | Half Time Home Goals |
| `HTAG` | 半场客队进球 | `int` | Half Time Away Goals |
| `HTR` | 半场结果 | `H / D / A` | Half Time Result |
| `HS` | 主队射门（总） | `int` | Home Shots |
| `AS` | 客队射门（总） | `int` | Away Shots |
| `HST` | 主队射正 | `int` | Home Shots on Target |
| `AST` | 客队射正 | `int` | Away Shots on Target |
| `HC` | 主队角球 | `int` | **核心目标变量成分** |
| `AC` | 客队角球 | `int` | **核心目标变量成分** |
| `HF` | 主队犯规 | `int` | Home Fouls |
| `AF` | 客队犯规 | `int` | Away Fouls |
| `HY` | 主队黄牌 | `int` | Home Yellow Cards |
| `AY` | 客队黄牌 | `int` | Away Yellow Cards |
| `HR` | 主队红牌 | `int` | Home Red Cards |
| `AR` | 客队红牌 | `int` | Away Red Cards |

## 其他列（CSV 中存在但本 skill 未使用）

`Div`, `B365H`, `B365D`, `B365A`, `B365>2.5`, `B365<2.5`, `B365AH`, `B365AHH`,
`WHH`, `WHD`, `WHA`, `VCH`, `VCD`, `VCA`, `IWH`, `IWD`, `IWA`,
`PSH`, `PSD`, `PSA`, `PSCH`, `PSCD`, `PSCA`, `MaxH`, `MaxD`, `MaxA`,
`AvgH`, `AvgD`, `AvgA`, `BWH`, `BWD`, `BWA`, `Bb1X2`, `BbOU`, `BbAH`,
`Referee` 等。

这些列主要包含赔率信息，根据禁止事项条款，本 skill 不使用任何赔率数据。

## 角球列的数据完整性

- **2010-11 及之后**：几乎所有比赛都有 `HC` / `AC` 数据
- **2009-10 及之前**：`HC` / `AC` 可能缺失 — 自动排除

## 赛季码对照

| 赛季 | code | URL |
|------|------|-----|
| 2020-21 | 2021 | `mmz4281/2021/E0.csv` |
| 2021-22 | 2122 | `mmz4281/2122/E0.csv` |
| 2022-23 | 2223 | `mmz4281/2223/E0.csv` |
| 2023-24 | 2324 | `mmz4281/2324/E0.csv` |
| 2024-25 | 2425 | `mmz4281/2425/E0.csv` |
| 2025-26 | 2526 | `mmz4281/2526/E0.csv` |
| 2026-27 | 2627 | `mmz4281/2627/E0.csv` |

代码规则：`YY(YY+1)`，其中 YY 为赛季起始年份的后两位。
