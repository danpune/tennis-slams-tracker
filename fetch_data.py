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
import json, os, re, sys, urllib.request
from datetime import datetime, timezone

BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
CANON = {"Roland Garros": "Roland-Garros"}  # ESPN's spelling -> the site's (and the tournament's own)
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

def competitor(x, rankmap):
    a = x.get("athlete") or {}
    r = x.get("roster") or {}
    name = a.get("displayName") or r.get("shortDisplayName") or r.get("displayName") or "?"
    code, cname = country(a) if a else ("", "")
    out = {"n": name, "c": code, "cn": cname,
           "s": [int(s.get("value", 0)) for s in (x.get("linescores") or [])],
           "w": bool(x.get("winner"))}
    # player id (headshots live at a.espncdn.com/i/headshots/tennis/players/full/<id>.png)
    for l in a.get("links") or []:
        m = re.search(r"/id/(\d+)/", l.get("href", ""))
        if m:
            out["i"] = m.group(1)
            break
    if out.get("i") in rankmap:
        out["r"] = rankmap[out["i"]]   # current ATP/WTA world ranking
    return out

def fetch_tour(tour, rankmap, dates=None):
    d = get(f"{BASE}/{tour}/scoreboard" + (f"?dates={dates}" if dates else ""))
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
                comps = [competitor(x, rankmap) for x in c.get("competitors", [])]
                if len(comps) != 2:
                    continue
                matches.append({"id": str(c.get("id", "")),
                                "round": (c.get("round") or {}).get("displayName", ""),
                                "date": c.get("date", ""), "done": bool(st.get("completed")),
                                "state": st.get("description", ""), "a": comps[0], "b": comps[1]})
            draws.append({"draw": gname, "matches": matches})
        nm = e.get("name", "")
        events.append({"tour": tour, "name": CANON.get(nm, nm), "start": e.get("date", ""),
                       "end": e.get("endDate", ""), "venue": (e.get("venue") or {}).get("fullName", ""),
                       "draws": draws})
    return events

def fetch_rankings(tour):
    """Full ranking list (~150 deep) — top-10 is displayed, the rest ranks draw players."""
    d = get(f"{BASE}/{tour}/rankings")
    out = []
    for x in (d.get("rankings") or [{}])[0].get("ranks") or []:
        a = x.get("athlete") or {}
        code, cname = country(a)
        out.append({"rank": int(x.get("current", 0)), "name": a.get("displayName", "?"),
                    "i": str(a.get("id", "")), "c": code, "cn": cname,
                    "points": int(float(x.get("points", 0)))})
    return out

def norm_name(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().replace("-", " ")

def fetch_odds(slams):
    """Polymarket match-winner prices for upcoming matches (informational only).
    Matches a market to a match when each outcome contains one side's surname(s);
    stores m["o"] = [P(side a), P(side b)]. Fail-safe: any error leaves data as-is."""
    events = []
    for off in range(0, 500, 100):
        batch = get("https://gamma-api.polymarket.com/events"
                    f"?tag_slug=tennis&closed=false&limit=100&offset={off}")
        if not batch:
            break
        events += batch
    marks = []
    for e in events:
        for mk in e.get("markets") or []:
            # events carry side markets too (handicaps, 1st set...); the match-winner
            # market is the one whose question is the event title itself
            if mk.get("question") != e.get("title"):
                continue
            try:
                outs = json.loads(mk.get("outcomes") or "[]")
                prices = [float(p) for p in json.loads(mk.get("outcomePrices") or "[]")]
            except Exception:
                continue
            if len(outs) == 2 and len(prices) == 2 and not mk.get("closed"):
                marks.append(([norm_name(o) for o in outs], prices))
    def side_hits(side, outcome):  # every surname of the side ("A / B" for doubles) in outcome
        return all(norm_name(p.strip()).split()[-1] in outcome
                   for p in side["n"].split(" / ") if p.strip())
    tagged = 0
    for s in slams:
        for dr in s["draws"]:
            for m in dr["matches"]:
                if m["done"] or m["a"]["n"] == "TBD" or m["b"]["n"] == "TBD":
                    continue
                hits = []
                for outs, prices in marks:
                    if side_hits(m["a"], outs[0]) and side_hits(m["b"], outs[1]):
                        hits.append(prices)
                    elif side_hits(m["a"], outs[1]) and side_hits(m["b"], outs[0]):
                        hits.append(prices[::-1])
                if len(hits) == 1 and 0 < hits[0][0] < 1:  # unambiguous, non-degenerate
                    m["o"] = [round(hits[0][0], 3), round(hits[0][1], 3)]
                    tagged += 1
    return tagged

ARCHIVE_ROUNDS = ("Quarterfinal", "Semifinal", "Final")

def update_editions(slams):
    """Archive a finished Slam's business end (QF/SF/F, every draw) into editions.json —
    merge-only, keyed year|name. The live feed drops a Slam days after it ends; this is
    how the four-majors cards can show completed editions' winners forever."""
    path = "editions.json"
    doc = {"note": "Completed editions, QF onward — captured automatically as each "
                   "Slam finishes (backfillable via build_editions.py).", "editions": []}
    if os.path.exists(path):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    have = {(e["year"], e["name"]) for e in doc["editions"]}
    added = 0
    for s in slams:
        year = int((s.get("start") or "0000")[:4])
        if (year, s["name"]) in have:
            continue
        singles = [dr for dr in s["draws"] if "Singles" in dr["draw"]]
        if not singles or not all(any(m["done"] and m["round"] == "Final"
                                      for m in dr["matches"]) for dr in singles):
            continue  # not finished yet
        doc["editions"].append({
            "year": year, "name": s["name"], "start": s.get("start", ""),
            "end": s.get("end", ""), "venue": s.get("venue", ""),
            "draws": [{"draw": dr["draw"],
                       "matches": [m for m in dr["matches"] if m["round"] in ARCHIVE_ROUNDS]}
                      for dr in s["draws"]]})
        added += 1
    if added:
        doc["editions"].sort(key=lambda e: (-e["year"], e["name"]))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    return added

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
        rankmap = {}
        for tour in ("atp", "wta"):
            full = fetch_rankings(tour)
            out["rankings"][tour] = full[:10]
            rankmap.update({x["i"]: x["rank"] for x in full if x["i"]})
        seen = set()
        for tour in ("atp", "wta"):
            for ev in fetch_tour(tour, rankmap):
                if ev["name"] in seen:
                    continue
                seen.add(ev["name"])
                out["slams"].append(ev)
    except Exception as e:
        print(f"Fetch failed ({e}); leaving existing files untouched.", file=sys.stderr)
        sys.exit(0)
    if not out["rankings"].get("atp") and not out["slams"]:
        print("Empty result; leaving existing files untouched.", file=sys.stderr)
        sys.exit(0)
    try:
        odds = fetch_odds(out["slams"])
    except Exception as e:
        odds = 0
        print(f"Odds fetch failed ({e}); continuing without.", file=sys.stderr)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    added = update_champions(out["slams"])
    update_editions(out["slams"])
    nm = sum(len(dr["matches"]) for s in out["slams"] for dr in s["draws"])
    print(f"Wrote data.json ({len(out['slams'])} slam(s), {nm} matches, {odds} with odds) · "
          f"champions.json +{added} new")

if __name__ == "__main__":
    main()
