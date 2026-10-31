#!/usr/bin/env python3
"""pm_edge.py — Compare model corner probabilities against live Polymarket prices.

Inputs
    --predictions  JSON from `predict.py --pred-out`   (model P(Over) per line)
    --pm           JSON from `pm_odds.py`              (live bid/ask per line)

Output
    TSV table (Excel-ready) + a ranked summary block.

Edge definition
    For each full-time total-corner line L:
        buy Over  : edge = P_model(>L)      - ask(Over)
        buy Under : edge = (1 - P_model(>L)) - ask(Under)
    `ask` is the executable taker price. A row is actionable when
    edge >= --min-edge AND the book has a real ask with non-zero size.

Stake sizing
    Full Kelly for a binary contract bought at price c with win prob p:
        f* = (p - c) / (1 - c)
    Reported stake = bankroll * kelly_frac * f*, capped at
    bankroll * max_stake_pct. Shares = stake / c.

Usage
    python pm_edge.py --predictions cache/predictions.json --pm cache/pm_odds.json
    python pm_edge.py --predictions cache/predictions.json --pm cache/pm_odds.json \
        --bankroll 1000 --kelly-frac 0.35 --min-edge 0.03 --format tsv
"""

import argparse
import json
import sys
from pathlib import Path

LINES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5]
LINES_DESC = list(reversed(LINES))   # 13.5 -> 7.5, monotone-increasing P


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def kelly_stake(p: float, price: float, bankroll: float, kelly_frac: float,
                max_stake_pct: float) -> tuple[float, float, float]:
    """Return (stake_usdc, shares, full_kelly_fraction)."""
    if not (0.0 < price < 1.0):
        return 0.0, 0.0, 0.0
    f_full = max(0.0, (p - price) / (1.0 - price))
    f_used = min(kelly_frac * f_full, max_stake_pct)
    stake = bankroll * f_used
    shares = stake / price if price > 0 else 0.0
    return stake, shares, f_full


def apply_match_cap(rows: list[dict], bankroll: float,
                    max_match_pct: float) -> list[str]:
    """Scale down a match's stakes so the 7 nested lines sum to <= max_match_pct.

    The 7 full-time lines are nested (>7.5 ⊃ >8.5 ⊃ … ⊃ >13.5; pairwise outcome
    correlation 0.39-0.80), so they are ONE payoff ladder on one event, not 7
    independent bets. Capping each bet at max_stake_pct alone lets a single match
    absorb ~7x that. This caps the aggregate.

    Scales every actionable row of a match by the same factor, so the relative
    ranking inside the match is preserved. Returns human-readable cap notes.
    """
    cap = bankroll * max_match_pct
    notes: list[str] = []
    by_fx: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if r["actionable"]:
            by_fx.setdefault((r["home"], r["away"]), []).append(r)

    for (home, away), fx_rows in by_fx.items():
        total = sum(r["stake"] for r in fx_rows)
        if total <= cap:
            continue
        factor = cap / total
        for r in fx_rows:
            r["stake"] *= factor
            r["shares"] = r["stake"] / r["ask"] if r["ask"] else 0.0
            # Compressing the stake does not create depth. If the book cannot
            # fill the reduced size, cap the row at what is actually there.
            if r["depth"] is not None and r["depth"] < r["shares"]:
                fill_shares = float(r["depth"])
                r["shares"] = fill_shares
                r["stake"] = fill_shares * r["ask"]
                r["note"] = (f"{r['note']}; " if r["note"] else "") + \
                            f"单场限仓压缩 {factor:.0%}，深度仅 {r['depth']:.0f} 份"
                r["actionable"] = r["depth"] > 0
        notes.append(
            f"{home} vs {away}: {len(fx_rows)} 条合计 ${total:.0f} → 压缩至 "
            f"${cap:.0f}（{max_match_pct:.0%} 上限，系数 {factor:.2f}）"
        )
    return notes


