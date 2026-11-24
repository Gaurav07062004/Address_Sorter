import json
import sqlite3
import faiss
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from sentence_transformers import SentenceTransformer

from config import (ALIAS_DB, EMBED_MODEL, FAISS_INDEX, FUZZY_WEIGHT, LOCALITY_BLOCK_CUTOFF,
                    REFERENCE_PARQUET, SEMANTIC_WEIGHT, TOP_K)
from normalize import ParsedLine, normalize


class AddressMatcher:
    def __init__(self):
        self.df = pd.read_parquet(REFERENCE_PARQUET)
        self.keys = self.df["search_key"].tolist()
        self.index = faiss.read_index(str(FAISS_INDEX))
        self.model = SentenceTransformer(EMBED_MODEL)
        self.places = {}   # normalized locality/city name -> row positions
        for col in ("locality", "city"):
            for i, name in enumerate(self.df[col]):
                self.places.setdefault(normalize(name), []).append(i)
        self.db = sqlite3.connect(ALIAS_DB, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS aliases (raw_norm TEXT PRIMARY KEY, record TEXT)")

    # ---- alias memory: approved corrections are reused on future runs
    def save_alias(self, raw: str, record: dict):
        self.db.execute("INSERT OR REPLACE INTO aliases VALUES (?, ?)", (normalize(raw), json.dumps(record)))
        self.db.commit()

    def _alias(self, raw: str):
        row = self.db.execute("SELECT record FROM aliases WHERE raw_norm=?", (normalize(raw),)).fetchone()
        return json.loads(row[0]) if row else None

    # ---- candidate search
    def _block(self, hints: list[str]):
        rows = set()
        for h in hints:
            hit = process.extractOne(normalize(h), list(self.places), scorer=fuzz.WRatio,
                                     score_cutoff=LOCALITY_BLOCK_CUTOFF)
            if hit:
                rows.update(self.places[hit[0]])
        return sorted(rows) or None

    def candidates(self, p: ParsedLine, k: int = TOP_K) -> list[dict]:
        out = []
        alias = self._alias(p.raw)
        if alias:
            out.append({**alias, "score": 100.0, "fuzzy": 100.0, "semantic": 100.0, "source": "alias"})

        q = normalize(" ".join([p.street, *p.hints]))
        if not q:
            return out

        block = self._block(p.hints)
        pool = block if block else range(len(self.keys))
        fuzzy_hits = process.extract(q, [self.keys[i] for i in pool], scorer=fuzz.WRatio, limit=20)
        pool = list(pool)
        ids = {pool[pos] for _, _, pos in fuzzy_hits}

        qv = self.model.encode(["query: " + q], normalize_embeddings=True).astype("float32")
        _, nn = self.index.search(qv, 20)
        ids.update(int(i) for i in nn[0] if i >= 0)

        scored = []
        for i in ids:
            fz = fuzz.WRatio(q, self.keys[i])
            cos = float(self.index.reconstruct(i) @ qv[0])
            sem = max(0.0, (cos - 0.7) / 0.3) * 100       # e5 cosines cluster high; rescale 0.7-1.0 -> 0-100
            scored.append((FUZZY_WEIGHT * fz + SEMANTIC_WEIGHT * sem, fz, sem, i))
        for total, fz, sem, i in sorted(scored, reverse=True)[:k]:
            r = self.df.iloc[i]
            out.append({"street": r["street"], "locality": r["locality"], "city": r["city"],
                        "postcode": r["postcode"], "score": round(total, 1),
                        "fuzzy": round(fz, 1), "semantic": round(sem, 1), "source": "reference"})
        return out[: k + 1]
