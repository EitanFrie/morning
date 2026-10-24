"""
NBA news - only the hand-picked "featured" stories of https://www.nba.com/news
(the ones the site shows with big images), not the endless "latest" feed.

The page carries its data as JSON (Next.js __NEXT_DATA__): pageProps.features.
Each story's own page has the full text in article.contentFiltered (HTML), which we
download on refresh and show in the same reader as the science articles.
"""

import asyncio
from datetime import datetime

import flet as ft
from bs4 import BeautifulSoup

from core.http import next_data
from core.source import Source
from core.speech import ENGLISH
from core.text import clean
from ui.reader import open_article
from ui.player_tracker import SplitView, download_headshots, tracker_panel
from ui.widgets import empty_message, feed_row

NEWS_URL = "https://www.nba.com/news"


class NbaNews(Source):
    id = "nba_news"
    title = "NBA News"
    subtitle = "nba.com featured"
    icon = ft.Icons.FEED_ROUNDED
    color = ft.Colors.ORANGE_800  # a shade of the NBA window's orange
    fills_window = True           # players on top, news below, a draggable bar between them

    def __init__(self):
        self.editing = False      # player list in edit mode (add / remove)

    async def fetch(self, app):
        response = await app.client.get(NEWS_URL)
        response.raise_for_status()
        features = next_data(response.text)["props"]["pageProps"].get("features") or []
        stories = [
            {
                "url": f["permalink"],
                "title": clean(f.get("title") or ""),
                "excerpt": clean(f.get("excerpt") or ""),
                "date": (f.get("date") or "")[:10],
                "category": (((f.get("category") or {}).get("name") if isinstance(f.get("category"), dict)
                              else f.get("category")) or "").split(",")[0],
                "language": ENGLISH,
            }
            for f in features if f.get("permalink") and f.get("title")
        ]
        if not stories:
            raise ValueError("no featured stories found - the page layout may have changed")

        # Download every story's text now, so opening one is instant (and works offline).
        pages = await asyncio.gather(*(app.client.get(s["url"]) for s in stories),
                                     return_exceptions=True)
        for story, page in zip(stories, pages):
            ok = not isinstance(page, Exception) and page.status_code == 200
            story["content"] = parse_story(page.text) if ok else None
        players_day, players = await _tracked_player_lines(app)
        return {"stories": stories, "players": players, "players_day": players_day}

    def render(self, data, app):
        section = app.sections.get(self.id)
        scroll = section.scroller if section else (lambda c: ft.Column([c], scroll=ft.ScrollMode.AUTO, expand=True))

        count = app.settings["nba_news_count"]  # Settings > NBA News (default 3)
        stories = data["stories"][:count]
        news = (ft.Column([_story_row(s, app) for s in stories], spacing=0) if stories
                else empty_message(ft.Icons.FEED_ROUNDED, "No featured stories right now"))

        def toggle_edit():
            self.editing = not self.editing
            app.sections[self.id].rerender()
            app.page.update()

        players = tracker_panel(app, self.id, data, self.editing, toggle_edit)
        # Tapping a story opens it over the WHOLE window (both parts) - see open_article.
        return SplitView(scroll(players), scroll(news), app.settings["nba_split"],
                         on_ratio=lambda r: app.settings.__setitem__("nba_split", r))


