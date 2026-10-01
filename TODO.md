# TODO

## Waiting for the next release (committed, not yet in an APK)
- Torah window color: brown -> purple (DEEP_PURPLE_400).

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

## Fixed APK signing key
Each CI build currently signs with a throwaway key, so a new APK may refuse to install over
the old one ("App not installed") → you'd have to uninstall first (losing settings/cache).
Fix: generate one keystore (`keytool -genkey ...`), store it base64 in a GitHub secret,
decode it in `build-apk.yml` and pass it to `flet build apk` (`--android-signing-key-store`,
`--android-signing-key-alias`, passwords via env/secrets).
