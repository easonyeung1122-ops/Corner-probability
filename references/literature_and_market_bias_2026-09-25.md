# Literature reconciliation & market-bias findings — 2026-09-25

Purpose: answer the question *"the paper says this model has edge — so why did the audit
find none?"* and record the one signal in the literature that is **not** a model signal.

---

## 1. This skill cites no paper

Verified across the whole repository and all 6 commits (`6d6dea3` → `c6c4a84`):
`SKILL.md`, `README.md`, `references/data_columns.md`, `references/feature_spec.md` contain
**zero** academic citations (grep for `paper|arxiv|doi|论文|文献|study`). The 19-feature set,
the RF design and the monotonicity rule were written directly, not transcribed from a source.

If a paper is being remembered as "the one in this skill", it came from outside the repo.

---

## 2. The closest paper to this project (and what it actually found)

**Pålsson, G. & Laurens, M. (2023).** *Forecasting Football Corner Odds: Statistical Modelling,
Betting Strategies and Assessing Market Efficiency.* Master's Theses in Mathematical Sciences,
**LUTFMS-3476-2023**, Lund University (supervisor J. Lindström).
https://lup.lub.lu.se/student-papers/record/9127007

Structurally it is almost a mirror of this skill:

| | Lund thesis | this skill |
|---|---|---|
| League | EPL (transfer test: Bundesliga) | EPL |
| Features | match-by-match team stats → rolling averages of several lengths + form/motivation | 19 rolling team-form features |
| Models | Negative binomial GLM, logistic regression, RF (numeric + classification) | 7 independent RF classifiers |
| Line | over/under **10.5** corners | 7.5 – 13.5 |
| Odds | **Betfair exchange**, 2018/19–2022/23, 2% commission on net winnings | Polymarket CLOB |
| Sizing | level stakes vs **Kelly** | level vs Kelly |

### Its stated conclusions (verbatim)

- "the best-performing models from each method were all profitable when tested on new data
  from the Premier League, **despite having a low degree of explanatory power**"
- "the match statistics-based models **are not significantly better than the naive models**"
- "the models seem **not to be sufficient to explain the number of corners**"
- Bundesliga transfer: "the majority of the models turned unprofitable"
- "**Due to the persistent randomness in the models, it is difficult to draw indisputable
  conclusions regarding which model should be preferred.**"

### Where the money actually came from — the market, not the model

- Tested on EPL, 1,211 matches: the null of unbiased pricing was **rejected, p = 0.0010**.
  Direction: **the UNDER side of the EPL over/under corner market is systematically undervalued.**
- Bundesliga, 589 matches: **p = 0.1909**, cannot reject (though the same direction, still profitable).

### Table 6.5 — EPL test seasons (544 matches with odds, Betfair, 2% commission)

| Strategy | Bets played | Wins | Total profit (u) | ROI |
|---|---|---|---|---|
| **Naive: always Under, level stakes (no model)** | 100% | **56.6%** | 29.5 | **+6.1%** |
| NegBin + level stakes | 96.7% | 50.9% | 14.1 | +3.0% |
| Logistic + level stakes | 94.4% | 50.5% | 17.2 | +3.8% |
| RF classification + level stakes | 96.3% | 53.0% | 35.7 | +7.7% |
| Logistic + Kelly | 94.4% | 50.5% | 54.2 | +11.9% |
| RF classification + Kelly | 96.3% | 53.0% | 74.0 | +15.9% |
| Logistic + Kelly, Under only | 44.8% | 57.4% | 49.9 | +23.1% |
| **RF classification + Kelly, Under only** | 53.1% | **59.0%** | 65.9 | **+25.8%** |

Reading: the naive always-Under leg already carries **+6.1% ROI with no model at all**.
The models lift it to +16…+26%, and they do so mostly by *restricting to the Under side and
varying the stake* — not by being well calibrated. Their own conclusion says as much.

**This is the same finding as the 2026-09-25 audit, not a contradiction.** AUC 0.465–0.528 and
negative Brier skill *is* "not significantly better than the naive model". The thesis is
compatible with the audit; only the *strategy conclusion* differs, because the thesis had a
mispriced market to lean on and we currently do not.

---

## 3. Does the under-bias survive in our own data?

Checked against `cache/epl_merged.csv` — **1,910 EPL matches with corner counts**,
2021-08 → 2026-08 (mean total corners 10.32, sd 3.39).

`P(Under 10.5)` = `P(HC + AC ≤ 10)`:

