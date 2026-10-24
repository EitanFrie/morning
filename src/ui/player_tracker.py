"""
NBA player tracker (top part of the NBA News window) + the draggable split between the parts.

- Tracked players live in settings["tracked_players"]: [{"id", "name", "team"}].
- Last night's stats: the NBA News refresh downloads the box scores of the tracked players'
  games on the most recent day with finished games (see nba_news._tracked_player_lines).
- Adding a player: pick a team, then a player from its roster (nba.com/team/<id>/roster -
  ~0.5 MB, only when you add someone).
"""

from pathlib import Path

import flet as ft

from core.http import next_data
from core.storage import data_dir
from ui.widgets import fs, thumb

ROSTER = "https://www.nba.com/team/{}/roster"

# NBA team ids (stable) -> (tricode, name)
TEAMS = {
    1610612737: ("ATL", "Hawks"), 1610612738: ("BOS", "Celtics"), 1610612751: ("BKN", "Nets"),
    1610612766: ("CHA", "Hornets"), 1610612741: ("CHI", "Bulls"), 1610612739: ("CLE", "Cavaliers"),
    1610612742: ("DAL", "Mavericks"), 1610612743: ("DEN", "Nuggets"), 1610612765: ("DET", "Pistons"),
    1610612744: ("GSW", "Warriors"), 1610612745: ("HOU", "Rockets"), 1610612754: ("IND", "Pacers"),
    1610612746: ("LAC", "Clippers"), 1610612747: ("LAL", "Lakers"), 1610612763: ("MEM", "Grizzlies"),
    1610612748: ("MIA", "Heat"), 1610612749: ("MIL", "Bucks"), 1610612750: ("MIN", "Timberwolves"),
    1610612740: ("NOP", "Pelicans"), 1610612752: ("NYK", "Knicks"), 1610612760: ("OKC", "Thunder"),
    1610612753: ("ORL", "Magic"), 1610612755: ("PHI", "76ers"), 1610612756: ("PHX", "Suns"),
    1610612757: ("POR", "Trail Blazers"), 1610612758: ("SAC", "Kings"), 1610612759: ("SAS", "Spurs"),
    1610612761: ("TOR", "Raptors"), 1610612762: ("UTA", "Jazz"), 1610612764: ("WAS", "Wizards"),
}


# ---------------------------------------------------------------- split view


