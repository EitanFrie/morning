"""
Morning - a personal news feed.
Run on the computer:   python src/main.py
Build for Android:     flet build apk   (or let GitHub Actions do it, see README)
"""

import flet as ft

from app import App


async def main(page: ft.Page):
    await App(page).start()


if __name__ == "__main__":
    import os

    if os.environ.get("MORNING_WEB"):  # preview in a browser: MORNING_WEB=1 python src/main.py
        ft.run(main, view=ft.AppView.WEB_BROWSER, port=8550)
    else:
        ft.run(main)
