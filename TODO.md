# TODO

## v0.5.1 — check on the phone
- Long readings: now read sentence by sentence (max ~400 chars), a failed piece is retried
  once (before: a 3000-char piece that failed was silently lost = "stops in the middle").
- ⏸/▶ next to ⏹ in the top bar (tablet: small floating bar). Pause resumes from the start of
  the current sentence (Android's voice engine has no real pause).
- NBA News: orange shade, Settings > NBA News > headlines to show (default 5).
- Your abbreviations always win over the built-in list (even a longer built-in phrase).
  Settings list is folded ("הקיצורים שלך (N)") with a search box.

## Idea: bigger built-in abbreviations.json
Sefaria has no separate abbreviation dictionary - they are entries inside the Ben Yehuda
dictionary (api/words). Possible one-time PC script: scan Rashi + main commentators on the whole
Torah, collect every abbreviation, look each up, auto-add unambiguous ones, list the rest for review.

## v0.5.0 — check on the phone
- Global stop button appears in the top bar while reading (tablet: floating red button).
- NBA scores stop button (was broken: refreshed buttons lost track of the reading).
- Flashes: reads ALL flashes, not 10. Weather 🔊 in the requested Hebrew format.
- Settings > Reading aloud > choose Hebrew / English voice (▶ samples; Android doesn't say
  male/female). Settings > Abbreviations: add / delete your own.
- Torah: יהוה -> השם; prefix letters (וא"י); 🎓 teach unknown abbreviations (Sefaria dictionary
  suggestions; daf-yomi.com blocks automated requests with a Cloudflare check, so not used).
- NBA News window (featured stories only).

## Shipped in v0.3.x — check these on the phone
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
Tested against live Sefaria (all 7 days, Rashi & Ramban); checked on screen in the preview.

Weekly bundle (done): once per parasha the whole week is downloaded - every verse with ALL
commentators (Sefaria /api/links per verse, 4 at a time, with retries) - and saved to
torah_week.json (~1.5 MB). New parasha (holidays too) -> old file deleted first.
Measured: ~45 s for the full week, then switching day/commentator ~0.2 s, offline.
The window shows "מוריד את תוכן השבוע… n/7" while downloading.
(A whole aliyah in ONE links request was ~7 MB and the server kept cutting it off.)

Offline (v0.3.6): opening the window offline uses the saved week (verses + commentators);
"&nbsp;"-style HTML codes are cleaned; a verse that times out (e.g. Genesis 1:1) is skipped
and retried on the next online start; progress shows aliyah + verse numbers.

Still to do / check:
- Download speed varies a lot: last week ~45 s, Bereishit ~9.5 min (very heavily commented,
  slow server). Idea if annoying: download TODAY's aliyah first and show it, rest in background.
- See it in the app on screen + phone (two dropdowns in the header; commentator list has ~34 names).
- Aliyah crossing chapters: tested OK with Genesis 1:1-2:3 (34 verses).
- If the download is interrupted halfway, it simply starts over next time (nothing partial is saved).

## Fixed APK signing key — DONE (secrets added, signed since v0.3.2)
Key: C:\Users\Eitan\morning-signing\morning.p12 (NOT in the repo — back it up! Losing it means
uninstalling the app to update). Values to paste: GITHUB_SECRETS.txt in the same folder.
build-apk.yml already uses ANDROID_KEYSTORE_BASE64 / ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS
(without them it warns and falls back to a temporary key).
