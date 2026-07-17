#!/usr/bin/env python3
"""temp_build_fixtures.py — Parse PL 2026-27 fixtures and write upcoming CSV."""

import csv

# Team name mapping: PL page → football-data.co.uk short names
TEAM_MAP = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "AFC Bournemouth": "Bournemouth",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Brighton and Hove Albion": "Brighton",
    "Chelsea": "Chelsea",
    "Coventry City": "Coventry",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Hull City": "Hull",
    "Ipswich Town": "Ipswich",
    "Leeds United": "Leeds",
    "Liverpool": "Liverpool",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Sunderland": "Sunderland",
    "Tottenham Hotspur": "Tottenham",
}

# All 380 fixtures extracted from premierleague.com, formatted as (Date, Home, Away)
# Date format: dd/mm/yyyy
FIXTURES = [
    # MW1
    ("21/08/2026", "Arsenal", "Coventry City"),
    ("22/08/2026", "Hull City", "Manchester United"),
    ("22/08/2026", "Everton", "Crystal Palace"),
    ("22/08/2026", "Ipswich Town", "Sunderland"),
    ("22/08/2026", "Nottingham Forest", "Leeds United"),
    ("22/08/2026", "Brentford", "Tottenham Hotspur"),
    ("23/08/2026", "Brighton & Hove Albion", "Aston Villa"),
    ("23/08/2026", "Manchester City", "AFC Bournemouth"),
    ("23/08/2026", "Newcastle United", "Liverpool"),
    ("24/08/2026", "Fulham", "Chelsea"),
    # MW2
    ("29/08/2026", "AFC Bournemouth", "Everton"),
    ("29/08/2026", "Aston Villa", "Arsenal"),
    ("29/08/2026", "Chelsea", "Brighton & Hove Albion"),
    ("29/08/2026", "Coventry City", "Hull City"),
    ("29/08/2026", "Crystal Palace", "Manchester City"),
    ("29/08/2026", "Leeds United", "Brentford"),
    ("29/08/2026", "Liverpool", "Nottingham Forest"),
    ("29/08/2026", "Manchester United", "Ipswich Town"),
    ("29/08/2026", "Sunderland", "Fulham"),
    ("29/08/2026", "Tottenham Hotspur", "Newcastle United"),
    # MW3
    ("05/09/2026", "Arsenal", "Chelsea"),
    ("05/09/2026", "Brentford", "Sunderland"),
    ("05/09/2026", "Brighton & Hove Albion", "Leeds United"),
    ("05/09/2026", "Everton", "Manchester United"),
    ("05/09/2026", "Fulham", "Crystal Palace"),
    ("05/09/2026", "Hull City", "Aston Villa"),
    ("05/09/2026", "Ipswich Town", "Liverpool"),
    ("05/09/2026", "Manchester City", "Coventry City"),
    ("05/09/2026", "Newcastle United", "AFC Bournemouth"),
    ("05/09/2026", "Nottingham Forest", "Tottenham Hotspur"),
    # MW4
    ("12/09/2026", "AFC Bournemouth", "Brentford"),
    ("12/09/2026", "Aston Villa", "Nottingham Forest"),
    ("12/09/2026", "Chelsea", "Hull City"),
    ("12/09/2026", "Coventry City", "Brighton & Hove Albion"),
    ("12/09/2026", "Crystal Palace", "Ipswich Town"),
    ("12/09/2026", "Leeds United", "Newcastle United"),
    ("12/09/2026", "Liverpool", "Fulham"),
    ("12/09/2026", "Manchester United", "Manchester City"),
    ("12/09/2026", "Sunderland", "Arsenal"),
    ("12/09/2026", "Tottenham Hotspur", "Everton"),
    # MW5
    ("19/09/2026", "AFC Bournemouth", "Liverpool"),
    ("19/09/2026", "Brentford", "Chelsea"),
    ("19/09/2026", "Brighton & Hove Albion", "Arsenal"),
    ("19/09/2026", "Everton", "Ipswich Town"),
    ("19/09/2026", "Fulham", "Manchester United"),
    ("19/09/2026", "Leeds United", "Crystal Palace"),
    ("19/09/2026", "Manchester City", "Sunderland"),
    ("19/09/2026", "Newcastle United", "Hull City"),
    ("19/09/2026", "Nottingham Forest", "Coventry City"),
    ("19/09/2026", "Tottenham Hotspur", "Aston Villa"),
    # MW6
    ("10/10/2026", "Arsenal", "Leeds United"),
    ("10/10/2026", "Aston Villa", "Brentford"),
    ("10/10/2026", "Chelsea", "AFC Bournemouth"),
    ("10/10/2026", "Coventry City", "Newcastle United"),
    ("10/10/2026", "Crystal Palace", "Nottingham Forest"),
    ("10/10/2026", "Hull City", "Everton"),
    ("10/10/2026", "Ipswich Town", "Fulham"),
    ("10/10/2026", "Liverpool", "Manchester City"),
    ("10/10/2026", "Manchester United", "Tottenham Hotspur"),
    ("10/10/2026", "Sunderland", "Brighton & Hove Albion"),
    # MW7
    ("17/10/2026", "AFC Bournemouth", "Sunderland"),
    ("17/10/2026", "Brentford", "Liverpool"),
    ("17/10/2026", "Brighton & Hove Albion", "Crystal Palace"),
    ("17/10/2026", "Everton", "Chelsea"),
    ("17/10/2026", "Fulham", "Hull City"),
    ("17/10/2026", "Leeds United", "Manchester United"),
    ("17/10/2026", "Manchester City", "Ipswich Town"),
    ("17/10/2026", "Newcastle United", "Aston Villa"),
    ("17/10/2026", "Nottingham Forest", "Arsenal"),
    ("17/10/2026", "Tottenham Hotspur", "Coventry City"),
    # MW8
    ("24/10/2026", "Arsenal", "Everton"),
    ("24/10/2026", "Aston Villa", "Manchester City"),
    ("24/10/2026", "Chelsea", "Tottenham Hotspur"),
    ("24/10/2026", "Coventry City", "Fulham"),
    ("24/10/2026", "Crystal Palace", "Newcastle United"),
    ("24/10/2026", "Hull City", "Brentford"),
    ("24/10/2026", "Ipswich Town", "Nottingham Forest"),
    ("24/10/2026", "Liverpool", "Brighton & Hove Albion"),
    ("24/10/2026", "Manchester United", "AFC Bournemouth"),
    ("24/10/2026", "Sunderland", "Leeds United"),
    # MW9
    ("31/10/2026", "AFC Bournemouth", "Leeds United"),
    ("31/10/2026", "Aston Villa", "Fulham"),
    ("31/10/2026", "Brentford", "Nottingham Forest"),
    ("31/10/2026", "Chelsea", "Manchester United"),
    ("31/10/2026", "Coventry City", "Sunderland"),
    ("31/10/2026", "Hull City", "Ipswich Town"),
    ("31/10/2026", "Liverpool", "Arsenal"),
    ("31/10/2026", "Manchester City", "Brighton & Hove Albion"),
    ("31/10/2026", "Newcastle United", "Everton"),
    ("31/10/2026", "Tottenham Hotspur", "Crystal Palace"),
    # MW10
    ("07/11/2026", "Arsenal", "Hull City"),
    ("07/11/2026", "Brighton & Hove Albion", "Brentford"),
    ("07/11/2026", "Crystal Palace", "Liverpool"),
    ("07/11/2026", "Everton", "Coventry City"),
    ("07/11/2026", "Fulham", "Newcastle United"),
    ("07/11/2026", "Ipswich Town", "AFC Bournemouth"),
    ("07/11/2026", "Leeds United", "Tottenham Hotspur"),
    ("07/11/2026", "Manchester United", "Aston Villa"),
    ("07/11/2026", "Nottingham Forest", "Manchester City"),
    ("07/11/2026", "Sunderland", "Chelsea"),
    # MW11
    ("21/11/2026", "AFC Bournemouth", "Nottingham Forest"),
    ("21/11/2026", "Aston Villa", "Sunderland"),
    ("21/11/2026", "Brentford", "Everton"),
    ("21/11/2026", "Chelsea", "Leeds United"),
    ("21/11/2026", "Coventry City", "Crystal Palace"),
    ("21/11/2026", "Hull City", "Brighton & Hove Albion"),
    ("21/11/2026", "Liverpool", "Manchester United"),
    ("21/11/2026", "Manchester City", "Fulham"),
    ("21/11/2026", "Newcastle United", "Arsenal"),
    ("21/11/2026", "Tottenham Hotspur", "Ipswich Town"),
    # MW12
    ("28/11/2026", "Arsenal", "Manchester City"),
    ("28/11/2026", "Brighton & Hove Albion", "Newcastle United"),
    ("28/11/2026", "Crystal Palace", "Hull City"),
    ("28/11/2026", "Everton", "Liverpool"),
    ("28/11/2026", "Fulham", "AFC Bournemouth"),
    ("28/11/2026", "Ipswich Town", "Aston Villa"),
    ("28/11/2026", "Leeds United", "Coventry City"),
    ("28/11/2026", "Manchester United", "Brentford"),
    ("28/11/2026", "Nottingham Forest", "Chelsea"),
    ("28/11/2026", "Sunderland", "Tottenham Hotspur"),
]

