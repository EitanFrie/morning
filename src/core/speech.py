"""
Reading aloud with the phone's own voice engine (via the flet_tts extension).

- One Speaker per app; only one thing is read at a time (a new request stops the previous).
- Hebrew text is prepared first: God's name -> "השם", abbreviations expanded (also with a
  prefix letter: וא"י -> וארץ ישראל), long text split into chunks the engine accepts.
- SpeakButton: the shared 🔊 / ⏹ button. Buttons are identified by a KEY (not the object),
  so a button that was re-created by a refresh still knows it is the one reading.
- Abbreviations = built-in list (abbreviations.json) + the ones you taught the app
  (settings["user_abbreviations"]); yours win.
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
CHUNK = 400  # sentence-sized pieces: a failure costs one sentence (retried), pause/resume is exact

LETTER = "א-ת"
MARKS = "֑-ׇ"          # nikud + cantillation
PREFIXES = "ובלכמהש"             # one-letter prefixes: ו and, ב in, ל to, כ as, מ from, ה the, ש that
_BUILT_IN: dict[str, str] | None = None

# יהוה with any vowel marks, optionally after prefix letters (לַיהוָה, וַיהוָה...)
_TETRAGRAMMATON = re.compile(
    rf"(?<![{LETTER}])((?:[{PREFIXES}][{MARKS}]*){{0,2}})"
    rf"י[{MARKS}]*ה[{MARKS}]*ו[{MARKS}]*ה[{MARKS}]*(?![{LETTER}])"
)
# An abbreviation as written: letters + " + one letter (רש"י) or letters + ' (וכו')
ABBREVIATION = re.compile(rf"(?<![{LETTER}])[{LETTER}]{{1,6}}(?:\"[{LETTER}]|'(?![{LETTER}]))")


def _built_in() -> dict[str, str]:
    global _BUILT_IN
    if _BUILT_IN is None:
        data = json.loads(Path(__file__).with_name("abbreviations.json").read_text(encoding="utf-8"))
        _BUILT_IN = {k: v for k, v in data.items() if not k.startswith("_")}
    return _BUILT_IN


def normalize_quotes(text: str) -> str:
    return (text.replace("״", '"').replace("׳", "'").replace("”", '"')
            .replace("“", '"').replace("’", "'"))


def all_abbreviations(settings) -> dict[str, str]:
    """YOUR abbreviations first (they always win - even over a longer built-in phrase),
    then the built-in list; each group longest first ('רבותינו ז"ל' before 'ז"ל')."""
    user = dict(settings["user_abbreviations"]) if settings else {}
    built_in = {k: v for k, v in _built_in().items() if k not in user}
    by_length = lambda table: sorted(table.items(), key=lambda kv: -len(kv[0]))  # noqa: E731
    return dict(by_length(user) + by_length(built_in))


def known(abbreviation: str, settings) -> bool:
    """True if the abbreviation (possibly with a prefix letter) has a meaning."""
    table = all_abbreviations(settings)
    word = normalize_quotes(abbreviation)
    for cut in range(0, 3):
        if cut and (len(word) <= cut + 1 or word[cut - 1] not in PREFIXES):
            break
        if word[cut:] in table:
            return True
    return word in (settings["ignored_abbreviations"] if settings else [])


def unknown_abbreviations(texts: list[str], settings) -> list[str]:
    """Abbreviations in the texts that the app can't read yet (each once, in order)."""
    seen, out = set(), []
    for text in texts:
        for match in ABBREVIATION.findall(normalize_quotes(text)):
            if match not in seen and not known(match, settings):
                seen.add(match)
                out.append(match)
    return out


def prepare_hebrew(text: str, settings=None) -> str:
    """God's name -> השם, ה' -> השם, abbreviations -> full words (keeping a prefix letter)."""
    text = _TETRAGRAMMATON.sub(lambda m: m.group(1) + "השם", text)
    text = normalize_quotes(text)
    text = re.sub(rf"(?<![{LETTER}])([{PREFIXES}]?)ה'(?![{LETTER}])", r"\1השם", text)
    for short, full in all_abbreviations(settings).items():
        if short == full:
            continue
        pattern = rf"(?<![{LETTER}])([{PREFIXES}]{{0,2}}){re.escape(short)}(?![{LETTER}])"
        text = re.sub(pattern, lambda m: m.group(1) + full, text)
    return text


