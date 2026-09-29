#!/usr/bin/env python3
"""Self-check: run `python3 test_fetch.py` after fetch_data.py, BEFORE committing.

Asserts only, no framework — the point is to be a gate in the pipeline, not a test
suite. It catches data that is WRONG rather than missing. A crash announces itself;
a silently bad commit does not.

Exits non-zero on failure, so the workflow stops before publishing bad data.
"""
import json
import subprocess
from datetime import datetime, timezone

d = json.load(open("data.json"))
now = datetime.now(timezone.utc)

# 1. fresh, and not stamped in the future
updated = datetime.strptime(d["updated"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
assert updated <= now, f"updated is in the future: {d['updated']}"

slams = d.get("slams") or []
# Between Slams the feed carries no tournament — that is normal, and the file still
# carries the rankings. Only a file with neither is empty.
assert slams or (d.get("rankings") or {}).get("atp"), "no slams and no rankings — refusing to publish an empty file"

# 1b. the rankings. Off-season they are the entire file and nothing below runs, so a
#     feed-shape change (rank 0, name "?") would publish and sit there for months.
#     Shape is only asserted when a list is present: a rankings outage mid-Slam must not
#     block a score update, but an empty list off-season means there is nothing to publish.
for tour in ("atp", "wta"):
    rows = (d.get("rankings") or {}).get(tour) or []
    assert rows or slams, f"{tour} top-10 is empty and no Slam is running"
    if rows:
        assert len(rows) == 10, f"{tour} top-10 has {len(rows)} rows"
        assert [x.get("rank") for x in rows] == list(range(1, 11)), f"{tour} ranks are not 1..10"
        assert all(x.get("name") and x["name"] != "?" for x in rows), f"{tour} has unnamed players"
        assert all((x.get("points") or 0) > 0 for x in rows), f"{tour} has zero-point players"
        assert len({x["name"] for x in rows}) == 10, f"{tour} repeats a player"

matches = []
for s in slams:
    for k in ("name", "start", "end", "draws"):
        assert s.get(k), f"slam {s.get('name')!r} missing {k}"
    for dr in s["draws"]:
        assert dr.get("draw"), f"unnamed draw in {s['name']}"
        assert dr.get("matches") is not None, f"draw {dr.get('draw')} has no matches list"
        matches += dr["matches"]

assert matches or not slams, "slams present but not one match between them"

# 2. identity: a duplicate id silently merges two matches in the UI
ids = [m["id"] for m in matches if m.get("id")]
assert len(set(ids)) == len(ids), f"duplicate match ids: {len(ids) - len(set(ids))}"

# 3. exactly one winner per finished match. Two winners or none is the bug that
#    would quietly corrupt a bracket — and it renders without complaining.
for m in matches:
    a, b = m.get("a") or {}, m.get("b") or {}
    assert a.get("n") and b.get("n"), f"match {m.get('id')} is missing a player name"
    if m.get("done"):
        winners = bool(a.get("w")) + bool(b.get("w"))
        assert winners == 1, (f"finished match {m.get('id')} "
                              f"({a.get('n')} v {b.get('n')}) has {winners} winners")

# 4. a finished match must not be scheduled in the future
stamp = now.strftime("%Y-%m-%dT%H:%MZ")
future = [m["id"] for m in matches if m.get("done") and m.get("date", "") > stamp]
assert not future, f"{len(future)} finished matches dated in the future, e.g. {future[0]}"

# 5. completeness, not just shape. Every gate here checks the data is WELL-FORMED; a
#    partial upstream failure produces well-formed data that is missing most of itself,
#    and sails through. Compare against the build we are replacing and refuse a sudden
#    collapse: a Slam that vanished mid-tournament, or a draw that lost its matches.
prev = None
try:
    prev = json.loads(subprocess.run(["git", "show", "HEAD:data.json"], check=True,
                                     capture_output=True, text=True).stdout)
except Exception:
    pass                      # no previous build to compare with (first run, or no git)
if prev:
    def bydraw(doc):
        return {(s["name"], dr["draw"]): len(dr["matches"])
                for s in doc.get("slams") or [] for dr in s.get("draws") or []}
    old, new = bydraw(prev), bydraw(d)
    for s in prev.get("slams") or []:
        # a Slam only disappears legitimately once it is over and ESPN drops it
        ended = s.get("end", "") < now.strftime("%Y-%m-%dT%H:%MZ")
        assert ended or any(x["name"] == s["name"] for x in slams), \
            f"{s['name']} vanished from the feed but its end date has not passed"
    lost = {k: (old[k], new[k]) for k in old if k in new and new[k] < old[k] * 0.9}
    assert not lost, f"draws lost more than 10% of their matches: {lost}"
    gone = [k for k in old if k not in new and any(x["name"] == k[0] for x in slams)]
    assert not gone, f"draws disappeared from a Slam still in the feed: {gone}"

done = sum(1 for m in matches if m.get("done"))
print(f"all checks passed — {len(slams)} slam(s), {len(matches)} matches "
      f"({done} finished), updated {d['updated']}")