def apply_total_cap(rows: list[dict], bankroll: float,
                    max_total_pct: float) -> list[str]:
    """Cap the whole book, and report directional concentration.

    Per-match caps do not bound a round where every edge points the same way.
    After per-line bias calibration the model sits below the market on all seven
    lines, so every actionable row comes out on the Under side: 20 "independent"
    bets that are one view — "this season's corner rate stays low" — repeated.
    On 2026-10-31 the uncapped book was 28% of bankroll on that single view.

    Scales all rows by a common factor when the book breaches the cap, so the
    cross-match ranking is preserved. Returns notes including the side split.
    """
    cap = bankroll * max_total_pct
    notes: list[str] = []
    act = [r for r in rows if r["actionable"]]
    if not act:
        return notes

    total = sum(r["stake"] for r in act)
    over = sum(r["stake"] for r in act if r["side"] == "Over")
    under = total - over
    n_over = sum(1 for r in act if r["side"] == "Over")
    n_under = len(act) - n_over
    notes.append(
        f"全组合: {len(act)} 条合计 ${total:.0f}（{total / bankroll:.1%} 本金）· "
        f"Over {n_over} 条 ${over:.0f} / Under {n_under} 条 ${under:.0f}"
    )
    dominant = max(over, under)
    if total > 0 and dominant / total >= 0.80:
        side = "Over" if over >= under else "Under"
        notes.append(
            f"⚠ 方向集中: {dominant / total:.0%} 敞口在 {side} 一个方向。"
            f"这是同一个判断重复 {n_over if side == 'Over' else n_under} 次，"
            f"不是 {len(act)} 个独立机会；一方全错则全仓同向亏损。"
        )
    if total <= cap:
        return notes

    factor = cap / total
    for r in act:
        r["stake"] *= factor
        r["shares"] = r["stake"] / r["ask"] if r["ask"] else 0.0
        r["note"] = ((r["note"] + "; ") if r["note"] else "") + \
                    f"全组合限仓 {factor:.0%}"
    notes.append(
        f"全组合限仓: ${total:.0f} → 压缩至 ${cap:.0f}"
        f"（{max_total_pct:.0%} 上限，系数 {factor:.2f}）"
    )
    return notes


