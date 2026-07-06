# Tennis Grand Slam Tracker — project notes

LIVE: https://danpune.github.io/tennis-slams-tracker/ · repo `danpune/tennis-slams-tracker`
Separate project from `~/worldcup2026` (same playbook, deliberately independent).

## Architecture
- `index.html` — the entire site, self-contained (inline CSS + vanilla JS, system fonts,
  no dependencies, no cookies/tracking/keys). Sections: countdown → four-majors cards
  (multi-year `eds` list, auto-rollover, "dates TBA" fallback) → Catch-up brief →
  live-Slam results (5 draws × round chips + ⭐ Following filter) → follow box →
  roll of honour → top-10 → highlights links.
- `fetch_data.py` → `data.json` (current Slam, all draws, per-set scores, countries,
  ESPN match `id`s; top-10 ATP/WTA) and append-only `champions.json` (evergreen roll
  of honour — the feed only carries current events, this file is the site's permanent
  memory; 2023–2025 singles seeded from public record).
- `build_highlights.py` → `highlights.json` (ESPN match id → {yt}, singles only).
  Scrapes the Slam's official channel /videos page (ytInitialData → lockupViewModel),
  matches titles by both players' last names + "Highlights" (short-form preferred over
  "Extended"), verifies EVERY id via YouTube oEmbed: `author_url` must equal the
  official channel URL (author_name is spoofable — learned on worldcup2026).
  Merge-only, fail-safe; runs in CI after the fetch with `|| true` (ok if YouTube
  blocks runners — entries can also be filled by hand). Official handles verified:
  @AustralianOpen · @RolandGarros · @Wimbledon · @usopen.
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
1. Draw bracket view (QF onward) — the worldcup2026 bracket tree is a good starting point.
2. Order-of-play "today" view during Slams (tennis has no fixed kickoff times).
3. Extend `SLAMS[].eds` with 2028 dates when announced.
