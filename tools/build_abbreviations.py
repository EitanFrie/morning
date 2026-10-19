"""
One-time harvest of Hebrew abbreviations from Torah commentaries (runs on the PC, not in the app).

1. Downloads the main commentators on all 5 books from Sefaria (chapter by chapter).
2. Finds every abbreviation (רש"י, וכו'...), counts it and keeps a few example sentences.
   Number-shaped tokens (י"ד, קכ"ז) are kept only if the dictionary knows them (ע"ה, ת"ח).
3. Looks each one up in Sefaria's dictionary (Ben Yehuda), also without a prefix letter.
4. Writes tools/abbr_candidates.json for the review panel (tools/review_abbreviations.py).

Run:   .venv\\Scripts\\python tools\\build_abbreviations.py
It is polite to Sefaria (a few requests at a time) and resumable: downloaded chapters are
cached in tools/.harvest_cache/, so running it again continues where it stopped.
"""

import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "src"))
from core.speech import ABBREVIATION, PREFIXES, _built_in, normalize_quotes  # noqa: E402
from core.text import clean  # noqa: E402

API = "https://www.sefaria.org/api"
CACHE = ROOT / ".harvest_cache"
OUT = ROOT / "abbr_candidates.json"

BOOKS = {"Genesis": 50, "Exodus": 40, "Leviticus": 27, "Numbers": 36, "Deuteronomy": 34}
# Sefaria titles: "<name> on <Book>" or "<name>, <Book>"
COMMENTATORS = [
    "Rashi on", "Ramban on", "Ibn Ezra on", "Sforno on", "Or HaChaim on", "Kli Yakar on",
    "Rashbam on", "Siftei Chakhamim,", "Chizkuni,", "Daat Zkenim on", "Haamek Davar on",
    "Malbim on",
]
MIN_COUNT = 2        # ignore abbreviations seen only once
MAX_LOOKUPS = 2500   # most frequent first
EXAMPLES = 3

# Hebrew numerals: hundreds, tens, units in descending order (קכ"ז, י"ד, ט"ו, ט"ז)
_HUNDREDS, _TENS, _UNITS = "תשרק", "צפעסנמלכי", "טחזוהדגבא"


def is_hebrew_number(token: str) -> bool:
    letters = re.sub(r"[\"']", "", token)
    if not letters or len(letters) > 5:
        return False
    if letters in ("טו", "טז"):
        return True
    order = _HUNDREDS + _TENS + _UNITS
    positions = [order.find(ch) for ch in letters]
    if -1 in positions:
        return False
    tens = [ch for ch in letters if ch in _TENS]
    units = [ch for ch in letters if ch in _UNITS]
    if len(tens) > 1 or len(units) > 1:
        return False
    if letters.endswith(("יה", "יו")):  # 15/16 are written ט"ו / ט"ז, never י"ה / י"ו
        return False
    return positions == sorted(positions)


def flatten(x):
    if isinstance(x, list):
        for item in x:
            yield from flatten(item)
    elif isinstance(x, str):
        yield x


async def get_json(client, url, params=None, tries=4):
    for attempt in range(tries):
        try:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except (httpx.HTTPError, ValueError):
            pass
        await asyncio.sleep(2 * (attempt + 1))
    return None


async def download_chapters(client) -> list[str]:
    CACHE.mkdir(exist_ok=True)
    limit = asyncio.Semaphore(4)
    jobs = [(c, b, ch) for c in COMMENTATORS for b, n in BOOKS.items() for ch in range(1, n + 1)]
    done = 0

    async def one(commentator, book, chapter):
        nonlocal done
        ref = f"{commentator} {book}.{chapter}"
        path = CACHE / (re.sub(r"[^\w.]+", "_", ref) + ".json")
        if path.exists():
            texts = json.loads(path.read_text(encoding="utf-8"))
        else:
            async with limit:
                data = await get_json(client, f"{API}/v3/texts/{ref}",
                                      {"version": "hebrew", "return_format": "text_only"})
            versions = (data or {}).get("versions") or []
            texts = list(flatten(versions[0]["text"])) if versions else []
            path.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
        done += 1
        if done % 100 == 0:
            print(f"  chapters {done}/{len(jobs)}", flush=True)
        return texts

    results = await asyncio.gather(*(one(*j) for j in jobs))
    return [clean(re.sub(r"<[^>]+>", "", t)) for texts in results for t in texts]


