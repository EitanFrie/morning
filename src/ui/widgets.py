"""
Small reusable design pieces, so every section looks like part of one app.
Change the look of the whole app from here.
"""

import flet as ft

RADIUS = 18
FAST = ft.Animation(220, ft.AnimationCurve.EASE_OUT)
SMOOTH = ft.Animation(350, ft.AnimationCurve.EASE_IN_OUT)


def fs(app, size: float) -> float:
    """Font size scaled by the user's text-size preference."""
    return round(size * app.settings["text_scale"], 1)


def _is_hover(e) -> bool:
    return e.data in (True, "true")


def card(content: ft.Control, on_click=None, padding=16, **kwargs) -> ft.Container:
    """A rounded surface. Clickable cards get a ripple and a soft hover lift."""
    box = ft.Container(
        content=content,
        padding=padding,
        border_radius=RADIUS,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        **kwargs,
    )
    if on_click:
        box.ink = True
        box.on_click = on_click
        box.animate_scale = FAST

        def hover(e):
            box.scale = 1.015 if _is_hover(e) else 1
            box.update()

        box.on_hover = hover
    return box


def pill(text: str, color=ft.Colors.PRIMARY, icon=None, size=12) -> ft.Container:
    """A small rounded label, e.g. a category or 'LIVE'."""
    parts = []
    if icon:
        parts.append(ft.Icon(icon, size=size + 2, color=color))
    parts.append(ft.Text(text, size=size, weight=ft.FontWeight.W_600, color=color))
    return ft.Container(
        content=ft.Row(parts, spacing=4, tight=True),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=50,
        bgcolor=ft.Colors.with_opacity(0.12, color),
    )


def icon_badge(icon, color, size=40) -> ft.Container:
    """A colored rounded square with an icon - the logo of each section."""
    return ft.Container(
        content=ft.Icon(icon, color=ft.Colors.WHITE, size=size * 0.55),
        width=size,
        height=size,
        border_radius=size * 0.32,
        alignment=ft.Alignment.CENTER,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[ft.Colors.with_opacity(0.75, color), color],
        ),
    )


class RoundButton(ft.Container):
    """A modern round icon button that can turn into a spinner while busy."""

    def __init__(self, icon, on_click, tooltip=None, size=40):
        self._icon = ft.Icon(icon, size=size * 0.5, color=ft.Colors.ON_PRIMARY_CONTAINER)
        self._spinner = ft.ProgressRing(width=size * 0.45, height=size * 0.45, stroke_width=2.5)
        self._switcher = ft.AnimatedSwitcher(
            content=self._icon,
            duration=250,
            reverse_duration=150,
            transition=ft.AnimatedSwitcherTransition.SCALE,
        )
        super().__init__(
            content=self._switcher,
            width=size,
            height=size,
            border_radius=size / 2,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            ink=True,
            on_click=on_click,
            tooltip=tooltip,
            animate_scale=FAST,
        )
        self.on_hover = self._hover

    def _hover(self, e):
        self.scale = 1.08 if _is_hover(e) else 1
        self.update()

    def set_busy(self, busy: bool):
        self._switcher.content = self._spinner if busy else self._icon
        self.disabled = busy


def skeleton(lines=4, with_image=False) -> ft.Control:
    """Shimmering grey placeholder shown while a section loads for the first time."""

    def bar(width=None, height=14):
        return ft.Container(
            width=width, height=height, border_radius=8, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
        )

    rows = []
    if with_image:
        rows.append(bar(height=140))
    widths = [None, 260, None, 180, 220, 140]
    for i in range(lines):
        rows.append(bar(widths[i % len(widths)]))
    return ft.Shimmer(
        content=card(ft.Column(rows, spacing=12)),
        base_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        highlight_color=ft.Colors.SURFACE_CONTAINER_LOW,
        period=1300,
    )


def error_box(message: str, on_retry) -> ft.Control:
    return card(
        ft.Column(
            [
                ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED, size=36, color=ft.Colors.ERROR),
                ft.Text("Couldn't load this section", weight=ft.FontWeight.W_600),
                ft.Text(message, size=12, color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER, max_lines=3),
                ft.FilledTonalButton("Try again", icon=ft.Icons.REFRESH_ROUNDED, on_click=on_retry),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        padding=24,
    )


def time_ago(minutes: float | None) -> str:
    if minutes is None:
        return "Not loaded yet"
    if minutes < 1:
        return "Updated just now"
    if minutes < 60:
        return f"Updated {int(minutes)} min ago"
    if minutes < 60 * 24:
        return f"Updated {int(minutes // 60)} h ago"
    return f"Updated {int(minutes // (60 * 24))} days ago"
