#!/usr/bin/env python3
"""pm_odds.py — Fetch live Polymarket "Total Corners" odds for EPL fixtures.

Polymarket auto-generates one event per match, slug pattern:
    epl-{home3}-{away3}-{YYYY-MM-DD}-total-corners
Each event carries 23 binary markets; this module only consumes the 7 full-time
total-corner lines (7.5 / 8.5 / 9.5 / 10.5 / 11.5 / 12.5 / 13.5) that the
prediction models cover.

Data sources (both keyless):
    Gamma API  https://gamma-api.polymarket.com   — event / market metadata
    CLOB API   https://clob.polymarket.com        — live order book (best bid/ask)

Usage:
    python pm_odds.py --list                       # list open EPL corner events
    python pm_odds.py --fixtures cache/epl_merged.csv --out cache/pm_odds.json
    python pm_odds.py --fixtures cache/epl_merged.csv --out - --no-book   # metadata only

Exit codes:
    0 — ran (even if zero fixtures matched; see "matched" count in output)
    2 — network / configuration failure
"""

import argparse
import csv
import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Polymarket "Premier League" series (recurrence: daily). Every per-match event
# family — moneyline, player props, total corners — hangs off this series id.
EPL_SERIES_ID = "10188"

LINES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5]

# ---------------------------------------------------------------------------
# Team-name reconciliation
# ---------------------------------------------------------------------------
# football-data.co.uk uses short names ("Man United", "Nott'm Forest"), Polymarket
# uses full legal-ish names ("Manchester United FC", "Nottingham Forest FC").
# We do fuzzy pair matching rather than a hard-coded table so that promoted /
# relegated clubs in future seasons resolve without code changes. The alias
# table below only seeds the tricky abbreviations the fuzzy matcher can miss.

PM_ALIASES = {
    "man city": "manchester city",
    "man united": "manchester united",
    "man utd": "manchester united",
    "newcastle": "newcastle united",
    "tottenham": "tottenham hotspur",
    "nott'm forest": "nottingham forest",
    "nottm forest": "nottingham forest",
    "brighton": "brighton and hove albion",
    "bournemouth": "afc bournemouth",
    "wolves": "wolverhampton wanderers",
    "west ham": "west ham united",
    "sheffield utd": "sheffield united",
    "leicester": "leicester city",
    "norwich": "norwich city",
    "cardiff": "cardiff city",
    "swansea": "swansea city",
    "stoke": "stoke city",
    "hull": "hull city",
    "ipswich": "ipswich town",
    "leeds": "leeds united",
    "coventry": "coventry city",
    "sunderland": "sunderland",
}

_DROP_TOKENS = {
    "fc", "afc", "cf", "sc", "ac", "club", "the",
}


def norm_team(name: str) -> str:
    """Normalize a club name to a comparable lowercase key."""
    if not name:
        return ""
    s = name.lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s']", " ", s)
    tokens = [t for t in s.split() if t and t not in _DROP_TOKENS]
    key = " ".join(tokens)
    key = re.sub(r"\s+", " ", key).strip()
    return PM_ALIASES.get(key, key)


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # containment bonus: "arsenal" vs "arsenal" already exact; "manchester city"
    # vs "manchester" should not score near 1, so keep it modest.
    if a in b or b in a:
        return 0.88
    return difflib.SequenceMatcher(None, a, b).ratio()


def pair_score(fd_home: str, fd_away: str, pm_home: str, pm_away: str) -> float:
    """Score how well a fixture matches a Polymarket event (0..1)."""
    h = _sim(norm_team(fd_home), norm_team(pm_home))
    a = _sim(norm_team(fd_away), norm_team(pm_away))
    if h < 0.6 or a < 0.6:
        return 0.0
    return (h + a) / 2


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 30, retries: int = 2):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — CLOB 404s on empty books are expected
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code in (400, 404):
                return None
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url} -> {last!r}")


# ---------------------------------------------------------------------------
# Event discovery
# ---------------------------------------------------------------------------

def _is_epl_corner_event(ev: dict) -> bool:
    slug = (ev.get("slug") or "").lower()
    title = ev.get("title") or ""
    return slug.startswith("epl-") and ("total-corners" in slug or "Total Corners" in title)


