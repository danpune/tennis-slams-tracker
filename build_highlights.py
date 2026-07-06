#!/usr/bin/env python3
"""
Fill highlights.json: completed singles matches -> official YouTube highlight video ids.

Scrapes the Slam's OFFICIAL channel /videos page (latest ~30 uploads), matches
video titles against finished singles matches in data.json (both players' last
names + the word "Highlights"), then verifies EVERY candidate via the YouTube
oEmbed endpoint: author_url must be the official channel URL (NOT author_name —
on the sibling World Cup project a spam channel renamed itself to spoof that).

Merge-only and fail-safe: never removes entries, exits 0 on any fetch failure.
Run manually or from CI after fetch_data.py. Standard library only, no API key.
"""
import json, os, re, sys, unicodedata, urllib.request

CHANNELS = {  # ESPN slam name (lowercased, substring match) -> official channel handle
    "australian open": "@AustralianOpen",
    "french open": "@RolandGarros",
    "roland garros": "@RolandGarros",
    "wimbledon": "@Wimbledon",
    "us open": "@usopen",
}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en"}

def norm(s):
    """Lowercase, strip accents, hyphens->spaces — so 'Auger-Aliassime' matches 'Auger Aliassime'."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[-‐-―]", " ", s).lower()

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def channel_videos(handle):
    """(videoId, title) for the channel's latest uploads, newest first."""
    html = fetch(f"https://www.youtube.com/{handle}/videos")
    m = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not m:
        return []
    vids = []
    def walk(o):
        if isinstance(o, dict):
            lv = o.get("lockupViewModel")
            if lv and lv.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
                title = (((lv.get("metadata") or {}).get("lockupMetadataViewModel") or {})
                         .get("title") or {}).get("content", "")
                if lv.get("contentId") and title:
                    vids.append((lv["contentId"], title))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads(m.group(1)))
    return vids

def official(video_id, handle):
    """True iff YouTube oEmbed says this video belongs to the official channel."""
    try:
        d = json.loads(fetch("https://www.youtube.com/oembed?format=json&url="
                             f"https://www.youtube.com/watch?v={video_id}"))
    except Exception:
        return False
    return (d.get("author_url") or "").lower().rstrip("/") == \
        f"https://www.youtube.com/{handle}".lower()

def main():
    data = json.load(open("data.json", encoding="utf-8"))
    path = "highlights.json"
    doc = {"_howto": "Auto-filled by build_highlights.py: ESPN match id -> official "
                     "YouTube highlight. Every entry is oEmbed-verified against the "
                     "official channel's author_url. Manual entries welcome; merge-only.",
           "highlights": {}}
    if os.path.exists(path):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    have = doc["highlights"]
    added = 0
    for slam in data.get("slams", []):
        handle = next((h for k, h in CHANNELS.items() if k in slam["name"].lower()), None)
        if not handle:
            continue
        try:
            videos = [(v, t) for v, t in channel_videos(handle) if "highlights" in t.lower()]
        except Exception as e:
            print(f"{slam['name']}: channel fetch failed ({e}); skipping.", file=sys.stderr)
            continue
        pending = [m for d in slam["draws"] if "singles" in d["draw"].lower()
                   for m in d["matches"]
                   if m["done"] and m.get("id") and m["id"] not in have]
        for vid, title in videos:  # newest first; plain 'Highlights' precedes 'Extended'
            t = norm(title)
            hits = [m for m in pending
                    if norm(m["a"]["n"]).split()[-1] in t and norm(m["b"]["n"]).split()[-1] in t]
            if len(hits) != 1:  # no match, or ambiguous — leave for a human
                if len(hits) > 1:
                    print(f"ambiguous, skipped: {title}", file=sys.stderr)
                continue
            m = hits[0]
            if "extended" in t and m["id"] in have:
                continue  # already have the short-form clip
            if not official(vid, handle):
                print(f"REJECTED (not {handle}): {vid} {title}", file=sys.stderr)
                continue
            if m["id"] not in have:
                added += 1
            have[m["id"]] = {"yt": vid}
    if added:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=0)
    print(f"highlights.json: +{added} new ({len(have)} total)")

if __name__ == "__main__":
    main()