class SplitView(ft.Column):
    """Two parts on top of each other with a bar between them: drag it, or tap it to step
    through sizes.
    `ratio` = share of the TOP part (0.1 - 0.85); on_ratio(ratio) is called when you let go."""

    def __init__(self, top: ft.Control, bottom: ft.Control, ratio: float, on_ratio):
        self._ratio = min(0.85, max(0.1, ratio))
        self._height = 0.0
        self._on_ratio = on_ratio
        self._top = ft.Container(top, expand=self._share(self._ratio))
        self._bottom = ft.Container(bottom, expand=self._share(1 - self._ratio))
        handle = ft.GestureDetector(
            content=ft.Container(
                ft.Container(width=44, height=5, border_radius=3, bgcolor=ft.Colors.OUTLINE),
                height=22, alignment=ft.Alignment.CENTER,
                border=ft.Border(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                 bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            ),
            mouse_cursor=ft.MouseCursor.RESIZE_ROW,
            drag_interval=30,
            on_vertical_drag_update=self._drag,
            on_vertical_drag_end=self._dropped,
            on_tap=self._step,  # tap the bar: 20% -> 35% -> 50% -> 20% (players part)
        )
        super().__init__([self._top, handle, self._bottom], spacing=0, expand=True,
                         on_size_change=self._sized)

    @staticmethod
    def _share(fraction: float) -> int:
        return max(1, int(fraction * 1000))

    def _sized(self, e):
        self._height = e.height

    def _drag(self, e):
        delta = e.primary_delta if e.primary_delta is not None else (e.local_delta.y if e.local_delta else None)
        if delta is None:
            return
        if not self._height:  # size not reported yet: estimate from the screen
            self._height = (self.page.height or 800) * 0.7
        self._ratio = min(0.85, max(0.1, self._ratio + delta / self._height))
        self._top.expand = self._share(self._ratio)
        self._bottom.expand = self._share(1 - self._ratio)
        self.update()

    def _step(self, e):
        steps = [0.2, 0.35, 0.5]
        self._ratio = next((s for s in steps if s > self._ratio + 0.01), steps[0])
        self._top.expand = self._share(self._ratio)
        self._bottom.expand = self._share(1 - self._ratio)
        self.update()
        self._on_ratio(self._ratio)

    def _dropped(self, e):
        self._on_ratio(round(self._ratio, 3))


# ---------------------------------------------------------------- tracker


def tracker_panel(app, section_id: str, data: dict, editing: bool, on_edit_toggle) -> ft.Control:
    """data = NBA News data: {"players": {id: {"played", "text", "team"}}, "players_day": "YYYY-MM-DD"}.
    Normal view: only the players who PLAYED that night. Edit view: everyone, with ▲▼ to reorder
    and ✕ to remove."""
    players = app.settings["tracked_players"]
    lines = data.get("players") or {}

    def save(new_list):
        app.settings["tracked_players"] = new_list
        _rerender(app, section_id)

    def move(index, step):
        j = index + step
        if 0 <= j < len(players):
            new = list(players)
            new[index], new[j] = new[j], new[index]
            save(new)

    def remove(player):
        save([p for p in players if p["id"] != player["id"]])

    rows = []
    for i, player in enumerate(players):
        info = lines.get(str(player["id"])) or {}
        if isinstance(info, str):  # data cached by an older version
            info = {"played": "PTS" in info, "text": info}
        if not editing and not info.get("played"):
            continue  # didn't play (injury, coach's decision, no game) -> not shown
        text = info.get("text") or "No game"
        order = ft.Column([
            ft.IconButton(ft.Icons.KEYBOARD_ARROW_UP_ROUNDED, icon_size=20, tooltip="Move up",
                          disabled=i == 0, on_click=lambda e, i=i: move(i, -1),
                          style=ft.ButtonStyle(padding=0), width=28, height=24),
            ft.IconButton(ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED, icon_size=20, tooltip="Move down",
                          disabled=i == len(players) - 1, on_click=lambda e, i=i: move(i, 1),
                          style=ft.ButtonStyle(padding=0), width=28, height=24),
        ], spacing=0, visible=editing)
        rows.append(ft.Container(
            ft.Row([
                order,
                _photo(app, player),
                ft.Column([ft.Text(player["name"], size=fs(app, 15), weight=ft.FontWeight.W_600),
                           ft.Text(f'{player["team"]} · {text}' if editing else text, size=fs(app, 12.5),
                                   color=ft.Colors.PRIMARY if info.get("played") else ft.Colors.ON_SURFACE_VARIANT)],
                          spacing=1, expand=True),
                ft.IconButton(ft.Icons.CLOSE_ROUNDED, tooltip="Stop tracking", visible=editing,
                              on_click=lambda e, p=player: remove(p)),
            ], spacing=10),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        ))
    if not players:
        rows.append(ft.Container(ft.Text("No players tracked yet - tap ✏️ to add",
                                         color=ft.Colors.ON_SURFACE_VARIANT), padding=14))
    elif not rows:
        rows.append(ft.Container(ft.Text("None of your players played",
                                         color=ft.Colors.ON_SURFACE_VARIANT), padding=14))

    header = ft.Row([
        ft.Text("Players · " + (_day_label(data.get("players_day")) or "last night"),
                size=fs(app, 14), weight=ft.FontWeight.BOLD, expand=True),
        ft.TextButton("Add player", icon=ft.Icons.PERSON_ADD_ALT_1_ROUNDED, visible=editing,
                      on_click=lambda e: open_team_picker(app, section_id)),
        ft.IconButton(ft.Icons.CHECK_ROUNDED if editing else ft.Icons.EDIT_ROUNDED,
                      tooltip="Done" if editing else "Edit players", on_click=lambda e: on_edit_toggle()),
    ])
    return ft.Column([ft.Container(header, padding=ft.Padding.only(left=14, right=6, top=4)), *rows], spacing=0)


# ---------------------------------------------------------------- head photos

HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/{}.png"  # ~15 KB each


def _headshot_file(player_id) -> Path:
    folder = data_dir() / "headshots"
    folder.mkdir(exist_ok=True)
    return folder / f"{player_id}.png"


async def download_headshots(app):
    """Download the photo of each tracked player once; kept on the phone. Others are deleted."""
    wanted = {str(p["id"]) for p in app.settings["tracked_players"]}
    for player_id in wanted:
        path = _headshot_file(player_id)
        if path.exists():
            continue
        try:
            response = await app.client.get(HEADSHOT.format(player_id))
            if response.status_code == 200 and response.content[1:4] == b"PNG":
                path.write_bytes(response.content)
        except Exception:
            pass  # no photo -> the team logo is shown
    for path in (data_dir() / "headshots").glob("*.png"):
        if path.stem not in wanted:  # player removed from the list
            path.unlink(missing_ok=True)


def _photo(app, player) -> ft.Control:
    path = _headshot_file(player["id"])
    if path.exists():
        return ft.Container(
            ft.Image(src=path.read_bytes(), fit=ft.BoxFit.COVER, width=52, height=52),
            width=52, height=52, border_radius=26, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        )
    return thumb(_logo(player["team"]), cover=False)


def _day_label(day: str | None) -> str:
    if not day:
        return ""
    from datetime import date
    return date.fromisoformat(day).strftime("%a %d/%m")


def _logo(code: str) -> str:
    from sources.nba import logo_url
    return logo_url(code)


def _rerender(app, section_id, refetch=False):
    app.sections[section_id].rerender()
    app.page.update()
    if refetch:  # a new player: download his stats now
        app.page.run_task(app.refresh, app.sections[section_id].source)


# ---------------------------------------------------------------- adding a player


def open_team_picker(app, section_id: str):
    """Step 1: choose the team."""
    teams = sorted(TEAMS.items(), key=lambda kv: kv[1][1])
    grid = ft.GridView(
        [ft.Container(
            ft.Column([thumb(_logo(code), cover=False), ft.Text(name, size=11, text_align=ft.TextAlign.CENTER)],
                      spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ink=True, border_radius=10, padding=4,
            on_click=lambda e, tid=tid, code=code: app.page.run_task(_open_roster, app, section_id, tid, code))
         for tid, (code, name) in teams],
        max_extent=90, child_aspect_ratio=0.9, spacing=6, run_spacing=6,
    )
    app.page.show_dialog(ft.AlertDialog(
        title=ft.Text("Choose the team"),
        content=ft.Container(grid, width=380, height=420),
        actions=[ft.TextButton("Cancel", on_click=lambda e: app.page.pop_dialog())],
    ))


async def _open_roster(app, section_id: str, team_id: int, code: str):
    """Step 2: choose the player from the team's roster."""
    app.page.pop_dialog()
    listing = ft.Column([ft.Row([ft.ProgressRing(width=20, height=20), ft.Text("Loading roster…")])],
                        scroll=ft.ScrollMode.AUTO, tight=True)
    dialog = ft.AlertDialog(title=ft.Text(f"{TEAMS[team_id][1]} roster"),
                            content=ft.Container(listing, width=380, height=420),
                            actions=[ft.TextButton("Back", on_click=lambda e: (app.page.pop_dialog(),
                                                                                open_team_picker(app, section_id))),
                                     ft.TextButton("Cancel", on_click=lambda e: app.page.pop_dialog())])
    app.page.show_dialog(dialog)
    try:
        response = await app.client.get(ROSTER.format(team_id))
        response.raise_for_status()
        roster = next_data(response.text)["props"]["pageProps"]["team"]["roster"]
    except Exception as ex:
        listing.controls = [ft.Text(f"Could not load the roster: {ex}", color=ft.Colors.ERROR)]
        dialog.update()
        return

    tracked = {p["id"] for p in app.settings["tracked_players"]}

    def add(player):
        app.settings["tracked_players"] = app.settings["tracked_players"] + [
            {"id": player["PLAYER_ID"], "name": player["PLAYER"], "team": code}]
        app.page.pop_dialog()
        _rerender(app, section_id, refetch=True)

    listing.controls = [
        ft.ListTile(
            leading=ft.Text(f'#{p.get("NUM") or ""}', width=36),
            title=ft.Text(p["PLAYER"]),
            subtitle=ft.Text(p.get("POSITION") or ""),
            trailing=ft.Icon(ft.Icons.CHECK_ROUNDED) if p["PLAYER_ID"] in tracked else None,
            on_click=(lambda e, p=p: add(p)) if p["PLAYER_ID"] not in tracked else None,
        )
        for p in sorted(roster, key=lambda p: p["PLAYER"])
    ]
    dialog.update()
