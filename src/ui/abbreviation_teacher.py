"""
"Teach the app" abbreviations it can't read yet (Torah window, current day + commentator).

For each unknown abbreviation: the sentence it appears in, suggestions from Sefaria's
dictionary (Ben Yehuda - looked up without a prefix letter like ו / ב), a free-text field,
and ✓ save / skip. Saved meanings go to settings["user_abbreviations"] and are never asked
again; "skip" adds it to settings["ignored_abbreviations"] (read as written).
(daf-yomi.com's dictionary would be nicer, but it blocks automated requests.)
"""

import re

import flet as ft

from core.speech import LETTER, PREFIXES, normalize_quotes

LEXICON = "https://www.sefaria.org/api/words/{}"


def _bases(abbreviation: str) -> list[str]:
    """'ובאוה"ע' -> ['ובאוה"ע', 'באוה"ע', 'אוה"ע'] (prefix letters peeled off)."""
    forms, word = [abbreviation], abbreviation
    while len(word) > 3 and word[0] in PREFIXES:
        word = word[1:]
        forms.append(word)
    return forms


async def suggestions(app, abbreviation: str) -> tuple[str, list[str]]:
    """-> (base form to save, meaning options) from Sefaria's dictionary."""
    for base in _bases(normalize_quotes(abbreviation)):
        try:
            response = await app.client.get(LEXICON.format(base),
                                            params={"never_split": 1, "always_consonants": 1})
            entries = response.json() if response.status_code == 200 else []
        except Exception:
            entries = []
        options = []
        for entry in entries if isinstance(entries, list) else []:
            if normalize_quotes(entry.get("headword", "")) != base:
                continue
            for definition in (entry.get("content") or {}).get("definition", []) or []:
                text = re.sub(r"<[^>]+>", "", str(definition)).replace("\u00a0", " ")
                text = re.sub(r'^[\s—–\-:]*(ר"ת|ראשי תבות|ראשי תיבות|קיצור של)?[\s:—–\-]*', "",
                              normalize_quotes(text))
                for option in re.split(r"[,;]|\s-\s", text):
                    option = option.strip(" .:")
                    if option and re.search(f"[{LETTER}]", option) and option not in options:
                        options.append(option)
        if options:
            return base, options[:8]
    # Nothing in the dictionary: save it exactly as written (ואכמ"ל - the ו is part of it)
    return normalize_quotes(abbreviation), []


def _context(abbreviation: str, texts: list[str]) -> str:
    for text in texts:
        text = normalize_quotes(text)
        i = text.find(abbreviation)
        if i >= 0:
            start, end = max(0, i - 40), min(len(text), i + len(abbreviation) + 40)
            return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
    return ""


def open_teacher(app, unknown: list[str], texts: list[str], on_done):
    """Dialog: one card per unknown abbreviation."""
    cards = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, tight=True)

    def card_for(abbreviation: str) -> ft.Control:
        custom = ft.TextField(hint_text="פירוש משלך…", rtl=True, dense=True, expand=True)
        options_row = ft.Row(wrap=True, spacing=6, rtl=True,
                             controls=[ft.ProgressRing(width=16, height=16, stroke_width=2),
                                       ft.Text("מחפש הצעות…", size=12)])
        base_holder = {"base": abbreviation}
        box = ft.Container(padding=12, border_radius=12, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT))

        def done(message: str):
            box.content = ft.Text(f"{abbreviation} — {message}", rtl=True, color=ft.Colors.PRIMARY)
            box.update()

        def save(meaning: str):
            meaning = meaning.strip()
            if not meaning:
                return
            app.settings["user_abbreviations"] = {**app.settings["user_abbreviations"],
                                                  base_holder["base"]: meaning}
            done(f"נשמר: {meaning}")

        def skip(e):
            ignored = list(app.settings["ignored_abbreviations"])
            if abbreviation not in ignored:
                app.settings["ignored_abbreviations"] = ignored + [abbreviation]
            done("ייקרא כפי שהוא כתוב")

        async def load():
            base, options = await suggestions(app, abbreviation)
            base_holder["base"] = base
            options_row.controls = [
                ft.OutlinedButton(o, on_click=lambda e, o=o: save(o)) for o in options
            ] or [ft.Text("אין הצעות במילון - כתוב פירוש משלך", size=12,
                          color=ft.Colors.ON_SURFACE_VARIANT)]
            try:
                options_row.update()
            except Exception:
                pass

        box.content = ft.Column([
            ft.Text(abbreviation, size=20, weight=ft.FontWeight.BOLD, rtl=True),
            ft.Text(_context(abbreviation, texts), size=12, color=ft.Colors.ON_SURFACE_VARIANT, rtl=True),
            options_row,
            ft.Row([custom, ft.IconButton(ft.Icons.CHECK_CIRCLE_ROUNDED, tooltip="שמור",
                                          on_click=lambda e: save(custom.value or ""))], rtl=True),
            ft.TextButton("דלג (קרא כפי שכתוב)", on_click=skip),
        ], spacing=6, rtl=True)
        app.page.run_task(load)
        return box

    cards.controls = [card_for(a) for a in unknown]

    def close(e):
        app.page.pop_dialog()
        on_done()

    app.page.show_dialog(ft.AlertDialog(
        title=ft.Text(f"ללמד קיצורים ({len(unknown)})", rtl=True),
        content=ft.Container(cards, width=420, height=480),
        actions=[ft.TextButton("סיום", on_click=close)],
    ))
