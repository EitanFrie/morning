"""
Python side of the TTS extension. The Dart side (flutter/flet_tts) talks to Android's own
text-to-speech engine, so nothing heavy is shipped with the app.
"""

from typing import Optional

import flet as ft


@ft.control("Tts")
class Tts(ft.Service):
    """Speaks text with the device's voice engine."""

    on_complete: Optional[ft.ControlEventHandler["Tts"]] = None
    """Fires when the current text has been spoken completely."""

    on_cancel: Optional[ft.ControlEventHandler["Tts"]] = None
    """Fires when speaking was stopped."""

    on_error: Optional[ft.ControlEventHandler["Tts"]] = None
    """Fires when the engine reports an error (e.data holds the message)."""

    async def speak(self, text: str, language: str = "he-IL", rate: float = 0.5,
                    pitch: float = 1.0):
        """Start speaking and return right away; on_complete fires when done."""
        await self._invoke_method(
            "speak", {"text": text, "language": language, "rate": rate, "pitch": pitch}
        )

    async def stop(self):
        await self._invoke_method("stop")

    async def is_language_available(self, language: str) -> bool:
        return bool(await self._invoke_method("is_language_available", {"language": language}))

    async def max_input_length(self) -> int:
        return int(await self._invoke_method("max_input_length") or 4000)
