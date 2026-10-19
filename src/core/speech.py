"""
Reading aloud with the phone's own voice engine (via the flet_tts extension).

- One Speaker per app; only one thing is read at a time (a new request stops the previous).
- Text is cleaned (Hebrew abbreviations expanded) and split into chunks the engine accepts.
- SpeakButton: the shared 🔊 / ⏹ button used in every section.
"""

import asyncio
import json
import re
from pathlib import Path

import flet as ft

try:  # the extension only works inside the built app (Android); on the PC it is a no-op
    from flet_tts import Tts
except ImportError:  # pragma: no cover
    Tts = None

HEBREW, ENGLISH = "he-IL", "en-US"
CHUNK = 3000  # Android's engine accepts ~4000 characters per utterance

_ABBREVIATIONS: dict[str, str] | None = None
_HEB_LETTER = "א-ת"


def _abbreviations() -> dict[str, str]:
    global _ABBREVIATIONS
    if _ABBREVIATIONS is None:
        path = Path(__file__).with_name("abbreviations.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        # longest first, so "רבותינו ז"ל" wins over "ז"ל"
        _ABBREVIATIONS = dict(sorted(((k, v) for k, v in data.items() if not k.startswith("_")),
                                     key=lambda kv: -len(kv[0])))
    return _ABBREVIATIONS


def expand_abbreviations(text: str) -> str:
    """ואכמ"ל -> ואין כאן מקום להאריך, etc. Accepts both " and ״ (and ' / ׳)."""
    text = text.replace("״", '"').replace("׳", "'").replace("”", '"').replace("“", '"')
    for short, full in _abbreviations().items():
        if short == full:
            continue
        pattern = rf"(?<![{_HEB_LETTER}]){re.escape(short)}(?![{_HEB_LETTER}])"
        text = re.sub(pattern, full, text)
    return text


def chunks(parts: list[str], size: int = CHUNK) -> list[str]:
    """Join short parts and split long ones so each piece fits the engine's limit."""
    out, current = [], ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        while len(part) > size:  # split a long part at a sentence end or space
            cut = max(part.rfind(". ", 0, size), part.rfind(": ", 0, size), part.rfind(" ", 0, size))
            cut = cut + 1 if cut > 0 else size
            out.append(part[:cut])
            part = part[cut:].strip()
        if len(current) + len(part) + 2 > size and current:
            out.append(current)
            current = ""
        current = f"{current}\n{part}" if current else part
    if current:
        out.append(current)
    return out


class Speaker:
    def __init__(self, app):
        self.app = app
        self._tts = None
        self._done = asyncio.Event()
        self._run = 0  # increases on every new request / stop -> older loops quit
        self.active_button: "SpeakButton | None" = None

    @property
    def available(self) -> bool:
        return Tts is not None

    def _engine(self):
        if self._tts is None and Tts is not None:
            self._tts = Tts(on_complete=self._finished, on_cancel=self._finished,
                            on_error=self._failed)
        return self._tts

    def _finished(self, e=None):
        self._done.set()

    def _failed(self, e=None):
        self._done.set()
        self.app.toast(f"Voice error: {getattr(e, 'data', '')}")

    async def say(self, parts: list[str], language: str = HEBREW, button: "SpeakButton | None" = None):
        """Read parts in order. Stops whatever was being read before."""
        await self.stop()
        engine = self._engine()
        if engine is None:
            self.app.toast("Reading aloud works in the phone app")
            return
        self._run += 1
        run = self._run
        self._set_button(button)
        if language == HEBREW:
            parts = [expand_abbreviations(p) for p in parts]
        try:
            for piece in chunks(parts):
                if run != self._run:
                    return
                self._done.clear()
                await engine.speak(piece, language=language, rate=self.app.settings["speech_rate"])
                # wait until this piece is spoken (generous timeout: ~12 chars per second)
                try:
                    await asyncio.wait_for(self._done.wait(), timeout=30 + len(piece) / 6)
                except asyncio.TimeoutError:
                    pass
        finally:
            if run == self._run:
                self._set_button(None)

    async def stop(self):
        self._run += 1
        self._set_button(None)
        if self._tts is not None:
            try:
                await self._tts.stop()
            except Exception:
                pass
        self._done.set()

    def _set_button(self, button):
        old, self.active_button = self.active_button, button
        for b in (old, button):
            if b is not None:
                b.refresh()


class SpeakButton(ft.IconButton):
    """🔊 reads `get_parts()` aloud; while reading it turns into ⏹ (tap to stop)."""

    def __init__(self, app, get_parts, language=HEBREW, size=22, tooltip="Read aloud"):
        super().__init__(icon=ft.Icons.VOLUME_UP_ROUNDED, icon_size=size, tooltip=tooltip,
                         icon_color=ft.Colors.PRIMARY)
        self._app = app
        self._get_parts = get_parts
        self._language = language
        self.on_click = self._clicked

    async def _clicked(self, e):
        speaker = self._app.speaker
        if speaker.active_button is self:
            await speaker.stop()
        else:
            await speaker.say(self._get_parts(), self._language, button=self)

    def refresh(self):
        reading = self._app.speaker.active_button is self
        self.icon = ft.Icons.STOP_CIRCLE_ROUNDED if reading else ft.Icons.VOLUME_UP_ROUNDED
        self.icon_color = ft.Colors.ERROR if reading else ft.Colors.PRIMARY
        try:
            self.update()
        except Exception:  # not on screen (e.g. its window was rebuilt)
            pass
