"""
One section of the feed: header (badge, title, "updated x ago", refresh button)
plus a body that smoothly switches between skeleton / content / error.
"""

from typing import TYPE_CHECKING

import flet as ft

from core.source import Source
from ui.widgets import RoundButton, error_box, fs, icon_badge, skeleton, time_ago

if TYPE_CHECKING:
    from app import App


class Section:
    def __init__(self, source: Source, app: "App"):
        self.source = source
        self.app = app
        self.loading = False
        self.error: str | None = None

        self.status = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.refresh_button = RoundButton(
            ft.Icons.REFRESH_ROUNDED, on_click=self._on_refresh_click, tooltip="Refresh"
        )
        self.extras = ft.Row(spacing=4, tight=True)
        # Thin bar under the header while refreshing data that is already shown.
        self.progress = ft.ProgressBar(height=3, border_radius=3, visible=False)
        self.body = ft.AnimatedSwitcher(
            content=skeleton(with_image=source.id == "science"),
            duration=350,
            reverse_duration=150,
            transition=ft.AnimatedSwitcherTransition.FADE,
            switch_in_curve=ft.AnimationCurve.EASE_OUT,
        )

        self.title = ft.Text(source.title, size=fs(app, 21), weight=ft.FontWeight.BOLD)
        header = ft.Row(
            [
                icon_badge(source.icon, source.color),
                ft.Column([self.title, self.status], spacing=0, expand=True),
                self.extras,
                self.refresh_button,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.control = ft.Container(
            content=ft.Column([header, self.progress, self.body], spacing=12),
            padding=ft.Padding.only(bottom=8),
        )

    # ---- state changes -------------------------------------------------

    def show_cached(self):
        """Render whatever is in the cache (instant, works offline)."""
        entry = self.app.cache.get(self.source.id)
        if entry:
            self._render(entry["data"])
        self.update_status()

    def rerender(self):
        self.title.size = fs(self.app, 21)
        self.extras.controls = self.source.header_extras(self.app)
        self.show_cached()

    def set_loading(self, loading: bool):
        self.loading = loading
        has_data = self.app.cache.get(self.source.id) is not None
        self.refresh_button.set_busy(loading)
        self.progress.visible = loading and has_data
        if loading and not has_data:
            self.body.content = skeleton(with_image=self.source.id == "science")
        if loading:
            self.status.value = "Refreshing…"
            self.status.color = ft.Colors.PRIMARY

    def show_error(self, message: str):
        self.error = message
        if self.app.cache.get(self.source.id) is None:
            self.body.content = error_box(message, self._on_refresh_click)
        self.update_status()

    def update_status(self):
        age = self.app.cache.age_minutes(self.source.id)
        if self.error:
            self.status.value = "Offline · " + (time_ago(age).lower() if age is not None else "no data")
            self.status.color = ft.Colors.ERROR
        else:
            self.status.value = time_ago(age)
            self.status.color = ft.Colors.ON_SURFACE_VARIANT

    # ---- internals -------------------------------------------------------

    def _render(self, data):
        try:
            self.body.content = self.source.render(data, self.app)
        except Exception as ex:  # a bug in one source must never break the whole app
            self.body.content = error_box(f"Display error: {ex}", self._on_refresh_click)

    def show_data(self):
        self.error = None
        self.extras.controls = self.source.header_extras(self.app)
        self.show_cached()

    async def _on_refresh_click(self, e=None):
        await self.app.refresh(self.source)
