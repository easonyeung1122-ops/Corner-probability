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
             kelly_frac: float, max_stake_pct: float, sides: str) -> list[dict]:
    rows = []
    for line in LINES:
        p_over = _f((pred.get("probs") or {}).get(str(line)))
        if p_over is None:
            continue

        mk = ((pm or {}).get("lines") or {}).get(str(line))
        row = {
            "date": pred.get("date", ""), "home": pred["home"], "away": pred["away"],
            "line": line, "p_over": p_over, "p_under": 1.0 - p_over,
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

        candidates = []
        if sides in ("both", "over") and ask_o is not None and 0 < ask_o < 1:
            mid_o = (ask_o + bid_o) / 2 if bid_o is not None else ask_o
            candidates.append({
                "side": "Over", "price": ask_o, "bid": bid_o, "mid": mid_o,
                "p": p_over, "edge": p_over - ask_o, "edge_mid": p_over - mid_o,
                "depth": size_o,
            })
        if sides in ("both", "under") and ask_u is not None and 0 < ask_u < 1:
            mid_u = (ask_u + bid_u) / 2 if bid_u is not None else ask_u
            candidates.append({
                "side": "Under", "price": ask_u, "bid": bid_u, "mid": mid_u,
                "p": 1.0 - p_over, "edge": (1.0 - p_over) - ask_u,
                "edge_mid": (1.0 - p_over) - mid_u, "depth": size_u,
            })

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
        if mk.get("closed"):
            note.append("已关闭")
        elif not mk.get("accepting_orders"):
            note.append("停止接单")
        if (best["depth"] or 0) <= 0:
            note.append("盘口无深度")
        elif best["depth"] is not None and stake > 0 and best["depth"] < shares:
            note.append(f"深度不足，仅可成交 {best['depth']:.0f} 份")

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
    """
    by_fx: dict[tuple, dict] = {}
    for r in rows:
        if r["mid"] is None or r["side"] == "":
            continue
        key = (r["home"], r["away"])
        by_fx.setdefault(key, {})[r["line"]] = (r["mid"] if r["side"] == "Over"
                                                else 1.0 - r["mid"])
    msgs = []
    for (home, away), mids in by_fx.items():
        seq = [mids.get(l) for l in LINES]
        if any(v is None for v in seq):
            continue
        bad = [(LINES[i], seq[i], LINES[i + 1], seq[i + 1])
               for i in range(len(seq) - 1) if seq[i] < seq[i + 1] - 1e-9]
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
    ap.add_argument("--min-edge", type=float, default=0.03, help="计入可交易的最小 Edge")
    ap.add_argument("--sides", choices=["both", "over", "under"], default="both")
    ap.add_argument("--format", choices=["tsv", "markdown"], default="tsv")
    ap.add_argument("--output", default="-", help="Output path, '-' for stdout")
    ap.add_argument("--json-out", default=None, help="Also dump full row data as JSON")
    args = ap.parse_args()

    pred_path, pm_path = Path(args.predictions), Path(args.pm)
    for p in (pred_path, pm_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)

    preds = load_predictions(pred_path)
    pms = load_pm(pm_path)

    all_rows: list[dict] = []
    missing = []
    for key, pred in preds.items():
        pm = pms.get(key)
        if pm is None:
            missing.append((pred.get("date", ""), pred["home"], pred["away"]))
        all_rows += evaluate(pred, pm, args.min_edge, args.bankroll,
                             args.kelly_frac, args.max_stake_pct, args.sides)

    out: list[str] = []
    pm_meta = json.loads(pm_path.read_text(encoding="utf-8"))
    out.append(f"# Polymarket Edge Report — 盘口抓取于 {pm_meta.get('fetched_at','?')}")
    out.append(f"# 本金 {args.bankroll:,.0f} USDC · {args.kelly_frac:.0%} Kelly · "
               f"单笔上限 {args.max_stake_pct:.1%} · Edge 阈值 {args.min_edge:.1%} · "
               f"方向 {args.sides}")
    out.append("# Edge = 模型概率 − 可成交价(ask)；EV% = Edge / ask；仅供参考")
    out.append("")

    cols = ["日期", "主队", "客队", "线", "方向", "模型P", "ask", "bid", "mid",
            "Edge", "EV%", "建议金额", "份数", "深度(份)", "备注"]
    out.append("\t".join(cols))
    for r in all_rows:
        out.append("\t".join([
            r["date"], r["home"], r["away"], f"{r['line']}",
            r["side"] or "—",
            fmt_pct(r["p_over"] if r["side"] != "Under" else r["p_under"]),
            "—" if r["ask"] is None else f"{r['ask']:.3f}",
            "—" if r["bid"] is None else f"{r['bid']:.3f}",
            "—" if r["mid"] is None else f"{r['mid']:.3f}",
            "—" if r["edge_ask"] is None else f"{r['edge_ask']*100:+.1f}%",
            "—" if (r["edge_ask"] is None or not r["ask"]) else f"{r['edge_ask']/r['ask']*100:+.1f}%",
            fmt_money(r["stake"]) if r["actionable"] else "—",
            fmt_money(r["shares"]) if r["actionable"] else "—",
            "—" if r["depth"] is None else f"{r['depth']:,.0f}",
            r["note"],
        ]))

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
