# 🎾 Tennis Grand Slam Tracker

All four tennis majors in one place — dates, countdown, results for **every draw**
(men's & women's singles, men's & women's doubles, mixed), world top-10 rankings,
and official highlights. One self-contained page, free to run, no ads, no tracking.

**Sibling project:** the same architecture as [worldcup2026](https://github.com/danpune/worldcup2026)
— a static page on GitHub Pages fed by a scheduled fetch script committing a JSON snapshot.

## How it works

- `index.html` — the whole site (inline CSS + vanilla JS, no dependencies)
- `fetch_data.py` — pulls the scoreboard + rankings from ESPN's public tennis feed and
  writes `data.json`; run every 30 min by [`update-data.yml`](.github/workflows/update-data.yml).
  Fail-safe: never overwrites good data with an empty fetch.
- Slam dates are static in `index.html` (they're announced years ahead); calendar buttons
  generate Google Calendar links and downloadable `.ics` files client-side.

During a Slam the page shows every match with per-set scores as they complete; between
Slams it's a countdown, the season calendar, and the current top 10.

## Data sources & attribution

- Results, draws and rankings: ESPN's public tennis feed (unofficial; not affiliated)
- Schedules: the official tournament sites (ausopen.com, rolandgarros.com, wimbledon.com, usopen.org)
- Not affiliated with the ATP, WTA, ITF or any tournament

## Roadmap

- Per-match official highlight links during the US Open (same verified-official pattern
  as the World Cup project's `highlights.json`)
- Follow-a-player stars
- Draw bracket view (QF onward)
