"""Results of the Sejm's public consultations ("konsultacje społeczne": an online survey on bills from
MPs, committees, citizens, and some from the Senate and the President), read from the results PDF
the Sejm publishes (a Power BI report, "Wyniki konsultacji społecznych - …").

The PDFs are on orka.sejm.gov.pl, which turns automated requests away, so they are saved by hand
(in a browser) into CACHE/konsultacje/ and read by `python -m sejmomat.survey`, which keeps what it
reads in data/survey.json: {bill number at the Sejm ("RPW/34574/2026"): {"respondents", "questions":
[{"n", "text", "scale", "answers": {label: count}}]}}. The PDFs themselves are not kept in git.

Each question is a table: a header row ("… Kobiety Mężczyźni Ogółem"), a row per answer ("wybrano
5", "Tak", "brak odpowiedzi") and "Ogółem". Charts printed beside the table put their own numbers on
the same lines, so a row's count is read from the "Ogółem" column only.
"""
import json
import re
import subprocess
import sys

from .config import CACHE as _CACHE, DATA

CACHE = _CACHE / "konsultacje"   # not committed
PATH = DATA / "survey.json"

_Q = re.compile(r"^\f?Pytanie\s+(\d+)\.?(?:\s|$)")   # at the line's start (the table's header is indented)
# a table's header; older reports say "Kobieta Mężczyzna Suma", newer "Kobiety Mężczyźni Ogółem"
_HEAD = re.compile(r"Kobiet[ya]\s+Mężczy(?:źni|zna)\s+(?:Ogółem|Suma)")
# an answer's row; a chart's label may come before it on the line
_ROW = re.compile(r"(?:^|\s{2,}|\)\s+)(wybrano\s+[0-5]|Tak|Nie|[Bb]rak\s+odpowiedzi|Siebie|Podmiot\s+inny\s+niż\s+osoba\s+prawna|Osobę\s+prawną)\b")
_TOTAL = re.compile(r"(?:^|\s{2,})(?:Ogółem|Suma)\b")


def _total_at(line, col):
    """The number ending at or just before column `col` (the header's "Ogółem" end), else None."""
    best = None
    for m in re.finditer(r"\d+", line):
        if col - 8 <= m.end() <= col + 14:
            best = int(m[0])
    return best


def parse(text):
    """The survey's questions with their answer counts, and the number of respondents."""
    lines = text.split("\n")
    out, respondents = [], None
    i = 0
    while i < len(lines):
        m = _Q.match(lines[i])
        if not m:
            i += 1
            continue
        n = int(m[1])
        words, j = [], i + 1
        while j < len(lines) and lines[j].strip() and not lines[j].lstrip().startswith(("Odpowiedzi w skali", "Odpowiedzi:")):
            words.append(lines[j].strip())
            j += 1
        scale = j < len(lines) and lines[j].lstrip().startswith("Odpowiedzi w skali")
        # the table's header: "… Kobiety Mężczyźni Ogółem" (chart labels may follow on the line)
        while j < len(lines) and not _Q.match(lines[j]) and not _HEAD.search(lines[j]):
            j += 1
        if j >= len(lines) or _Q.match(lines[j]):
            i = j
            continue
        col = _HEAD.search(lines[j]).end()
        answers = {}
        j += 1
        while j < len(lines) and not _Q.match(lines[j]):
            s = lines[j]
            if _TOTAL.search(s) and _total_at(s, col) is not None:
                total = _total_at(s, col)
                respondents = respondents or total
                break
            r = _ROW.search(s)
            if r:
                count = _total_at(s, col)
                if count is not None:
                    label = re.sub(r"\s+", " ", r[1]).lower()
                    answers[label] = count
            j += 1
        out.append({"n": n, "text": " ".join(words), "scale": scale, "answers": answers})
        i = j
    return {"respondents": respondents, "questions": out}


def support(result, n):
    """Question `n` on the 1–5 scale as {"for": 4–5, "neutral": 3, "against": 1–2, "none": no
    answer, "total"}, or None."""
    q = next((q for q in result.get("questions", []) if q["n"] == n and q["scale"]), None)
    if not q:
        return None
    a = q["answers"]
    got = {"for": a.get("wybrano 5", 0) + a.get("wybrano 4", 0), "neutral": a.get("wybrano 3", 0),
           "against": a.get("wybrano 2", 0) + a.get("wybrano 1", 0),
           "strongly_for": a.get("wybrano 5", 0), "strongly_against": a.get("wybrano 1", 0),
           "none": a.get("brak odpowiedzi", 0) + a.get("wybrano 0", 0)}
    got["total"] = sum(v for k, v in got.items() if k in ("for", "neutral", "against", "none"))
    got["text"] = q["text"]
    return got if got["total"] else None


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}


def read_cache():
    """Reads every PDF in CACHE (named as the Sejm names them: RPW-34574-2026_wyniki.pdf) into
    data/survey.json, keyed by the bill's number at the Sejm."""
    known = load()
    for pdf in sorted(CACHE.glob("*_wyniki*.pdf")):
        stem = re.sub(r"_wyniki.*$", "", pdf.stem)
        text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        res = parse(text)
        if res["questions"]:
            known[stem] = res
        else:
            print(f"survey: nothing read from {pdf.name}")
    PATH.write_text(json.dumps(known, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(f"survey: {len(known)} consultations read")


def key(number):
    """A bill's number at the Sejm as the PDFs name it: "RPW/34574/2026" -> "RPW-34574-2026"."""
    return number.replace("/", "-")


if __name__ == "__main__":
    read_cache() if len(sys.argv) < 2 else print(json.dumps(parse(open(sys.argv[1]).read()), ensure_ascii=False, indent=1))