def discover_events(include_closed: bool = True) -> list[dict]:
    """Return all EPL Total Corners events (open first, then recent closed)."""
    found: dict[str, dict] = {}
    closed_opts = ["false", "true"] if include_closed else ["false"]

    urls = []
    for c in closed_opts:
        urls.append(f"{GAMMA}/events?tag_slug=epl&closed={c}&limit=100&offset=0"
                    f"&order=endDate&ascending=false")
        urls.append(f"{GAMMA}/events?series_id={EPL_SERIES_ID}&closed={c}&limit=100"
                    f"&order=endDate&ascending=false")

    for u in urls:
        try:
            d = _get(u)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {u} -> {e!r}", file=sys.stderr)
            continue
        for ev in (d or []):
            if _is_epl_corner_event(ev):
                found[ev["slug"]] = ev
    return sorted(found.values(), key=lambda e: e.get("endDate") or "")


def parse_market_lines(event: dict) -> dict[float, dict]:
    """Extract the full-time total-corner lines from an event."""
    out: dict[float, dict] = {}
    for m in event.get("markets") or []:
        title = m.get("groupItemTitle") or ""
        # only "Total Corners: O/U x.5" — skip 1st/2nd half and per-team lines
        if not title.startswith("Total Corners:"):
            continue
        mm = re.search(r"O/U\s+(\d+(?:\.\d+)?)", title)
        if not mm:
            continue
        line = float(mm.group(1))
        if line not in LINES:
            continue
        try:
            outcomes = json.loads(m.get("outcomes") or "[]")
        except Exception:  # noqa: BLE001
            outcomes = []
        try:
            tokens = json.loads(m.get("clobTokenIds") or "[]")
        except Exception:  # noqa: BLE001
            tokens = []
        try:
            prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
        except Exception:  # noqa: BLE001
            prices = []
        out[line] = {
            "group": title,
            "question": m.get("question"),
            "outcomes": outcomes,
            "tokens": tokens,
            "gamma_prices": prices,
            "condition_id": m.get("conditionId"),
            "accepting_orders": bool(m.get("acceptingOrders")),
            "closed": bool(m.get("closed")),
        }
    return out


# ---------------------------------------------------------------------------
# Order book
# ---------------------------------------------------------------------------

def _book_side(token_id: str) -> dict:
    """Best bid/ask + size-at-best for one outcome token."""
    b = _get(f"{CLOB}/book?token_id={urllib.parse.quote(token_id)}")
    if not b:
        return {"best_bid": None, "best_ask": None, "bid_size": None, "ask_size": None,
                "n_bids": 0, "n_asks": 0}
    bids = [(float(x["price"]), float(x["size"])) for x in (b.get("bids") or [])]
    asks = [(float(x["price"]), float(x["size"])) for x in (b.get("asks") or [])]
    bb = max(bids, key=lambda x: x[0]) if bids else None
    ba = min(asks, key=lambda x: x[0]) if asks else None
    return {
        "best_bid": bb[0] if bb else None,
        "best_ask": ba[0] if ba else None,
        "bid_size": bb[1] if bb else None,
        "ask_size": ba[1] if ba else None,
        "n_bids": len(bids),
        "n_asks": len(asks),
    }


def attach_books(markets: dict[float, dict], max_workers: int = 8) -> None:
    """Populate 'over' / 'under' book quotes for each line, in place."""
    jobs = []
    for line, mk in markets.items():
        toks = mk.get("tokens") or []
        if len(toks) >= 2 and not mk.get("closed"):
            jobs.append((line, "over", toks[0]))
            jobs.append((line, "under", toks[1]))

    if not jobs:
        return

    def work(job):
        line, side, tid = job
        try:
            return line, side, _book_side(tid)
        except Exception as e:  # noqa: BLE001
            return line, side, {"error": repr(e)}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for line, side, book in ex.map(work, jobs):
            markets[line][side] = book


# ---------------------------------------------------------------------------
# Fixture matching
# ---------------------------------------------------------------------------

def load_upcoming_fixtures(csv_path: Path) -> list[dict]:
    rows = list(csv.DictReader(open(csv_path, "r", encoding="utf-8-sig", errors="replace")))
    out, seen = [], set()
    for r in rows:
        hc = (r.get("HC") or "").strip()
        if hc:                      # completed match
            continue
        home = (r.get("HomeTeam") or "").strip()
        away = (r.get("AwayTeam") or "").strip()
        if not home or not away:
            continue
        key = (home, away)
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": (r.get("Date") or "").strip(), "home": home, "away": away})
    return out


def _parse_date(s: str):
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), f)
        except Exception:  # noqa: BLE001
            continue
    return None


