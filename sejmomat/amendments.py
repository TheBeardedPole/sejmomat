"""Splitting committee reports and Senate resolutions into numbered amendments.

Three document shapes are handled:

* additional report ("dodatkowe sprawozdanie", print NNNN-A): amendments from
  the second reading, each followed by its author ("– KP PiS"), the
  committee's recommendation ("– przyjąć"/"– odrzucić") and optional
  "Uwaga:" notes about joint voting or amendments becoming moot;
* committee report (print NNNN): minority motions ("wnioski mniejszości")
  listed after the recommendation to pass the bill, each followed by authors;
* Senate resolution (.docx) with the amendments, plus the Sejm committee
  report on it which only gives "pkt N – przyjąć/odrzucić".
"""
import re
from dataclasses import dataclass, field

from .plaintext import FURNITURE_RE



@dataclass
class Amendment:
    number: int
    text: str = ""
    authors: list = field(default_factory=list)
    recommendation: str | None = None  # "przyjąć" / "odrzucić"
    notes: list = field(default_factory=list)

    def as_dict(self):
        return {
            "number": self.number, "text": self.text, "authors": self.authors,
            "recommendation": self.recommendation, "notes": self.notes,
        }


_PAGE_NUM_RE = re.compile(r"^\s*[–—-]?\s*\d+\s*[–—-]?\s*$")
# "l)"/"I)" for "1)" are common misreads in poor PDF text layers.
_ITEM_RE = re.compile(r"^(\s*)([\dlIO]{1,3})\s?\)\s*(.*)$")
_SINGLE_RE = re.compile(r"następując(?:ą|y)\s+(?:poprawkę|wniosek)", re.I)
_REC_RE = re.compile(r"[–—-]\s*(przyjąć|odrzucić)\s*\.?\s*$")
_AUTHOR_RE = re.compile(
    r"^\s*[–—-]\s*("
    r"(?:pos(?:eł|ł|l)\w*|KKP|KK|Koło|Klub\w*|klub\w*|koło|Komisj\w*|Prezydium|Rada|Rząd)\b.*"
    r"|K\s?P[\sA-Z].*"  # "KP PiS", also misread as "K PKO" / "KPKO"
    r")$"
)
_NOTE_RE = re.compile(r"^\s*Uwaga\s*:?\s*(.*)$")
_END_RE = re.compile(r"^\s*(Warszawa,|Tłoczono)")
# Signature lines also end the list, but the same words occur in quoted law
# ("Przewodniczący Rady ..."), so they only count outside quotes.
_SIGNATURE_RE = re.compile(r"^\s*(Przewodnicząc|Sprawozdawc|Zastępca Przewodnicz)")


def _clean_lines(text):
    for line in text.replace("\f", "\n").splitlines():
        if _PAGE_NUM_RE.match(line) or re.match(r"^\s*Druk nr \S+\s*$", line) or FURNITURE_RE.match(line):
            continue
        # pdftotext renders the low opening quote typed as two commas literally
        yield line.replace(",,", "„").rstrip()


def _join(lines):
    """Join wrapped lines, keeping a line break where a new unit starts."""
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if out and not re.match(r"^([„\"]?\s*[\w…]{1,4}\)|[-–—]\s)", s):
            out[-1] += " " + s
        else:
            out.append(s)
    return "\n".join(out)


