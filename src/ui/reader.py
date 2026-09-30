"""
Full-screen, distraction-free article reader.
Works with any source that provides {"title", "subtitle", "image", "blocks"}.
"""

from typing import TYPE_CHECKING

import flet as ft

from ui.widgets import fs, skeleton

if TYPE_CHECKING:
    from app import App

MAX_WIDTH = 720  # comfortable line length on tablets


def open_reader(app: "App", article: dict):
    """article = list-card data; article["content"] may be missing (not downloaded yet)."""
    body = ft.AnimatedSwitcher(content=skeleton(lines=8, with_image=True), duration=300)
    view = ft.View(
        route="/reader",
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text(article["title"], size=16, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            actions=[
                ft.IconButton(ft.Icons.OPEN_IN_NEW_ROUNDED, tooltip="Open on website",
                              on_click=lambda e: app.open_url(article["url"])),
            ],
        ),
        controls=[
            ft.ListView(
                [ft.Row([ft.Container(body, width=min(MAX_WIDTH, app.page.width or 400), padding=20)],
                        alignment=ft.MainAxisAlignment.CENTER)],
                expand=True,
            )
        ],
    )
    app.push_view(view)

    if article.get("content"):
        body.content = _article_body(app, article, article["content"])
        view.update()
    else:
        app.page.run_task(_download_and_show, app, article, body, view)


async def _download_and_show(app, article, body, view):
    from sources.davidson_science import parse_article  # only needed here

    try:
        response = await app.client.get(article["url"])
        response.raise_for_status()
        article["content"] = parse_article(response.text)
        body.content = _article_body(app, article, article["content"])
    except Exception as ex:
        body.content = ft.Text(f"Could not load the article: {ex}", color=ft.Colors.ERROR)
    view.update()


def _article_body(app, article: dict, content: dict) -> ft.Control:
    paragraph = ft.TextStyle(height=1.6)
    parts: list[ft.Control] = []

    if content.get("image"):
        parts.append(ft.Image(src=content["image"], border_radius=16, fit=ft.BoxFit.COVER,
                              width=float("inf"), fade_in_animation=ft.Animation(300)))
    parts.append(ft.Text(content.get("title") or article["title"], size=fs(app, 28),
                         weight=ft.FontWeight.BOLD, selectable=True))
    if content.get("subtitle"):
        parts.append(ft.Text(content["subtitle"], size=fs(app, 18),
                             color=ft.Colors.ON_SURFACE_VARIANT, selectable=True))
    meta = " · ".join(x for x in [article.get("author"), article.get("date"), article.get("reading_time")] if x)
    if meta:
        parts.append(ft.Text(meta, size=13, color=ft.Colors.PRIMARY))
    parts.append(ft.Divider(height=24))

    for block in content["blocks"]:
        kind = block["type"]
        if kind == "p":
            parts.append(ft.Text(block["text"], size=fs(app, 17), style=paragraph, selectable=True))
        elif kind == "h":
            parts.append(ft.Text(block["text"], size=fs(app, 21), weight=ft.FontWeight.BOLD))
        elif kind == "li":
            parts.append(ft.Text("•  " + block["text"], size=fs(app, 17), style=paragraph, selectable=True))
        elif kind == "quote":
            parts.append(ft.Container(
                ft.Text(block["text"], size=fs(app, 17), italic=True, style=paragraph),
                padding=ft.Padding.only(right=14),
                border=ft.Border(right=ft.BorderSide(3, ft.Colors.PRIMARY)),
            ))
        elif kind == "img" and block.get("src"):
            parts.append(ft.Column([
                ft.Image(src=block["src"], border_radius=12, fit=ft.BoxFit.CONTAIN, width=float("inf")),
                ft.Text(block.get("caption", ""), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=6))

    parts.append(ft.Container(height=40))
    return ft.Column(parts, spacing=14, rtl=True)