def collect(texts: list[str]):
    counts, examples = Counter(), defaultdict(list)
    for text in texts:
        text = normalize_quotes(text)
        for m in ABBREVIATION.finditer(text):
            token = m.group(0)
            counts[token] += 1
            if len(examples[token]) < EXAMPLES:
                s, e = max(0, m.start() - 60), min(len(text), m.end() + 60)
                examples[token].append(("…" if s else "") + text[s:e] + ("…" if e < len(text) else ""))
    return counts, examples


def bases(token: str) -> list[str]:
    forms, word = [token], token
    while len(word) > 3 and word[0] in PREFIXES:
        word = word[1:]
        forms.append(word)
    return forms


def parse_definitions(entries, headword) -> list[str]:
    options = []
    for entry in entries if isinstance(entries, list) else []:
        if normalize_quotes(entry.get("headword", "")) != headword:
            continue
        for definition in (entry.get("content") or {}).get("definition", []) or []:
            text = re.sub(r"<[^>]+>", "", str(definition)).replace(" ", " ")
            text = re.sub(r'^[\s—–\-:]*(ר"ת|ראשי תבות|ראשי תיבות|קיצור של)?[\s:—–\-]*', "",
                          normalize_quotes(text))
            for option in re.split(r"[,;]|\s-\s", text):
                option = re.sub(r'^[\s—–\-:]*(ר"ת|ראשי תבות|ראשי תיבות)?[\s:—–\-]*', "", option)
                option = re.sub(r"\s+", " ", option).strip(" .:")
                if option and re.search("[א-ת]", option) and option not in options:
                    options.append(option)
    return options[:8]


async def lookup_all(client, tokens: list[str]) -> dict:
    limit = asyncio.Semaphore(3)
    found, done = {}, 0
    cache_file = CACHE / "lookups.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}

    async def one(token):
        nonlocal done
        for base in bases(token):
            if base not in cache:
                async with limit:
                    cache[base] = await get_json(client, f"{API}/words/{base}",
                                                 {"never_split": 1, "always_consonants": 1})
            options = parse_definitions(cache[base], base)
            if options:
                found[token] = {"base": base, "options": options}
                break
        done += 1
        if done % 100 == 0:
            print(f"  lookups {done}/{len(tokens)}", flush=True)

    await asyncio.gather(*(one(t) for t in tokens))
    cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return found


async def main():
    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": "MorningApp abbreviation harvest"}) as client:
        print("Downloading commentaries…", flush=True)
        texts = await download_chapters(client)
        print(f"  {len(texts)} comments", flush=True)

        counts, examples = collect(texts)
        known = set(_built_in()) | {"ה'"}  # ה' is read as השם by the app already

        def is_known(token):  # וכו' is itself known - don't peel it to כו'
            return any(form in known for form in bases(token))

        # merge prefixed forms into their base when the base itself is common (ובא"י -> א"י)
        merged = Counter()
        for token, n in counts.items():
            if is_known(token):
                continue
            target = next((b for b in bases(token)[1:] if counts.get(b, 0) >= 3), token)
            merged[target] += n
            if target != token:
                examples[target] = (examples[target] + examples[token])[:EXAMPLES]
        todo = [t for t, n in merged.most_common() if n >= MIN_COUNT and not is_known(t)][:MAX_LOOKUPS]
        print(f"  {len(merged)} distinct abbreviations, {len(todo)} to look up", flush=True)

        print("Looking up in Sefaria's dictionary…", flush=True)
        found = await lookup_all(client, todo)

    candidates = []
    for token in todo:
        hit = found.get(token)
        number_like = is_hebrew_number(token)
        if number_like and not hit:
            continue  # י"ד, קכ"ז... a number, not an abbreviation
        candidates.append({
            "abbr": hit["base"] if hit else token,
            "seen_as": token,
            "count": merged[token],
            "number_like": number_like,  # ע"ה / ת"ח look like numbers too
            "options": hit["options"] if hit else [],
            "examples": examples[token],
        })
    by_abbr = {}
    for cand in candidates:
        if cand["abbr"] in by_abbr:
            first = by_abbr[cand["abbr"]]
            first["count"] += cand["count"]
            first["examples"] = (first["examples"] + cand["examples"])[:EXAMPLES]
        else:
            by_abbr[cand["abbr"]] = cand
    candidates = sorted(by_abbr.values(), key=lambda c: -c["count"])
    OUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    one = sum(len(c["options"]) == 1 for c in candidates)
    many = sum(len(c["options"]) > 1 for c in candidates)
    print(f"Done: {len(candidates)} candidates -> {OUT.name}  "
          f"(1 meaning: {one}, several: {many}, not in dictionary: {len(candidates) - one - many})")


if __name__ == "__main__":
    asyncio.run(main())
