#!/usr/bin/env python3
"""
Fill photos.json: ESPN athlete id -> a freely licensed Wikimedia Commons photo, for
players ESPN has no headshot for (ESPN's own headshot stays first choice when it exists).

Matching never guesses a face:
  1. Wikidata item whose "ESPN.com tennis player ID" (P11585) IS the ESPN id — exact.
  2. Otherwise exactly ONE Wikidata item whose English label equals the ESPN name (accents
     ignored) AND
     whose occupation is tennis player (Q10833314). Zero or several => skipped.
The chosen item's image (P18) is resolved on Commons to a small thumbnail plus its
author and licence, which the page shows as credit in the photo lightbox.

Merge-only and fail-safe like the other builders: ids already decided (photo or checked)
are not looked up again, so after the first run a CI tick costs one read of data.json.
Every new Slam re-checks the "checked" ids (see main); delete one to retry it sooner. Standard library only, no API key.
"""
import html, json, os, re, sys, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "TennisSlamTracker/1.0 (https://github.com/danpune/tennis-slams-tracker)"}
TENNIS_PLAYER = "Q10833314"
SAFE_IMG = re.compile(r"https://(upload|thumb)\.wikimedia\.org/")
SAFE_FILE = re.compile(r"https://commons\.wikimedia\.org/wiki/File:")
SAFE_LIC = re.compile(r"https?://creativecommons\.org/")

