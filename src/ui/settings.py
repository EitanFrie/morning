"""Settings screen. Every change is saved immediately."""

from typing import TYPE_CHECKING

import flet as ft

from core.speech import ENGLISH, HEBREW, normalize_quotes
from core.storage import data_dir
from core.updates import current_version
from ui.widgets import card

if TYPE_CHECKING:
    from app import App

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


# ---------------------------------------------------------------- voices


def _voice_row(app, language: str, label: str) -> ft.Control:
    key = "voice_he" if language == HEBREW else "voice_en"
    current = app.settings[key]
    return _row(label, ft.OutlinedButton(
        "Choose", icon=ft.Icons.RECORD_VOICE_OVER_ROUNDED,
        on_click=lambda e: app.page.run_task(_choose_voice, app, language, key)),
        current["name"] if current else "Phone default")


async def _choose_voice(app, language: str, key: str):
    """List the phone's voices for this language; ▶ plays a sample, tap the name to choose.
    (Android doesn't say male/female - pick by ear.)"""
    voices = await app.speaker.voices(language)
    if not voices:
        app.toast("No voices found (works in the phone app; install voices in Android settings)")
        return

    def choose(voice):
        app.settings[key] = {"name": voice["name"], "locale": voice.get("locale", language)} if voice else None
        app.page.pop_dialog()
        app.toast("Voice saved")

    def row(voice):
        info = " · ".join(x for x in [voice.get("locale"), voice.get("quality"),
                                       "needs internet" if voice.get("network_required") == "1" else ""] if x)
        return ft.ListTile(
            title=ft.Text(voice["name"], size=14),
            subtitle=ft.Text(info, size=11),
            leading=ft.IconButton(ft.Icons.PLAY_ARROW_ROUNDED, tooltip="Listen",
                                  on_click=lambda e: app.page.run_task(app.speaker.sample, voice, language)),
            on_click=lambda e: choose(voice),
            selected=(app.settings[key] or {}).get("name") == voice["name"],
        )

    app.page.show_dialog(ft.AlertDialog(
        title=ft.Text("Choose a voice"),
        content=ft.Container(ft.Column(
            [ft.Text("▶ to listen, tap the name to choose", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
             *[row(v) for v in voices]], scroll=ft.ScrollMode.AUTO, tight=True), width=380, height=420),
        actions=[ft.TextButton("Phone default", on_click=lambda e: choose(None)),
                 ft.TextButton("Close", on_click=lambda e: app.page.pop_dialog())],
    ))


# ---------------------------------------------------------------- abbreviations


def _abbreviation_editor(app) -> list[ft.Control]:
    """Your abbreviations: add manually; the list is folded (tap to open) and searchable.
    Yours always win over the built-in list."""
    listing = ft.Column(spacing=0, visible=False)
    short = ft.TextField(label='קיצור (למשל ואכמ"ל)', rtl=True, dense=True, expand=1)
    full = ft.TextField(label="פירוש מלא", rtl=True, dense=True, expand=2)
    search = ft.TextField(hint_text="חיפוש…", prefix_icon=ft.Icons.SEARCH_ROUNDED, rtl=True,
                          dense=True, visible=False, on_change=lambda e: refresh(update=True))
    header_text = ft.Text(rtl=True, weight=ft.FontWeight.W_600, expand=True)
    arrow = ft.Icon(ft.Icons.EXPAND_MORE_ROUNDED)

    def refresh(update=False):
        learned = app.settings["user_abbreviations"]
        header_text.value = f"הקיצורים שלך ({len(learned)})"
        query = normalize_quotes(search.value or "").strip()
        rows = [(k, v) for k, v in sorted(learned.items())
                if not query or query in k or query in v]
        listing.controls = [
            ft.Row([ft.Text(f"{k}  ←  {v}", rtl=True, expand=True, size=14),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE_ROUNDED, tooltip="Delete",
                                  on_click=lambda e, k=k: remove(k))])
            for k, v in rows
        ] or [ft.Text("אין קיצורים" if not learned else "לא נמצא", size=12,
                      color=ft.Colors.ON_SURFACE_VARIANT, rtl=True)]
        if update:
            for c in (header_text, listing):
                c.update()

    def toggle(e):
        listing.visible = search.visible = not listing.visible
        arrow.icon = ft.Icons.EXPAND_LESS_ROUNDED if listing.visible else ft.Icons.EXPAND_MORE_ROUNDED
        for c in (listing, search, arrow):
            c.update()

    def save(table):
        app.settings["user_abbreviations"] = table  # also saves the file
        refresh(update=True)

    def add(e):
        k, v = normalize_quotes(short.value or "").strip(), (full.value or "").strip()
        if not k or not v:
            app.toast("Fill in both fields")
            return
        save({**app.settings["user_abbreviations"], k: v})
        short.value = full.value = ""
        short.update()
        full.update()

    def remove(k):
        table = dict(app.settings["user_abbreviations"])
        table.pop(k, None)
        save(table)

    refresh()
    return [
        ft.Text("נקראים במקום הקיצור בזמן הקראה, ותמיד גוברים על הרשימה המובנית. "
                "אפשר גם ללמד את האפליקציה מתוך חלון פרשת השבוע (🎓).",
                size=12, color=ft.Colors.ON_SURFACE_VARIANT, rtl=True),
        ft.Row([short, full, ft.IconButton(ft.Icons.ADD_CIRCLE_ROUNDED, tooltip="Add", on_click=add)], rtl=True),
        ft.Container(ft.Row([header_text, arrow], rtl=True), ink=True, on_click=toggle,
                     padding=ft.Padding.symmetric(vertical=8), border_radius=8),
        search,
        listing,
    ]


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

    # --- NBA news ---
    news_count_text = ft.Text(str(s["nba_news_count"]), weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY)

    def on_news_count(e):
        s["nba_news_count"] = int(e.control.value)
        news_count_text.value = str(s["nba_news_count"])
        news_count_text.update()
        app.sections["nba_news"].rerender()
        app.page.update()

    news_count = ft.Slider(min=1, max=12, divisions=11, value=s["nba_news_count"], label="{value}",
                           on_change_end=on_news_count)

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

    # --- reading aloud ---
    rate_labels = {0.3: "Slow", 0.4: "Calm", 0.5: "Normal", 0.6: "Brisk", 0.7: "Fast"}
    rate_text = ft.Text(rate_labels.get(s["speech_rate"], ""), weight=ft.FontWeight.W_600,
                        color=ft.Colors.PRIMARY)

    def on_rate(e):
        s["speech_rate"] = round(float(e.control.value), 1)
        rate_text.value = rate_labels.get(s["speech_rate"], "")
        rate_text.update()

    rate = ft.Slider(min=0.3, max=0.7, divisions=4, value=s["speech_rate"], on_change_end=on_rate)

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
                    _group("NBA News", ft.Icons.FEED_ROUNDED,
                           _row("Headlines to show", news_count_text, "Featured stories from nba.com"),
                           news_count),
                    _group("Science", ft.Icons.SCIENCE_ROUNDED,
                           _row("Articles in the feed", science)),
                    _group("Reading aloud", ft.Icons.RECORD_VOICE_OVER_ROUNDED,
                           _row("Speed", rate_text, "Uses your phone's voice (Settings > Text-to-speech)"),
                           rate,
                           _voice_row(app, HEBREW, "Hebrew voice"),
                           _voice_row(app, ENGLISH, "English voice")),
                    _group("Abbreviations (for reading aloud)", ft.Icons.SPELLCHECK_ROUNDED,
                           *_abbreviation_editor(app)),
                    _group("Auto refresh", ft.Icons.UPDATE_ROUNDED,
                           ft.Text("When the app opens, a section reloads by itself if its data "
                                   "is older than this. The refresh button on each section always works.",
                                   size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                           *[refresh_dropdown(src) for src in app.sources]),
                    _group("Data", ft.Icons.STORAGE_ROUNDED,
                           _row("Cached news", ft.OutlinedButton("Clear", icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                                                                 on_click=clear_cache)),
                           _row("App version", ft.OutlinedButton(
                               "Check now", icon=ft.Icons.SYSTEM_UPDATE_ROUNDED,
                               on_click=lambda e: app.page.run_task(app.check_for_updates, True)),
                               f"v{current_version()} · updates come from GitHub releases"),
                           ft.Text(f"Data in {data_dir()}",
                                   size=11, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)),
                ],
                padding=16,
                spacing=14,
                expand=True,
            )
        ],
    )
    app.push_view(view)
