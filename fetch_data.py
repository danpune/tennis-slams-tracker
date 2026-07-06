#!/usr/bin/env python3
"""
Fetch Grand Slam data from ESPN's public scoreboard/rankings feeds.
Writes:
  data.json      — current Slam(s): every draw, every match, per-set scores + top-10s
  champions.json — EVERGREEN roll of honour: whenever a final completes, the champion
                   and runner-up are appended here permanently (the live feed only
                   carries current events, so this file is the site's memory).
Run by GitHub Actions every 30 min. No API key. Standard library only.
Fail-safe: never overwrites good files on a failed/empty fetch; champions merge-only.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
UA = {"User-Agent": "grandslams-tracker/1.0 (github.com/danpune/tennis-slams-tracker)"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)

def country(athlete):
    """3-letter code + name from the flag object/url ESPN attaches to every player."""
    fl = athlete.get("flag")
    if isinstance(fl, dict):
        href, alt = fl.get("href", ""), fl.get("alt", "")
    else:
        href, alt = str(fl or ""), athlete.get("flagAltText", "")
    code = href.rsplit("/", 1)[-1].split(".")[0].upper() if href else ""
    return code, alt

def competitor(x):
    a = x.get("athlete") or {}
    r = x.get("roster") or {}
    name = a.get("displayName") or r.get("shortDisplayName") or r.get("displayName") or "?"
    code, cname = country(a) if a else ("", "")
    return {"n": name, "c": code, "cn": cname,
            "s": [int(s.get("value", 0)) for s in (x.get("linescores") or [])],
            "w": bool(x.get("winner"))}

def fetch_tour(tour):
    d = get(f"{BASE}/{tour}/scoreboard")
    events = []
    for e in d.get("events", []):
        if not e.get("major"):
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
                matches.append({"round": (c.get("round") or {}).get("displayName", ""),
                                "date": c.get("date", ""), "done": bool(st.get("completed")),
                                "state": st.get("description", ""), "a": comps[0], "b": comps[1]})
            draws.append({"draw": gname, "matches": matches})
        events.append({"tour": tour, "name": e.get("name", ""), "start": e.get("date", ""),
                       "end": e.get("endDate", ""), "venue": (e.get("venue") or {}).get("fullName", ""),
                       "draws": draws})
    return events

def fetch_rankings(tour):
    d = get(f"{BASE}/{tour}/rankings")
    out = []
    for x in ((d.get("rankings") or [{}])[0].get("ranks") or [])[:10]:
        a = x.get("athlete") or {}
        code, cname = country(a)
        out.append({"rank": int(x.get("current", 0)), "name": a.get("displayName", "?"),
                    "c": code, "cn": cname, "points": int(float(x.get("points", 0)))})
    return out

def update_champions(slams):
    """Merge completed finals into champions.json — append-only, keyed year|slam|draw."""
    path = "champions.json"
    doc = {"note": "Roll of honour, accumulated automatically as finals complete "
                   "(2023-2025 seeded from public record).", "champions": []}
    if os.path.exists(path):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    have = {(c["year"], c["slam"], c["draw"]) for c in doc["champions"]}
    added = 0
    for s in slams:
        year = int((s.get("start") or "0000")[:4])
        for dr in s["draws"]:
            fin = next((m for m in dr["matches"] if m["done"] and m["round"] == "Final"), None)
            if not fin:
                continue
            w = fin["a"] if fin["a"]["w"] else (fin["b"] if fin["b"]["w"] else None)
            if not w:
                continue
            l = fin["b"] if w is fin["a"] else fin["a"]
            key = (year, s["name"], dr["draw"])
            if key in have:
                continue
            doc["champions"].append({"year": year, "slam": s["name"], "draw": dr["draw"],
                                     "champion": w["n"], "champC": w["c"],
                                     "runnerUp": l["n"], "runnerC": l["c"]})
            have.add(key); added += 1
    if added:
        doc["champions"].sort(key=lambda c: (-c["year"], c["slam"], c["draw"]))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=0)
    return added

def main():
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "ESPN (unofficial public feed)", "slams": [], "rankings": {}}
    try:
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
        print(f"Fetch failed ({e}); leaving existing files untouched.", file=sys.stderr)
        sys.exit(0)
    if not out["rankings"].get("atp") and not out["slams"]:
        print("Empty result; leaving existing files untouched.", file=sys.stderr)
        sys.exit(0)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    added = update_champions(out["slams"])
    nm = sum(len(dr["matches"]) for s in out["slams"] for dr in s["draws"])
    print(f"Wrote data.json ({len(out['slams'])} slam(s), {nm} matches) · "
          f"champions.json +{added} new")

if __name__ == "__main__":
    main()
