"""
NBA scores + box scores, read from nba.com.

nba.com pages carry all their data as JSON inside the page (Next.js "__NEXT_DATA__"):
  https://www.nba.com/games?date=YYYY-MM-DD   -> every game of that day
  https://www.nba.com/game/<gameId>/box-score -> full box score of one game
On refresh we download the scoreboard AND the box score of every game that has
started, all at once - so tapping a game opens its box score instantly.
Nothing updates by itself while you watch; only on app open / refresh button.
"""

import asyncio
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import flet as ft

from core.http import next_data
from core.source import Source
from ui.boxscore import open_box_score
from ui.widgets import card, fs, pill

BASE = "https://www.nba.com"
NEW_YORK = ZoneInfo("America/New_York")
SCHEDULED, LIVE, FINAL = 1, 2, 3


def default_game_day() -> date:
    """'Tonight' in US time. Until 6am New York time we still mean last night's games -
    which is exactly what you want to see in the Israeli morning."""
    return (datetime.now(NEW_YORK) - timedelta(hours=6)).date()


class NbaScores(Source):
    id = "nba"
    title = "NBA"
    subtitle = "Scores & box scores"
    icon = ft.Icons.SPORTS_BASKETBALL_ROUNDED
    color = ft.Colors.DEEP_ORANGE_600

    def __init__(self):
        # None = automatic ("tonight"). For testing, NBA_DAY=2026-04-10 forces a date.
        forced = os.environ.get("NBA_DAY")
        self.day: date | None = date.fromisoformat(forced) if forced else None

    async def fetch(self, app):
        day = self.day or default_game_day()
        response = await app.client.get(f"{BASE}/games", params={"date": day.isoformat()})
        response.raise_for_status()
        props = next_data(response.text)["props"]["pageProps"]

        games = []
        for module in (props.get("gameCardFeed") or {}).get("modules") or []:
            for c in module.get("cards") or []:
                data = c.get("cardData") or {}
                if data.get("gameId"):
                    games.append(_game_from_card(data))

        # Box scores for every game that started - downloaded in parallel (max 6 at a time).
        limit = asyncio.Semaphore(6)

        async def box(game_id):
            async with limit:
                return await _fetch_box_score(app, game_id)

        started = [g for g in games if g["status"] != SCHEDULED]
        boxes = await asyncio.gather(*(box(g["id"]) for g in started), return_exceptions=True)
        for game, result in zip(started, boxes):
            game["box"] = None if isinstance(result, Exception) else result
        return {"day": day.isoformat(), "games": games}

    # ------------------------------------------------------------------ UI

    def header_extras(self, app):
        day = self.day or default_game_day()

        def shift(days):
            async def handler(e):
                self.day = day + timedelta(days=days)
                await app.refresh(self)
            return handler

        async def back_to_tonight(e):
            self.day = None
            await app.refresh(self)

        return [
            ft.IconButton(ft.Icons.CHEVRON_LEFT_ROUNDED, on_click=shift(-1), tooltip="Previous day"),
            ft.TextButton(
                day.strftime("%a %d/%m"),
                on_click=back_to_tonight,
                tooltip="Back to tonight",
                style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=6)),
            ),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT_ROUNDED, on_click=shift(1), tooltip="Next day"),
        ]

    def render(self, data, app):
        games = data["games"]
        if not games:
            day = date.fromisoformat(data["day"]).strftime("%A, %d %B")
            return card(ft.Row([ft.Icon(ft.Icons.EVENT_BUSY_ROUNDED, color=ft.Colors.ON_SURFACE_VARIANT),
                                ft.Text(f"No games on {day}", color=ft.Colors.ON_SURFACE_VARIANT)]))
        # live games first, then upcoming, then finished
        order = {LIVE: 0, SCHEDULED: 1, FINAL: 2}
        games = sorted(games, key=lambda g: order.get(g["status"], 3))
        return ft.ResponsiveRow(
            [ft.Container(_game_card(g, app), col={"xs": 12, "md": 6, "xl": 4}) for g in games],
            spacing=14,
            run_spacing=14,
        )


# ---------------------------------------------------------------- parsing


def _team_from_card(team: dict) -> dict:
    return {
        "name": team.get("teamName", ""),
        "code": team.get("teamTricode", ""),
        "score": team.get("score", 0),
        "record": team.get("teamSubtitle", ""),
        "periods": [p.get("score", 0) for p in team.get("periods") or []],
    }


def _game_from_card(c: dict) -> dict:
    return {
        "id": c["gameId"],
        "status": c.get("gameStatus", SCHEDULED),
        "status_text": (c.get("gameStatusText") or "").strip(),
        "time_utc": c.get("gameTimeUtc"),
        "info": c.get("seriesText") or c.get("info") or c.get("seasonType") or "",
        "away": _team_from_card(c.get("awayTeam") or {}),
        "home": _team_from_card(c.get("homeTeam") or {}),
        "box": None,
    }