| Season | n | P(Under 10.5) | Break-even decimal odds |
|---|---|---|---|
| 2021-22 | 380 | 55.00% | 1.835 |
| 2022-23 | 380 | **57.11%** | 1.766 |
| 2023-24 | 380 | **47.63%** | 2.122 |
| 2024-25 | 380 | 51.58% | 1.958 |
| 2025-26 | 380 | 56.32% | 1.791 |
| **all** | **1,910** | **53.72%** (95% CI 51.5 – 56.0) | 1.879 |

Break-even odds assume 2% commission on net winnings, matching the thesis convention:
`d* = 1 + (1 − p) / (0.98 p)`.

**Cross-check:** the thesis's test sample showed a 56.6% Under win rate on 544 EPL matches drawn
from 2021-22 / 2022-23. Our full-population figure for those two seasons is **56.05% on 760
matches** — the samples agree.

**But the bias is regime-unstable.** Back-solving the thesis's average Under-10.5 Betfair price
(ROI +6.1% at 56.6% wins ⇒ **average odds ≈ 1.892**, implied 52.8%), and applying it to each
season:

| Sample | p | EV per bet at 1.892 |
|---|---|---|
| 2021-22 | 55.00% | +3.08% |
| 2022-23 | 57.11% | +7.03% |
| 2023-24 | 47.63% | **−10.73%** |
| 2024-25 | 51.58% | **−3.33%** |
| 2025-26 | 56.32% | +5.55% |
| **all 1,910** | 53.72% | **+0.68%** |

At the sample size we actually have, the naive always-Under leg prices to **+0.7% per bet** —
inside noise, and well below the spread on a thin Polymarket book.

**Caveat:** the 1.892 figure is *derived* (back-solved from the thesis's aggregate ROI), not a
measured per-match price series. We hold real corner counts but **no historical corner odds**,
so this cannot be settled conclusively from local data. It is an order-of-magnitude reconciliation.

---

## 4. The other commonly-cited "profitable" paper

**Wheatcroft, E. (2020).** *A profitable model for predicting the over/under market in football.*
*International Journal of Forecasting* **36**(3), 916–932. doi:10.1016/j.ijforecast.2019.11.001

- It is the **goals** over/under 2.5 market, **not corners**. Corners appear only as an *input*
  to the GAP rating, never as the target.
- Headline result: ~**+0.8% per bet over 12 years / 68,672 bets** using shots and corners as inputs.
- **The result only holds with maximum odds across all bookmakers** (BetBrain archive).
  The paper states that repeating the analysis with **average odds produces a loss under both
  betting strategies**. The edge lives in best-price shopping, not in the forecast.
- Follow-up: Wheatcroft (2021), *Journal of Sports Analytics* **7**(2), 77–97
  (doi:10.3233/JSA-200462) — match-outcome market — explicitly notes that profit **declines over
  the later seasons** as odds absorb more information.

---

## 5. Consequences for this skill

1. The model-vs-market edge path is unchanged: **no measured out-of-sample edge → no non-zero
   stake.** The literature does not rescue it; the closest paper says the same thing more politely.
2. The only literature-supported signal is **market-side**: EPL over/under corner **Under** is
   cheap. It requires no predictive skill, but it does require a **price ≥ break-even** on the
   specific match, and our own 5-season panel shows it is **not persistent** (2 of 5 seasons
   negative at the thesis-average price).
3. Therefore the actionable form is *not* "always bet Under". It is: quote an Under-side edge
   only when the executable ask implies a probability below the empirical Under rate for that
   line, and size it small.
4. To make (3) testable we need something we do not yet have: **a time series of Polymarket
   corner prices joined to outcomes.** Start persisting every `pm_odds.json` snapshot with the
   final corner count. Without it the under-bias can never be confirmed or refuted on the venue
   we actually trade.
5. Remaining honest position: 2021-23 looked like a real Under edge; 2023-25 did not. A single
   regime is not an edge. **Do not quote a position off this document alone.**

---

## Sources

- Pålsson, G. & Laurens, M. (2023), LUTFMS-3476-2023, Lund University — https://lup.lub.lu.se/student-papers/record/9127007
- Wheatcroft, E. (2020), *International Journal of Forecasting* 36(3), 916–932 — https://doi.org/10.1016/j.ijforecast.2019.11.001
- Wheatcroft, E. (2021), *Journal of Sports Analytics* 7(2), 77–97 — https://doi.org/10.3233/JSA-200462
- Own data: `cache/epl_merged.csv`, 1,910 EPL matches with corner counts, 2021-08 → 2026-08
