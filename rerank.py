import json
import os
import anthropic
from config import LLM_MODEL, LLM_SKIP_ABOVE

SYSTEM = (
    "You match misspelled Mauritian addresses to a list of official candidates. "
    "Names may mix French and English (Rue/Street, Route Royale/Royal Road) and use Creole spellings. "
    'Reply with JSON only: {"best_id": <int or null>, "confidence": <0-1>, "reason": "<short>"}. '
    "Use null if no candidate is a plausible match. Never invent a candidate."
)


def rerank(raw: str, cands: list[dict]) -> list[dict]:
    if not cands or not os.getenv("ANTHROPIC_API_KEY") or cands[0]["score"] >= LLM_SKIP_ABOVE:
        return cands
    payload = {"input": raw, "candidates": [
        {"id": i, "street": c["street"], "locality": c["locality"], "city": c["city"], "postcode": c["postcode"]}
        for i, c in enumerate(cands)]}
    try:
        msg = anthropic.Anthropic().messages.create(
            model=LLM_MODEL, max_tokens=300, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        text = msg.content[0].text.strip().strip("`").removeprefix("json").strip()
        res = json.loads(text)
        best = res.get("best_id")
        if best is None:
            for c in cands:
                c["llm_says_none"] = True          # don't auto-accept; ask the person
            cands[0]["llm_reason"] = res.get("reason")
        elif isinstance(best, int) and 0 <= best < len(cands):
            cands = [cands[best]] + [c for i, c in enumerate(cands) if i != best]
            cands[0]["llm_confidence"] = res.get("confidence")
            cands[0]["llm_reason"] = res.get("reason")
    except Exception:
        pass   # fall back to the score-based ranking
    return cands