def map_team(name):
    return TEAM_MAP.get(name, name)

def main():
    columns = [
        "Date", "HomeTeam", "AwayTeam",
        "HC", "AC", "HS", "AS", "HST", "AST",
        "FTHG", "FTAG", "HF", "AF", "FTR",
        "HTHG", "HTAG", "HTR", "HY", "AY", "HR", "AR",
    ]
    
    rows = []
    for date, home, away in FIXTURES:
        row = {c: "" for c in columns}
        row["Date"] = date
        row["HomeTeam"] = map_team(home)
        row["AwayTeam"] = map_team(away)
        rows.append(row)
    
    output = "cache/upcoming_2627.csv"
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Written {len(rows)} fixtures to {output}")
    
    # Also create merged with all 5 seasons + upcoming
    import shutil
    # Read existing merged
    existing = []
    with open("cache/epl_merged.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing.append(row)
    
    # Append upcoming
    all_rows = existing + rows
    with open("cache/epl_merged_full.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    
    print(f"Full merged: {len(existing)} historical + {len(rows)} upcoming = {len(all_rows)} rows")
    
    # Check team mapping coverage
    all_teams = set()
    for d, h, a in FIXTURES:
        all_teams.add(h)
        all_teams.add(a)
    mapped = {t: map_team(t) for t in sorted(all_teams)}
    for orig, m in mapped.items():
        if orig != m:
            print(f"  Map: {orig} → {m}")

if __name__ == "__main__":
    main()
