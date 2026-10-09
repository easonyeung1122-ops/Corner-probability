#!/usr/bin/env python3
"""inject_fixtures.py — 把指定轮次的赛程注入 merged 数据尾部（HC/AC 留空 = upcoming）。

用法：
    python scripts/inject_fixtures.py --mw 6
    python scripts/inject_fixtures.py --mw 6 --fixtures cache/epl_merged_mw6.csv

赛程数据来自 temp_build_fixtures.py 内置的官方 2026-27 全季赛程表（380 场）。
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from temp_build_fixtures import FIXTURES, map_team  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE = SCRIPT_DIR.parent / "cache"


def fixtures_for_mw(mw: int) -> list[tuple[str, str, str]]:
    """按 MW 注释切分 FIXTURES，返回该轮全部赛程。"""
    out = FIXTURES[(mw - 1) * 10:(mw - 1) * 10 + 10]
    if len(out) != 10:
        raise SystemExit(f"MW{mw} 取到 {len(out)} 场，赛程表可能不完整")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mw", type=int, required=True, help="Matchweek number (1-38)")
    ap.add_argument("--merged", type=str, default="cache/epl_merged.csv")
    ap.add_argument("--fixtures", type=str, default=None,
                    help="输出文件（默认 cache/epl_merged_mw{mw}.csv）")
    args = ap.parse_args()

    merged_path = Path(args.merged)
    if not merged_path.is_absolute():
        merged_path = SCRIPT_DIR.parent / merged_path
    out_path = Path(args.fixtures) if args.fixtures else CACHE / f"epl_merged_mw{args.mw}.csv"
    if not out_path.is_absolute():
        out_path = SCRIPT_DIR.parent / out_path

    with open(merged_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    new_rows = []
    for date, home, away in fixtures_for_mw(args.mw):
        row = {c: "" for c in fieldnames}
        row["Date"] = date
        row["HomeTeam"] = map_team(home)
        row["AwayTeam"] = map_team(away)
        new_rows.append(row)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows + new_rows)

    print(f"{len(rows)} completed + {len(new_rows)} MW{args.mw} upcoming "
          f"= {len(rows) + len(new_rows)} rows -> {out_path}")
    for r in new_rows:
        print(f"  {r['Date']}  {r['HomeTeam']} vs {r['AwayTeam']}")


if __name__ == "__main__":
    main()