_SENTENCE_END = re.compile(r"(?<=[.!?:׃;])\s+")


def chunks(parts: list[str], size: int = CHUNK) -> list[str]:
    """Split into sentences, then join short ones into pieces of at most `size` characters.
    Small pieces matter: Android's engine sometimes fails on long text (and the whole piece
    was lost), and pause/resume restarts from the beginning of the current piece."""
    sentences = []
    for part in parts:
        for sentence in _SENTENCE_END.split(part.strip()):
            sentence = sentence.strip()
            while len(sentence) > size:  # a very long sentence: cut at a comma or space
                cut = max(sentence.rfind(", ", 0, size), sentence.rfind(" ", 0, size))
                cut = cut + 1 if cut > 0 else size
                sentences.append(sentence[:cut])
                sentence = sentence[cut:].strip()
            if sentence:
                sentences.append(sentence)
    out, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > size:
            out.append(current)
            current = ""
        current = f"{current} {sentence}" if current else sentence
    if current:
        out.append(current)
    return out


class Speaker:
    def __init__(self, app):
        self.app = app
        self._tts = None
        self._done = asyncio.Event()
        self._run = 0                  # increases on every new request / stop -> older loops quit
        self.active_key: str | None = None   # which button is reading
        self._queue: list[str] = []          # pieces still to read
        self._index = 0                      # current piece
        self._language = HEBREW
        self._paused = False
        self._error = False
        self._engine_lock = asyncio.Lock()  # never two calls to the voice engine at once
        self._loop_idle = asyncio.Event()   # set when no reading loop is running
        self._loop_idle.set()
        self._buttons: dict[str, list] = {}  # key -> live buttons with that key
        self.listeners: list = []      # called on start/stop (e.g. the global stop button)

    @property
    def speaking(self) -> bool:
        return self.active_key is not None

    def _engine(self):
        if self._tts is None and Tts is not None:
            self._tts = Tts(on_complete=self._finished, on_cancel=self._finished,
                            on_error=self._failed)
        return self._tts

    def _finished(self, e=None):
        self._done.set()

    def _failed(self, e=None):
        self._error = True  # _play retries the piece once
        self._done.set()

    def _voice(self, language):
        return self.app.settings["voice_he" if language == HEBREW else "voice_en"]

    async def say(self, parts: list[str], language: str = HEBREW, key: str | None = None):
        """Read parts in order. Stops whatever was being read before."""
        await self.stop()
        if self._engine() is None:
            self.app.toast("Reading aloud works in the phone app")
            return
        if language == HEBREW:
            parts = [prepare_hebrew(p, self.app.settings) for p in parts]
        self._queue, self._index, self._language = chunks(parts), 0, language
        self._set_active(key or "_")
        await self._play()

    async def _engine_call(self, method: str, *args, **kwargs):
        engine = self._engine()
        if engine is None:
            return
        async with self._engine_lock:
            try:
                await getattr(engine, method)(*args, **kwargs)
            except Exception:
                self._error = True

    def _time_limit(self, piece: str) -> float:
        """How long a piece may take before we call it stuck (~14 chars/s at normal speed)."""
        chars_per_second = 14 * max(self.app.settings["speech_rate"], 0.2) / 0.5
        return 8 + len(piece) / (chars_per_second * 0.6)

    async def _play(self):
        """Speak the queue from the current index until done, paused or stopped.
        Only one loop runs at a time: a new one waits until the old one has fully ended."""
        self._run += 1
        run = self._run
        await self._loop_idle.wait()
        if run != self._run:
            return
        self._loop_idle.clear()
        try:
            retried = False
            while self._index < len(self._queue):
                if run != self._run:
                    return  # paused or stopped - the index stays on the interrupted piece
                piece = self._queue[self._index]
                self._done.clear()
                self._error = False
                await self._engine_call("speak", piece, language=self._language,
                                        rate=self.app.settings["speech_rate"],
                                        voice=self._voice(self._language))
                try:
                    await asyncio.wait_for(self._done.wait(), timeout=self._time_limit(piece))
                except asyncio.TimeoutError:
                    # the engine went silent ("stuck"): stop it and treat as a failure
                    await self._engine_call("stop")
                    self._error = True
                if run != self._run:
                    return
                if self._error and not retried:
                    retried = True  # try this piece once more
                    continue
                if self._error:
                    self.app.toast("A sentence could not be read - skipped")
                retried = False
                self._index += 1
            if run == self._run:  # finished normally
                self._queue = []
                self._set_active(None)
        finally:
            self._loop_idle.set()

    @property
    def paused(self) -> bool:
        return self._paused

    async def pause(self):
        """Stop the voice but remember where we are (resume repeats the current sentence)."""
        if not self.speaking or self._paused:
            return
        self._paused = True
        self._run += 1
        self._done.set()
        await self._engine_call("stop")
        await self._wait_idle()
        self._notify()

    async def resume(self):
        if not self._paused:
            return
        self._paused = False
        self._notify()
        await self._play()

    async def toggle_pause(self):
        if self._paused:
            await self.resume()
        else:
            await self.pause()

    async def stop(self):
        """Stop and wait until the old reading loop has really ended, so a new reading never
        overlaps the previous one inside the voice engine."""
        self._run += 1
        self._paused = False
        self._queue = []
        self._set_active(None)
        self._done.set()
        if self._tts is not None:
            await self._engine_call("stop")
        await self._wait_idle()

    async def _wait_idle(self):
        try:
            await asyncio.wait_for(self._loop_idle.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._loop_idle.set()  # never block forever on a broken engine

    async def voices(self, language: str) -> list[dict]:
        engine = self._engine()
        if engine is None:
            return []
        prefix = language.split("-")[0].lower()
        all_voices = await engine.get_voices()
        return sorted((v for v in all_voices if str(v.get("locale", "")).lower().startswith(prefix)),
                      key=lambda v: (v.get("network_required") == "1", v.get("name", "")))

    async def sample(self, voice: dict, language: str):
        text = "שלום, זה הקול שנבחר לקריאה." if language == HEBREW else "Hello, this is the selected voice."
        await self.stop()
        await self._engine_call("speak", text, language=language,
                                rate=self.app.settings["speech_rate"], voice=voice)

    # ---- buttons ----

    def register(self, button):
        self._buttons.setdefault(button.key_name, []).append(button)

    def _set_active(self, key):
        old, self.active_key = self.active_key, key
        for k in {old, key} - {None}:
            alive = []
            for b in self._buttons.get(k, []):
                if b.refresh():
                    alive.append(b)
            self._buttons[k] = alive
        self._notify()

    def _notify(self):
        for listener in list(self.listeners):
            try:
                listener()
            except Exception:
                pass


class SpeakButton(ft.IconButton):
    """🔊 reads `get_parts()` aloud; while reading it turns into ⏹ (tap to stop).
    `key` names WHAT is read (e.g. "inn", "torah:16:4"): a re-created button with the
    same key still shows ⏹ and stops it."""

    def __init__(self, app, get_parts, language=HEBREW, size=22, tooltip="Read aloud", key=None):
        reading = app.speaker.active_key == key
        super().__init__(icon=ft.Icons.STOP_CIRCLE_ROUNDED if reading else ft.Icons.VOLUME_UP_ROUNDED,
                         icon_size=size, tooltip=tooltip,
                         icon_color=ft.Colors.ERROR if reading else ft.Colors.PRIMARY)
        self._app = app
        self.key_name = key or f"button-{id(self)}"
        self._get_parts = get_parts
        self._language = language
        self.on_click = self._clicked
        app.speaker.register(self)

    async def _clicked(self, e):
        speaker = self._app.speaker
        if speaker.active_key == self.key_name:
            await speaker.stop()
        else:
            await speaker.say(self._get_parts(), self._language, key=self.key_name)

    def refresh(self) -> bool:
        """Update the icon. False if this button is no longer on screen."""
        reading = self._app.speaker.active_key == self.key_name
        self.icon = ft.Icons.STOP_CIRCLE_ROUNDED if reading else ft.Icons.VOLUME_UP_ROUNDED
        self.icon_color = ft.Colors.ERROR if reading else ft.Colors.PRIMARY
        try:
            self.update()
            return True
        except Exception:
            return False
