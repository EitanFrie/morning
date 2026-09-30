"""Settings screen. Every change is saved immediately."""

from typing import TYPE_CHECKING

import flet as ft

from core.storage import data_dir
from ui.widgets import card

if TYPE_CHECKING:
    from app import App

APP_VERSION = "0.1.0"
REFRESH_CHOICES = [5, 10, 15, 30, 60, 180, 360, 720, 1440]


def _label(minutes: int) -> str:
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h"


def _group(title: str, icon, *rows: ft.Control) -> ft.Control:
    return card(
        ft.Column(
            [ft.Row([ft.Icon(icon, color=ft.Colors.PRIMARY), ft.Text(title, size=17, weight=ft.FontWeight.BOLD)]),
             *rows],
            spacing=14,
        ),
        padding=20,
    )


def _row(label: str, control: ft.Control, hint: str | None = None) -> ft.Control:
    text = [ft.Text(label, size=15)]
    if hint:
        text.append(ft.Text(hint, size=12, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Row([ft.Column(text, spacing=0, expand=True), control],
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)


def open_settings(app: "App"):
    s = app.settings

    # --- appearance ---
    def on_theme(e):
        app.set_theme(e.control.selected[0])

    theme = ft.SegmentedButton(
        selected=[s["theme"]],
        segments=[
            ft.Segment("system", label=ft.Text("Auto"), icon=ft.Icon(ft.Icons.BRIGHTNESS_AUTO_ROUNDED)),
            ft.Segment("light", label=ft.Text("Light"), icon=ft.Icon(ft.Icons.LIGHT_MODE_ROUNDED)),
            ft.Segment("dark", label=ft.Text("Dark"), icon=ft.Icon(ft.Icons.DARK_MODE_ROUNDED)),
        ],
        on_change=on_theme,
    )

    def on_text_size(e):
        s["text_scale"] = float(e.control.selected[0])
        app.rerender_all()

    text_size = ft.SegmentedButton(
        selected=[str(s["text_scale"])],
        segments=[ft.Segment("0.9", label=ft.Text("S")), ft.Segment("1.0", label=ft.Text("M")),
                  ft.Segment("1.15", label=ft.Text("L"))],
        show_selected_icon=False,
        on_change=on_text_size,
    )

    # --- news flashes ---
    hours_text = ft.Text(f'{s["inn_hours_back"]} hours', weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY)

    def on_hours_change(e):
        hours_text.value = f"{int(e.control.value)} hours"
        hours_text.update()

    async def on_hours_done(e):
        s["inn_hours_back"] = int(e.control.value)
        await app.refresh_by_id("inn")

    hours = ft.Slider(min=1, max=24, divisions=23, value=s["inn_hours_back"], label="{value} h",
                      on_change=on_hours_change, on_change_end=on_hours_done)

    # --- science ---
    def on_science(e):
        s["science_count"] = int(e.control.selected[0])
        app.sections["science"].rerender()
        app.page.update()

    science = ft.SegmentedButton(
        selected=[str(s["science_count"])],
        segments=[ft.Segment("3", label=ft.Text("3")), ft.Segment("6", label=ft.Text("6"))],
        show_selected_icon=False,
        on_change=on_science,
    )

    # --- refresh timing per source ---
    def refresh_dropdown(source):
        current = s["refresh_minutes"].get(source.id, 30)

        def on_select(e):
            s.data["refresh_minutes"][source.id] = int(e.control.value)
            s.save()

        choices = sorted(set(REFRESH_CHOICES + [current]))
        return _row(
            source.title,
            ft.Dropdown(value=str(current), width=130, on_select=on_select,
                        options=[ft.DropdownOption(key=str(m), text=_label(m)) for m in choices]),
        )

    # --- data ---
    def clear_cache(e):
        app.cache.clear()
        app.state.data["expanded"] = {}
        app.state.save()
        app.page.show_dialog(ft.SnackBar(ft.Text("Cache cleared - pull fresh data with Refresh all")))

    view = ft.View(
        route="/settings",
        padding=0,
        appbar=ft.AppBar(title=ft.Text("Settings")),
        controls=[
            ft.ListView(
                [
                    _group("Appearance", ft.Icons.PALETTE_ROUNDED,
                           ft.Text("Theme", size=15),
                           theme,
                           _row("Text size", text_size)),
                    _group("News flashes", ft.Icons.NEWSPAPER_ROUNDED,
                           _row("Show the last", hours_text, "How far back to load headlines"),
                           hours),
                    _group("Science", ft.Icons.SCIENCE_ROUNDED,
                           _row("Articles in the feed", science)),
                    _group("Auto refresh", ft.Icons.UPDATE_ROUNDED,
                           ft.Text("When the app opens, a section reloads by itself if its data "
                                   "is older than this. The refresh button on each section always works.",
                                   size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                           *[refresh_dropdown(src) for src in app.sources]),
                    _group("Data", ft.Icons.STORAGE_ROUNDED,
                           _row("Cached news", ft.OutlinedButton("Clear", icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                                                                 on_click=clear_cache)),
                           ft.Text(f"Morning v{APP_VERSION} · data in {data_dir()}",
                                   size=11, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)),
                ],
                padding=16,
                spacing=14,
                expand=True,
            )
        ],
    )
    app.push_view(view)
