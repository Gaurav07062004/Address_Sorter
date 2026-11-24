import re
from dataclasses import dataclass, field
from unidecode import unidecode

PHRASES = {"route royale": "royal road", "rue ": "rue "}
ABBREV = {
    "rd": "road", "rte": "route", "av": "avenue", "ave": "avenue", "bd": "boulevard",
    "blvd": "boulevard", "ch": "chemin", "cit": "cite", "lot": "lotissement",
    "lotis": "lotissement", "imm": "immeuble", "res": "residence", "appt": "apartment",
    "apt": "apartment", "pl": "place", "st": "saint", "ste": "sainte", "mt": "mont",
    "pte": "pointe", "pt": "pointe", "gde": "grande", "gd": "grand",
}
EXTRA_RE = re.compile(r"\b(lotissement|cite|residence|immeuble|apartment|building|bloc|flat|floor)\b")
# 5 digits, letter + 4 digits (islands), or the alphanumeric style e.g. 742CU001 -- verify against your data
POSTCODE_RE = re.compile(r"\b(\d{3}[A-Za-z]{2}\d{3}|[A-Za-z]?\d{5})\b")
NUMBER_RE = re.compile(r"^\s*(\d+[A-Za-z]?(?:\s*[-/]\s*\d+)?)\s+(.*)$")


def normalize(text: str) -> str:
    t = unidecode(str(text)).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for k, v in PHRASES.items():
        t = t.replace(k, v)
    return " ".join(ABBREV.get(w, w) for w in t.split())


@dataclass
class ParsedLine:
    raw: str
    number: str = ""
    street: str = ""
    street2: str = ""
    hints: list = field(default_factory=list)   # locality / city words found after the street
    postcode: str = ""


def parse_line(raw: str) -> ParsedLine:
    p = ParsedLine(raw=raw)
    text = raw
    m = POSTCODE_RE.search(text)
    if m:
        p.postcode = m.group(0).upper()
        text = text.replace(m.group(0), " ")
    parts = [x.strip() for x in re.split(r"[,;\n]", text) if x.strip()]
    extras, main = [], []
    for part in parts:
        (extras if EXTRA_RE.search(normalize(part)) else main).append(part)
    if main:
        m = NUMBER_RE.match(main[0])
        if m:
            p.number, main[0] = m.group(1), m.group(2)
        p.street = main[0]
        p.hints = main[1:]
    p.street2 = ", ".join(extras)
    return p
