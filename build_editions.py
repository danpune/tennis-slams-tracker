#!/usr/bin/env python3
"""
Backfill editions.json (and the roll of honour) for Slams that finished BEFORE this
site existed, using ESPN's historical scoreboard (?dates=YYYYMMDD returns the full
event snapshot). Going forward fetch_data.py archives editions automatically — this
tool is only for backfill. Usage: python3 build_editions.py 20260201 20260607 ...
"""
import sys
import fetch_data as F

def main():
    dates = sys.argv[1:] or ["20260201", "20260607"]  # AO + RG 2026 final weekends
    slams = []
    for d in dates:
        seen = set()
        for tour in ("atp", "wta"):
            for ev in F.fetch_tour(tour, {}, dates=d):
                if ev["name"] in seen:
                    continue
                seen.add(ev["name"])
                slams.append(ev)
    for s in slams:
        n = sum(len(dr["matches"]) for dr in s["draws"])
        print(f"fetched {s['name']} ({s['start'][:4]}): {len(s['draws'])} draws, {n} matches")
    ed = F.update_editions(slams)
    ch = F.update_champions(slams)
    print(f"editions.json +{ed} · champions.json +{ch}")

if __name__ == "__main__":
    main()
