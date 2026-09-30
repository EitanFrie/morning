"""Box score screen: score header, line score, then each team's table (away above home)."""

from typing import TYPE_CHECKING

import flet as ft

from ui.widgets import card, fs

if TYPE_CHECKING:
    from app import App

COLUMNS = [  # (header, key in the player dict)
    ("MIN", "min"), ("PTS", "pts"), ("REB", "reb"), ("AST", "ast"), ("STL", "stl"),
    ("BLK", "blk"), ("TO", "tov"), ("FG", "fg"), ("3PT", "3pt"), ("FT", "ft"), ("+/-", "pm"),
]


def open_box_score(app: "App", game: dict):
    box = game["box"]
    away, home = game["away"], game["home"]
    view = ft.View(
        route="/boxscore",
        padding=0,
        appbar=ft.AppBar(title=ft.Text(f'{away["code"]} @ {home["code"]}')),
        controls=[
            ft.ListView(
                [
                    _score_header(game, app),
                    _line_score(game),
                    _team_table(box["away"], app),
                    _team_table(box["home"], app),
                    ft.Container(height=30),
                ],
                padding=16,
                spacing=18,
                expand=True,
            )
        ],
    )
    app.push_view(view)


def _score_header(game: dict, app) -> ft.Control:
    away, home = game["away"], game["home"]

    def side(team):
        return ft.Column(
            [
                ft.Text(team["code"], size=fs(app, 15), weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(str(team["score"]), size=fs(app, 40), weight=ft.FontWeight.BOLD),
                ft.Text(team["name"], size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            expand=True,
        )

    return card(
        ft.Row(
            [
                side(away),
                ft.Column(
                    [ft.Text(game["status_text"], weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY),
                     ft.Text(game["info"], size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                             text_align=ft.TextAlign.CENTER)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                side(home),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=20,
    )


def _table(columns: list[str], rows: list[ft.DataRow]) -> ft.Control:
    table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text(c), numeric=i > 0) for i, c in enumerate(columns)],
        rows=rows,
        column_spacing=18,
        horizontal_margin=12,
        heading_row_height=38,
        data_row_min_height=36,
        data_row_max_height=40,
        heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGH,
        heading_text_style=ft.TextStyle(size=12, weight=ft.FontWeight.BOLD,
                                        color=ft.Colors.ON_SURFACE_VARIANT),
        divider_thickness=0.4,
    )
    # Scroll sideways on narrow phones; on tablets it simply fits.
    return ft.Container(
        ft.Row([table], scroll=ft.ScrollMode.AUTO),
        border_radius=14,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


def _line_score(game: dict) -> ft.Control:
    away, home = game["away"], game["home"]
    n = max(len(away["periods"]), len(home["periods"]))
    headers = ["TEAM"] + [str(i + 1) if i < 4 else f"OT{i - 3}" for i in range(n)] + ["T"]

    def row(team):
        cells = [team["code"]] + [str(p) for p in team["periods"]] + [""] * (n - len(team["periods"]))
        cells.append(str(team["score"]))
        return ft.DataRow([
            ft.DataCell(ft.Text(v, weight=ft.FontWeight.BOLD if i in (0, len(cells) - 1) else None))
            for i, v in enumerate(cells)
        ])

    return _table(headers, [row(away), row(home)])


def _team_table(team: dict, app) -> ft.Control:
    rows = []
    for i, p in enumerate(team["players"]):
        starter = bool(p["pos"])
        name = ft.Row(
            [ft.Text(p["name"], weight=ft.FontWeight.W_600 if starter else None),
             ft.Text(p["pos"], size=11, color=ft.Colors.ON_SURFACE_VARIANT)],
            spacing=6, tight=True,
        )
        if p["played"]:
            cells = [ft.DataCell(name)] + [ft.DataCell(ft.Text(str(p[key]))) for _, key in COLUMNS]
        else:  # did not play: show the reason in the MIN column, blanks elsewhere
            note = (p.get("note") or "DNP").split(" - ")[0]
            cells = [ft.DataCell(name), ft.DataCell(ft.Text(note, size=11, color=ft.Colors.ON_SURFACE_VARIANT))]
            cells += [ft.DataCell(ft.Text("")) for _ in COLUMNS[1:]]
        stripe = ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE) if i % 2 else None
        rows.append(ft.DataRow(cells, color=stripe))

    totals = team["totals"]
    rows.append(ft.DataRow(
        [ft.DataCell(ft.Text("TOTAL", weight=ft.FontWeight.BOLD))]
        + [ft.DataCell(ft.Text("" if key in ("min", "pm") else str(totals[key]), weight=ft.FontWeight.BOLD))
           for _, key in COLUMNS],
        color=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
    ))

    title = ft.Row(
        [
            ft.Container(ft.Text(team["code"], size=12, weight=ft.FontWeight.BOLD,
                                 color=ft.Colors.ON_PRIMARY_CONTAINER),
                         width=44, height=30, border_radius=10, alignment=ft.Alignment.CENTER,
                         bgcolor=ft.Colors.PRIMARY_CONTAINER),
            ft.Text(team["name"], size=fs(app, 18), weight=ft.FontWeight.BOLD, expand=True),
            ft.Text(str(team["score"]), size=fs(app, 22), weight=ft.FontWeight.BOLD),
        ],
        spacing=12,
    )
    return ft.Column([title, _table(["PLAYER"] + [c for c, _ in COLUMNS], rows)], spacing=10)
