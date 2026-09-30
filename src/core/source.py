"""
The plugin interface every news source implements.

To add a new site:
  1. create a file in src/sources/ with a class that extends Source
  2. add it to the SOURCES list in src/sources/__init__.py
That's it - it gets a section in the feed, a sidebar entry and a refresh button.
"""

from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from app import App


class Source:
    id: str = ""                    # short unique name, used for cache + settings
    title: str = ""                 # shown in the sidebar and section header
    subtitle: str = ""              # small text under the title
    icon: ft.IconData = ft.Icons.ARTICLE_ROUNDED
    color: str = ft.Colors.INDIGO   # accent color of the section badge

    async def fetch(self, app: "App"):
        """Download + parse. Must return plain JSON-able data (dicts/lists/str/numbers),
        because it is saved to the cache file as-is."""
        raise NotImplementedError

    def render(self, data, app: "App") -> ft.Control:
        """Build the section body from the data fetch() returned."""
        raise NotImplementedError

    def header_extras(self, app: "App") -> list[ft.Control]:
        """Optional extra controls shown in the section header (e.g. a date picker)."""
        return []
