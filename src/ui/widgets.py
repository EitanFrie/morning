"""
Small reusable design pieces, so every section looks like part of one app.
Change the look of the whole app from here.
"""

import math

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


def skeleton(rows=6, image=False) -> ft.Control:
    """Shimmering placeholder rows (same shape as feed_row) shown while loading."""

    def bar(width=None, height=14):
        return ft.Container(
            width=width, height=height, border_radius=7, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
        )

    widths = [220, 160, 250, 190, 140, 230]
    items = []
    for i in range(rows):
        parts = [ft.Container(width=THUMB, height=THUMB, border_radius=12,
                              bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST)] if image else []
        parts.append(ft.Column([bar(60, 10), bar(widths[i % len(widths)], 16)], spacing=8, expand=True))
        items.append(ft.Container(ft.Row(parts, spacing=14), padding=ROW_PADDING))
    return ft.Shimmer(
        content=ft.Column(items, spacing=0),
        base_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        highlight_color=ft.Colors.SURFACE_CONTAINER_LOW,
        period=1300,
    )


# ---------------------------------------------------------------- the one feed row

THUMB = 52  # size of the image slots on both sides of a row
ROW_PADDING = ft.Padding.symmetric(horizontal=16, vertical=12)


def thumb(src: str | None, cover=True) -> ft.Control:
    """An image for a row's side slot (article photo -> cover, team logo -> contain)."""
    if not src:
        return ft.Container(width=THUMB, height=THUMB)
    return ft.Container(
        ft.Image(src=src, width=THUMB, height=THUMB, fit=ft.BoxFit.COVER if cover else ft.BoxFit.CONTAIN,
                 fade_in_animation=ft.Animation(250),
                 error_content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED, color=ft.Colors.OUTLINE)),
        width=THUMB, height=THUMB, border_radius=12, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST if cover else None,
    )


def feed_row(
    app,
    title: str | list[ft.TextSpan],
    *,
    meta: ft.Control | str | None = None,
    subtitle: str | None = None,
    leading: ft.Control | None = None,
    trailing: ft.Control | None = None,
    on_click=None,
    details: ft.Control | None = None,
    expanded: bool = False,
    on_toggle=None,
    title_bold: bool = True,
    center: bool = False,
    title_lines: int | None = 2,
) -> ft.Control:
    """
    The single item format used by EVERY section:

        [leading image]  meta line (time / status / category)   [trailing image]
                         Headline
                         subtitle (optional)

    - on_click: open something (box score, article...)
    - details:  extra content revealed under the row when tapped (news flashes);
                on_toggle(is_open) lets the caller remember the state.
    """
    middle: list[ft.Control] = []
    align = ft.TextAlign.CENTER if center else None  # center=True: centered text (NBA)
    if meta is not None:
        middle.append(meta if isinstance(meta, ft.Control) else
                      ft.Text(meta, text_align=align, size=fs(app, 12), color=ft.Colors.PRIMARY, weight=ft.FontWeight.W_600))
    # title: plain text, or a list of TextSpans for mixed styling (e.g. dimmed losing team)
    spans = title if isinstance(title, list) else None
    middle.append(ft.Text(None if spans else title, spans=spans, size=fs(app, 16), max_lines=title_lines, text_align=align,
                          overflow=ft.TextOverflow.ELLIPSIS if title_lines else None,
                          weight=ft.FontWeight.W_600 if title_bold else None))
    if subtitle:
        middle.append(ft.Text(subtitle, text_align=align, size=fs(app, 12.5), color=ft.Colors.ON_SURFACE_VARIANT,
                              max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))

    row_parts: list[ft.Control] = []
    if leading:
        row_parts.append(leading)
    row_parts.append(ft.Column(middle, spacing=3, expand=True,
                               horizontal_alignment=ft.CrossAxisAlignment.CENTER if center else None))
    if trailing:
        row_parts.append(trailing)

    chevron = None
    if details is not None:
        chevron = ft.Icon(ft.Icons.EXPAND_MORE_ROUNDED, size=20, color=ft.Colors.ON_SURFACE_VARIANT,
                          rotate=math.pi if expanded else 0, animate_rotation=FAST)
        row_parts.append(chevron)
        details_box = ft.Container(details, visible=expanded, padding=ft.Padding.only(top=8))

    content: list[ft.Control] = [ft.Row(row_parts, spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)]
    if details is not None:
        content.append(details_box)

    box = ft.Container(
        content=ft.Column(content, spacing=0),
        padding=ROW_PADDING,
        ink=bool(on_click or details is not None),
        animate_size=FAST,
        border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.45, ft.Colors.OUTLINE_VARIANT))),
    )
    if details is not None:
        def toggle(e):
            details_box.visible = not details_box.visible
            chevron.rotate = math.pi if details_box.visible else 0
            if on_toggle:
                on_toggle(details_box.visible)
            box.update()
        box.on_click = toggle
    elif on_click:
        box.on_click = on_click
    return box


def error_box(message: str, on_retry) -> ft.Control:
    return ft.Container(
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
        alignment=ft.Alignment.CENTER,
    )


def empty_message(icon, text: str) -> ft.Control:
    return ft.Container(
        ft.Column([ft.Icon(icon, size=36, color=ft.Colors.OUTLINE),
                   ft.Text(text, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER)],
                  horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
        padding=40,
        alignment=ft.Alignment.CENTER,
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
