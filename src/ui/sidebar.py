"""Sidebar: jump to a section, quick dark-mode switch, and settings at the bottom."""

from datetime import datetime
from typing import TYPE_CHECKING

import flet as ft

from ui.widgets import icon_badge

if TYPE_CHECKING:
    from app import App

WIDTH = 270


def _nav_item(icon, title: str, color, on_click, trailing: ft.Control | None = None) -> ft.Control:
    item = ft.Container(
        content=ft.Row(
            [ft.Icon(icon, color=color, size=22), ft.Text(title, size=15, weight=ft.FontWeight.W_500, expand=True)]
            + ([trailing] if trailing else []),
            spacing=14,
        ),
        padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        border_radius=14,
        ink=True,
        on_click=on_click,
        animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
    )

    def hover(e):
        item.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY) if e.data in (True, "true") else None
        item.update()

    item.on_hover = hover
    return item


def build_sidebar(app: "App", height: float | None = None) -> ft.Control:
    def jump(source_id):
        async def handler(e):
            await app.jump_to(source_id)
        return handler

    async def toggle_dark(e):
        app.set_theme("dark" if e.control.value else "light")

    header = ft.Row(
        [
            icon_badge(ft.Icons.WB_SUNNY_ROUNDED, ft.Colors.AMBER_700, size=44),
            ft.Column([
                ft.Text("Morning", size=22, weight=ft.FontWeight.BOLD),
                ft.Text(datetime.now().strftime("%A, %d %B"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=0),
        ],
        spacing=12,
    )

    sources = [
        _nav_item(s.icon, s.title, s.color, jump(s.id)) for s in app.sources
    ]

    bottom = [
        ft.Divider(),
        _nav_item(
            ft.Icons.DARK_MODE_ROUNDED, "Dark mode", ft.Colors.ON_SURFACE_VARIANT, None,
            trailing=ft.Switch(value=app.is_dark(), on_change=toggle_dark),
        ),
        _nav_item(ft.Icons.SETTINGS_ROUNDED, "Settings", ft.Colors.ON_SURFACE_VARIANT,
                  lambda e: app.open_settings()),
    ]

    return ft.Container(
        content=ft.Column(
            [header, ft.Container(height=12), *sources, ft.Container(expand=True), *bottom],
            spacing=4,
        ),
        width=WIDTH,
        height=height,
        padding=ft.Padding.only(left=14, right=14, top=24, bottom=16),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
    )
