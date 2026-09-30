"""Helpers for turning website HTML into clean readable text."""

import re

from bs4 import BeautifulSoup

_SPACES = re.compile(r"[ \t ‏‎]+")


def clean(text: str) -> str:
    """Collapse runs of spaces, keep line breaks, trim."""
    lines = (_SPACES.sub(" ", line).strip() for line in (text or "").splitlines())
    return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    """HTML snippet -> paragraphs separated by a blank line."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    blocks = [b for b in soup.find_all(["p", "li", "h2", "h3", "h4"]) if not b.find(["p", "li"])]
    if not blocks:
        return clean(soup.get_text())
    return "\n\n".join(t for t in (clean(b.get_text()) for b in blocks) if t)
