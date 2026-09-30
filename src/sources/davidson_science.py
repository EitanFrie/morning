"""
Davidson Institute science news (https://davidson.org.il/read-experience/sciencenews/).

No API, so we read the HTML:
  - the list page gives the latest article cards (title, image, excerpt, author...)
  - each article page is reduced to title / subtitle / paragraphs / images,
    and shown in our own clean reader view.
The latest 6 articles are downloaded on refresh, so opening one is instant.
"""

import asyncio

import flet as ft
from bs4 import BeautifulSoup

from core.source import Source
from core.text import clean
from ui.reader import open_reader
from ui.widgets import card, fs, pill

LIST_URL = "https://davidson.org.il/read-experience/sciencenews/"
MAX_ARTICLES = 6


class DavidsonScience(Source):
    id = "science"
    title = "חדשות מדע"
    subtitle = "מכון דוידסון"
    icon = ft.Icons.SCIENCE_ROUNDED
    color = ft.Colors.TEAL_600

    async def fetch(self, app):
        response = await app.client.get(LIST_URL)
        response.raise_for_status()
        articles = parse_list(response.text)[:MAX_ARTICLES]
        if not articles:
            raise ValueError("no articles found - the site layout may have changed")

        # Download all article pages at the same time.
        pages = await asyncio.gather(
            *(app.client.get(a["url"]) for a in articles), return_exceptions=True
        )
        for article, page in zip(articles, pages):
            ok = not isinstance(page, Exception) and page.status_code == 200
            article["content"] = parse_article(page.text) if ok else None
        return {"articles": articles}

    # ------------------------------------------------------------------ UI

    def render(self, data, app):
        count = app.settings["science_count"]
        articles = data["articles"][:count]
        cards = [
            ft.Container(_article_card(a, app), col={"xs": 12, "md": 6, "xl": 4})
            for a in articles
        ]
        more = count < len(data["articles"])

        def toggle_count(e):
            app.settings["science_count"] = 6 if more else 3
            app.sections[self.id].rerender()
            app.page.update()

        toggle = ft.TextButton(
            f"הצג {len(data['articles'])} כתבות" if more else "הצג פחות",
            icon=ft.Icons.EXPAND_MORE_ROUNDED if more else ft.Icons.EXPAND_LESS_ROUNDED,
            on_click=toggle_count,
        )
        return ft.Column(
            [ft.ResponsiveRow(cards, spacing=14, run_spacing=14), ft.Row([toggle], alignment=ft.MainAxisAlignment.CENTER)],
            rtl=True,
            spacing=6,
        )


def _article_card(article: dict, app) -> ft.Control:
    meta = " · ".join(x for x in [article.get("author"), article.get("date"), article.get("reading_time")] if x)
    parts: list[ft.Control] = []
    if article.get("image"):
        parts.append(
            ft.Image(src=article["image"], height=170, fit=ft.BoxFit.COVER,
                     width=float("inf"), fade_in_animation=ft.Animation(300))
        )
    parts.append(
        ft.Container(
            padding=16,
            content=ft.Column(
                [
                    ft.Row([pill(c, ft.Colors.TEAL_600) for c in article.get("categories", [])[:2]],
                           wrap=True, spacing=6),
                    ft.Text(article["title"], size=fs(app, 18), weight=ft.FontWeight.BOLD),
                    ft.Text(article.get("excerpt", ""), size=fs(app, 14), max_lines=3,
                            overflow=ft.TextOverflow.ELLIPSIS, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(meta, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                spacing=8,
            ),
        )
    )
    return card(ft.Column(parts, spacing=0), padding=0, on_click=lambda e: open_reader(app, article))


# ---------------------------------------------------------------- parsing


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    articles, seen = [], set()
    for item in soup.select("div.item"):
        link = item.select_one("a.item__link-post")
        title = item.select_one(".item__title")
        if not link or not title or link["href"] in seen:
            continue
        seen.add(link["href"])
        image = item.select_one("img.item__img")
        author = item.select_one(".authors .name")
        date = item.select_one(".date__text")
        reading = item.select_one(".reading-time")
        excerpt = item.select_one(".item__excerpt")
        articles.append(
            {
                "url": link["href"],
                "title": clean(title.get_text()),
                "excerpt": clean(excerpt.get_text()) if excerpt else "",
                "image": image.get("src") if image else None,
                "categories": [clean(c.get_text()) for c in item.select(".item__cat")],
                "author": clean(author.get_text()) if author else "",
                "date": clean(date.get_text()) if date else "",
                "reading_time": clean(reading.get_text()) if reading else "",
            }
        )
    return articles


def parse_article(html: str) -> dict:
    """Article page -> {"title", "subtitle", "image", "blocks": [...]}.
    A block is {"type": "p"|"h"|"li"|"quote", "text"} or {"type": "img", "src", "caption"}."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".article-main-content__title")
    subtitle = soup.select_one(".article-main-content__desc")
    og_image = soup.find("meta", property="og:image")

    blocks = []
    for part in soup.select(".article-text, .article-image-info"):
        if "article-image-info" in part.get("class", []):
            img = part.find("img")
            if img:
                src = img.get("data-src") or img.get("src")
                blocks.append({"type": "img", "src": src, "caption": clean(part.get_text(" "))})
            continue
        for el in part.find_all(["p", "h2", "h3", "h4", "li", "blockquote"]):
            if el.name == "p" and el.find_parent(["li", "blockquote"]):
                continue  # already included through its parent
            text = clean(el.get_text())
            if not text:
                continue
            kind = {"h2": "h", "h3": "h", "h4": "h", "li": "li", "blockquote": "quote"}.get(el.name, "p")
            blocks.append({"type": kind, "text": text})

    return {
        "title": clean(title.get_text()) if title else "",
        "subtitle": clean(subtitle.get_text()) if subtitle else "",
        "image": og_image.get("content") if og_image else None,
        "blocks": blocks,
    }
