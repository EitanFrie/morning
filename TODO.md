# TODO

## Daily Torah portion — first version BUILT (src/sources/torah_portion.py)
Done: 4th window, parasha from Sefaria calendar, aliyah by weekday (Sun=1st … Shabbat=7th),
day picker, commentator picker (default Rashi, saved), verse + commentary rows, ~20 KB per load.
Tested against live Sefaria (all 7 days, Rashi & Ramban). Not yet seen on screen/phone.

Still to do / check:
- Look at it in the app (layout of the two dropdowns in the header on a phone).
- Aliyah that crosses chapters (e.g. "Exodus 11:4-12:20"): mapping code exists, untested —
  this week (Shemini Atzeret) has none.
- Offline: only the last viewed day+commentator is cached. Optionally pre-download all 7 days
  of the week for the chosen commentator (small: ~7 × 20 KB), replace on a new parasha.
- Holidays: Sefaria returns the holiday reading as "Parashat Hashavua" (may have 8 aliyot;
  we use the first 7). Decide if that's the wanted behaviour.
- Commentator list is fixed (10 classics); could be built from `/api/related/{ref}`
  (commentators that really exist for the aliyah) — ~1.3 MB, so maybe once per week.
- Don't use `/api/links/{ref}?with_text=1`: ~7 MB per aliyah.

## Fixed APK signing key
Each CI build currently signs with a throwaway key, so a new APK may refuse to install over
the old one ("App not installed") → you'd have to uninstall first (losing settings/cache).
Fix: generate one keystore (`keytool -genkey ...`), store it base64 in a GitHub secret,
decode it in `build-apk.yml` and pass it to `flet build apk` (`--android-signing-key-store`,
`--android-signing-key-alias`, passwords via env/secrets).