def parse_report(text, section):
    """Parse a committee report.

    section="amendments": items after "wnoszą" (an NNNN-A report).
    section="minority": items after "wnioski mniejszości" (a base report).
    """
    start_re = {
        "amendments": re.compile(r"\bwnos(?:zą|za|i)\b", re.I),
        "minority": re.compile(r"wnios\w*\s+mniejszo", re.I),
    }[section]
    items, cur, lines, indent = [], None, [], 0
    started, note_open = False, False
    depth = 0  # open „…” quotes in the current item; nothing inside starts an item

    def close():
        if cur is not None:
            cur.text = _join(lines)
            items.append(cur)

    def item_number(m):
        try:
            return int(m[2].replace("l", "1").replace("I", "1").replace("O", "0"))
        except ValueError:
            return None

    for line in _clean_lines(text):
        if not started:
            started = bool(start_re.search(line))
            # "raczy następującą poprawkę:" - a single, unnumbered item
            if started and _SINGLE_RE.search(line):
                cur, lines, indent = Amendment(1), [], 0
            continue
        if _END_RE.match(line):
            break
        if _SIGNATURE_RE.match(line) and depth <= 0 and (cur is None or cur.authors or cur.recommendation):
            break
        if cur is None and _SINGLE_RE.search(line):
            cur, lines, indent = Amendment(1), [], 0
            continue
        m = _ITEM_RE.match(line)
        expected = (cur.number + 1) if cur else 1
        number = item_number(m) if m else None
        closed = cur is None or cur.authors or cur.recommendation
        if number == expected and (closed or (depth <= 0 and len(m[1]) <= indent + 1)):
            pass
        elif number == expected + 1 and cur and closed and depth <= 0:
            pass  # item `expected` was unreadable; resync rather than stall
        else:
            number = None
        if number:
            close()
            cur, lines, indent, note_open = Amendment(number), [m[3]], len(m[1]), False
            depth = m[3].count("„") - m[3].count("”")
            continue
        if cur is None:
            continue
        if not line.strip():
            note_open = False
            continue
        if n := _NOTE_RE.match(line):
            cur.notes.append(n[1].strip())
            note_open = True
            continue
        if note_open:
            cur.notes[-1] += " " + line.strip()
            continue
        rest = line
        if r := _REC_RE.search(line):
            cur.recommendation = r[1]
            rest = line[: r.start()]
        if a := _AUTHOR_RE.match(rest):
            cur.authors.append(re.sub(r"^K\s?P\s*", "KP ", a[1].strip().rstrip(";")))
        elif rest.strip() and not r:
            if cur.authors:
                # wrapped author list ("– posłowie A, B,\n C"); anything else
                # after the author line is layout noise
                if cur.authors[-1].endswith(","):
                    cur.authors[-1] += " " + rest.strip()
            else:
                lines.append(rest)
                depth += rest.count("„") - rest.count("”")
    close()
    return items


def parse_senate_resolution(paragraphs):
    """Items from a Senate resolution's paragraphs (see textract.docx_paragraphs)."""
    items, cur, parts, started = [], None, [], False
    single = False

    def close():
        if cur is not None:
            cur.text = "\n".join(p for p in parts if p)
            items.append(cur)

    for p in paragraphs:
        text = p["text"]
        if not started:
            if re.search(r"następując\w*\s+poprawk", text, re.I):
                started = True
                single = bool(re.search(r"następującą\s+poprawkę", text, re.I))
                if single:
                    cur, parts = Amendment(1), []
            continue
        if re.match(r"^(MARSZAŁEK SENATU|uzasadnienie)", text, re.I):
            break
        # Numbering is either Word's own (level 0) or typed by hand ("1)").
        typed = re.match(r"^(\d+)\)\s*(.*)$", text) if p["level"] is None else None
        if typed and int(typed[1]) != len(items) + (2 if cur else 1):
            typed = None
        if (p["level"] == 0 or typed) and not single:
            close()
            cur, parts = Amendment(len(items) + 1), [typed[2] if typed else text]
        elif cur is not None:
            parts.append(text)
    close()
    return items


_SENATE_REC_RE = re.compile(r"pkt\s+([\d\s,i–-]+?)\s*[–—-]\s*(przyjąć|odrzucić)")


def parse_senate_report(text):
    """{amendment number: (recommendation, [notes])} from the committee report."""
    out, last = {}, []
    for line in _clean_lines(text):
        if m := _SENATE_REC_RE.search(line):
            last = []
            for a, b in re.findall(r"(\d+)(?:\s*[–-]\s*(\d+))?", m[1]):
                rng = range(int(a), int(b) + 1) if b else [int(a)]
                for n in rng:
                    out[n] = (m[2], [])
                    last.append(n)
        elif (n := _NOTE_RE.match(line)) and last:
            for num in last:
                out[num][1].append(n[1].strip())
    return out
