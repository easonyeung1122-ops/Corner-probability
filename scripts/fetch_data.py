#!/usr/bin/env python3
"""fetch_data.py — Pull EPL historical data from football-data.co.uk.

Usage:
    python fetch_data.py --start 2021 --output cache/
    python fetch_data.py --start 2021 --output cache/ --no-cache
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request

URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"

# Column mapping from football-data.co.uk names to our internal names
COL_MAP = {
    "Date": "Date",
    "HomeTeam": "HomeTeam",
    "AwayTeam": "AwayTeam",
    "HC": "HC",
    "AC": "AC",
    "HS": "HS",
    "AS": "AS",
    "HST": "HST",
    "AST": "AST",
    "FTHG": "FTHG",
    "FTAG": "FTAG",
    "HF": "HF",
    "AF": "AF",
    "FTR": "FTR",
    "HTHG": "HTHG",
    "HTAG": "HTAG",
    "HTR": "HTR",
    "HY": "HY",
    "AY": "AY",
    "HR": "HR",
    "AR": "AR",
}


def season_code(season_start_year: int) -> str:
    """Convert 2021 → '2122' for season 2021-22."""
    yy = season_start_year % 100
    return f"{yy:02d}{(yy + 1) % 100:02d}"


def current_season_start(dt: datetime = None) -> int:
    """Determine current season start year based on date.
    EPL season runs August to May. If month >= 8, current season started this year."""
    if dt is None:
        dt = datetime.now()
    return dt.year if dt.month >= 8 else dt.year - 1


def season_codes(start: int, end: int) -> list[str]:
    """Generate all season codes from start to end (inclusive)."""
    return [season_code(y) for y in range(start, end + 1)]


def fetch_csv(code: str, timeout: int = 30) -> str | None:
    """Fetch a single season CSV. Returns raw text or None on failure."""
    url = URL_TEMPLATE.format(code=code)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EPL-Corner-Skill/1.0)"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        if raw.strip() == "" or "<html" in raw.lower()[:200]:
            return None
        return raw
    except Exception as e:
        print(f"  [WARN] fetch {url}: {e}", file=sys.stderr)
        return None


def parse_csv(raw: str) -> list[dict]:
    """Parse CSV into list of dicts, renaming columns via COL_MAP."""
    lines = raw.strip().splitlines()
    reader = csv.DictReader(lines)
    rows = []
    for row in reader:
        parsed = {}
        for src, dst in COL_MAP.items():
            if src in row:
                parsed[dst] = row[src].strip()
        rows.append(parsed)
    return rows


def filter_completed(rows: list[dict]) -> list[dict]:
    """Keep only completed matches (has HC/AC, not future)."""
    out = []
    for r in rows:
        hc = r.get("HC", "")
        ac = r.get("AC", "")
        if hc and ac:
            try:
                float(hc)
                float(ac)
                out.append(r)
            except ValueError:
                continue
    return out


def fetch_season(code: str, cache_dir: Path, no_cache: bool = False) -> list[dict]:
    """Fetch a single season, using cache unless --no-cache."""
    cache_file = cache_dir / f"season_{code}.csv"
    if not no_cache and cache_file.exists():
        raw = cache_file.read_text(encoding="utf-8")
        rows = parse_csv(raw)
        completed = filter_completed(rows)
        print(f"  {code}: {len(completed)} matches (cached)")
        return completed

    raw = fetch_csv(code)
    if raw is None:
        print(f"  {code}: not available")
        return []

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(raw, encoding="utf-8")
    rows = parse_csv(raw)
    completed = filter_completed(rows)
    print(f"  {code}: {len(completed)} matches (fetched)")
    return completed


def merge_all(all_rows: list[list[dict]]) -> list[dict]:
    """Merge all seasons, sort by date, remove duplicates."""
    seen = set()
    merged = []
    for season_rows in all_rows:
        for r in season_rows:
            key = (r.get("Date", ""), r.get("HomeTeam", ""), r.get("AwayTeam", ""))
            if key not in seen:
                seen.add(key)
                merged.append(r)
    merged.sort(key=lambda x: x.get("Date", ""))
    return merged


def required_columns_present(rows: list[dict]) -> bool:
    """Check that minimum required columns exist."""
    if not rows:
        return False
    required = {"HC", "AC", "HS", "AS", "HST", "AST", "FTHG", "FTAG", "HF", "AF"}
    sample = rows[0]
    missing = required - set(sample.keys())
    if missing:
        print(f"  [ERROR] Missing columns in data: {missing}", file=sys.stderr)
        return False
    return True


def write_output(rows: list[dict], output_path: Path):
    """Write merged rows to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(COL_MAP.values())
    all_cols = sorted(set(k for r in rows for k in r.keys()))
    final_cols = [c for c in columns if c in rows[0]] + [c for c in all_cols if c not in columns]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=final_cols)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} matches to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Fetch EPL historical data")
    parser.add_argument("--start", type=int, default=2021, help="Start season year (e.g. 2021 = 2021-22)")
    parser.add_argument("--output", type=str, default="cache/", help="Output directory")
    parser.add_argument("--no-cache", action="store_true", help="Force re-fetch all seasons")
    args = parser.parse_args()

    start_year = args.start
    current_start = current_season_start()
    output_dir = Path(args.output)

    print(f"EPL Corner Data Fetcher")
    print(f"  Seasons: {start_year}-{(start_year+1)%100:02d} to {current_start}-{(current_start+1)%100:02d}")
    print(f"  Output:  {output_dir.resolve()}")
    print()

    codes = season_codes(start_year, current_start)
    all_rows = []
    for code in codes:
        # Current season always re-fetch
        is_current = (code == season_code(current_start))
        rows = fetch_season(code, output_dir, no_cache=(is_current or args.no_cache))
        all_rows.append(rows)

    merged = merge_all(all_rows)
    if not merged:
        print("ERROR: No data fetched. Check network or season codes.", file=sys.stderr)
        sys.exit(1)

    if not required_columns_present(merged):
        sys.exit(1)

    output_path = output_dir / "epl_merged.csv"
    write_output(merged, output_path)

    print(f"\nDone. Years: {start_year}-{str(start_year+1)[-2:]} to {current_start}-{str(current_start+1)[-2:]}, Total: {len(merged)} matches.")


if __name__ == "__main__":
    main()
