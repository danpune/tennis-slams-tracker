# Tennis Grand Slam Tracker — project notes

LIVE: https://danpune.github.io/tennis-slams-tracker/ · repo `danpune/tennis-slams-tracker`
Separate project from `~/worldcup2026` (same playbook, deliberately independent —
including visually: this site is LIGHT (white cards / Wimbledon green `--acc`), the
World Cup one is dark; keep it that way).

## Architecture
- `index.html` — the entire site, self-contained (inline CSS + vanilla JS, system fonts,
  no dependencies, no cookies/tracking/keys; player headshots hot-linked from
  `a.espncdn.com/i/headshots/tennis/players/full/<id>.png`, click any photo for a
  lightbox, click any player NAME for their path-through-the-Slam panel).
  Sections: countdown → four-majors cards (multi-year `eds` list, auto-rollover,
  "dates TBA" fallback) → Catch-up brief → live-Slam results (5 draws × round chips
  + ⭐ Following filter, ▶ Highlights links from highlights.json) → follow box →
  roll of honour → top-10 (singles only — ESPN's feed has NO doubles/mixed
  rankings, don't invent them) → highlights links.
- `fetch_data.py` → `data.json` (current Slam, all draws, per-set scores, countries,
  ESPN match `id`s + athlete `i`ds + world ranking `r` per singles side (rankings feed
  is ~150 deep, stamped onto draw players by athlete id); top-10 ATP/WTA). Also
  stamps `o` = [P(a),P(b)] match-winner prices from Polymarket's public gamma API
  (tag_slug=tennis; the winner market is the one whose question == event title —
  events also carry handicap/set side markets; matched to our matches by surname(s)
  per side, ambiguous ⇒ skipped; fail-safe). Shown as % on upcoming matches with a
  not-betting-advice disclaimer. NO head-to-head data exists in any of our free
  sources (ESPN summary endpoint 404s for tennis) — don't fabricate one and append-only `champions.json` (evergreen roll
  of honour — the feed only carries current events, this file is the site's permanent
  memory; 2023–2025 singles seeded from public record).
- `build_highlights.py` → `highlights.json` (ESPN match id → {yt, w, l, sc, dr, rd, d, sl},
  singles only). The match context is stored WITH the clip on purpose: the live feed drops
  a Slam days after it ends, so without it the 🎬 gallery would go blank between
  tournaments. Like champions.json, this file is the site's memory — renderHLGal()
  prefers live match data when a Slam is running and falls back to the stored copy.
  Scrapes the Slam's official channel /videos page (ytInitialData → lockupViewModel),
  matches titles by both players' last names + "Highlights" (short-form preferred over
  "Extended"), verifies EVERY id via YouTube oEmbed: `author_url` must equal the
  official channel URL (author_name is spoofable — learned on worldcup2026).
  Merge-only, fail-safe; runs in CI after the fetch with `|| true` (ok if YouTube
  blocks runners — entries can also be filled by hand). Official handles verified:
  @AustralianOpen · @RolandGarros · @Wimbledon · @usopen.
- `editions.json` — completed editions, QF onward, every draw (auto-captured by
  fetch_data.update_editions when both singles finals are done; backfill past Slams
  with `build_editions.py <YYYYMMDD final-weekend dates>` — ESPN scoreboard accepts
  `?dates=` for historical snapshots). Powers the ✓ Completed four-majors cards
  ("how it was won" panel) and backfilled 2026 AO/RG into champions.json.
  NOTE: ESPN spells it "Roland Garros" (no hyphen) — match slams by normSlam().
- Player photos: ESPN full-size headshots exist for only ~1/4 of draw players, so
  `build_photos.py` → `photos.json` fills the gap with freely licensed Wikimedia Commons
  photos (user asked for this 2026-09-12). Identity is never guessed: Wikidata's
  "ESPN.com tennis player ID" (P11585) must equal the ESPN id, else exactly one Wikidata
  tennis player (Q10833314) with that exact English name — otherwise skipped. Credit
  (author + licence) shows in the photo lightbox; CC BY/BY-SA require it — keep it.
  Doubles sides carry `ids` (one per partner) and get two faces. No photo ⇒ initials chip.
  Players with no photo (`checked`) are re-looked-up once per new Slam (`slam` key).
  Don't add photo sources without a licence (ATP/WTA/agency images are not free).
- `.github/workflows/update-data.yml` — every 30 min, SHA-pinned, rebase-before-push,
  fail-safe (never overwrites good data with an empty fetch).

## Data source (free, no key, unofficial)
ESPN: `https://site.api.espn.com/apis/site/v2/sports/tennis/{atp|wta}/{scoreboard|rankings}`
- A Slam's `events[].groupings[]` = the 5 draws (MS/WS/MD/WD/XD), each competition has
  `competitors[].linescores` (sets), `.winner`, `round.displayName`, `status.type`.
- Player country: `athlete.flag.href` ends `/<3-letter>.png`, `flag.alt` = country name.
- `event.major` flags Slams; `previousWinners` = last year's champions.
- Unofficial ⇒ could change; fetch script fails safe and the page degrades gracefully.

## Conventions (learned on the sibling project — follow them)
- **Edit `index.html` with Python `str.replace`, never the Edit tool** (Edit corrupts
  quotes to Unicode curly quotes in big HTML files). After every edit:
  `python3 -c "import re;h=open('index.html').read();m=re.search(r'<script>(.*?)</script>',h,re.S);open('/tmp/gs.js','w').write(m.group(1))" && node --check /tmp/gs.js`
- Never fabricate sports data (champions, rankings, dates) — fetch it or verify it;
  unknown ⇒ show "TBA"/nothing.
- Verify UI changes in a real browser before committing (local: `python3 -m http.server 4600`).
- No PII, no personal identity anywhere public; commit author is the GitHub noreply alias.
- Slam dates are static in `SLAMS[].eds` — extend with each year's announced dates
  (AO ausopen.com · RG rolandgarros.com · W wimbledon.com/en_GB/atoz/dates.html · USO usopen.org).

## Roadmap
1. Extend `SLAMS[].eds` with 2028 dates when announced.
2. Live-scores freshness — ADDRESSED client-side, see refreshLive() in index.html.
   GitHub's cron fires ~6x/day, not 48, so during a Slam the build can be hours behind
   and a finished match still reads "In Progress" (three were wrong on 2026-09-09).
   The page now asks ESPN itself: every 3 min while a match is in progress, otherwise
   only when the build is >45 min old, and never while the tab is hidden — the tennis
   scoreboard returns the WHOLE draw (~1.7MB, `?dates=` does not narrow it), so it is
   only fetched when it would actually help. Merged by match id, and a match whose
   feed-side names no longer match the stored ones is SKIPPED rather than guessed.
   It merges START TIME and COURT as well as scores — the order-of-play view is made
   entirely of those two, and a 15-minute reschedule of the 2026 US Open women's final
   sat wrong on the page (and in its GCal/.ics links) until the next build. Single-flight:
   the freshness gate is read before the await, so without a guard a tab-switch landing
   mid-fetch starts a second 1.7MB download. #upd has ONE writer (stampUpd) so the
   "scores may be delayed" warning can still re-appear after a successful refresh.
   An external pinger + repo-scoped token would still give a fresher committed build,
   but is no longer needed for correct scores on screen.

DONE: bracket view (QF onward, 🏆 Bracket chip — QFs ordered by deriving which
pair feeds each semi from player names, not feed order); order-of-play "today"
view (grouped by court, in playing order).
Views are linkable: #bracket, #today, #all-days, #mens-singles … (hashView() in index.html;
a hash beats the order-of-play default).
