"""
Distraction-free article reader. Opens INSIDE its category window (covering only it).
Works with any source that provides {"title", "subtitle", "image", "blocks"}.
"""

from typing import TYPE_CHECKING

import flet as ft

from ui.widgets import fs, skeleton

if TYPE_CHECKING:
    from app import App

MAX_WIDTH = 720  # comfortable line length on tablets


def open_article(app: "App", section_id: str, article: dict):
    """article = list-row data; article["content"] may be missing (not downloaded yet)."""
    section = app.sections[section_id]
    actions = [ft.IconButton(ft.Icons.OPEN_IN_NEW_ROUNDED, tooltip="Open on website",
                             on_click=lambda e: app.open_url(article["url"]))]
    if article.get("content"):
        section.open_detail(article["title"], _article_body(app, article, article["content"]), actions)
    else:
        section.open_detail(article["title"], skeleton(rows=8), actions)
        app.page.run_task(_download_and_show, app, section, article)


async def _download_and_show(app, section, article):
    from sources.davidson_science import parse_article  # only needed here

    try:
        response = await app.client.get(article["url"])
        response.raise_for_status()
        article["content"] = parse_article(response.text)
        section.set_detail_content(_article_body(app, article, article["content"]))
    except Exception as ex:
        section.set_detail_content(ft.Text(f"Could not load the article: {ex}", color=ft.Colors.ERROR))


def _article_body(app, article: dict, content: dict) -> ft.Control:
    paragraph = ft.TextStyle(height=1.6)
    parts: list[ft.Control] = []
    # Fit the window: full window width on a phone, at most MAX_WIDTH on a tablet.
    width = min(MAX_WIDTH, app.window_width() - 8)
    image_width = width - 32  # inside the 16 px padding on both sides

    if content.get("image"):
        parts.append(_zoomable(app, content["image"], image_width, height=220, cover=True))
    parts.append(ft.Text(content.get("title") or article["title"], size=fs(app, 26),
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
                _zoomable(app, block["src"], image_width),
                ft.Text(block.get("caption", ""), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=6))

    parts.append(ft.Container(height=40))
    return ft.Row(
        [ft.Container(ft.Column(parts, spacing=14, rtl=True), width=width, padding=16)],
        alignment=ft.MainAxisAlignment.CENTER,
    )


def _zoomable(app, src: str, width: float, height: float | None = None, cover=False) -> ft.Control:
    """An article image sized to the window; tap it to open the full-screen zoom view."""
    return ft.Container(
        ft.Image(src=src, width=width, height=height, fit=ft.BoxFit.COVER if cover else ft.BoxFit.FIT_WIDTH,
                 fade_in_animation=ft.Animation(300),
                 error_content=ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, color=ft.Colors.OUTLINE)),
        border_radius=12,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        on_click=lambda e: open_image(app, src),
        tooltip="Tap to zoom",
    )


def open_image(app, src: str):
    """Full-screen image: pinch to zoom, drag to move. Back closes it."""
    view = ft.View(
        route="/image",
        padding=0,
        bgcolor=ft.Colors.BLACK,
        appbar=ft.AppBar(bgcolor=ft.Colors.BLACK, color=ft.Colors.WHITE),
        controls=[
            ft.InteractiveViewer(
                ft.Image(src=src, fit=ft.BoxFit.CONTAIN),
                min_scale=1,
                max_scale=8,
                boundary_margin=ft.Margin.all(40),
                expand=True,
            )
        ],
    )
    app.push_view(view)
