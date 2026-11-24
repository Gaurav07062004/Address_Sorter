"""Run with:  streamlit run review_app.py

Upload a file: every line is matched automatically. Confident matches are filled in for you;
you are only asked about the lines the matcher isn't sure of."""
import os

import pandas as pd
import streamlit as st

from config import AUTO_ACCEPT_LLM, AUTO_ACCEPT_MARGIN, AUTO_ACCEPT_SCORE
from export import COLUMNS, to_excel_bytes
from ingest import read_lines
from match import AddressMatcher
from pipeline import decide, suggest, to_record


@st.cache_resource
def get_matcher():
    return AddressMatcher()


st.set_page_config(page_title="Mauritius address cleaner", layout="wide")
st.title("Mauritius address cleaner")
matcher = get_matcher()

sb = st.sidebar
use_llm = sb.toggle("LLM re-rank (needs ANTHROPIC_API_KEY)", value=bool(os.getenv("ANTHROPIC_API_KEY")))
with sb.expander("When to accept automatically"):
    min_score = st.slider("Minimum match score", 50, 100, AUTO_ACCEPT_SCORE)
    min_margin = st.slider("Minimum lead over the next address", 0, 30, AUTO_ACCEPT_MARGIN)
    min_llm = st.slider("Minimum LLM confidence", 0.5, 1.0, AUTO_ACCEPT_LLM, 0.05)
    st.caption("Raise these to be asked more often; lower them to automate more.")

up = st.file_uploader("Upload a document (one address per line)", type=["txt", "docx", "pdf", "xlsx", "csv"])
if up and st.session_state.get("file") != up.name:
    lines = read_lines(up.name, up.getvalue())
    items = []
    bar = st.progress(0.0, text="Matching addresses...")
    for n, raw in enumerate(lines):
        parsed, cands = suggest(raw, matcher, use_llm)
        items.append({"raw": raw, "parsed": parsed, "cands": cands,
                      "answer": None,        # "approved" / "skipped" once you've answered
                      "record": None,        # your approved values
                      "force_ask": False})   # you sent an automatic one back to the questions
        bar.progress((n + 1) / len(lines), text=f"Matching addresses... {n + 1}/{len(lines)}")
    bar.empty()
    st.session_state.update(file=up.name, results=items)

if "results" not in st.session_state:
    st.stop()
items = st.session_state["results"]

# Decide (cheap, so it follows the sidebar sliders live)
for it in items:
    auto, reason = decide(it["cands"], min_score, min_margin, min_llm)
    it["auto"], it["reason"] = auto and not it["force_ask"], reason
    if it["answer"] is None and it["auto"]:
        it["auto_record"] = to_record(it["parsed"], it["cands"][0])

auto_items = [it for it in items if it["auto"] and it["answer"] is None]
questions = [it for it in items if not it["auto"] and it["answer"] is None]
answered = [it for it in items if it["answer"] is not None]


def final_rows():
    rows = []
    for it in items:
        if it["answer"] == "approved":
            rec, status = it["record"], "approved by you"
        elif it["answer"] == "skipped":
            rec, status = {c: "" for c in COLUMNS}, "skipped"
        elif it["auto"]:
            rec, status = it["auto_record"], f"automatic ({it['reason']})"
        else:
            rec, status = {c: "" for c in COLUMNS}, "waiting for your answer"
        rows.append({**rec, "Original": it["raw"], "Status": status})
    return rows


m1, m2, m3, m4 = st.columns(4)
m1.metric("Lines", len(items))
m2.metric("Filled automatically", len(auto_items))
m3.metric("Answered by you", len(answered))
m4.metric("Waiting for you", len(questions))
sb.download_button("Download Excel", to_excel_bytes(final_rows(), ("Original", "Status")),
                   file_name="clean_addresses.xlsx", type="primary")

tab_q, tab_auto, tab_all = st.tabs([f"Needs your answer ({len(questions)})",
                                    f"Filled automatically ({len(auto_items)})", "All results"])

# ---------------------------------------------------------------- questions
with tab_q:
    if not questions:
        st.success("Nothing left to ask. Download the Excel file from the sidebar.")
    else:
        it = questions[0]
        idx = items.index(it)
        parsed, cands = it["parsed"], it["cands"]
        st.caption(f"Question 1 of {len(questions)}. Why I'm asking: {it['reason']}")
        st.subheader(it["raw"])

        choice = st.radio(
            "Which address is it?", range(len(cands) + 1), key=f"choice_{idx}",
            format_func=lambda i: (f"{cands[i]['street']}, {cands[i]['locality']}, {cands[i]['city']}  "
                                   f"[score {cands[i]['score']}, {cands[i]['source']}]")
            if i < len(cands) else "None of these - enter manually")
        if choice < len(cands) and cands[choice].get("llm_reason"):
            st.caption(f"LLM: {cands[choice]['llm_reason']}")

        rec = to_record(parsed, cands[choice] if choice < len(cands) else None)
        k = f"{idx}_{choice}"
        c1, c2, c3, c4 = st.columns(4)
        street1 = c1.text_input("Street 1", rec["Street 1"], key=f"s1_{k}")
        street2 = c2.text_input("Street 2", rec["Street 2"], key=f"s2_{k}")
        city = c3.text_input("City", rec["City"], key=f"ci_{k}")
        locality = c4.text_input("Locality", rec["Locality"], key=f"lo_{k}")

        b1, b2, _ = st.columns([1, 1, 6])
        if b1.button("Approve", type="primary"):
            it["answer"], it["record"] = "approved", {"Street 1": street1, "Street 2": street2,
                                                      "City": city, "Locality": locality}
            street = cands[choice]["street"] if choice < len(cands) else street1.removeprefix(parsed.number).strip()
            matcher.save_alias(it["raw"], {"street": street, "locality": locality, "city": city,
                                           "postcode": cands[choice].get("postcode", "") if choice < len(cands) else ""})
            st.rerun()
        if b2.button("Skip"):
            it["answer"] = "skipped"
            st.rerun()

# ------------------------------------------------------- automatic results
with tab_auto:
    if not auto_items:
        st.info("No lines were confident enough to fill automatically.")
    else:
        st.caption("Spot-check if you like. You can edit a cell directly, or tick "
                   "'Ask me' to move a line to the questions.")
        df = pd.DataFrame([{"Ask me": False, "Original": it["raw"], **it["auto_record"], "Why": it["reason"]}
                           for it in auto_items])
        edited = st.data_editor(df, hide_index=True, width="stretch",
                                disabled=["Original", "Why"],
                                key=f"auto_{st.session_state.file}_{hash(tuple(id(it) for it in auto_items))}")
        changed = False
        for it, (_, row) in zip(auto_items, edited.iterrows()):
            if row["Ask me"]:
                it["force_ask"], changed = True, True
            else:
                it["auto_record"] = {c: row[c] for c in COLUMNS}
                if any(row[c] != to_record(it["parsed"], it["cands"][0])[c] for c in COLUMNS):
                    it["answer"], it["record"] = "approved", it["auto_record"]   # your edit wins
                    changed = True
        if changed:
            st.rerun()

# -------------------------------------------------------------- everything
with tab_all:
    st.dataframe(pd.DataFrame(final_rows())[["Original", *COLUMNS, "Status"]],
                 hide_index=True, width="stretch")
