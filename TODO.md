# TODO

## Waiting for the next release (committed, not yet in an APK)
- Torah window color: brown -> purple (DEEP_PURPLE_400).
- Side strip (for moving between categories) 50% wider: 30 -> 45 px, bigger dots.
- Window headers on two lines: centered title + one-line "updated" status, pickers centered below.
- Torah pickers: label always shows the FIRST letters (Hebrew, right-aligned, "…" at the end).
- Science article reader fits the window width on phones (was a fixed 720 px -> right half cut).
- Article images: sized to the window (were collapsing on the phone); tap an image ->
  full-screen viewer with pinch-zoom and drag (back closes it). Check on the phone.
- In-app update check: on every app start + Settings > "Check now". Newer GitHub
  release -> message with a Download button (opens the APK). Version comes from
  src/version.txt, written by the GitHub build ("dev" when running from source).

## Daily Torah portion — first version BUILT (src/sources/torah_portion.py)
Done: 4th window, parasha from Sefaria calendar, aliyah by weekday (Sun=1st … Shabbat=7th),
day picker, commentator picker (default Rashi, saved), verse + commentary rows, ~20 KB per load.
Tested against live Sefaria (all 7 days, Rashi & Ramban). Not yet seen on screen/phone.

Weekly bundle (done): once per parasha the whole week is downloaded - every verse with ALL
commentators (Sefaria /api/links per verse, 4 at a time, with retries) - and saved to
torah_week.json (~1.5 MB). New parasha (holidays too) -> old file deleted first.
Measured: ~45 s for the full week, then switching day/commentator ~0.2 s, offline.
The window shows "מוריד את תוכן השבוע… n/7" while downloading.
(A whole aliyah in ONE links request was ~7 MB and the server kept cutting it off.)

Still to do / check:
- See it in the app on screen + phone (two dropdowns in the header; commentator list has ~34 names).
- Aliyah crossing chapters (e.g. "Exodus 11:4-12:20"): mapping code exists, untested this week.
- If the download is interrupted halfway, it simply starts over next time (nothing partial is saved).

## Fixed APK signing key — key created, waiting for the 3 GitHub secrets
Key: C:\Users\Eitan\morning-signing\morning.p12 (NOT in the repo — back it up! Losing it means
uninstalling the app to update). Values to paste: GITHUB_SECRETS.txt in the same folder.
build-apk.yml already uses ANDROID_KEYSTORE_BASE64 / ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS
(without them it warns and falls back to a temporary key).
