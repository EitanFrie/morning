"""
Daily Torah portion: this week's parasha split into its 7 aliyot - one per day
(Sunday = 1st ... Shabbat = 7th). Every verse is followed by the chosen commentator.

Sefaria API (free, no key - https://developers.sefaria.org):
  /api/calendars                   -> this week's parasha + its aliyot refs
  /api/v3/texts/{aliyah}           -> the verses (Hebrew)
  /api/links/{aliyah}?with_text=1  -> ALL commentators on the aliyah, with their text

Once per week (new parasha, or nothing stored) the whole week - 7 aliyot with all
commentators - is downloaded (~50 MB of downloads), reduced to what we show, and saved to
torah_week.json. The previous week's file is deleted first (holiday weeks too).
After that, switching day or commentator needs no internet at all.
"""

import asyncio
import html
import json
import re
from datetime import datetime

import flet as ft
import httpx
from bs4 import BeautifulSoup

from core.source import Source
from core.storage import data_dir
from core.text import clean
from ui.widgets import empty_message, feed_row, fs, picker

API = "https://www.sefaria.org/api"
DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
COMMENTATORS = [  # (Sefaria name, Hebrew name)
    ("Rashi", 'רש"י'), ("Ramban", 'רמב"ן'), ("Ibn Ezra", "אבן עזרא"), ("Sforno", "ספורנו"),
    ("Or HaChaim", "אור החיים"), ("Rashbam", 'רשב"ם'), ("Kli Yakar", "כלי יקר"),
    ("Baal HaTurim", "בעל הטורים"), ("Haamek Davar", "העמק דבר"), ("Malbim", 'מלבי"ם'),
]
WEEK_FILE = data_dir() / "torah_week.json"
_TEAMIM = re.compile(r"[֑-ֽ֯]")  # cantillation marks (keep the nikud)


def today_index() -> int:
    """Sunday=0 ... Shabbat=6 (Python's weekday() is Monday=0)."""
    return (datetime.now().weekday() + 1) % 7


class TorahPortion(Source):
    id = "torah"
    title = "פרשת השבוע"
    subtitle = "Sefaria"
    icon = ft.Icons.MENU_BOOK_ROUNDED
    color = ft.Colors.DEEP_PURPLE_400

    def __init__(self):
        self.day: int | None = None  # None = today

    async def fetch(self, app):
        day = today_index() if self.day is None else self.day
        try:
            calendar = (await app.client.get(f"{API}/calendars",
                                             params={"diaspora": 0, "custom": "ashkenazi"})).json()
        except httpx.HTTPError:
            # Offline: the whole week (verses + commentators) is already on the phone.
            week = _stored_week()
            if week is None:
                raise
        else:
            parasha = next(i for i in calendar["calendar_items"] if i["title"]["en"] == "Parashat Hashavua")
            week = await self._week(app, parasha)

        today = week["days"][min(day, len(week["days"]) - 1)]
        # commentators that really exist on this aliyah - Rashi first, then the most active
        counts = {en: sum(1 for v in today["commentary"].values() if en in v) for en in today["names"]}
        available = sorted(today["names"], key=lambda en: (en != "Rashi", -counts[en]))
        commentator = app.settings["torah_commentator"]
        return {
            "parasha": week["parasha"],
            "aliyah_ref": today["ref"],
            "day": day,
            "commentator": commentator,
            "commentator_he": today["names"].get(commentator, commentator),
            "available": [[en, today["names"][en]] for en in available],
            "verses": [
                {**v, "text": _fix(v["text"]),
                 "comments": [_fix(c) for c in today["commentary"].get(v["label"], {}).get(commentator, [])]}
                for v in today["verses"]
            ],
        }

    async def _week(self, app, parasha) -> dict:
        """This week's bundle from disk, or download it (deleting last week's)."""
        key = parasha["ref"]
        week = _stored_week()
        if week and week.get("key") == key:
            if any(d.get("missing") for d in week["days"]) and await _refill_missing(app.client, week):
                WEEK_FILE.write_text(json.dumps(week, ensure_ascii=False), encoding="utf-8")
            return week
        WEEK_FILE.unlink(missing_ok=True)  # a new week: delete the old one

        section = app.sections[self.id]
        aliyot = parasha["extraDetails"]["aliyot"][:7]  # holidays may add an 8th (maftir)
        days = []
        note = "זה קורה פעם בשבוע (כמה דקות), אחר כך הכל זמין גם בלי אינטרנט"
        for i, ref in enumerate(aliyot):
            def progress(done, total, i=i):
                section.show_progress(f"מוריד את תוכן השבוע… עלייה {i + 1}/{len(aliyot)} · פסוק {done}/{total}",
                                      note)
            days.append(await _download_aliyah(app.client, ref, progress))
        week = {"key": key, "parasha": parasha["displayValue"]["he"], "days": days}
        WEEK_FILE.write_text(json.dumps(week, ensure_ascii=False), encoding="utf-8")
        return week

    # ------------------------------------------------------------------ UI

    def header_extras(self, app):
        day = today_index() if self.day is None else self.day

        async def pick_day(key):
            self.day = int(key)
            await app.refresh(self)

        async def pick_commentator(key):
            app.settings["torah_commentator"] = key
            await app.refresh(self)

        choices = self._choices(app)
        current = app.settings["torah_commentator"]
        return [
            picker(DAYS[day], [(str(i), d) for i, d in enumerate(DAYS)], pick_day, width=110),
            picker(dict(choices).get(current, current), choices, pick_commentator, expand=True),
        ]

    def _choices(self, app) -> list:
        """Commentators found in the downloaded week (fallback: the classic list)."""
        entry = app.cache.get(self.id)
        choices = entry["data"].get("available") if entry else None
        choices = [tuple(c) for c in choices] if choices else list(COMMENTATORS)
        current = app.settings["torah_commentator"]
        if current not in [en for en, _ in choices]:
            choices.insert(0, (current, dict(COMMENTATORS).get(current, current)))
        return choices

    def render(self, data, app):
        heb = data.get("commentator_he") or data["commentator"]
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


