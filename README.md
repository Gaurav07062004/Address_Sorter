# Mauritius address cleaner

1. `pip install -r requirements.txt`
2. `python build_reference.py` (optionally `--postcodes data/postcodes.csv --extra data/licensed.csv`;
   don't type the square brackets used in usage messages)
   Downloads Mauritius streets/places from OpenStreetMap via Overpass and builds the parquet + FAISS index.
3. Optional: `$env:ANTHROPIC_API_KEY="..."` in PowerShell (enables LLM re-ranking; model via ADDRESS_LLM_MODEL)
4. `streamlit run review_app.py`, then upload a document.

## How it works

Every line is matched as soon as you upload the file:

- **Filled automatically** when the matcher is sure:
  - the line matches a correction you approved before, or
  - the LLM picked a candidate with high confidence, or
  - the best match scores high **and** is clearly ahead of the next different address.
- **Needs your answer**: everything else, one question at a time, with the reason it's asking
  (low score, or a close call between two addresses). Pick the right one, edit if needed, then
  **Approve** (or **Skip**).
- The **Filled automatically** tab lets you spot-check: edit any cell, or tick **Ask me** to move
  a line back into the questions.
- **Download Excel** (sidebar) at any time. Lines are in their original order, with
  `Street 1, Street 2, City, Locality`, plus `Original` and `Status` (automatic / approved by
  you / skipped / waiting for your answer).

Approved answers are stored in `data/aliases.db` and filled in automatically next time.

## Tuning how often it asks

Use **When to accept automatically** in the sidebar (changes apply instantly), or set the
defaults in `config.py`:

| Setting | Default | Higher means |
|---|---|---|
| `AUTO_ACCEPT_SCORE` | 90 | asked more often (only very close matches are automatic) |
| `AUTO_ACCEPT_MARGIN` | 5 | asked more often when two addresses are similar |
| `AUTO_ACCEPT_LLM` | 0.85 | LLM picks must be more confident to count |
