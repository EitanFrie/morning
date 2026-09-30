# TODO

## Daily Torah portion (פרשת השבוע + commentator) — planned, not built yet

Replaces the old `test.py` experiment (Sefaria API + Twilio/WhatsApp). In this app it
becomes a 4th category window (`src/sources/torah_portion.py`), no WhatsApp needed.

**Idea:** the weekly parasha is split into its 7 aliyot. Each day shows one aliyah
(Sunday = 1st … Shabbat = 7th). Every verse is shown with the chosen commentator's
comment right under it. Default commentator: Rashi.

### API (Sefaria, free, no key)
Docs: https://developers.sefaria.org
1. `GET https://www.sefaria.org/api/calendars?diaspora=0&custom=ashkenazi`
   → item with title "Parashat Hashavua": `displayValue` (name), `extraDetails.aliyot`
   = list of 7 (sometimes 8 with maftir) refs, e.g. `"Exodus 11:4-12:20"`.
2. Verse text (Hebrew): `GET /api/v3/texts/{ref}?version=hebrew&return_format=text_only`
3. Commentary for the WHOLE aliyah in one call (instead of the old loop that asked
   verse-by-verse, up to 177 requests):
   `GET /api/links/{ref}?with_text=1` → keep links with `category == "Commentary"`;
   each has `collectiveTitle` (he/en), `anchorRef` (which verse) and `he`/`text`.
   → group by `anchorRef` verse and by commentator.

### Behaviour
- fetch(): download all 7 aliyot of the week + their commentary once, cache it.
  Cache key = parasha name + week; a new week (Sunday) → drop the old cache, download the new one.
  (Maybe only download the day's aliyah first, the rest in the background — check size.)
- Commentator picker in the window header (dropdown). Options = commentators that
  actually exist in this week's data (not every commentator covers every parasha).
  Default Rashi, choice saved in settings.
- Day picker (Sun…Shabbat chips) in the header; default = today. Lets you catch up on a missed day.
- Row format: feed_row per verse — meta = verse number (פרק:פסוק), headline = verse text,
  details (expand) = commentator text. Or show commentary always-open; decide when testing.
- RTL, Hebrew text; strip HTML tags that Sefaria includes (`<b>`, `<small>`, footnotes).

### Bugs noticed in the old test.py (for reference)
- Weekday → aliyah index: Shabbat produced 7 (out of range for 0–6). Use
  `(datetime.today().weekday() + 1) % 7` → Sun=0 … Sat=6.
- Verse-by-verse `/api/related` loop is slow; use `/api/links/{range}?with_text=1`.
- Israel vs. diaspora readings can differ some weeks: keep `diaspora=0` (Israel).