def _stats_row(s: dict) -> dict:
    return {
        "min": (s.get("minutes") or "").split(":")[0] or "0",
        "pts": s.get("points", 0),
        "reb": s.get("reboundsTotal", 0),
        "ast": s.get("assists", 0),
        "stl": s.get("steals", 0),
        "blk": s.get("blocks", 0),
        "tov": s.get("turnovers", 0),
        "fg": f'{s.get("fieldGoalsMade", 0)}-{s.get("fieldGoalsAttempted", 0)}',
        "3pt": f'{s.get("threePointersMade", 0)}-{s.get("threePointersAttempted", 0)}',
        "ft": f'{s.get("freeThrowsMade", 0)}-{s.get("freeThrowsAttempted", 0)}',
        "pm": f'{int(s.get("plusMinusPoints") or 0):+d}',
    }


async def _fetch_box_score(app, game_id: str) -> dict:
    response = await app.client.get(f"{BASE}/game/{game_id}/box-score")
    response.raise_for_status()
    game = next_data(response.text)["props"]["pageProps"]["game"]

    def team(t: dict) -> dict:
        players = []
        for p in t.get("players") or []:
            s = p.get("statistics") or {}
            played = bool(s.get("minutes")) and s.get("minutes") not in ("0:00", "00:00")
            players.append({
                "name": p.get("nameI") or f'{p.get("firstName", "")} {p.get("familyName", "")}',
                "pos": p.get("position", ""),
                "played": played,
                "note": p.get("comment", ""),
                **_stats_row(s),
            })
        return {
            "name": f'{t.get("teamCity", "")} {t.get("teamName", "")}'.strip(),
            "code": t.get("teamTricode", ""),
            "score": t.get("score", 0),
            "players": players,
            "totals": _stats_row(t.get("statistics") or {}),
        }

    return {"away": team(game.get("awayTeam") or {}), "home": team(game.get("homeTeam") or {})}


# ---------------------------------------------------------------- UI pieces


def _live_dot() -> ft.Control:
    """A softly pulsing red dot for live games."""
    dot = ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.RED_ACCENT_400,
                       animate_opacity=900)

    def pulse(e):
        dot.opacity = 0.25 if dot.opacity == 1 else 1
        dot.update()

    dot.on_animation_end = pulse
    dot.opacity = 0.99  # kick off the first animation
    return dot


def _status_pill(game: dict, app) -> ft.Control:
    if game["status"] == LIVE:
        return ft.Container(
            ft.Row([_live_dot(), ft.Text(game["status_text"] or "LIVE", size=12,
                                         weight=ft.FontWeight.W_600, color=ft.Colors.RED_ACCENT_400)],
                   spacing=6, tight=True),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4), border_radius=50,
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.RED_ACCENT_400),
        )
    if game["status"] == FINAL:
        return pill(game["status_text"] or "Final", ft.Colors.ON_SURFACE_VARIANT)
    # scheduled: show tip-off in the phone's timezone setting
    text = game["status_text"]
    if game.get("time_utc"):
        tip = datetime.fromisoformat(game["time_utc"].replace("Z", "+00:00"))
        text = tip.astimezone(ZoneInfo(app.settings["timezone"])).strftime("%H:%M")
    return pill(text, ft.Colors.PRIMARY, icon=ft.Icons.SCHEDULE_ROUNDED)


def _team_row(team: dict, dim: bool, app) -> ft.Control:
    return ft.Row(
        [
            ft.Container(
                ft.Text(team["code"], size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY_CONTAINER),
                width=44, height=32, border_radius=10, alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.PRIMARY_CONTAINER,
            ),
            ft.Column([
                ft.Text(team["name"], size=fs(app, 16), weight=ft.FontWeight.W_600),
                ft.Text(team["record"], size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=0, expand=True),
            ft.Text(str(team["score"]), size=fs(app, 26), weight=ft.FontWeight.BOLD),
        ],
        spacing=12,
        opacity=0.5 if dim else 1,
    )


def _game_card(game: dict, app) -> ft.Control:
    away, home = game["away"], game["home"]
    final = game["status"] == FINAL
    started = game["status"] != SCHEDULED
    footer = ft.Row(
        [ft.Text("Box score", size=12, color=ft.Colors.PRIMARY, weight=ft.FontWeight.W_600),
         ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=16, color=ft.Colors.PRIMARY)],
        spacing=2, alignment=ft.MainAxisAlignment.END, visible=bool(game.get("box")),
    )
    content = ft.Column(
        [
            ft.Row([_status_pill(game, app),
                    ft.Text(game["info"], size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True,
                            text_align=ft.TextAlign.END)]),
            _team_row(away, final and away["score"] < home["score"], app),
            _team_row(home, final and home["score"] < away["score"], app),
            footer,
        ],
        spacing=10,
    )
    on_click = (lambda e: open_box_score(app, game)) if started and game.get("box") else None
    return card(content, on_click=on_click)