def match_fixture(fixture: dict, events: list[dict], min_score: float = 0.85):
    """Pick the best (event, score) for a fixture, preferring date proximity."""
    best, best_score = None, 0.0
    fdate = _parse_date(fixture.get("date", ""))
    for ev in events:
        title = ev.get("title") or ""
        if " - Total Corners" not in title:
            continue
        pair = title.split(" - Total Corners")[0]
        if " vs. " not in pair:
            continue
        pm_home, pm_away = [p.strip() for p in pair.split(" vs. ", 1)]
        s = pair_score(fixture["home"], fixture["away"], pm_home, pm_away)
        if s <= 0:
            continue
        edate = _parse_date((ev.get("endDate") or "")[:10])
        if fdate and edate:
            delta = abs((edate - fdate).days)
            if delta > 3:
                continue
            s -= 0.02 * delta
        if s > best_score:
            best, best_score = ev, s
    if best is None or best_score < min_score:
        return None
    return best, best_score


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_payload(fixtures_path: Path | None, with_book: bool, include_closed: bool) -> dict:
    events = discover_events(include_closed=include_closed)
    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "source": {"gamma": GAMMA, "clob": CLOB, "series_id": EPL_SERIES_ID},
        "n_events_total": len(events),
        "fixtures": [],
    }

    if fixtures_path is None:
        # pure listing mode
        for ev in events:
            payload["fixtures"].append({
                "slug": ev.get("slug"), "title": ev.get("title"),
                "end_date": ev.get("endDate"), "closed": ev.get("closed"),
                "volume": ev.get("volume"),
            })
        return payload

    if not fixtures_path.exists():
        raise SystemExit(f"fixtures CSV not found: {fixtures_path}")

    fixtures = load_upcoming_fixtures(fixtures_path)
    unmatched = []
    for fx in fixtures:
        hit = match_fixture(fx, events)
        if not hit:
            unmatched.append(fx)
            continue
        ev, score = hit
        markets = parse_market_lines(ev)
        if with_book:
            attach_books(markets)

        lines_out = {}
        for line in sorted(markets):
            mk = markets[line]
            over = mk.get("over") or {}
            under = mk.get("under") or {}
            lines_out[str(line)] = {
                "group": mk.get("group"),
                "accepting_orders": mk.get("accepting_orders"),
                "closed": mk.get("closed"),
                "over": {k: over.get(k) for k in
                         ("best_bid", "best_ask", "bid_size", "ask_size")},
                "under": {k: under.get(k) for k in
                          ("best_bid", "best_ask", "bid_size", "ask_size")},
            }

        payload["fixtures"].append({
            "date": fx["date"],
            "home": fx["home"],
            "away": fx["away"],
            "slug": ev.get("slug"),
            "event_title": ev.get("title"),
            "end_date": ev.get("endDate"),
            "closed": ev.get("closed"),
            "volume": ev.get("volume"),
            "match_score": round(score, 3),
            "lines": lines_out,
        })

    payload["n_matched"] = len(payload["fixtures"])
    payload["unmatched"] = unmatched
    return payload


def main():
    ap = argparse.ArgumentParser(description="Fetch Polymarket EPL total-corner odds")
    ap.add_argument("--fixtures", type=str, default=None,
                    help="Merged CSV holding upcoming fixtures (rows with empty HC)")
    ap.add_argument("--out", type=str, default="-", help="Output JSON path, or '-' for stdout")
    ap.add_argument("--list", action="store_true", help="Only list EPL corner events")
    ap.add_argument("--no-book", action="store_true",
                    help="Skip CLOB order book (metadata + gamma prices only)")
    ap.add_argument("--open-only", action="store_true",
                    help="Only consider events where closed=false")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = ap.parse_args()

    fixtures_path = Path(args.fixtures) if args.fixtures else None
    if args.list:
        fixtures_path = None

    try:
        payload = build_payload(fixtures_path, with_book=not args.no_book,
                                include_closed=not args.open_only)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    if args.list:
        if not payload["fixtures"]:
            print("未发现英超角球事件。", file=sys.stderr)
        for e in payload["fixtures"]:
            print(f"{e['end_date']}  closed={str(e['closed']):<5}  vol={e['volume'] or 0:>10.0f}  {e['title']}")
        return

    text = json.dumps(payload, ensure_ascii=False,
                      indent=1 if args.pretty else None)
    if args.out == "-":
        print(text)
    else:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"matched {payload.get('n_matched', 0)} fixtures / "
              f"{len(payload.get('unmatched') or [])} unmatched "
              f"(events scanned: {payload['n_events_total']}) -> {out}", file=sys.stderr)
        for u in payload.get("unmatched") or []:
            print(f"  [unmatched] {u['date']} {u['home']} vs {u['away']}", file=sys.stderr)


if __name__ == "__main__":
    main()
