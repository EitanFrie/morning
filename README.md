# Morning ☀

A personal morning news feed for Android phone & tablet, written in Python with [Flet](https://flet.dev).
No server: the app itself downloads and cleans up the sites.

| Section | Source | How |
|---|---|---|
| **מבזקים** | inn.co.il/flashes | The site's own JSON API — last N hours (setting), tap a headline to expand (remembered) |
| **NBA** | nba.com | Scoreboard + every box score downloaded together; tap a game for its box score |
| **חדשות מדע** | davidson.org.il | Latest 3 (or 6) articles, opened in a clean reader view |

## Run it on the computer

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python src\main.py
```

To preview in a browser instead: set `MORNING_WEB=1` first (then open http://localhost:8550).
To test NBA on a day with games: set `NBA_DAY=2026-04-10`.

## Get it on the phone

1. Push this repo to GitHub.
2. Create a version tag: `git tag v0.1.0` then `git push --tags`.
   GitHub Actions builds the APK (≈10 min) and attaches it to a Release.
3. On the phone install **Obtainium** (from GitHub/F-Droid), "Add app" → paste the repo URL.
   It installs the APK and will offer every new version you tag.

## Code map

```
src/
  main.py                 entry point
  app.py                  layout, refresh logic, auto-refresh on open/resume
  core/
    source.py             the plugin interface (fetch + render)
    storage.py            settings.json / cache.json / state.json
    http.py, text.py      download + HTML cleaning helpers
  sources/
    __init__.py           list of sources shown in the feed
    inn_flashes.py        news flashes
    nba.py                scores + box scores
    davidson_science.py   science articles
  ui/
    widgets.py            shared design (cards, pills, buttons, skeleton loaders)
    section.py            section header + refresh button + loading states
    sidebar.py, settings.py, reader.py, boxscore.py
```

## Adding a new site

1. Create `src/sources/my_site.py` with a class extending `Source`:
   - `fetch(app)` → download + parse, return plain JSON-able data (it is cached)
   - `render(data, app)` → build the Flet controls
2. Add it to `create_sources()` in `src/sources/__init__.py`.
3. Add its default refresh time in `DEFAULT_SETTINGS["refresh_minutes"]` (`core/storage.py`).

If a site changes its layout, only that site's file needs fixing — the other sections keep working
and the broken one shows the last cached data with an "Offline" note.
