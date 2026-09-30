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
from ui.widgets import empty_message, feed_row, fs, thumb

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
            return empty_message(ft.Icons.EVENT_BUSY_ROUNDED, f"No games on {day}")
        # live games first, then upcoming, then finished
        order = {LIVE: 0, SCHEDULED: 1, FINAL: 2}
        games = sorted(games, key=lambda g: order.get(g["status"], 3))
        return ft.Column([_game_row(g, app) for g in games], spacing=0)


# ---------------------------------------------------------------- parsing


def _team_from_card(team: dict) -> dict:
    return {
        "name": team.get("teamName", ""),
        "code": team.get("teamTricode", ""),
        "score": team.get("score", 0),
        "record": team.get("teamSubtitle", ""),
        "periods": [p.get("score", 0) for p in team.get("periods") or []],
        "id": team.get("teamId"),
        "leader": _leader(team.get("teamLeader") or {}),
    }


def _leader(leader: dict) -> str:
    if not leader.get("name") or str(leader.get("points", "0")) == "0":
        return ""
    return f'{leader["name"].split(" ")[-1]} {leader["points"]}'


# ESPN serves small team logos; a few of its team codes differ from the NBA's.
ESPN_CODES = {"GSW": "gs", "NOP": "no", "NYK": "ny", "SAS": "sa", "UTA": "utah", "WAS": "wsh"}


def logo_url(code: str) -> str:
    espn = ESPN_CODES.get(code, code.lower())
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nba/500/{espn}.png&w=96&h=96"


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
    dot = ft.Container(width=7, height=7, border_radius=4, bgcolor=ft.Colors.RED_ACCENT_400,
                       animate_opacity=900)

    def pulse(e):
        dot.opacity = 0.25 if dot.opacity == 1 else 1
        dot.update()

    dot.on_animation_end = pulse
    dot.opacity = 0.99  # kick off the first animation
    return dot


def _meta(game: dict, app) -> ft.Control:
    """Status line: LIVE Q3 5:21 / Final / tip-off time, plus game info."""
    size = fs(app, 12)
    if game["status"] == LIVE:
        parts = [_live_dot(), ft.Text(game["status_text"] or "LIVE", size=size, weight=ft.FontWeight.W_600,
                                      color=ft.Colors.RED_ACCENT_400)]
    elif game["status"] == FINAL:
        parts = [ft.Text(game["status_text"] or "Final", size=size, weight=ft.FontWeight.W_600,
                         color=ft.Colors.ON_SURFACE_VARIANT)]
    else:  # scheduled: tip-off in your timezone
        text = game["status_text"]
        if game.get("time_utc"):
            tip = datetime.fromisoformat(game["time_utc"].replace("Z", "+00:00"))
            text = tip.astimezone(ZoneInfo(app.settings["timezone"])).strftime("%H:%M")
        parts = [ft.Text(text, size=size, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY)]
    if game["info"]:
        parts.append(ft.Text("· " + game["info"], size=size, color=ft.Colors.ON_SURFACE_VARIANT,
                             max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
    return ft.Row(parts, spacing=6, tight=True)


def _game_row(game: dict, app) -> ft.Control:
    """Away logo | Pistons 118 - 100 Hornets | home logo  (the loser is dimmed when final)."""
    away, home = game["away"], game["home"]
    final = game["status"] == FINAL
    started = game["status"] != SCHEDULED

    def team_span(team, other):
        lost = final and team["score"] < other["score"]
        return ft.TextSpan(team["name"], ft.TextStyle(
            color=ft.Colors.ON_SURFACE_VARIANT if lost else None,
            weight=ft.FontWeight.W_500 if lost else ft.FontWeight.BOLD))

    if started:
        title = [team_span(away, home), ft.TextSpan(f'  {away["score"]} – {home["score"]}  '), team_span(home, away)]
    else:
        title = [team_span(away, home), ft.TextSpan("  @  "), team_span(home, away)]

    leaders = " · ".join(x for x in [away["leader"], home["leader"]] if x)
    subtitle = leaders or f'{away["record"]} · {home["record"]}'
    return feed_row(
        app,
        title,
        meta=_meta(game, app),
        subtitle=subtitle,
        leading=thumb(logo_url(away["code"]), cover=False),
        trailing=thumb(logo_url(home["code"]), cover=False),
        center=True,
        on_click=(lambda e: open_box_score(app, "nba", game)) if started and game.get("box") else None,
    )
