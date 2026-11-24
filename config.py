import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

REFERENCE_PARQUET = DATA_DIR / "reference.parquet"
FAISS_INDEX = DATA_DIR / "reference.faiss"
ALIAS_DB = DATA_DIR / "aliases.db"

EMBED_MODEL = "intfloat/multilingual-e5-small"   # handles French/English/Creole-ish spellings
LLM_MODEL = os.getenv("ADDRESS_LLM_MODEL", "claude-sonnet-5-5")

TOP_K = 5
FUZZY_WEIGHT = 0.6
SEMANTIC_WEIGHT = 0.4
LOCALITY_BLOCK_CUTOFF = 80   # fuzzy score needed to restrict search to a locality/city hint
LLM_SKIP_ABOVE = 97          # skip the LLM call when the top match is already near-perfect

# Automatic acceptance: a line is filled in without asking you when
#  - it matches a correction you approved before, or
#  - the LLM picked a candidate with at least AUTO_ACCEPT_LLM confidence, or
#  - the top score is >= AUTO_ACCEPT_SCORE AND beats the next different address by >= AUTO_ACCEPT_MARGIN.
# Everything else is put in the "Needs your answer" list.
AUTO_ACCEPT_SCORE = 90
AUTO_ACCEPT_MARGIN = 5
AUTO_ACCEPT_LLM = 0.85