def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={**UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def espn_has(i):
    try:
        req = urllib.request.Request(
            f"https://a.espncdn.com/i/headshots/tennis/players/full/{i}.png", method="HEAD", headers=UA)
        return urllib.request.urlopen(req, timeout=15).status == 200
    except Exception:
        return False

def players(data):
    """{espn id: full name} for everyone in the current Slam, singles and doubles."""
    out = {}
    for s in data.get("slams", []):
        for d in s["draws"]:
            for m in d["matches"]:
                for p in (m["a"], m["b"]):
                    if p.get("i"):
                        out[p["i"]] = p["n"]
                    for i in p.get("ids") or []:
                        out.setdefault(i, None)   # doubles carry initials only; name comes from ESPN
    return out

def by_espn_id(ids):
    """{espn id: Commons file name} via P11585 — exact identity."""
    found = {}
    for k in range(0, len(ids), 200):
        vals = " ".join(f'"{x}"' for x in ids[k:k + 200])
        q = f"SELECT ?espn ?img WHERE {{ VALUES ?espn {{ {vals} }} ?item wdt:P11585 ?espn; wdt:P18 ?img }}"
        d = get("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q}),
                "application/sparql-results+json")
        for b in d["results"]["bindings"]:   # several images: keep the first, deterministically
            f = urllib.parse.unquote(b["img"]["value"].rsplit("/", 1)[1])
            found[b["espn"]["value"]] = min(found.get(b["espn"]["value"], f), f)
    return found

def fold(s):
    """'Jakub Menšík' == 'Jakub Mensik': ESPN drops diacritics, Wikidata keeps them."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()

def by_unique_name(name):
    """Commons file name iff exactly one tennis player on Wikidata has this exact label."""
    d = get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": name, "language": "en", "type": "item",
         "limit": 10, "format": "json"}))
    qids = [x["id"] for x in d.get("search", []) if fold(x.get("label", "")) == fold(name)]
    if not qids:
        return None
    ents = get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbgetentities", "ids": "|".join(qids), "props": "claims", "format": "json"}))["entities"]
    def vals(e, p):
        return [c["mainsnak"].get("datavalue", {}).get("value") for c in e["claims"].get(p, [])]
    tennis = [e for e in ents.values() if any(v and v.get("id") == TENNIS_PLAYER for v in vals(e, "P106"))]
    if len(tennis) != 1:
        return None
    imgs = sorted(v for v in vals(tennis[0], "P18") if v)
    return imgs[0] if imgs else None

def commons_info(files):
    """{file: {u, a, l, lu, f}} — 120px thumbnail, author, licence, file page."""
    out = {}
    files = sorted(set(files))
    for k in range(0, len(files), 50):
        d = get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 120,
             "titles": "|".join("File:" + f for f in files[k:k + 50]), "format": "json"}))
        norm = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
        for page in d["query"]["pages"].values():
            ii = (page.get("imageinfo") or [None])[0]
            if not ii:
                continue
            md = ii.get("extmetadata") or {}
            lic = (md.get("LicenseShortName") or {}).get("value", "")
            if not lic:   # no machine-readable licence => don't use it
                continue
            author = re.sub(r"<[^>]+>", "", html.unescape((md.get("Artist") or {}).get("value", ""))).strip()
            title = page["title"]
            u, f = ii.get("thumburl", ""), ii.get("descriptionurl", "")
            lu = (md.get("LicenseUrl") or {}).get("value", "")
            # these strings reach src/href on the page, and Commons pages are editable by
            # anyone: accept only Wikimedia's own image/file URLs and a Creative Commons link
            if not (SAFE_IMG.match(u) and SAFE_FILE.match(f)):
                continue
            out[norm.get(title, title)[5:]] = {
                "u": u, "a": author[:80], "l": lic, "lu": lu if SAFE_LIC.match(lu) else "", "f": f}
    return out

def espn_names(ids):
    """Full names for doubles partners, from the ESPN scoreboard rosters."""
    names = {}
    for tour in ("atp", "wta"):
        try:
            d = get(f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard")
        except Exception:
            continue
        for ev in d.get("events", []):
            for g in ev.get("groupings", []):
                for c in g.get("competitions", []):
                    for comp in c.get("competitors", []):
                        for a in (comp.get("roster") or {}).get("athletes") or []:
                            m = re.search(r"/id/(\d+)/", ((a.get("links") or [{}])[0]).get("href", ""))
                            if m and m.group(1) in ids:
                                names[m.group(1)] = a.get("displayName")
    return names

def main():
    path = "photos.json"
    doc = {"_howto": "Auto-filled by build_photos.py: ESPN athlete id -> Wikimedia Commons photo "
                     "(u thumbnail, a author, l licence, lu licence url, f file page, how=espn-id|name) "
                     "for players without an ESPN headshot. 'checked' = looked up, no Commons photo needed (ESPN has one) or none safely matched.",
           "photos": {}, "checked": []}
    if os.path.exists(path):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"{path} unreadable ({e}); refusing to overwrite.", file=sys.stderr)
            return
    data = json.load(open("data.json", encoding="utf-8"))
    ppl = players(data)
    # A new Slam re-checks everyone still without a photo: Commons gains fresh tournament
    # photos every week, and most of the draw returns. Found photos are kept for good.
    slam = f"{data['slams'][0]['name']} {data['slams'][0]['start'][:4]}" if data.get("slams") else None
    if slam and doc.get("slam") != slam:
        doc["checked"] = []
    todo = [i for i in ppl if i not in doc["photos"] and i not in doc["checked"]]
    if not todo:
        print(f"photos.json: nothing new ({len(doc['photos'])} photos)")
        return   # (a new-Slam reset always leaves todo non-empty, so it is never lost here)
    try:
        with ThreadPoolExecutor(24) as ex:
            need = [i for i, has in zip(todo, ex.map(espn_has, todo)) if not has]
        have_espn = set(todo) - set(need)
        exact = by_espn_id(need)
        rest = [i for i in need if i not in exact]
        missing_names = [i for i in rest if not ppl.get(i)]
        ppl.update(espn_names(set(missing_names)) if missing_names else {})
        with ThreadPoolExecutor(4) as ex:
            named = {i: f for i, f in zip(rest, ex.map(
                lambda i: by_unique_name(ppl[i]) if ppl.get(i) else None, rest)) if f}
        info = commons_info(list(exact.values()) + list(named.values()))
    except Exception as e:
        print(f"lookup failed ({e}); photos.json left untouched.", file=sys.stderr)
        return
    added = 0
    for i in need:
        f, how = (exact[i], "espn-id") if i in exact else (named.get(i), "name")
        if f and f in info:
            doc["photos"][i] = {**info[f], "n": ppl.get(i) or "", "how": how}
            added += 1
        else:
            doc["checked"].append(i)
    # ESPN headshot exists: nothing to store, and no reason to look again
    doc["checked"].extend(sorted(have_espn))
    doc["checked"] = sorted(set(doc["checked"]))
    doc["slam"] = slam   # only stamped after a completed run, so a failed lookup retries
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=0)
    print(f"photos.json: +{added} photos ({len(doc['photos'])} total); "
          f"{len(have_espn)} have ESPN headshots; {len(need) - added} with no safe match")

if __name__ == "__main__":
    main()
