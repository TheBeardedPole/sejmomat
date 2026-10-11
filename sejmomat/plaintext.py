"""Reflow pdftotext layout output into readable paragraphs."""
import re

# Page footers of bills printed by the Sejm's legislative office:
#   "Liczba stron : 8   Data : 2026-07-31   Nazwa pliku : V7_141-22.NK   5"
#   "X kadencja/druk 2007 i 2010"
FURNITURE = r"Liczba stron\s*:.*|[IVX]+ kadencja\s*/\s*druk.*"
FURNITURE_RE = re.compile(rf"^\s*(?:{FURNITURE})\s*$")
_DROP_RE = re.compile(
    rf"^\s*([–—-]?\s*\d+\s*[–—-]?|Druk nr \S+|Tłoczono z polecenia Marszałka Sejmu.*|{FURNITURE})\s*$"
)
# Lines that start a new unit of legal text and so must not be joined to the
# previous line: "1)", "a)", "Art. 5.", "§ 2.", "– poseł X", "Uwaga:", "„3) ..."
_BREAK_RE = re.compile(
    r"^([„\"]?\s*(\d+[a-z]*|[a-z]{1,2})\)|[„\"]?\s*Art\.\s*\d|[„\"]?§\s*\d|[–—-]\s|Uwaga\b|\d+[a-z]*\.\s)"
)


def reflow(text):
    """List of paragraphs with page furniture removed and wrapped lines joined."""
    paras, cur = [], []

    def flush():
        if cur:
            paras.append(" ".join(cur))
            cur.clear()

    lines = text.replace("\f", "\n").splitlines()
    # Drop page numbers/headers together with the blank lines around them, so
    # a sentence running across a page break stays one paragraph.
    keep = [True] * len(lines)
    for i, raw in enumerate(lines):
        if raw.strip() and _DROP_RE.match(raw):
            keep[i] = False
            for step in (-1, 1):
                j = i + step
                while 0 <= j < len(lines) and not lines[j].strip():
                    keep[j] = False
                    j += step

    for raw, k in zip(lines, keep):
        if not k:
            continue
        # "W y s o k i S e j m" -> "Wysoki Sejm": join letter-spaced runs, then
        # split where a capital follows a lowercase letter.
        line = re.sub(
            r"\b(?:\w ){3,}\w\b",
            lambda m: re.sub(r"(?<=[a-ząćęłńóśźż])(?=[A-ZĄĆĘŁŃÓŚŹŻ])", " ", m[0].replace(" ", "")),
            raw,
        )
        line = re.sub(r"\s{2,}", " ", line).strip().replace(",,", "„")
        if not line:
            flush()
            continue
        if cur and _BREAK_RE.match(line):
            flush()
        if cur and re.search(r"\w-$", cur[-1]):
            cur[-1] += line  # "COVID-" + "19"
        else:
            cur.append(line)
    flush()
    return paras
