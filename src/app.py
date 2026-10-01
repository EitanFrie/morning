"""
The app controller: owns settings/cache, builds the layout, and refreshes sources.

Layout:
  every category is a full-screen "window"; windows are stacked vertically and snap.
  wide screens (tablet)  -> sidebar always visible on the left
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

WIDE_SCREEN = 900  # px: from here on the sidebar is always shown
WINDOW_TRANSITION_MS = 850  # slow, gentle glide between categories
GUTTER = 45        # px: empty strip beside the windows, for scrolling between them

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
        self.current = 0        # index of the window on screen
        self._last_move = 0.0

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
        page.views[0].on_confirm_pop = self._on_back
        page.on_app_lifecycle_state_change = self._on_lifecycle

        for section in self.sections.values():
            section._set_extras()
            section.show_cached()  # instant: show yesterday's data while loading
        self._build_layout()
        page.update()

        page.run_task(self._tick_status_labels)
        await self.refresh_stale()

    # ------------------------------------------------------------ layout

    def _page_width(self) -> float:
        return self.page.width or 400

    def window_width(self) -> float:
        """Inner width of a category window (page minus sidebar, margins and side strip)."""
        sidebar = 272 if self._page_width() >= WIDE_SCREEN else 0
        return self._page_width() - sidebar - 10 - GUTTER - 2

    def _build_layout(self):
        """Every category is one full-screen window; the windows are stacked vertically
        and snap into place (a vertical PageView)."""
        page = self.page
        self.wide = self._page_width() >= WIDE_SCREEN
        self.pager = ft.PageView(
            controls=[self._window_page(s) for s in self.sections.values()],
            horizontal=False,
            selected_index=self.current,
            on_change=self._on_page_change,
            expand=True,
        )
        # Position dots in the empty strip on the side (tap one to jump there).
        self.dots = ft.Column(spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True)
        self._update_dots()
        feed = ft.Stack(
            [self.pager, ft.Container(self.dots, padding=ft.Padding.only(right=4))],
            alignment=ft.Alignment.CENTER_RIGHT,
            expand=True,
        )

        page.controls.clear()
        if self.wide:
            page.appbar = None
            page.drawer = None
            page.controls.append(
                ft.Row([build_sidebar(self), ft.VerticalDivider(width=1), feed], expand=True, spacing=0)
            )
        else:
            page.appbar = ft.AppBar(
                leading=ft.IconButton(ft.Icons.MENU_ROUNDED, on_click=self._open_drawer),
                title=ft.Text("Morning", weight=ft.FontWeight.BOLD),
                actions=[
                    ft.IconButton(ft.Icons.REFRESH_ROUNDED, tooltip="Refresh all", on_click=self._refresh_all_click),
                    ft.IconButton(ft.Icons.SETTINGS_ROUNDED, on_click=lambda e: self.open_settings()),
                ],
            )
            page.drawer = ft.NavigationDrawer(controls=[build_sidebar(self, height=page.height)])
            page.controls.append(feed)

    def _window_page(self, section: Section) -> ft.Control:
        # The empty strip on the side (GUTTER) belongs to the pager, not to the
        # window: dragging there always moves between categories.
        return ft.Container(
            section.window,
            padding=ft.Padding.only(left=10, top=10, bottom=10, right=GUTTER),
        )

    def _update_dots(self):
        def dot(i, section):
            active = i == self.current

            async def go(e):
                await self.go_to(i)

            return ft.Container(
                ft.Container(width=10, height=30 if active else 10, border_radius=5,
                             bgcolor=section.source.color if active else ft.Colors.OUTLINE_VARIANT,
                             animate=ft.Animation(250, ft.AnimationCurve.EASE_OUT)),
                padding=ft.Padding.symmetric(horizontal=12, vertical=5),
                on_click=go,
                tooltip=section.source.title,
            )

        self.dots.controls = [dot(i, s) for i, s in enumerate(self.sections.values())]

    async def _on_resize(self, e):
        if (self._page_width() >= WIDE_SCREEN) != self.wide:
            self._build_layout()
        elif self.page.drawer:
            self.page.drawer.controls = [build_sidebar(self, height=self.page.height)]
        self.page.update()

    async def _open_drawer(self, e):
        await self.page.show_drawer()

    async def _refresh_all_click(self, e):
        await self.refresh_all()

    # ------------------------------------------------------------ moving between windows

    async def go_to(self, index: int):
        index = max(0, min(index, len(self.sources) - 1))
        if index == self.current:
            return
        self.current = index
        self._update_dots()
        self.page.update()
        await self.pager.go_to_page(index, animation_duration=ft.Duration(milliseconds=WINDOW_TRANSITION_MS),
                                    animation_curve=ft.AnimationCurve.EASE_IN_OUT_CUBIC)

    async def move_window(self, source_id: str, direction: int):
        """Called when a window is scrolled past its end: go to the next/previous one."""
        index = list(self.sections).index(source_id)
        # Only the window on screen may switch, and only once per gesture - otherwise the
        # leftover momentum would carry on through the next window too.
        if index != self.current or time.monotonic() - self._last_move < 1.5:
            return
        self._last_move = time.monotonic()
        await self.go_to(index + direction)

    async def _on_page_change(self, e):
        self.current = e.control.selected_index
        self._last_move = time.monotonic()
        self._update_dots()
        self.page.update()

    async def jump_to(self, source_id: str):
        if not self.wide:
            await self.page.close_drawer()
        await self.go_to(list(self.sections).index(source_id))

    async def _on_back(self, e):
        """Android back button: close an open box score / article first."""
        section = list(self.sections.values())[self.current]
        if section.detail_open:
            section.close_detail()
            await e.control.confirm_pop(False)
        else:
            await e.control.confirm_pop(True)

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
