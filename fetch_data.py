#!/usr/bin/env python3
"""
Fetch Grand Slam data from ESPN's public scoreboard/rankings feeds and write data.json,
which the page reads. Run by GitHub Actions on a schedule. No API key required.
Sources (unofficial but stable for years):
  https://site.api.espn.com/apis/site/v2/sports/tennis/{atp|wta}/scoreboard
  https://site.api.espn.com/apis/site/v2/sports/tennis/{atp|wta}/rankings
Covers all five draws per Slam: the scoreboard's groupings are Men's/Women's Singles,
Men's/Women's Doubles and Mixed Doubles, with per-set scores and winner flags.
No third-party packages (standard library only). Fail-safe: never overwrites a good
data.json with an empty result.
"""
import json, sys, urllib.request
from datetime import datetime, timezone

BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
UA = {"User-Agent": "grandslams-tracker/1.0 (github.com/danpune/grandslams)"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)

def competitor(x):
    """Slim one side of a match: name + per-set games."""
    a = x.get("athlete") or {}
    r = x.get("roster") or {}
    name = a.get("displayName") or r.get("shortDisplayName") or r.get("displayName") or "?"
    sets = [int(s.get("value", 0)) for s in (x.get("linescores") or [])]
    return {"n": name, "s": sets, "w": bool(x.get("winner"))}

def fetch_tour(tour):
    """One tour's scoreboard -> list of major (Slam) events with all-draw matches."""
    d = get(f"{BASE}/{tour}/scoreboard")
    events = []
    for e in d.get("events", []):
        if not e.get("major"):          # Slams only — the whole point of the site
            continue
        draws = []
        for g in e.get("groupings", []):
            gname = (g.get("grouping") or {}).get("displayName", "?")
            matches = []
            for c in g.get("competitions", []):
                st = (c.get("status") or {}).get("type") or {}
                comps = [competitor(x) for x in c.get("competitors", [])]
                if len(comps) != 2:
                    continue
                matches.append({
                    "round": (c.get("round") or {}).get("displayName", ""),
                    "date": c.get("date", ""),
                    "done": bool(st.get("completed")),
                    "state": st.get("description", ""),
                    "a": comps[0], "b": comps[1],
                })
            draws.append({"draw": gname, "matches": matches})
        events.append({
            "tour": tour, "name": e.get("name", ""), "start": e.get("date", ""),
            "end": e.get("endDate", ""), "venue": (e.get("venue") or {}).get("fullName", ""),
            "champs2025": [{"name": w.get("displayName", ""), "draw": (w.get("type") or {}).get("text", "")}
                            for w in e.get("previousWinners", [])],
            "draws": draws,
        })
    return events

def fetch_rankings(tour):
    d = get(f"{BASE}/{tour}/rankings")
    ranks = ((d.get("rankings") or [{}])[0].get("ranks") or [])[:10]
    return [{"rank": int(x.get("current", 0)),
             "name": (x.get("athlete") or {}).get("displayName", "?"),
             "points": int(float(x.get("points", 0)))} for x in ranks]

def main():
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "ESPN (unofficial public feed)", "slams": [], "rankings": {}}
    try:
        # ATP + WTA scoreboards describe the same Slam; merge by name (draws differ per tour feed —
        # each feed carries all five draws, so take the first occurrence and skip duplicates).
        seen = set()
        for tour in ("atp", "wta"):
            for ev in fetch_tour(tour):
                if ev["name"] in seen:
                    continue
                seen.add(ev["name"])
                out["slams"].append(ev)
        out["rankings"]["atp"] = fetch_rankings("atp")
        out["rankings"]["wta"] = fetch_rankings("wta")
    except Exception as e:
        print(f"Fetch failed ({e}); leaving existing data.json untouched.", file=sys.stderr)
        sys.exit(0)
    if not out["rankings"].get("atp") and not out["slams"]:
        print("Empty result; leaving existing data.json untouched.", file=sys.stderr)
        sys.exit(0)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    nm = sum(len(dr["matches"]) for s in out["slams"] for dr in s["draws"])
    print(f"Wrote data.json: {len(out['slams'])} slam(s), {nm} matches, "
          f"top-10 ATP+WTA. Size: {len(json.dumps(out))//1024}KB")

if __name__ == "__main__":
    main()
