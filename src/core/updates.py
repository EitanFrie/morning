"""
Checks GitHub for a newer release of the app.

The GitHub build writes the version (e.g. "0.3.1") into src/version.txt before building
the APK. When running from source there is no such file -> version "dev" -> no checks.
"""

from pathlib import Path

REPO = "EitanFrie/morning"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def current_version() -> str:
    try:
        return (Path(__file__).parent.parent / "version.txt").read_text().strip() or "dev"
    except OSError:
        return "dev"


def _as_tuple(version: str) -> tuple:
    return tuple(int(p) for p in version.lstrip("v").split(".") if p.isdigit())


async def newer_release(client) -> dict | None:
    """{"version", "url"} of a newer release, or None if up to date (or running from source)."""
    current = current_version()
    if current == "dev":
        return None
    response = await client.get(LATEST, headers={"Accept": "application/vnd.github+json"})
    response.raise_for_status()
    release = response.json()
    tag = release.get("tag_name", "")
    if not tag or _as_tuple(tag) <= _as_tuple(current):
        return None
    apk = next((a["browser_download_url"] for a in release.get("assets", [])
                if a.get("name", "").endswith(".apk")), None)
    return {"version": tag.lstrip("v"), "url": apk or RELEASES_PAGE}
