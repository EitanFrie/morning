"""
INN / Arutz 7 news flashes (https://www.inn.co.il/flashes/).

The site's own page loads its flashes from a JSON API, so we call that API
directly - no ads, no scraping of HTML, just the data.
Each API page holds 40 flashes (newest first); we keep reading pages until
we pass the "hours back" limit from the settings.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import flet as ft

from core.source import Source
from core.text import clean, html_to_text
from ui.widgets import empty_message, feed_row, fs

API = "https://www.inn.co.il/api/NewAPI/Cat"
ISRAEL = ZoneInfo("Asia/Jerusalem")
MAX_PAGES = 15  # safety limit (~60 hours of flashes)


class InnFlashes(Source):
    id = "inn"
    title = "מבזקים"
    subtitle = "ערוץ 7"
    icon = ft.Icons.NEWSPAPER_ROUNDED
    color = ft.Colors.BLUE_700

    async def fetch(self, app):
        hours = app.settings["inn_hours_back"]
        # The API times are Israel local time without a timezone.
        cutoff = datetime.now(ISRAEL).replace(tzinfo=None) - timedelta(hours=hours)
        flashes, seen = [], set()
        page = 0
        for _ in range(MAX_PAGES):
            response = await app.client.get(API, params={"type": 10, "page": page})
            response.raise_for_status()
            payload = response.json()
            items = payload.get("Items") or []
            for item in items:
                when = datetime.fromisoformat(item["itemDate"])
                if when < cutoff:
                    return flashes
                flash_id = str(item.get("item") or item.get("shotedLink") or item["title"])
                if flash_id in seen:
                    continue
                seen.add(flash_id)
                flashes.append(
                    {
                        "id": flash_id,
                        "time": item["itemDate"],
                        "title": clean(item.get("title") or ""),
                        "body": html_to_text(item.get("content") or ""),
                        "link": item.get("shotedLink") or "https://www.inn.co.il/flashes/",
                    }
                )
            if not items or not payload.get("nextPage"):
                break
            page = payload["nextPage"]
        return flashes

    # ------------------------------------------------------------------ UI

    def render(self, flashes, app):
        if not flashes:
            return empty_message(ft.Icons.NEWSPAPER_ROUNDED, "אין מבזקים בטווח השעות שנבחר")

        today = datetime.now(ISRAEL).date()
        rows: list[ft.Control] = []
        last_day = today
        for flash in flashes:
            day = datetime.fromisoformat(flash["time"]).date()
            if day != last_day:  # a small divider when the list crosses midnight
                label = "אתמול" if day == today - timedelta(days=1) else day.strftime("%d/%m")
                rows.append(_day_divider(label))
                last_day = day
            rows.append(_flash_row(flash, app))
        return ft.Column(rows, spacing=0, rtl=True)


def _day_divider(label: str) -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [ft.Divider(expand=True), ft.Text(label, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
             ft.Divider(expand=True)],
            spacing=10,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=4),
    )


def _flash_row(flash: dict, app) -> ft.Control:
    """One headline (no images). Tapping reveals the full text; the open state is remembered."""
    expandable = bool(flash["body"]) and flash["body"].strip() != flash["title"].strip()
    is_new = app.is_new_since_last_visit(datetime.fromisoformat(flash["time"]).replace(tzinfo=ISRAEL))

    meta = ft.Row(
        [ft.Text(flash["time"][11:16], size=fs(app, 12), weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY),
         ft.Container(width=7, height=7, border_radius=4, bgcolor=ft.Colors.RED_ACCENT_400,
                      visible=is_new, tooltip="חדש מאז הביקור הקודם")],
        spacing=6,
    )
    details = None
    if expandable:
        details = ft.Column(
            [
                ft.Text(flash["body"], size=fs(app, 15), color=ft.Colors.ON_SURFACE_VARIANT, selectable=True),
                ft.TextButton("לכתבה באתר", icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                              on_click=lambda e: app.open_url(flash["link"])),
            ],
            spacing=2,
        )
    return feed_row(
        app,
        flash["title"],
        meta=meta,
        details=details,
        expanded=expandable and app.is_expanded("inn", flash["id"]),
        on_toggle=lambda is_open: app.set_expanded("inn", flash["id"], is_open),
    )