def load_predictions(path: Path) -> dict[tuple[str, str], dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for fx in d.get("fixtures", []):
        out[(fx["home"], fx["away"])] = fx
    return out


def load_pm(path: Path) -> dict[tuple[str, str], dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for fx in d.get("fixtures", []):
        if "lines" not in fx:       # listing mode output
            continue
        out[(fx["home"], fx["away"])] = fx
    return out


def evaluate(pred: dict, pm: dict | None, min_edge: float, bankroll: float,
             kelly_frac: float, max_stake_pct: float, sides: str,
             bias: dict | None = None) -> list[dict]:
    rows = []
    for line in LINES:
        p_raw = _f((pred.get("probs") or {}).get(str(line)))
        if p_raw is None:
            continue

        # --- Bias calibration ----------------------------------------------
        # A model trained on five seasons averages over their corner rate. When
        # the current season runs cold, every line reads too high by several
        # points — on 2026-10-31 by +6.4pp to +15.1pp, which was larger than
        # the entire quoted edge. calibrate_bias.py measures that offset on
        # realised results; subtract it here before scoring.
        adj = (bias or {}).get(str(line))
        if adj is None:
            p_over = p_raw
        else:
            p_over = min(max(p_raw - float(adj), 0.001), 0.999)

        mk = ((pm or {}).get("lines") or {}).get(str(line))
        row = {
            "date": pred.get("date", ""), "home": pred["home"], "away": pred["away"],
            "line": line, "p_over": p_over, "p_under": 1.0 - p_over,
            "p_raw": p_raw, "bias": adj,
            "has_market": bool(mk),
        }

        if not mk:
            row.update({"side": "", "ask": None, "bid": None, "mid": None,
                        "edge_ask": None, "edge_mid": None,
                        "stake": 0.0, "shares": 0.0, "depth": None,
                        "actionable": False, "note": "无盘口"})
            rows.append(row)
            continue

        over, under = mk.get("over") or {}, mk.get("under") or {}
        ask_o, bid_o = _f(over.get("best_ask")), _f(over.get("best_bid"))
        ask_u, bid_u = _f(under.get("best_ask")), _f(under.get("best_bid"))
        size_o, size_u = _f(over.get("ask_size")), _f(under.get("ask_size"))

        # --- Shell book detection -------------------------------------------
        # Polymarket lists a market before anyone quotes it: both sides sit at
        # ~0.97/0.98 ask and ~0.02/0.03 bid, depth 20-50 shares. Such a book
        # has no information and its mid (~0.50) destroys market monotonicity
        # by construction. Treat it as "no quote".
        # A real book has over_ask + under_ask <= ~1.05 and a non-trivial depth.
        sum_ask = (ask_o or 0) + (ask_u or 0)
        shell = (ask_o is not None and ask_u is not None
                 and sum_ask > 1.05
                 and max(size_o or 0, size_u or 0) < 100)

        candidates = []
        if not shell and sides in ("both", "over") and ask_o is not None and 0 < ask_o < 1:
            mid_o = (ask_o + bid_o) / 2 if bid_o is not None else ask_o
            candidates.append({
                "side": "Over", "price": ask_o, "bid": bid_o, "mid": mid_o,
                "p": p_over, "edge": p_over - ask_o, "edge_mid": p_over - mid_o,
                "depth": size_o,
            })
        if not shell and sides in ("both", "under") and ask_u is not None and 0 < ask_u < 1:
            mid_u = (ask_u + bid_u) / 2 if bid_u is not None else ask_u
            candidates.append({
                "side": "Under", "price": ask_u, "bid": bid_u, "mid": mid_u,
                "p": 1.0 - p_over, "edge": (1.0 - p_over) - ask_u,
                "edge_mid": (1.0 - p_over) - mid_u, "depth": size_u,
            })

        if shell:
            row.update({"side": "", "ask": None, "bid": None, "mid": None,
                        "edge_ask": None, "edge_mid": None,
                        "stake": 0.0, "shares": 0.0, "depth": None,
                        "actionable": False, "note": "空盘（无真实报价）"})
            rows.append(row)
            continue

        if not candidates:
            row.update({"side": "", "ask": None, "bid": None, "mid": None,
                        "edge_ask": None, "edge_mid": None,
                        "stake": 0.0, "shares": 0.0, "depth": None,
                        "actionable": False,
                        "note": "已关闭" if mk.get("closed") else "无报价"})
            rows.append(row)
            continue

        best = max(candidates, key=lambda c: c["edge"])
        stake, shares, _ = kelly_stake(best["p"], best["price"], bankroll,
                                       kelly_frac, max_stake_pct)
        actionable = (best["edge"] >= min_edge and (best["depth"] or 0) > 0
                      and not mk.get("closed") and mk.get("accepting_orders"))

        note = []
        if adj is not None:
            note.append(f"校准 {float(adj)*100:+.1f}pp（原始 {p_raw*100:.1f}%）")
        if mk.get("closed"):
            note.append("已关闭")
        elif not mk.get("accepting_orders"):
            note.append("停止接单")
        if (best["depth"] or 0) <= 0:
            note.append("盘口无深度")
        elif best["depth"] is not None and stake > 0 and best["depth"] < shares:
            # The reported stake must be what can actually be filled at the best
            # ask. Quoting the full Kelly-sized amount against a 5-share book is
            # a phantom position.
            capped_shares = float(best["depth"])
            capped_stake = capped_shares * best["price"]
            note.append(f"深度不足，仅可成交 {capped_shares:.0f} 份")
            stake, shares = capped_stake, capped_shares

        row.update({
            "side": best["side"], "ask": best["price"], "bid": best["bid"],
            "mid": best["mid"], "edge_ask": best["edge"], "edge_mid": best["edge_mid"],
            "stake": stake, "shares": shares, "depth": best["depth"],
            "actionable": actionable, "note": "; ".join(note),
        })
        rows.append(row)
    return rows


def market_monotonicity(rows: list[dict]) -> list[str]:
    """Flag fixtures whose market-implied P(Over) violates monotonicity.

    P(Over 7.5) >= ... >= P(Over 13.5) must hold; a violation means Polymarket
    quotes are internally inconsistent (stale book / free cross-line arb).

    Lines whose book is wide are skipped. On 2026-10-31 Newcastle vs Everton
    quoted >12.5 at 0.43/0.06 and >13.5 at 0.49/0.02 — a 0.37-0.47 spread with
    500 shares on each side. The mid of such a book is an artefact of a market
    maker who left a resting order and walked away, so it breaks monotonicity
    by construction and the alarm is false. Only books tight enough for the mid
    to mean anything are tested.
    """
    MAX_SPREAD = 0.20
    by_fx: dict[tuple, dict] = {}
    for r in rows:
        if r["mid"] is None or r["side"] == "":
            continue
        if r["ask"] is None or r["bid"] is None:
            continue
        if abs(r["ask"] - r["bid"]) > MAX_SPREAD:
            continue
        key = (r["home"], r["away"])
        by_fx.setdefault(key, {})[r["line"]] = (r["mid"] if r["side"] == "Over"
                                                else 1.0 - r["mid"])
    msgs = []
    for (home, away), mids in by_fx.items():
        seq = [mids.get(l) for l in LINES]
        # Only compare adjacent lines that both have a usable mid. A dropped
        # wide-spread line leaves a hole, so pairs are filtered individually
        # rather than discarding the whole fixture.
        bad = []
        for i in range(len(seq) - 1):
            x, y = seq[i], seq[i + 1]
            if x is None or y is None:
                continue
            if x < y - 1e-9:
                bad.append((LINES[i], x, LINES[i + 1], y))
        if bad:
            detail = "; ".join(f"P(>{a})={x:.3f} < P(>{b})={y:.3f}" for a, x, b, y in bad)
            msgs.append(f"{home} vs {away}: {detail}")
    return msgs


def fmt_pct(x, nd=1):
    return "—" if x is None else f"{x*100:.{nd}f}%"


def fmt_money(x):
    return "—" if x is None else f"{x:,.0f}"


def main():
    ap = argparse.ArgumentParser(description="Polymarket edge report for EPL corners")
    ap.add_argument("--predictions", required=True, help="predictions JSON from predict.py")
    ap.add_argument("--pm", required=True, help="odds JSON from pm_odds.py")
    ap.add_argument("--bankroll", type=float, default=1000.0, help="本金 (USDC)")
    ap.add_argument("--kelly-frac", type=float, default=0.35, help="Kelly 折扣系数")
    ap.add_argument("--max-stake-pct", type=float, default=0.05,
                    help="单笔上限占本金比例")
    ap.add_argument("--max-match-pct", type=float, default=0.06,
                    help="同场次全部线合计上限占本金比例（7 条线嵌套，必须聚合限仓）")
    ap.add_argument("--max-total-pct", type=float, default=0.10,
                    help="全组合（同轮所有场次）合计上限占本金比例；方向单边集中时首要约束")
    ap.add_argument("--min-edge", type=float, default=0.03, help="计入可交易的最小 Edge")
    ap.add_argument("--sides", choices=["both", "over", "under"], default="both")
    ap.add_argument("--format", choices=["tsv", "markdown"], default="tsv")
    ap.add_argument("--output", default="-", help="Output path, '-' for stdout")
    ap.add_argument("--json-out", default=None, help="Also dump full row data as JSON")
    ap.add_argument("--bias", default=None,
                    help="bias.json from calibrate_bias.py — subtract measured per-line "
                         "over-prediction before scoring edge. Strongly recommended: "
                         "uncalibrated output conflates model bias with market edge.")
    args = ap.parse_args()

    pred_path, pm_path = Path(args.predictions), Path(args.pm)
    for p in (pred_path, pm_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)

    preds = load_predictions(pred_path)
    pms = load_pm(pm_path)

    bias_meta: dict | None = None
    bias: dict | None = None
    if args.bias:
        bias_path = Path(args.bias)
        if not bias_path.exists():
            print(f"ERROR: bias file {bias_path} not found", file=sys.stderr)
            sys.exit(1)
        bias_meta = json.loads(bias_path.read_text(encoding="utf-8"))
        bias = bias_meta.get("bias") or {}
        if not bias:
            print(f"[warn] {bias_path} contains no bias values — scoring raw probabilities",
                  file=sys.stderr)
            bias, bias_meta = None, None
        else:
            print(f"bias calibration: {len(bias)} lines, season "
                  f"{bias_meta.get('season','?')}, n={bias_meta.get('n_matches','?')}")

    all_rows: list[dict] = []
    missing = []
    for key, pred in preds.items():
        pm = pms.get(key)
        if pm is None:
            missing.append((pred.get("date", ""), pred["home"], pred["away"]))
        all_rows += evaluate(pred, pm, args.min_edge, args.bankroll,
                             args.kelly_frac, args.max_stake_pct, args.sides, bias)

    cap_notes = apply_match_cap(all_rows, args.bankroll, args.max_match_pct)
    total_notes = apply_total_cap(all_rows, args.bankroll, args.max_total_pct)

    out: list[str] = []
    pm_meta = json.loads(pm_path.read_text(encoding="utf-8"))
    out.append(f"# Polymarket Edge Report — 盘口抓取于 {pm_meta.get('fetched_at','?')}")
    out.append(f"# 本金 {args.bankroll:,.0f} USDC · {args.kelly_frac:.0%} Kelly · "
               f"单笔上限 {args.max_stake_pct:.1%} · 同场合计上限 {args.max_match_pct:.1%} · "
               f"全组合上限 {args.max_total_pct:.1%} · "
               f"Edge 阈值 {args.min_edge:.1%} · 方向 {args.sides}")
    out.append("# Edge = 模型概率 − 可成交价(ask)；EV% = Edge / ask；仅供参考")
    if bias_meta:
        med = bias_meta.get("bias_median")
        med_s = f"中位 {float(med)*100:+.1f}pp" if med is not None else ""
        out.append(f"# 概率已校准：按 {bias_meta.get('season','?')} 实测偏差扣减 "
                   f"({bias_meta.get('n_matches','?')} 场{('，' + med_s) if med_s else ''})。"
                   f"未校准时模型系统性高估 Over。")
    out.append("")

    cols = ["日期", "主队", "客队", "线", "方向", "模型P"]
    if bias_meta:
        cols.append("原始P")
    cols += ["ask", "bid", "mid", "Edge", "EV%", "建议金额", "份数", "深度(份)", "备注"]
    out.append("\t".join(cols))
    for r in all_rows:
        cells = [
            r["date"], r["home"], r["away"], f"{r['line']}",
            r["side"] or "—",
            fmt_pct(r["p_over"] if r["side"] != "Under" else r["p_under"]),
        ]
        if bias_meta:
            cells.append(fmt_pct(r["p_raw"] if r["side"] != "Under" else 1.0 - r["p_raw"]))
        cells += [
            "—" if r["ask"] is None else f"{r['ask']:.3f}",
            "—" if r["bid"] is None else f"{r['bid']:.3f}",
            "—" if r["mid"] is None else f"{r['mid']:.3f}",
            "—" if r["edge_ask"] is None else f"{r['edge_ask']*100:+.1f}%",
            "—" if (r["edge_ask"] is None or not r["ask"]) else f"{r['edge_ask']/r['ask']*100:+.1f}%",
            fmt_money(r["stake"]) if r["actionable"] else "—",
            fmt_money(r["shares"]) if r["actionable"] else "—",
            "—" if r["depth"] is None else f"{r['depth']:,.0f}",
            r["note"],
        ]
        out.append("\t".join(cells))

    acts = sorted([r for r in all_rows if r["actionable"]],
                  key=lambda r: r["edge_ask"], reverse=True)
    out.append("")
    out.append(f"# ——— 可交易 Edge（≥{args.min_edge:.1%}，共 {len(acts)} 条）———")
    if not acts:
        out.append("# 无。模型与市场无显著分歧，或盘口未开 / 无深度。")
    for r in acts:
        out.append(
            f"# {r['home']} vs {r['away']} | >{r['line']} {r['side']} @ {r['ask']:.3f} | "
            f"模型 {fmt_pct(r['p_over'] if r['side'] != 'Under' else r['p_under'])} | "
            f"Edge {r['edge_ask']*100:+.1f}% | 建议 ${r['stake']:.0f} / {r['shares']:.0f} 份"
        )

    mono = market_monotonicity(all_rows)
    out.append("")
    out.append("# ——— 市场自洽性检查（P(>7.5) ≥ … ≥ P(>13.5)）———")
    if mono:
        for m in mono:
            out.append(f"# ⚠ 非单调：{m}")
    else:
        out.append("# 未发现市场报价违反单调性。")

    if cap_notes:
        out.append("")
        out.append(f"# ——— 单场聚合限仓（上限 {args.max_match_pct:.0%} 本金）———")
        for n in cap_notes:
            out.append(f"# {n}")

    if total_notes:
        out.append("")
        out.append(f"# ——— 全组合敞口（上限 {args.max_total_pct:.0%} 本金）———")
        for n in total_notes:
            out.append(f"# {n}")

    if missing:
        out.append("")
        out.append(f"# ——— 无 Polymarket 盘口（{len(missing)} 场）———")
        for d, h, a in missing:
            out.append(f"# {d} {h} vs {a}")

    result = "\n".join(out)
    if args.output == "-":
        print(result)
    else:
        Path(args.output).write_text(result, encoding="utf-8", newline="")
        print(f"Edge report written to {args.output}", file=sys.stderr)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"rows": all_rows, "actionable": acts, "monotonicity": mono,
                        "params": vars(args)}, ensure_ascii=False, indent=1,
                       default=str),
            encoding="utf-8")
        print(f"Edge rows JSON written to {args.json_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