async def _download_aliyah(client, ref: str, progress=None) -> dict:
    """One aliyah: its verses + every commentator's Hebrew text, grouped by verse."""
    params = {"version": "hebrew", "return_format": "text_only"}
    verses_json = (await client.get(f"{API}/v3/texts/{ref}", params=params, timeout=60)).json()
    start = [int(x) for x in verses_json["sections"]]  # [chapter, verse]
    multi = verses_json["sections"][0] != verses_json["toSections"][0]
    verses = _by_verse(verses_json["versions"][0]["text"], start, multi)

    # All commentators with text, one verse per request (a whole aliyah at once is ~7 MB
    # and the server often cuts such big answers off). 4 verses at a time.
    book = ref.rsplit(" ", 1)[0].replace(" ", "_")
    limit = asyncio.Semaphore(4)
    done = [0]
    if progress:
        progress(0, len(verses))

    async def verse_links(c, v):
        async with limit:
            try:
                return await _get_json(client, f"{API}/links/{book}.{c}.{v}", {"with_text": 1})
            except (httpx.HTTPError, ValueError):
                return None  # e.g. Genesis 1:1 has so many commentaries the server times out
            finally:
                done[0] += 1
                if progress:
                    progress(done[0], len(verses))

    per_verse = await asyncio.gather(*(verse_links(c, v) for c, v in verses))
    found = []  # (verse label, commentator, order, text)
    names = {}
    missing = []  # verses whose commentary could not be downloaded - retried next time
    for (c, v), links in zip(verses, per_verse):
        if links is None:
            missing.append(f"{c}:{v}")
            continue
        found += _commentary_entries(f"{c}:{v}", links, names)

    commentary: dict[str, dict[str, list[str]]] = {}
    for label, en, _, text in sorted(found, key=lambda f: f[2]):
        commentary.setdefault(label, {}).setdefault(en, []).append(text)
    return {
        "ref": ref,
        "book": book,
        "missing": missing,
        "verses": [{"label": f"{c}:{v}", "text": _TEAMIM.sub("", clean(_strip_html(t)))}
                   for (c, v), t in verses.items()],
        "commentary": commentary,
        "names": names,
    }


async def _get_json(client, url: str, params: dict, attempts: int = 3):
    """Big responses (several MB) sometimes get cut off by the server - just try again."""
    for attempt in range(attempts):
        try:
            response = await client.get(url, params=params, timeout=180)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(2 * (attempt + 1))


def _url_ref(ref: str) -> str:
    """'Deuteronomy 14:22-14:29' -> 'Deuteronomy.14.22-14.29' (the links API needs this form)."""
    book, place = ref.rsplit(" ", 1)
    return book.replace(" ", "_") + "." + place.replace(":", ".")


def _commentary_entries(label: str, links: list, names: dict) -> list:
    """Sefaria links of one verse -> [(label, commentator, order, Hebrew text)]."""
    entries = []
    for link in links:
        if link.get("category") != "Commentary" or not link.get("he"):
            continue
        texts = link["he"] if isinstance(link["he"], list) else [link["he"]]
        text = "\n".join(t for t in (clean(_strip_html(str(x))) for x in _flatten(texts)) if t)
        if not text:
            continue
        en, he = link["collectiveTitle"]["en"], link["collectiveTitle"]["he"]
        names[en] = he
        entries.append((label, en, float(link.get("commentaryNum") or 0), text))
    return entries


async def _refill_missing(client, week: dict) -> bool:
    """Try again for verses whose commentary failed last time. True if something was added."""
    changed = False
    for day in week["days"]:
        for label in list(day.get("missing", [])):
            c, v = label.split(":")
            try:
                links = await _get_json(client, f"{API}/links/{day['book']}.{c}.{v}", {"with_text": 1})
            except (httpx.HTTPError, ValueError):
                continue
            for _, en, _, text in sorted(_commentary_entries(label, links, day["names"]), key=lambda f: f[2]):
                day["commentary"].setdefault(label, {}).setdefault(en, []).append(text)
            day["missing"].remove(label)
            changed = True
    return changed


def _flatten(items):
    for x in items:
        if isinstance(x, list):
            yield from _flatten(x)
        else:
            yield x


def _stored_week() -> dict | None:
    """The week saved on the phone (verses + all commentators), or None."""
    try:
        return json.loads(WEEK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _strip_html(text: str) -> str:
    text = BeautifulSoup(text, "html.parser").get_text() if "<" in text else text
    return _fix(text)


def _fix(text: str) -> str:
    """Turn leftover HTML codes into real characters: '&nbsp;' -> space, '&amp;' -> '&'...
    (also repairs weeks downloaded before this fix)."""
    if "&" in text:
        text = html.unescape(html.unescape(text))  # twice: some come double-encoded (&amp;nbsp;)
    return text.replace("\u00a0", " ").replace("\u2009", " ")  # no-break / thin spaces


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
