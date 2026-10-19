"""
Review panel for harvested abbreviations (runs on the PC, in the browser).

Run:   .venv\\Scripts\\streamlit run tools\\review_abbreviations.py

One card per abbreviation, most frequent first: example sentences from the commentaries,
the dictionary's suggestions, your own meaning, or skip. Every choice is saved immediately
to tools/abbr_review.json - close it any time and continue later.
When you're done, press "Submit" (writes tools/abbr_approved.json) and tell Claude.
"""

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
CANDIDATES = ROOT / "abbr_candidates.json"
REVIEW = ROOT / "abbr_review.json"
APPROVED = ROOT / "abbr_approved.json"

st.set_page_config(page_title="Abbreviations review", page_icon="📖", layout="centered")
st.markdown("""<style>
.rtl { direction: rtl; text-align: right; font-size: 1.05rem; line-height: 1.7; }
.abbr { direction: rtl; text-align: center; font-size: 3rem; font-weight: 700; margin: .2rem 0; }
.example { direction: rtl; text-align: right; background: rgba(127,127,127,.12);
           border-radius: 10px; padding: .5rem .8rem; margin: .3rem 0; }
.example b { color: #e8590c; }
div[data-testid="stButton"] button p { font-size: 1.05rem; }
</style>""", unsafe_allow_html=True)


@st.cache_data
def load_candidates():
    if not CANDIDATES.exists():
        return []
    return json.loads(CANDIDATES.read_text(encoding="utf-8"))


def load_review() -> dict:
    if REVIEW.exists():
        return json.loads(REVIEW.read_text(encoding="utf-8"))
    return {}


def save_review(review: dict):
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")


candidates = load_candidates()
if not candidates:
    st.warning("No candidates yet - run tools/build_abbreviations.py first.")
    st.stop()

if "review" not in st.session_state:
    st.session_state.review = load_review()
review = st.session_state.review

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Progress")
    decided = sum(1 for c in candidates if c["abbr"] in review)
    st.progress(decided / len(candidates), text=f"{decided} / {len(candidates)} reviewed")
    kept = sum(1 for v in review.values() if v.get("meaning"))
    st.caption(f"✅ {kept} with a meaning · ⏭ {decided - kept} skipped")

    st.header("Show")
    show = st.radio("Which", ["Not reviewed yet", "All", "Reviewed"], label_visibility="collapsed")
    kind = st.radio("Kind", ["All kinds", "One suggestion", "Several suggestions", "No suggestion"])
    min_count = st.slider("Seen at least … times", 2, 50, 2)
    search = st.text_input("Search", placeholder='e.g. א"י')

    st.divider()
    if st.button("✅ Submit (I'm done for now)", use_container_width=True, type="primary"):
        approved = {c["abbr"]: review[c["abbr"]]["meaning"]
                    for c in candidates if review.get(c["abbr"], {}).get("meaning")}
        APPROVED.write_text(json.dumps(approved, ensure_ascii=False, indent=1), encoding="utf-8")
        st.success(f"Saved {len(approved)} abbreviations to {APPROVED.name}. Tell Claude!")


def visible(c) -> bool:
    if show == "Not reviewed yet" and c["abbr"] in review:
        return False
    if show == "Reviewed" and c["abbr"] not in review:
        return False
    n = len(c["options"])
    if kind == "One suggestion" and n != 1 or kind == "Several suggestions" and n < 2 \
            or kind == "No suggestion" and n:
        return False
    if c["count"] < min_count:
        return False
    if search and search not in c["abbr"] and search not in c["seen_as"]:
        return False
    return True


items = [c for c in candidates if visible(c)]
if not items:
    st.success("Nothing left in this view 🎉")
    st.stop()

if "pos" not in st.session_state:
    st.session_state.pos = 0
st.session_state.pos = min(st.session_state.pos, len(items) - 1)
c = items[st.session_state.pos]


def decide(value: dict):
    review[c["abbr"]] = value
    save_review(review)
    if show == "All" or show == "Reviewed":
        st.session_state.pos = min(st.session_state.pos + 1, len(items) - 1)
    # in "Not reviewed yet" the decided card disappears, the next one slides into place


# ---------------------------------------------------------------- card
st.caption(f"{st.session_state.pos + 1} of {len(items)} in this view · seen {c['count']} times"
           + (f" · written as {c['seen_as']}" if c["seen_as"] != c["abbr"] else ""))
st.markdown(f'<div class="abbr">{c["abbr"]}</div>', unsafe_allow_html=True)
if c.get("number_like"):
    st.info("Looks like a Hebrew number too (e.g. 14 = י\"ד). Choose a meaning only if the examples use it as an abbreviation.")
if c["abbr"] in review:
    current = review[c["abbr"]]
    st.markdown(f'<div class="rtl">החלטה נוכחית: <b>{current.get("meaning") or "דילוג"}</b></div>',
                unsafe_allow_html=True)

st.subheader("In context")
for example in c["examples"]:
    highlighted = example.replace(c["seen_as"], f"<b>{c['seen_as']}</b>")
    st.markdown(f'<div class="example">{highlighted}</div>', unsafe_allow_html=True)

st.subheader("Meaning")
if c["options"]:
    for i, option in enumerate(c["options"]):
        if st.button(option, key=f"opt-{c['abbr']}-{i}", use_container_width=True):
            decide({"meaning": option})
            st.rerun()
else:
    st.caption("No suggestion in the dictionary - write it below, or skip.")

with st.form(key=f"custom-{c['abbr']}", clear_on_submit=True):
    custom = st.text_input("Your own meaning", placeholder="למשל: ואין כאן מקום להאריך")
    if st.form_submit_button("Save my meaning", use_container_width=True) and custom.strip():
        decide({"meaning": custom.strip()})
        st.rerun()

col1, col2, col3 = st.columns(3)
if col1.button("⏮ Back", use_container_width=True):
    st.session_state.pos = max(0, st.session_state.pos - 1)
    st.rerun()
if col2.button("⏭ Skip (read as written)", use_container_width=True):
    decide({"skip": True})
    st.rerun()
if col3.button("Next ⏩", use_container_width=True):
    st.session_state.pos = min(st.session_state.pos + 1, len(items) - 1)
    st.rerun()
