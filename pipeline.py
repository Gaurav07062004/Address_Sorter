from config import AUTO_ACCEPT_LLM, AUTO_ACCEPT_MARGIN, AUTO_ACCEPT_SCORE
from match import AddressMatcher
from normalize import ParsedLine, normalize, parse_line
from rerank import rerank


def suggest(raw: str, matcher: AddressMatcher, use_llm: bool = True) -> tuple[ParsedLine, list[dict]]:
    parsed = parse_line(raw)
    cands = matcher.candidates(parsed)
    if use_llm:
        cands = rerank(raw, cands)
    return parsed, cands


def _same_place(a: dict, b: dict) -> bool:
    return (normalize(a["street"]), normalize(a["locality"])) == (normalize(b["street"]), normalize(b["locality"]))


def decide(cands: list[dict], min_score: float = AUTO_ACCEPT_SCORE, min_margin: float = AUTO_ACCEPT_MARGIN,
           min_llm: float = AUTO_ACCEPT_LLM) -> tuple[bool, str]:
    """(accept automatically?, short reason shown to the user)."""
    if not cands:
        return False, "no match found"
    top = cands[0]
    if top.get("source") == "alias":
        return True, "you approved this before"
    if top.get("llm_says_none"):
        return False, "LLM found no plausible match"

    llm = top.get("llm_confidence")
    if isinstance(llm, (int, float)) and llm >= min_llm:
        return True, f"LLM {llm:.0%} sure"

    runner = next((c for c in cands[1:] if not _same_place(c, top)), None)
    margin = top["score"] - runner["score"] if runner else 100.0
    if top["score"] >= min_score and margin >= min_margin:
        return True, f"score {top['score']:.0f}, {margin:.0f} ahead of next"
    if top["score"] < min_score:
        return False, f"low score ({top['score']:.0f})"
    return False, (f"close call: {top['street']}, {top['locality']} ({top['score']:.0f}) vs "
                   f"{runner['street']}, {runner['locality']} ({runner['score']:.0f})")


def to_record(parsed: ParsedLine, cand: dict | None) -> dict:
    cand = cand or {"street": "", "city": "", "locality": ""}
    return {"Street 1": f"{parsed.number} {cand['street']}".strip() if cand["street"] else parsed.number,
            "Street 2": parsed.street2, "City": cand["city"], "Locality": cand["locality"]}
