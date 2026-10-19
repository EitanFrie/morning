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
from ui.widgets import empty_message, feed_row

NEWS_URL = "https://www.nba.com/news"


class NbaNews(Source):
    id = "nba_news"
    title = "NBA News"
    subtitle = "nba.com featured"
    icon = ft.Icons.FEED_ROUNDED
    color = ft.Colors.ORANGE_800  # a shade of the NBA window's orange

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
        return {"stories": stories}

    def render(self, data, app):
        if not data["stories"]:
            return empty_message(ft.Icons.FEED_ROUNDED, "No featured stories right now")
        count = app.settings["nba_news_count"]  # Settings > NBA News (default 5)
        return ft.Column([_story_row(s, app) for s in data["stories"][:count]], spacing=0)


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
