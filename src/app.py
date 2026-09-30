"""
The app controller: owns settings/cache, builds the layout, and refreshes sources.

Layout:
  wide screens (tablet)  -> sidebar always visible on the left + feed
  narrow screens (phone) -> top bar with a menu button that opens the sidebar
"""

import asyncio
import time
from datetime import datetime

import flet as ft

from core.http import make_client
from core.source import Source
from core.storage import Cache, JsonFile, Settings
from sources import create_sources
from ui.section import Section
from ui.settings import open_settings
from ui.sidebar import build_sidebar

WIDE_SCREEN = 900      # px: from here on the sidebar is always shown
MAX_FEED_WIDTH = 1000  # px: keep lines readable on big tablets
FEED_TOP = 4
FEED_SPACING = 26

THEMES = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.settings = Settings()
        self.cache = Cache()
        self.state = JsonFile("state.json", {"expanded": {}, "last_visit": 0})
        self.client = make_client()
        self.launcher = ft.UrlLauncher()

        # Remember when you were here last, to mark new headlines.
        self.previous_visit = self.state.data["last_visit"]
        self.state.data["last_visit"] = time.time()
        self.state.save()

        self.sources: list[Source] = create_sources()
        self.sections = {s.id: Section(s, self) for s in self.sources}
        self.wide: bool | None = None
        self.feed: ft.Column | None = None

    # ------------------------------------------------------------ startup

    async def start(self):
        page = self.page
        page.title = "Morning"
        page.padding = 0
        page.spacing = 0
        seed = ft.Colors.INDIGO
        page.theme = ft.Theme(color_scheme_seed=seed)
        page.dark_theme = ft.Theme(color_scheme_seed=seed)
        page.theme_mode = THEMES.get(self.settings["theme"], ft.ThemeMode.SYSTEM)
        page.on_resize = self._on_resize
        page.on_view_pop = self._on_view_pop
        page.on_app_lifecycle_state_change = self._on_lifecycle

        for section in self.sections.values():
            section.extras.controls = section.source.header_extras(self)
            section.show_cached()  # instant: show yesterday's data while loading
        self._build_layout()
        page.update()

        page.run_task(self._tick_status_labels)
        await self.refresh_stale()

    # ------------------------------------------------------------ layout

    def _page_width(self) -> float:
        return self.page.width or 400

    def _build_layout(self):
        page = self.page
        self.wide = self._page_width() >= WIDE_SCREEN
        self.greeting = self._greeting()
        # Remember every block's rendered height, so the sidebar can compute where
        # each section starts and scroll there.
        self.heights: dict[str, float] = {}
        blocks = [("_greeting", self.greeting)] + [(sid, s.control) for sid, s in self.sections.items()]
        for block_id, control in blocks:
            control.on_size_change = self._remember_height(block_id)
        self.feed = ft.Column(
            [ft.Container(height=FEED_TOP)]
            + [control for _, control in blocks]
            + [ft.Container(height=40)],
            spacing=FEED_SPACING,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._apply_feed_width()
        page.controls.clear()
        if self.wide:
            page.appbar = None
            page.drawer = None
            page.controls.append(
                ft.Row([build_sidebar(self), ft.VerticalDivider(width=1), self.feed], expand=True, spacing=0)
            )
        else:
            page.appbar = ft.AppBar(
                leading=ft.IconButton(ft.Icons.MENU_ROUNDED, on_click=self._open_drawer),
                title=ft.Text("Morning", weight=ft.FontWeight.BOLD),
                actions=[ft.IconButton(ft.Icons.SETTINGS_ROUNDED, on_click=lambda e: self.open_settings())],
            )
            page.drawer = ft.NavigationDrawer(controls=[build_sidebar(self, height=page.height)])
            page.controls.append(self.feed)

    def _apply_feed_width(self):
        """Centered feed: full width on phones, at most MAX_FEED_WIDTH on big screens."""
        available = self._page_width() - (272 if self.wide else 0)
        width = min(available - 32, MAX_FEED_WIDTH)
        self.greeting.width = width
        for section in self.sections.values():
            section.control.width = width

    def _greeting(self) -> ft.Control:
        hour = datetime.now().hour
        hello = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"

        async def refresh_all(e):
            await self.refresh_all()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column([
                        ft.Text(hello, size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        ft.Text(datetime.now().strftime("%A, %d %B %Y"), size=14,
                                color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE)),
                    ], spacing=2, expand=True),
                    ft.FilledButton(
                        "Refresh all",
                        icon=ft.Icons.REFRESH_ROUNDED,
                        on_click=refresh_all,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.with_opacity(0.22, ft.Colors.WHITE),
                            color=ft.Colors.WHITE,
                            shape=ft.RoundedRectangleBorder(radius=14),
                            padding=ft.Padding.symmetric(horizontal=16, vertical=14),
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=22,
            border_radius=24,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[ft.Colors.INDIGO_400, ft.Colors.DEEP_PURPLE_400, ft.Colors.PINK_300],
            ),
        )

    async def _on_resize(self, e):
        if (self._page_width() >= WIDE_SCREEN) != self.wide:
            self._build_layout()
        else:
            self._apply_feed_width()
            if self.page.drawer:
                self.page.drawer.controls = [build_sidebar(self, height=self.page.height)]
        self.page.update()

    async def _open_drawer(self, e):
        await self.page.show_drawer()

    def _remember_height(self, block_id: str):
        def handler(e):
            self.heights[block_id] = e.height
        return handler

    async def jump_to(self, source_id: str):
        if not self.wide:
            await self.page.close_drawer()
        # Section start = top padding + heights of everything above it (+ spacing).
        offset = FEED_TOP + FEED_SPACING + self.heights.get("_greeting", 0) + FEED_SPACING
        for sid in self.sections:
            if sid == source_id:
                break
            offset += self.heights.get(sid, 0) + FEED_SPACING
        await self.feed.scroll_to(offset=max(0, offset - 8), duration=500,
                                  curve=ft.AnimationCurve.EASE_IN_OUT)

    # ------------------------------------------------------------ refreshing

    async def refresh(self, source: Source):
        section = self.sections[source.id]
        if section.loading:
            return
        section.set_loading(True)
        self.page.update()
        try:
            data = await source.fetch(self)
            self.cache.put(source.id, data)
            section.show_data()
        except Exception as ex:  # network down, site changed... keep the old data
            section.show_error(f"{type(ex).__name__}: {ex}")
        finally:
            section.set_loading(False)
            section.update_status()
            self.page.update()

    async def refresh_by_id(self, source_id: str):
        await self.refresh(self.sections[source_id].source)

    async def refresh_all(self):
        await asyncio.gather(*(self.refresh(s) for s in self.sources))

    async def refresh_stale(self):
        """Refresh every source whose data is older than its setting (or missing)."""
        stale = []
        for s in self.sources:
            age = self.cache.age_minutes(s.id)
            if age is None or age >= self.settings["refresh_minutes"].get(s.id, 30):
                stale.append(s)
        await asyncio.gather(*(self.refresh(s) for s in stale))

    async def _on_lifecycle(self, e):
        # Coming back to the app (e.g. next morning) -> refresh what is old.
        if e.state == ft.AppLifecycleState.RESUME:
            for section in self.sections.values():
                section.update_status()
            self.page.update()
            await self.refresh_stale()

    async def _tick_status_labels(self):
        """Keep 'Updated x min ago' labels honest. Only text changes - no downloads."""
        while True:
            await asyncio.sleep(60)
            for section in self.sections.values():
                if not section.loading:
                    section.update_status()
            self.page.update()

    # ------------------------------------------------------------ helpers used by sources/UI

    def is_expanded(self, source_id: str, item_id: str) -> bool:
        return item_id in self.state.data["expanded"].get(source_id, [])

    def set_expanded(self, source_id: str, item_id: str, expanded: bool):
        items = self.state.data["expanded"].setdefault(source_id, [])
        if expanded and item_id not in items:
            items.append(item_id)
        elif not expanded and item_id in items:
            items.remove(item_id)
        del items[:-500]  # only remember the last 500
        self.state.save()

    def is_new_since_last_visit(self, when: datetime) -> bool:
        return bool(self.previous_visit) and when.timestamp() > self.previous_visit

    def open_url(self, url: str):
        self.page.run_task(self.launcher.launch_url, url)

    def is_dark(self) -> bool:
        mode = self.settings["theme"]
        if mode == "system":
            return self.page.platform_brightness == ft.Brightness.DARK
        return mode == "dark"

    def set_theme(self, mode: str):
        self.settings["theme"] = mode
        self.page.theme_mode = THEMES[mode]
        self.page.update()

    def rerender_all(self):
        for section in self.sections.values():
            section.rerender()
        self.page.update()

    def open_settings(self):
        open_settings(self)

    def push_view(self, view: ft.View):
        self.page.views.append(view)
        self.page.update()

    async def _on_view_pop(self, e):
        if len(self.page.views) > 1:
            self.page.views.pop()
            self.page.update()
