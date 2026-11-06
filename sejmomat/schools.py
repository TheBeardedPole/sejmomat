"""What the MPs studied: their "Ukończona szkoła" and "Tytuł/stopień naukowy" from the Sejm's MP pages
(not in the API: read once, slowly, in a browser, into data/schools.json, {MP id: {"school", "title"}};
an older entry is the school's text alone). The text lists each school as "Uczelnia,
Wydział X, Kierunek - stopień (rok)", one after another; read here into the highest degree and the
field of the highest degree's studies.

    python -m sejmomat.schools path/to/downloaded.json   # merges a download into data/schools.json
"""
import json
import re
import sys

from .config import DATA

PATH = DATA / "schools.json"

# degrees and titles, highest first; "lekarz" (a medical degree) and "magister inżynier" count as a
# master's degree; postgraduate studies and a secondary school's "technik" are no degree
DEGREES = ["profesor", "doktor habilitowany", "doktor", "magister", "inżynier", "licencjat"]
NONE = "bez stopnia"
_DEGREE = [
    ("profesor", re.compile(r"\bprof(?:esor|\.)", re.I)),
    ("doktor habilitowany", re.compile(r"doktor\s+habilitowan|\bdr\s+hab|habilitacj", re.I)),
    ("doktor", re.compile(r"\bdoktor\b|\bdr\b(?!\s+hab)", re.I)),
    ("magister", re.compile(r"\bmagister\b|\blekarz\b|\bmgr\b", re.I)),
    ("inżynier", re.compile(r"\binżynier\b|\binż\.", re.I)),
    ("licencjat", re.compile(r"\blicencjat\b", re.I)),
]

# a field of study by the words of its studies (kierunek, else the faculty), in order: the first match
FIELDS = [
    ("Prawo i administracja", r"prawo|prawa|administracj|prawnicz"),
    ("Medycyna i zdrowie", r"lekar|medy|farmac|pielęgniar|zdrowi|weteryn|stomatolog|fizjoterap"),
    ("Ekonomia i zarządzanie", r"ekonom|zarządz|finans|rachunkow|handl|marketing|bankow|mba|biznes|logisty|turysty"),
    ("Politologia i stosunki międzynarodowe", r"politolog|nauk\w* polityczn|stosunk\w* międzynarod|europeist|bezpieczeństw"),
    ("Nauki techniczne", r"politechni|technicz|inżynier|mechani|elektr|budownict|informaty|automaty|transport|górnic|energety|chemi|geodez|architekt|telekomun|lotnic|morsk"),
    ("Rolnictwo i leśnictwo", r"rolni|leśn|zootechn|ogrodni|agro|technolog\w* żywności"),
    ("Pedagogika i nauczanie", r"pedagog|nauczan|wychowani|oligofreno|edukac"),
    ("Nauki humanistyczne i społeczne", r"histor|filolog|polonist|filozof|teolog|kulturozn|socjolog|psycholog|dziennikar|anglist|germanist|"
                                        r"archeolog|etnograf|etnolog|antropolog|nauk\w* społeczn|sztuk|muzy|teatr|aktor|film|komunikac"),
    ("Nauki ścisłe i przyrodnicze", r"matemat|fizyk|biolog|geograf|ochron\w* środowiska|ekolog|chemia"),
    ("Służby mundurowe i wojsko", r"wojsk|policj|pożarn|obron|oficer"),
    ("Sport", r"wychowani\w* fizyczn|sport|awf"),
]
_FIELD = [(name, re.compile(words, re.I)) for name, words in FIELDS]
OTHER = "Inny kierunek"


def schools(text):
    """The text as its schools, one each: [(name, degree or None, year or None)]."""
    if "\n" in (text or ""):   # read with its line breaks: a school a line
        parts = [x for x in text.split("\n")]
        return [_school(p) for p in parts if p.strip()]
    # schools run together on the page: "…(1996)Uniwersytet…", "…studia podyplomowePolitechnika…"
    parts = re.split(r"(?<=\))(?=\s*[A-ZĄĆĘŁŃÓŚŹŻ])|(?<=[a-ząćęłńóśźż])(?=[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż])", (text or "").strip())
    return [_school(p) for p in parts if p.strip()]


def _school(p):
    """One school: (its text, the degree it gave or None, the year or None). Postgraduate and doctoral
    studies ("studia doktoranckie") are no degree by themselves."""
    p = p.strip()
    year = re.search(r"\((\d{4})\)", p)
    deg = next((name for name, rule in _DEGREE if rule.search(p)), None)
    if re.search(r"studia\s+(?:podyplomowe|doktoranckie)", p, re.I) and not re.search(r"-\s*(?:doktor|profesor)", p, re.I):
        deg = None
    return (p, deg, int(year[1]) if year else None)


def _entry(entry):
    """(school text, title) of an entry, old (text) or new ({"school", "title"})."""
    if isinstance(entry, dict):
        return entry.get("school") or "", entry.get("title") or ""
    return entry or "", ""


def degree(entry):
    """The highest degree or title: the page's own "Tytuł/stopień naukowy" first (profesor, doktor
    habilitowany, doktor), else the highest the schools name; NONE without any."""
    text, title = _entry(entry)
    t = title.lower()
    if re.search(r"\bprof", t):
        return "profesor"
    if re.search(r"habilit|dr\s+hab", t):
        return "doktor habilitowany"
    if re.search(r"\bdoktor|\bdr\b", t):
        best = "doktor"
    else:
        best = None
    found = {d for _, d, _ in schools(text) if d}
    if re.search(r"\bprof(?:esor|\.)", text, re.I):
        found.add("profesor")
    if best:
        found.add(best)
    return next((d for d in DEGREES if d in found), NONE)


def field(entry):
    """The field of study of the highest degree's studies (the next school's where that one says
    nothing readable, e.g. in English), or None (no studies)."""
    text, _ = _entry(entry)
    studied = sorted(((p, d) for p, d, _ in schools(text) if d), key=lambda x: DEGREES.index(x[1]))
    if not studied:
        return None
    for school, _ in studied:
        head = school.split(" - ")[0]   # without " - magister inżynier (1985)": the degree is no field
        # the kierunek (the last part: "Uczelnia, Wydział X, Kierunek"), else the faculty and school
        for part in (head.split(",")[-1], head):
            for name, rule in _FIELD:
                if rule.search(part):
                    return name
    return OTHER


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}


def merge(path):
    """A download from the browser ({id: text}) into data/schools.json."""
    known = load()
    got = json.loads(open(path, encoding="utf-8").read())
    known.update({str(k): v for k, v in got.items() if v and (not isinstance(v, dict) or v.get("school") or v.get("title"))})
    PATH.write_text(json.dumps(dict(sorted(known.items(), key=lambda kv: int(kv[0]))), ensure_ascii=False, indent=0),
                    encoding="utf-8")
    print(f"schools: {len(known)} MPs")


if __name__ == "__main__":
    merge(sys.argv[1])
