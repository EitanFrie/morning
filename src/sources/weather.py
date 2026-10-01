"""
Weather for your city - Open-Meteo (free, no API key - https://open-meteo.com).

  geocoding-api.open-meteo.com/v1/search  -> city search (Hebrew names too)
  api.open-meteo.com/v1/forecast          -> hourly + daily forecast, 4 days

Shows today: an hour-by-hour graph (sky icon, temperature bar, chance of rain) and the
day's min-max in °C. A button reveals the next 3 days (like the science "show 6").
The city is chosen with a small search box; it is remembered in settings.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone

import flet as ft

from core.source import Source
from ui.widgets import feed_row, fs

FORECAST = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
DAY_NAMES = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]  # Python weekday() order

# WMO weather code -> (Hebrew text, day icon, night icon, color)
SKY = [
    ({0}, "בהיר", ft.Icons.WB_SUNNY_ROUNDED, ft.Icons.NIGHTLIGHT_ROUNDED, ft.Colors.AMBER_600),
    ({1, 2}, "מעונן חלקית", ft.Icons.WB_CLOUDY_ROUNDED, ft.Icons.NIGHTLIGHT_ROUNDED, ft.Colors.AMBER_400),
    ({3}, "מעונן", ft.Icons.CLOUD_ROUNDED, ft.Icons.CLOUD_ROUNDED, ft.Colors.BLUE_GREY_400),
    ({45, 48}, "ערפל", ft.Icons.FOGGY, ft.Icons.FOGGY, ft.Colors.BLUE_GREY_300),
    ({51, 53, 55, 56, 57}, "טפטוף", ft.Icons.GRAIN_ROUNDED, ft.Icons.GRAIN_ROUNDED, ft.Colors.LIGHT_BLUE_400),
    ({61, 63, 65, 66, 67}, "גשם", ft.Icons.WATER_DROP_ROUNDED, ft.Icons.WATER_DROP_ROUNDED, ft.Colors.BLUE_500),
    ({80, 81, 82}, "ממטרים", ft.Icons.UMBRELLA_ROUNDED, ft.Icons.UMBRELLA_ROUNDED, ft.Colors.BLUE_600),
    ({71, 73, 75, 77, 85, 86}, "שלג", ft.Icons.AC_UNIT_ROUNDED, ft.Icons.AC_UNIT_ROUNDED, ft.Colors.CYAN_300),
    ({95, 96, 99}, "סופת רעמים", ft.Icons.THUNDERSTORM_ROUNDED, ft.Icons.THUNDERSTORM_ROUNDED, ft.Colors.DEEP_PURPLE_400),
]


def temp_range(lo, hi) -> str:
    """'16°–23°' kept left-to-right inside Hebrew text (otherwise RTL flips it to '°23–16°')."""
    return f"⁦{lo}°–{hi}°⁩"


def sky(code: int, is_day: bool = True):
    """-> (text, icon, color) for a weather code."""
    for codes, text, day_icon, night_icon, color in SKY:
        if code in codes:
            return text, (day_icon if is_day else night_icon), color
    return "", ft.Icons.HELP_OUTLINE_ROUNDED, ft.Colors.OUTLINE


class Weather(Source):
    id = "weather"
    title = "מזג אוויר"
    subtitle = "Open-Meteo"
    icon = ft.Icons.WB_SUNNY_ROUNDED
    color = ft.Colors.AMBER_700

    async def fetch(self, app):
        city = app.settings["weather_city"]
        response = await app.client.get(FORECAST, params={
            "latitude": city["lat"], "longitude": city["lon"], "timezone": "auto", "forecast_days": 4,
            "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        })
        response.raise_for_status()
        f = response.json()
        h = f["hourly"]
        hours = [
            {"time": t, "temp": round(temp), "code": code, "rain": rain or 0, "day": bool(day)}
            for t, temp, code, rain, day in zip(h["time"], h["temperature_2m"], h["weather_code"],
                                                h["precipitation_probability"], h["is_day"])
            if temp is not None
        ]
        d = f["daily"]
        days = [
            {"date": t, "code": code, "max": round(hi), "min": round(lo), "rain": rain or 0}
            for t, code, hi, lo, rain in zip(d["time"], d["weather_code"], d["temperature_2m_max"],
                                             d["temperature_2m_min"], d["precipitation_probability_max"])
        ]
        return {"city": city["name"], "days": days, "hours": hours,
                "utc_offset": f.get("utc_offset_seconds", 0)}

    # ------------------------------------------------------------------ UI

    def header_extras(self, app):
        city = app.settings["weather_city"]
        return [ft.Container(
            ft.Row([ft.Icon(ft.Icons.LOCATION_ON_ROUNDED, size=18, color=ft.Colors.PRIMARY),
                    ft.Text(city["name"], size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Icon(ft.Icons.SEARCH_ROUNDED, size=18, color=ft.Colors.ON_SURFACE_VARIANT)],
                   spacing=6, tight=True, rtl=True),
            height=40,
            padding=ft.Padding.symmetric(horizontal=14),
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=20,
            ink=True,
            on_click=lambda e: open_city_search(app, self),
        )]

    def render(self, data, app):
        days = data["days"]
        today, upcoming = days[0], days[1:]
        # "now" in the city's own time zone (the forecast times are local to the city)
        city_now = datetime.now(timezone.utc) + timedelta(seconds=data.get("utc_offset", 0))
        now = city_now.strftime("%Y-%m-%dT%H:00")
        next_24 = [h for h in data["hours"] if h["time"] >= now][:24]
        text, icon, color = sky(today["code"])

        rows: list[ft.Control] = [
            # today: big summary + hour-by-hour graph
            ft.Container(
                ft.Row([
                    ft.Icon(icon, size=56, color=color),
                    ft.Column([
                        ft.Text(f'{text} · {temp_range(today["min"], today["max"])}', size=fs(app, 22),
                                weight=ft.FontWeight.BOLD),
                        ft.Text(f'היום · {data["city"]}' + (f' · גשם {today["rain"]}%' if today["rain"] else ""),
                                size=fs(app, 13), color=ft.Colors.ON_SURFACE_VARIANT),
                    ], spacing=2, expand=True),
                ], spacing=16),
                padding=ft.Padding.only(left=16, right=16, top=14, bottom=4),
            ),
            hourly_graph(next_24, app),
        ]

        show = app.settings["weather_show_days"]

        def toggle(e):
            app.settings["weather_show_days"] = not show
            app.sections[self.id].rerender()
            app.page.update()

        if show:
            rows += [_day_row(d, data["hours"], app) for d in upcoming]
        rows.append(ft.Row([ft.TextButton(
            "הסתר את הימים הבאים" if show else f"הצג {len(upcoming)} ימים הבאים",
            icon=ft.Icons.EXPAND_LESS_ROUNDED if show else ft.Icons.EXPAND_MORE_ROUNDED,
            on_click=toggle,
        )], alignment=ft.MainAxisAlignment.CENTER))
        return ft.Column(rows, spacing=0, rtl=True)


def _day_row(day: dict, hours: list, app) -> ft.Control:
    """One coming day, same row format as everything else; tap it for its hourly graph."""
    d = date.fromisoformat(day["date"])
    text, icon, color = sky(day["code"])
    return feed_row(
        app,
        f'{text} · {temp_range(day["min"], day["max"])}',
        meta=f'יום {DAY_NAMES[d.weekday()]} · {d.strftime("%d/%m")}',
        subtitle=f'סיכוי לגשם {day["rain"]}%' if day["rain"] else "ללא גשם",
        leading=ft.Container(ft.Icon(icon, size=34, color=color), width=52, height=52,
                             alignment=ft.Alignment.CENTER),
        details=hourly_graph([h for h in hours if h["time"].startswith(day["date"])], app),
    )


def hourly_graph(hours: list, app) -> ft.Control:
    """Hour-by-hour columns: time, sky icon, temperature bar (taller = warmer), °, rain %.
    Scrolls sideways on a phone."""
    if not hours:
        return ft.Container()
    lo = min(h["temp"] for h in hours)
    hi = max(h["temp"] for h in hours)
    span = max(hi - lo, 1)

    def column(h):
        _, icon, color = sky(h["code"], h["day"])
        bar = 12 + 36 * (h["temp"] - lo) / span  # 12..48 px
        return ft.Column(
            [
                ft.Text(h["time"][11:16], size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Icon(icon, size=22, color=color),
                ft.Text(f'{h["temp"]}°', size=fs(app, 14), weight=ft.FontWeight.W_600),
                ft.Container(height=48 - bar),  # aligns the bars on the bottom
                ft.Container(width=14, height=bar, border_radius=7,
                             gradient=ft.LinearGradient(begin=ft.Alignment.TOP_CENTER,
                                                        end=ft.Alignment.BOTTOM_CENTER,
                                                        colors=[ft.Colors.ORANGE_400, ft.Colors.AMBER_200])),
                ft.Text(f'{h["rain"]}%' if h["rain"] else "", size=10, color=ft.Colors.BLUE_400),
            ],
            width=46,
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    return ft.Container(
        ft.Row([column(h) for h in hours], spacing=2, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding.symmetric(horizontal=8, vertical=12),
    )


# ---------------------------------------------------------------- city search


def open_city_search(app, source: Weather):
    """A small dialog: type a city, tap a result. Nothing more."""
    results = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=300)
    status = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    last_query = {"text": ""}

    async def search(query: str):
        last_query["text"] = query
        await asyncio.sleep(0.4)  # wait until typing pauses
        if query != last_query["text"] or len(query) < 2:
            return
        try:
            r = await app.client.get(GEOCODE, params={"name": query, "count": 8, "language": "he"})
            found = r.json().get("results") or []
        except Exception:
            found, status.value = [], "אין חיבור לאינטרנט"
        else:
            status.value = "" if found else "לא נמצאו תוצאות"
        results.controls = [_result_tile(c, choose) for c in found]
        dialog.update()

    async def choose(city: dict):
        app.settings["weather_city"] = {"name": city["name"], "lat": city["latitude"],
                                        "lon": city["longitude"], "country": city.get("country", "")}
        app.page.pop_dialog()
        app.sections[source.id].rerender()
        await app.refresh(source)

    field = ft.TextField(hint_text="חיפוש עיר…", autofocus=True, rtl=True,
                         prefix_icon=ft.Icons.SEARCH_ROUNDED,
                         on_change=lambda e: app.page.run_task(search, e.control.value.strip()))
    dialog = ft.AlertDialog(
        title=ft.Text("בחירת עיר", rtl=True),
        content=ft.Container(ft.Column([field, status, results], tight=True, spacing=8, rtl=True), width=360),
        actions=[ft.TextButton("ביטול", on_click=lambda e: app.page.pop_dialog())],
    )
    app.page.show_dialog(dialog)


def _result_tile(city: dict, choose) -> ft.Control:
    place = ", ".join(x for x in [city.get("admin1"), city.get("country")] if x)

    async def click(e):
        await choose(city)

    return ft.ListTile(
        leading=ft.Icon(ft.Icons.LOCATION_ON_ROUNDED),
        title=ft.Text(city["name"]),
        subtitle=ft.Text(place, size=12),
        on_click=click,
        rtl=True,
    )