async def _tracked_player_lines(app) -> tuple[str, dict]:
    """Last night's stats for the tracked players, found by their permanent NBA id.

    Day: the most recent one with finished games (tonight's if over, else the day before).
    1. Box scores of the games of the players' saved teams (few downloads).
    2. Anyone still not found (e.g. traded) -> the other finished games of that night too,
       and his saved team is updated when he turns up on a new one.
    Returns (day, {id: {"played": bool, "text": str, "team": code}}).
    """
    from datetime import timedelta

    from sources.nba import FINAL, LIVE, _fetch_box_score, _game_from_card, default_game_day

    tracked = app.settings["tracked_players"]
    if not tracked:
        return "", {}
    for day in (default_game_day(), default_game_day() - timedelta(days=1)):
        response = await app.client.get("https://www.nba.com/games", params={"date": day.isoformat()})
        response.raise_for_status()
        props = next_data(response.text)["props"]["pageProps"]
        cards = [c.get("cardData") or {} for m in (props.get("gameCardFeed") or {}).get("modules") or []
                 for c in m.get("cards") or []]
        games = [_game_from_card(c) for c in cards if c.get("gameId")]
        if any(g["status"] in (FINAL, LIVE) for g in games):
            break
    else:
        return "", {}

    started = [g for g in games if g["status"] in (FINAL, LIVE)]
    wanted = {str(p["id"]) for p in tracked}
    lines: dict[str, dict] = {}

    async def read(game_list):
        boxes = await asyncio.gather(*(_fetch_box_score(app, g["id"]) for g in game_list),
                                     return_exceptions=True)
        for box in boxes:
            if isinstance(box, Exception):
                continue
            for side in ("away", "home"):
                for p in box[side]["players"]:
                    pid = str(p["id"])
                    if pid not in wanted:
                        continue
                    if p["played"]:
                        text = (f'{p["pts"]} PTS · {p["reb"]} REB · {p["ast"]} AST · '
                                f'{p["min"]} MIN · FG {p["fg"]}')
                    else:
                        reason = (p.get("note") or "").split(" - ")[-1]
                        text = "Didn't play" + (f" ({reason})" if reason else "")
                    lines[pid] = {"played": p["played"], "text": text, "team": box[side]["code"]}

    teams = {p["team"] for p in tracked}
    first = [g for g in started if {g["away"]["code"], g["home"]["code"]} & teams]
    await read(first)
    if wanted - set(lines):  # someone not found on his saved team (traded?) - look everywhere
        await read([g for g in started if g not in first])

    # keep the saved team up to date (logo fallback + next time's first pass)
    changed = False
    for player in tracked:
        found = lines.get(str(player["id"]))
        if found and found["team"] and found["team"] != player["team"]:
            player["team"] = found["team"]
            changed = True
    if changed:
        app.settings["tracked_players"] = list(tracked)
    await download_headshots(app)
    return day.isoformat(), lines


def _story_row(story: dict, app) -> ft.Control:
    when = ""
    if story.get("date"):
        try:
            when = datetime.fromisoformat(story["date"]).strftime("%d/%m")
        except ValueError:
            pass
    meta = " · ".join(x for x in [story.get("category"), when] if x)
    return feed_row(app, story["title"], meta=meta or None, subtitle=story.get("excerpt"),
                    on_click=lambda e: open_article(app, "nba_news", story))


def parse_story(html: str) -> dict | None:
    """Story page -> {"title", "subtitle", "image", "blocks"} (same shape as science articles)."""
    try:
        article = next_data(html)["props"]["pageProps"]["article"]
    except (KeyError, ValueError):
        return None
    soup = BeautifulSoup(article.get("contentFiltered") or "", "html.parser")
    blocks = []
    for el in soup.find_all(["p", "h2", "h3", "h4", "li", "blockquote", "img"]):
        if el.name == "img":
            if el.get("src") and not el.find_parent("blockquote"):
                caption = el.find_parent("div")
                blocks.append({"type": "img", "src": el["src"],
                               "caption": clean(caption.get_text(" ")) if caption else ""})
            continue
        if el.name == "p" and el.find_parent(["li", "blockquote"]):
            continue
        text = clean(el.get_text())
        if not text:
            continue
        kind = {"h2": "h", "h3": "h", "h4": "h", "li": "li", "blockquote": "quote"}.get(el.name, "p")
        blocks.append({"type": kind, "text": text})
    image = article.get("featuredImage")
    if isinstance(image, str):  # the top photo is usually repeated as the first inline image
        blocks = [b for b in blocks if not (b["type"] == "img" and b["src"] == image)]
    author = (article.get("author") or {}).get("name", "") if isinstance(article.get("author"), dict) else ""
    return {
        "title": clean(article.get("title") or ""),
        "subtitle": clean(article.get("excerpt") or ""),
        "image": image if isinstance(image, str) else None,
        "author": author,
        "blocks": blocks,
    }
