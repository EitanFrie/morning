"""
One category "window" - fills the whole screen (one page of the feed).

    ┌──────────────────────────────────────────┐
    │ [←] badge  Title / status   extras   ↻  │  header
    │──────────────────────────────────────────│
    │  list of rows (scrolls inside the window)│  list layer
    │  …or a detail (box score / article) that │  detail layer, slides over the list
    │  covers only THIS window                 │
    └──────────────────────────────────────────┘

Scrolling past the top/bottom of the window moves to the previous/next window.
"""

from typing import TYPE_CHECKING

import flet as ft

from core.source import Source
from ui.widgets import RADIUS, RoundButton, error_box, fs, icon_badge, skeleton, time_ago

if TYPE_CHECKING:
    from app import App

OVERSCROLL_TO_SWITCH = 70  # px of "pulling" past the edge before switching window
HIDDEN = ft.Offset(1.05, 0)
SHOWN = ft.Offset(0, 0)


class Section:
    def __init__(self, source: Source, app: "App"):
        self.source = source
        self.app = app
        self.loading = False
        self.error: str | None = None
        self.detail_open = False
        self._pull = 0.0  # accumulated overscroll of the current gesture

        # ---- header ----
        self.status = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1,
                              overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER)
        self.title = ft.Text(source.title, size=fs(app, 20), weight=ft.FontWeight.BOLD,
                             text_align=ft.TextAlign.CENTER,
                             max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.back_button = ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, visible=False, tooltip="Back",
                                         on_click=lambda e: self.close_detail())
        self.badge = icon_badge(source.icon, source.color)
        self.extras = ft.Row(spacing=8, alignment=ft.MainAxisAlignment.CENTER, visible=False)
        self.detail_actions = ft.Row(spacing=0, tight=True, visible=False)
        self.refresh_button = RoundButton(ft.Icons.REFRESH_ROUNDED, on_click=self._on_refresh_click,
                                          tooltip="Refresh")
        # Two lines: [badge | centered title + status | actions], then the
        # section's own pickers (dates, commentator...) centered underneath.
        header = ft.Container(
            ft.Column([
                ft.Row(
                    [self.back_button, self.badge,
                     ft.Column([self.title, self.status], spacing=0, expand=True,
                               horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                     self.detail_actions, self.refresh_button],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.extras,
            ], spacing=8),
            padding=ft.Padding.only(left=14, right=12, top=12, bottom=10),
        )
        self.progress = ft.ProgressBar(height=2, visible=False)

        # ---- list layer ----
        self.body = ft.AnimatedSwitcher(
            content=skeleton(image=source.id != "inn"),
            duration=350,
            reverse_duration=150,
            transition=ft.AnimatedSwitcherTransition.FADE,
            switch_in_curve=ft.AnimationCurve.EASE_OUT,
        )
        self.list_layer = self._scroller(self.body)

        # ---- detail layer (slides in from the side, covers only this window) ----
        self.detail_layer = ft.Container(
            left=0, top=0, right=0, bottom=0,
            offset=HIDDEN,
            animate_offset=ft.Animation(320, ft.AnimationCurve.EASE_OUT_CUBIC),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        )

        self.window = ft.Container(
            content=ft.Column(
                [header, ft.Divider(height=1), self.progress,
                 ft.Stack([ft.Container(self.list_layer, left=0, top=0, right=0, bottom=0),
                           self.detail_layer], expand=True)],
                spacing=0,
            ),
            expand=True,
            border_radius=RADIUS,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

    # ---------------------------------------------------------------- scrolling

    def _scroller(self, content: ft.Control) -> ft.Column:
        """A scroll area inside the window that hands over to the next/previous
        window when you keep pulling at its end."""
        return ft.Column([content], scroll=ft.ScrollMode.AUTO, expand=True,
                         on_scroll=self._on_scroll, scroll_interval=30)

    async def _on_scroll(self, e: ft.OnScrollEvent):
        if e.event_type == ft.ScrollType.START:
            self._pull = 0
        elif e.event_type == ft.ScrollType.OVERSCROLL and e.overscroll:
            self._pull += e.overscroll
            if abs(self._pull) >= OVERSCROLL_TO_SWITCH:
                direction = 1 if self._pull > 0 else -1
                self._pull = 0
                await self.app.move_window(self.source.id, direction)

    # ---------------------------------------------------------------- detail

    def open_detail(self, title: str, content: ft.Control, actions: list[ft.Control] | None = None):
        """Show a box score / article inside this window only."""
        self.detail_layer.content = self._scroller(content)
        self.detail_layer.offset = SHOWN
        self.detail_open = True
        self.back_button.visible = True
        self.badge.visible = False
        self.extras.visible = False
        self.detail_actions.controls = actions or []
        self.detail_actions.visible = True
        self.title.value = title
        self.status.value = self.source.title
        self.status.color = ft.Colors.PRIMARY
        self.app.page.update()

    def set_detail_content(self, content: ft.Control):
        """Replace the detail (e.g. when an article finished downloading)."""
        if self.detail_open:
            self.detail_layer.content = self._scroller(content)
            self.app.page.update()

    def close_detail(self):
        self.detail_layer.offset = HIDDEN
        self.detail_open = False
        self.back_button.visible = False
        self.badge.visible = True
        self.extras.visible = bool(self.extras.controls)
        self.detail_actions.visible = False
        self.title.value = self.source.title
        self.update_status()
        self.app.page.update()

    # ---------------------------------------------------------------- state

    def _set_extras(self):
        self.extras.controls = self.source.header_extras(self.app)
        self.extras.visible = bool(self.extras.controls) and not self.detail_open

    def show_cached(self):
        """Render whatever is in the cache (instant, works offline)."""
        entry = self.app.cache.get(self.source.id)
        if entry:
            self._render(entry["data"])
        self.update_status()

    def rerender(self):
        self.title.size = fs(self.app, 20)
        self._set_extras()
        self.show_cached()

    def show_data(self):
        self.error = None
        self._set_extras()
        self.show_cached()

    def set_loading(self, loading: bool):
        self.loading = loading
        has_data = self.app.cache.get(self.source.id) is not None
        self.refresh_button.set_busy(loading)
        self.progress.visible = loading and has_data
        if loading and not has_data:
            self.body.content = skeleton(image=self.source.id != "inn")
        if loading and not self.detail_open:
            self.status.value = "Refreshing…"
            self.status.color = ft.Colors.PRIMARY

    def show_progress(self, title: str, note: str = ""):
        """A long download (e.g. the weekly Torah bundle): tell the user what's happening."""
        self.status.value = title
        self.status.color = ft.Colors.PRIMARY
        self.body.content = ft.Container(
            ft.Column([ft.ProgressRing(width=36, height=36),
                       ft.Text(title, size=16, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                       ft.Text(note, size=12, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER)],
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12, rtl=True),
            padding=40, alignment=ft.Alignment.CENTER,
        )
        self.app.page.update()

    def show_error(self, message: str):
        self.error = message
        if self.app.cache.get(self.source.id) is None:
            self.body.content = error_box(message, self._on_refresh_click)
        self.update_status()

    def update_status(self):
        if self.detail_open:
            return  # the header shows the detail's title meanwhile
        age = self.app.cache.age_minutes(self.source.id)
        if self.error:
            self.status.value = "Offline · " + (time_ago(age).lower() if age is not None else "no data")
            self.status.color = ft.Colors.ERROR
        else:
            self.status.value = time_ago(age)
            self.status.color = ft.Colors.ON_SURFACE_VARIANT

    def _render(self, data):
        try:
            self.body.content = self.source.render(data, self.app)
        except Exception as ex:  # a bug in one source must never break the whole app
            self.body.content = error_box(f"Display error: {ex}", self._on_refresh_click)

    async def _on_refresh_click(self, e=None):
        await self.app.refresh(self.source)
