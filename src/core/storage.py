"""
Tiny JSON-file storage.

Three files live in the app's data folder:
  settings.json  - your preferences (theme, hours back, refresh timings...)
  cache.json     - the last data fetched from every source, so the app opens
                   instantly (and works offline) before refreshing.
  state.json     - small UI memory, e.g. which news flashes you expanded.

Plain JSON on purpose: you can open these files and read them.
"""

import json
import os
import time
from pathlib import Path


def data_dir() -> Path:
    # On Android/iOS, Flet sets FLET_APP_STORAGE_DATA to a private app folder.
    # On the desktop we fall back to ~/.eitan_morning
    base = os.environ.get("FLET_APP_STORAGE_DATA") or (Path.home() / ".eitan_morning")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


class JsonFile:
    """A dict that is loaded from / saved to one JSON file."""

    def __init__(self, name: str, defaults: dict | None = None):
        self.path = data_dir() / name
        self.data: dict = json.loads(json.dumps(defaults or {}))  # deep copy
        if self.path.exists():
            try:
                self._merge(self.data, json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass  # a broken file just means "start fresh"

    @staticmethod
    def _merge(base: dict, loaded: dict):
        # Keep defaults for keys that were added in newer app versions.
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                JsonFile._merge(base[key], value)
            else:
                base[key] = value

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)  # atomic: never leaves a half-written file

    def clear(self):
        self.data = {}
        self.save()


DEFAULT_SETTINGS = {
    "theme": "system",          # system | light | dark
    "text_scale": 1.0,          # 0.9 | 1.0 | 1.15
    "inn_hours_back": 10,       # how many hours of news flashes to show
    "science_count": 3,         # 3 or 6 science articles
    "timezone": "Asia/Jerusalem",  # used to show NBA tip-off times
    "torah_commentator": "Rashi",  # Sefaria name of the chosen commentator
    "weather_city": {"name": "ירושלים", "lat": 31.76904, "lon": 35.21633, "country": "ישראל"},
    "weather_show_days": False,    # show the next 3 days under today
    # A source refreshes by itself when the app is opened (or brought back)
    # and its data is older than this many minutes.
    "refresh_minutes": {"weather": 60, "inn": 30, "nba": 10, "science": 360, "torah": 720},
}


class Settings(JsonFile):
    def __init__(self):
        super().__init__("settings.json", DEFAULT_SETTINGS)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()


class Cache(JsonFile):
    """source_id -> {"fetched_at": unix time, "data": whatever fetch() returned}"""

    def __init__(self):
        super().__init__("cache.json")

    def get(self, source_id: str):
        return self.data.get(source_id)

    def put(self, source_id: str, data):
        self.data[source_id] = {"fetched_at": time.time(), "data": data}
        self.save()

    def age_minutes(self, source_id: str) -> float | None:
        entry = self.data.get(source_id)
        if not entry:
            return None
        return (time.time() - entry["fetched_at"]) / 60
