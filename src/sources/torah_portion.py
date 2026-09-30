"""
Daily Torah portion: this week's parasha split into its 7 aliyot - one per day
(Sunday = 1st ... Shabbat = 7th). Every verse is followed by the chosen commentator.

Sefaria API (free, no key - https://developers.sefaria.org):
  /api/calendars                       -> this week's parasha + its aliyot refs
  /api/v3/texts/{aliyah}               -> the verses (Hebrew)
  /api/v3/texts/{Commentator on aliyah} -> that commentator, as a list of comments per verse
Only the chosen day + commentator is downloaded (~20 KB), so switching is quick.
(The "links with text" API would bring every commentator at once, but it is ~7 MB per aliyah.)
"""

import asyncio
import re
from datetime import datetime

import flet as ft
from bs4 import BeautifulSoup

from core.source import Source
from core.text import clean
from ui.widgets import empty_message, feed_row, fs

API = "https://www.sefaria.org/api"
DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
COMMENTATORS = [  # (Sefaria name, Hebrew name)
    ("Rashi", 'רש"י'), ("Ramban", 'רמב"ן'), ("Ibn Ezra", "אבן עזרא"), ("Sforno", "ספורנו"),
    ("Or HaChaim", "אור החיים"), ("Rashbam", 'רשב"ם'), ("Kli Yakar", "כלי יקר"),
    ("Baal HaTurim", "בעל הטורים"), ("Haamek Davar", "העמק דבר"), ("Malbim", 'מלבי"ם'),
]
_TEAMIM = re.compile(r"[֑-ֽ֯]")  # cantillation marks (keep the nikud)


def today_index() -> int:
    """Sunday=0 ... Shabbat=6 (Python's weekday() is Monday=0)."""
    return (datetime.now().weekday() + 1) % 7


class TorahPortion(Source):
    id = "torah"
    title = "פרשת השבוע"
    subtitle = "Sefaria"
    icon = ft.Icons.MENU_BOOK_ROUNDED
    color = ft.Colors.BROWN_400

    def __init__(self):
        self.day: int | None = None  # None = today

    async def fetch(self, app):
        day = today_index() if self.day is None else self.day
        commentator = app.settings["torah_commentator"]
        client = app.client

        calendar = (await client.get(f"{API}/calendars", params={"diaspora": 0, "custom": "ashkenazi"})).json()
        parasha = next(i for i in calendar["calendar_items"] if i["title"]["en"] == "Parashat Hashavua")
        aliyot = parasha["extraDetails"]["aliyot"][:7]  # holidays may add an 8th (maftir)
        ref = aliyot[min(day, len(aliyot) - 1)]

        params = {"version": "hebrew", "return_format": "text_only"}
        verses_resp, comm_resp = await asyncio.gather(
            client.get(f"{API}/v3/texts/{ref}", params=params),
            client.get(f"{API}/v3/texts/{commentator} on {ref}", params=params),
        )
        verses_json = verses_resp.json()
        start = [int(x) for x in verses_json["sections"]]  # [chapter, verse]
        multi = verses_json["sections"][0] != verses_json["toSections"][0]
        verses = _by_verse(verses_json["versions"][0]["text"], start, multi)

        comments = {}
        if comm_resp.status_code == 200 and comm_resp.json().get("versions"):
            comments = _by_verse(comm_resp.json()["versions"][0]["text"], start, multi)

        return {
            "parasha": parasha["displayValue"]["he"],
            "ref": parasha["ref"],
            "aliyah_ref": ref,
            "day": day,
            "commentator": commentator,
            "verses": [
                {"label": f"{c}:{v}", "text": _TEAMIM.sub("", clean(_strip_html(text))),
                 "comments": [clean(_strip_html(x)) for x in comments.get((c, v), []) if x]}
                for (c, v), text in verses.items()
            ],
        }

    # ------------------------------------------------------------------ UI

    def header_extras(self, app):
        day = today_index() if self.day is None else self.day

        async def pick_day(e):
            self.day = int(e.control.value)
            await app.refresh(self)

        async def pick_commentator(e):
            app.settings["torah_commentator"] = e.control.value
            await app.refresh(self)

        return [
            ft.Dropdown(value=str(day), width=110, dense=True, on_select=pick_day,
                        options=[ft.DropdownOption(key=str(i), text=d) for i, d in enumerate(DAYS)]),
            ft.Dropdown(value=app.settings["torah_commentator"], width=140, dense=True,
                        on_select=pick_commentator,
                        options=[ft.DropdownOption(key=en, text=he) for en, he in COMMENTATORS]),
        ]

    def render(self, data, app):
        heb = dict(COMMENTATORS).get(data["commentator"], data["commentator"])
        rows: list[ft.Control] = [
            ft.Container(
                ft.Column([
                    ft.Text(f'פרשת {data["parasha"]} · יום {DAYS[data["day"]]}', size=fs(app, 18),
                            weight=ft.FontWeight.BOLD),
                    ft.Text(f'{data["aliyah_ref"]} · עם {heb}', size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ], spacing=2),
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            )
        ]
        if not any(v["comments"] for v in data["verses"]):
            rows.append(empty_message(ft.Icons.INFO_OUTLINE_ROUNDED, f"ל{heb} אין פירוש על קטע זה - נסה פרשן אחר"))
        for verse in data["verses"]:
            details = None
            if verse["comments"]:
                details = ft.Container(
                    ft.Column([ft.Text(c, size=fs(app, 15), selectable=True,
                                       style=ft.TextStyle(height=1.5)) for c in verse["comments"]], spacing=8),
                    padding=ft.Padding.only(right=12),
                    border=ft.Border(right=ft.BorderSide(3, self.color)),
                )
            rows.append(feed_row(
                app, verse["text"], meta=verse["label"], details=details,
                expanded=True, title_lines=None, title_bold=False,
            ))
        return ft.Column(rows, spacing=0, rtl=True)


# ---------------------------------------------------------------- helpers


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text() if "<" in text else text


def _by_verse(text: list, start: list[int], multi_chapter: bool) -> dict:
    """Map Sefaria's list to {(chapter, verse): item}. A range crossing chapters comes
    as a list of chapters; a single-chapter range as a plain list of verses."""
    chapters = text if multi_chapter else [text]
    out = {}
    for ci, items in enumerate(chapters):
        v = start[1] if ci == 0 else 1
        for item in items:
            out[(start[0] + ci, v)] = item
            v += 1
    return out
