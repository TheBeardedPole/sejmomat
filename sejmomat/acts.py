"""Current text of amended acts and before/after views of bill changes.

Bills amend acts with instructions such as
  "w art. 30 w ust. 2a pkt 5 otrzymuje brzmienie: „5) ...”"
To show what changes, we fetch the act's consolidated text from the ELI API
(Dziennik Ustaw), parse it into addressable units (art. → ust. → pkt → lit.)
and compare the addressed unit with its new wording.

Since 2025 the ELI API publishes acts as PDF only, so the structure is parsed
from pdftotext output.
"""
import json
import re
import difflib
from bisect import bisect_right
from dataclasses import dataclass, field
from functools import cache
from html import escape

from .changes import word_diff_html
from .config import ACTS

# ---------------------------------------------------------------- act text

_PAGE_HEADER_RE = re.compile(r"^\s*Dziennik Ustaw\s+[–-]\s*\d+\s*[–-]\s+Poz\.\s*\d+\s*$")
# Footnotes at page bottoms: "15) Dodany przez art. 1 pkt 6 ...".
_FOOTNOTE_START = (
    r"(Dodan[ya]|W brzmieniu|Uchylon[ya]|Ze zmian|Utracił|Zmian[ay]|Zmienion|Skreślon|"
    r"Niniejsz|Stosuje się|Wszedł|Weszł|Wchodzi|Ustawa|Przepis|Zgodnie|Termin|Część wspólna|"
    r"Oznaczenie|Tytuł|Nagłówek|Dotychczasow|Uznan[ya]|Por\.|Zob\.|Projekt|Przepisy)"
)
# Footnotes at page bottoms: "15) Dodany przez art. 1 pkt 6 ...", or the
# marker on its own line followed by the text ("1)" / "Niniejszą ustawą ...").
_FOOTNOTE_RE = re.compile(r"^\s*\d+\)\s+" + _FOOTNOTE_START)
_FOOTNOTE_TEXT_RE = re.compile(r"^\s*" + _FOOTNOTE_START)
# A unit label with a footnote reference glued on: "1b)15) wolno stojących"
_LABEL_FOOTNOTE_RE = re.compile(r"^(\s*(?:\d+[a-z]*|[a-z]{1,2})\))\d+\)")
_ART_FOOTNOTE_RE = re.compile(r"^(\s*Art\.\s*\d+[a-z]*\.)\d+\)")


def clean_act_text(text, bill=False):
    """Lines of an act (or of the bill attached to a committee report) with
    page furniture and footnotes removed."""
    lines = text.replace("\f", "\n").splitlines()
    if bill:
        # reports put the bill after a "Projekt" heading
        start = next((i for i, l in enumerate(lines) if re.fullmatch(r"\s*Projekt\s*", l)), None)
        if start is None:
            start = next((i for i, l in enumerate(lines) if re.match(r"\s*Art\.\s*1\.\s", l)), 0)
    else:
        # the consolidated text is an annex to the Marshal's announcement; the
        # act itself starts at the line "U S T A W A" / "USTAWA"
        start = next((i for i, l in enumerate(lines) if re.fullmatch(r"\s*U\s*S\s*T\s*A\s*W\s*A\s*", l)), 0)
    out, in_footnote, marker = [], False, False
    for line in lines[start:]:
        if _PAGE_HEADER_RE.match(line) or (bill and _BILL_FURNITURE_RE.match(line)):
            in_footnote = False
            continue
        if _FOOTNOTE_RE.match(line) or (marker and _FOOTNOTE_TEXT_RE.match(line)):
            in_footnote, marker = True, False
            continue
        if in_footnote:
            if not line.strip():
                in_footnote = False
            continue
        if re.fullmatch(r"\s*\d+\)\s*", line):
            marker = True  # a footnote reference set on its own line
            continue
        if line.strip():
            marker = False
        line = _LABEL_FOOTNOTE_RE.sub(r"\1", line)
        line = _ART_FOOTNOTE_RE.sub(r"\1", line)
        out.append(line.replace(",,", "„").rstrip())
    return out


# ------------------------------------------------------------- structure

@dataclass
class Unit:
    kind: str          # "art", "ust", "pkt", "lit", "tiret"
    label: str         # "29", "1", "40", "a"
    text: str = ""     # own text (without children)
    children: list = field(default_factory=list)

    def full_text(self, depth=0):
        """Text of the unit with its children, one sub-unit per line."""
        head = {
            "art": f"Art. {self.label}. ", "ust": f"{self.label}. ", "pkt": f"{self.label}) ",
            "lit": f"{self.label}) ", "tiret": "– ",
        }[self.kind]
        lines = [head + self.text if self.text or self.kind != "art" else head.strip()]
        for c in self.children:
            lines.append(c.full_text(depth + 1))
        return "\n".join(l for l in lines if l)

    def head(self):
        return {"art": f"Art. {self.label}.", "ust": f"{self.label}.", "pkt": f"{self.label})",
                "lit": f"{self.label})", "tiret": "–", "root": ""}[self.kind]

    def lines(self, depth=0):
        """[(depth, text)] for the unit and its sub-units, one per line."""
        out = [(depth, f"{self.head()} {self.text}".strip())]
        for c in self.children:
            out.extend(c.lines(depth + 1))
        return out

    def summary(self, limit=220):
        """One line for showing the unit as context."""
        text = f"{self.head()} {self.text}".strip()
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0] + " …"
        elif self.children:
            text += " …"
        return text

    def find(self, kind, label):
        for c in self.children:
            if c.kind == kind and c.label == label:
                return c
        return None


_ART_RE = re.compile(r"^\s*Art\.\s*(\d+[a-z]*)\.\s*(.*)$")
_UST_RE = re.compile(r"^\s*(\d+[a-z]*)\.\s+(.*)$")
_PKT_RE = re.compile(r"^\s*(\d+[a-z]*)\)\s*(.*)$")
_LIT_RE = re.compile(r"^\s*([a-z]{1,2})\)\s*(.*)$")
_TIRET_RE = re.compile(r"^\s*[–-]\s+(.*)$")
_RANK = {"root": -1, "art": 0, "ust": 1, "pkt": 2, "lit": 3, "tiret": 4}


def _join_line(prev, line):
    # "za-" + "budowy" -> "zabudowy"; keep the hyphen before a capital ("Bielsko-Biała")
    if re.fullmatch(r"[a-ząćęłńóśźż]-", prev[-2:]) and re.match(r"[a-ząćęłńóśźż]", line):
        return prev[:-1] + line
    return f"{prev} {line}" if prev else line


def parse_act(lines):
    """{article label: Unit} from cleaned act lines."""
    articles, stack = {}, []

    def attach(unit):
        while stack and _RANK[stack[-1].kind] >= _RANK[unit.kind]:
            stack.pop()
        if stack:
            stack[-1].children.append(unit)
        stack.append(unit)

    depth = 0  # open „…” quotes: quoted provisions (in bills) are text, not units
    last_art = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if depth > 0 and stack:
            # An unbalanced quote must not swallow the rest of the bill: the
            # next article in sequence, not itself quoted, starts afresh.
            m = _ART_RE.match(line)
            if not (m and last_art and m[1] == _next_label(last_art)):
                stack[-1].text = _join_line(stack[-1].text, line)
                depth = quote_depth(line, depth)
                continue
            depth = 0
        depth = quote_depth(line, depth)
        if m := _ART_RE.match(line):
            last_art = m[1]
            art = Unit("art", m[1])
            articles.setdefault(m[1], art)  # first occurrence wins (later ones are quotes)
            stack[:] = [art]
            rest = m[2]
            if um := _UST_RE.match(rest):   # "Art. 29. 1. Nie wymaga ..."
                attach(Unit("ust", um[1], um[2]))
            else:
                art.text = rest
            continue
        if not stack:
            continue
        cur = stack[-1]
        if (m := _UST_RE.match(line)) and _is_next_label(stack, "ust", m[1]):
            attach(Unit("ust", m[1], m[2]))
        elif (m := _PKT_RE.match(line)) and _is_next_label(stack, "pkt", m[1]):
            attach(Unit("pkt", m[1], m[2]))
        elif (m := _LIT_RE.match(line)) and _is_next_label(stack, "lit", m[1]):
            attach(Unit("lit", m[1], m[2]))
        elif (m := _TIRET_RE.match(line)) and cur.kind in ("lit", "tiret", "pkt"):
            attach(Unit("tiret", "", m[1]))
        else:
            cur.text = _join_line(cur.text, line)
    return articles


def quote_depth(line, depth):
    """Quote nesting after `line`. „ opens; ” and “ close; a straight " closes
    when a quote is open (",,...\"" style) and opens otherwise."""
    for ch in line:
        if ch == "„":
            depth += 1
        elif ch in "”“":
            depth -= 1
        elif ch == '"':
            depth += -1 if depth > 0 else 1
    return max(depth, 0)


def _next_label(label):
    m = re.fullmatch(r"(\d+)", label)
    return str(int(m[1]) + 1) if m else None


def _label_key(label):
    m = re.match(r"(\d+)([a-z]*)", label)
    return (int(m[1]), m[2]) if m else (0, label)


def _is_next_label(stack, kind, label):
    """Guard against wrapped lines that happen to start like a label
    ("2000 kWh;" never, but "1. stycznia" could): a new unit's label must sort
    after its previous sibling's."""
    parent = None
    for u in reversed(stack):
        if _RANK[u.kind] < _RANK[kind]:
            parent = u
            break
    if parent is None:
        return False
    siblings = [c for c in parent.children if c.kind == kind]
    if not siblings:
        return True
    prev = siblings[-1].label
    if kind == "lit":
        return label > prev or len(label) > len(prev)
    return _label_key(label) > _label_key(prev)


def lookup(articles, path):
    """Unit at path [("art","29"),("ust","1"),("pkt","40")], or None.

    A missing "ust" level is tolerated: "art. 33 pkt 2" in an article without
    paragraphs addresses the article's points directly.
    """
    if not path or path[0][0] != "art":
        return None
    unit = articles.get(path[0][1])
    for kind, label in path[1:]:
        if unit is None:
            return None
        unit = unit.find(kind, label)
    return unit


# ------------------------------------------------------- bill instructions

# "W ustawie z dnia 7 lipca 1994 r. – Prawo budowlane (Dz. U. z 2026 r. poz. 524, 605 i 646)"
CITE_RE = re.compile(
    r"W\s+ustawie\s+z\s+dnia\s+(?P<date>\d{1,2}\s+\S+\s+(?P<ayear>\d{4}))\s+r\.\s*(?:[–-]\s*)?"
    r"(?P<name>[^()]{0,250}?)\s*\(\s*Dz\.\s*U\.\s*(?:z\s+(?P<year>\d{4})\s+r\.\s*)?poz\.\s*(?P<pos>\d+)"
    r"(?P<rest>[^)]*)\)\s*(?P<list>wprowadza\s+się\s+następujące\s+zmiany\s*:)?"
)
_BILL_FURNITURE_RE = re.compile(
    r"^\s*(Liczba stron\s*:.*|[IVX]+ kadencja/druk nr \S+|\d+|[–-]\s*\d+\s*[–-]|Druk nr \S+)\s*$"
)


def clean_bill_lines(text):
    out = []
    for line in text.replace("\f", "\n").splitlines():
        if _BILL_FURNITURE_RE.match(line):
            continue
        out.append(line.replace(",,", "„").rstrip())
    return out


def _depth_delta(s):
    return s.count("„") - s.count("”")


def _split(lines, marker):
    """Split lines into (head, [(label, lines)]) at `marker` lines outside quotes."""
    head, items, depth = [], [], 0
    for line in lines:
        m = marker.match(line) if depth <= 0 else None
        if m:
            items.append((m[1], [line[m.end():]]))
        elif items:
            items[-1][1].append(line)
        else:
            head.append(line)
        depth += _depth_delta(line)
    return head, items


_NUM_MARK = re.compile(r"^\s*(\d+[a-z]*)\)\s*")
_LIT_MARK = re.compile(r"^\s*([a-z]{1,2})\)\s*")
_TIRET_MARK = re.compile(r"^\s*([–-])\s+")


def _flat(lines):
    out = ""
    for line in lines:
        s = line.strip()
        if s:
            out = _join_line(out, s)
    return out


def instructions(lines):
    """Flatten a change list into [(label, context, own text)].

    "4) w art. 42 w ust. 1: a) w pkt 1 ..., b) w pkt 2 ..." yields
    ("4a", "w art. 42 w ust. 1:", "w pkt 1 ...") and so on.
    """
    out = []

    def walk(lines, label, ctx, markers):
        if markers:
            head, items = _split(lines, markers[0])
            if items:
                head_text = _flat(head)
                for sub, sub_lines in items:
                    walk(sub_lines, f"{label}{sub if sub not in '–-' else '–'}",
                         f"{ctx} {head_text}".strip(), markers[1:])
                return
            return walk(lines, label, ctx, markers[1:])
        out.append((label, ctx, _flat(lines)))

    walk(lines, "", "", [_NUM_MARK, _LIT_MARK, _TIRET_MARK])
    return out


_ADDR_RE = re.compile(
    r"\b(art\.?|ust\.?|§|pkt|lit\.|tiret)\s*(\d+[a-z]*|[a-z]{1,2}(?![a-ząćęłńóśźż])|"
    r"pierwsze|drugie|trzecie|czwarte|piąte|szóste)"
)
_KIND = {"art.": "art", "art": "art", "ust.": "ust", "ust": "ust", "§": "ust", "pkt": "pkt", "lit.": "lit", "tiret": "tiret"}


def address(text):
    """[("art","30"),("ust","2a"),("pkt","5")] from "w art. 30 w ust. 2a pkt 5"."""
    path = []
    for m in _ADDR_RE.finditer(text):
        kind, label = _KIND[m[1]], m[2]
        # a new higher-or-equal level restarts the path below it
        path = [p for p in path if _RANK[p[0]] < _RANK[kind]]
        path.append((kind, label))
    return path


def tokens(text):
    """Address tokens in order, without restarting at "art." (see resolve)."""
    return [(_KIND[m[1]], m[2]) for m in _ADDR_RE.finditer(text)]


def normalize_quotes(text):
    """Straight quotes ("...") as Polish „...” so quote handling works."""
    if '"' not in text:
        return text
    out, open_ = [], True
    for ch in text:
        if ch == '"':
            out.append("„" if open_ else "”")
            open_ = not open_
        else:
            out.append(ch)
    return "".join(out)


_LINE_KIND = [
    (re.compile(r"^Art\.\s*(\d+[a-z]*)\.\s*"), "art"), (re.compile(r"^§\s*(\d+[a-z]*)\.\s*"), "ust"),
    (re.compile(r"^(\d+[a-z]*)\.\s+"), "ust"), (re.compile(r"^(\d+[a-z]*)\)\s*"), "pkt"),
    (re.compile(r"^([a-z]{1,2})\)\s*"), "lit"), (re.compile(r"^[–-]()\s+"), "tiret"),
]


def tree_from_text(text):
    """Unit tree of quoted legal text (e.g. the wording a bill gives a provision)."""
    root, stack = Unit("root", ""), []
    stack.append(root)
    for _, line in split_units(text):
        for rx, kind in _LINE_KIND:
            if m := rx.match(line):
                unit = Unit(kind, m[1], line[m.end():])
                while _RANK[stack[-1].kind] >= _RANK[kind]:
                    stack.pop()
                stack[-1].children.append(unit)
                stack.append(unit)
                break
        else:
            stack[-1].text = f"{stack[-1].text} {line}".strip()
    return root


def _quoted_part(text):
    i = text.find("„")
    return (text[:i], _quoted(text, i + 1)) if i >= 0 else (text, "")


def resolve(articles, toks):
    """(unit, context unit) for an address that may reach inside quoted text.

    "w art. 1 w pkt 34, w art. 38a ust. 14": art. 1 pkt 34 is a unit of the
    bill; art. 38a ust. 14 is inside the provision that unit quotes.
    """
    if not toks or toks[0][0] != "art" or toks[0][1] not in articles:
        return None, None
    unit, parent = articles[toks[0][1]], None
    for i, (kind, label) in enumerate(toks[1:], start=1):
        child = unit.find(kind, label)
        if child is not None:
            unit, parent = child, unit
            continue
        # Not a direct sub-unit: descend into the provision this unit quotes.
        head, quoted = _quoted_part(unit.text)
        if not quoted:
            return None, None
        own = tokens(head)          # what the quoting unit itself addresses
        rest = toks[i:]
        k = 0
        while k < len(own) and k < len(rest) and own[k] == rest[k]:
            k += 1
        if k == 0 and own:
            return None, None
        inner = tree_from_text(quoted)
        target = inner
        if len(inner.children) == 1 and own and inner.children[0].kind == own[-1][0]:
            target = inner.children[0]  # the quoted text is the addressed unit itself
        for kind2, label2 in rest[k:]:
            target = target.find(kind2, label2) if target else None
        return target, unit
    return unit, parent


def where_label(path):
    names = {"art": "art.", "ust": "ust.", "pkt": "pkt", "lit": "lit.", "tiret": "tiret"}
    return " ".join(f"{names[k]} {l}" for k, l in path)


# Bills use descriptive forms ("otrzymuje brzmienie", "dodaje się"),
# amendments to bills imperative ones ("nadać brzmienie", "dodać").
_REPLACE_RE = re.compile(r"(?:otrzymuj[eą]|nadaje\s+się|nadać)\s+(?:mu\s+|im\s+)?brzmienie\s*[:;]?\s*„")
_WORDS_RE = re.compile(
    r"(?:wyraz\w*|oznaczeni\w*|liczb\w*|kwot\w*|zdani\w*|cyfr\w*|dat\w*)\s+„([^”„]*)”\s+"
    r"(?:zastępuje\s+się|zastąpić)\s+\w+\s+„([^”„]*)”"
)
_REPEAL_RE = re.compile(r"\b(?:uchyla\s+się|skreśla\s+się|skreślić|uchylić)\b")
_ADD_RE = re.compile(r"\b(?:dodaje\s+się|dodać)\s+(.{0,80}?)\s+w\s+brzmieniu\s*:?\s*„")
_AFTER_RE = re.compile(r"\bpo\s+(?:art\.|ust\.|§|pkt|lit\.|tiret)")
# "kropkę zastępuje się średnikiem" / "średnik zastąpić przecinkiem" before an addition
_PUNCT_RE = re.compile(
    r"\b(kropk\w*|średnik\w*|przecin\w*)\s+(?:zastępuje\s+się|zastąpić)\s+(kropk\w*|średnik\w*|przecin\w*)"
)
_PUNCT = {"kropk": ".", "średnik": ";", "przecin": ","}


def _punct(word):
    return next(v for k, v in _PUNCT.items() if word.startswith(k))


def _quoted(text, start):
    """Text from position `start` (just after an opening „) to its closing ”."""
    depth, i = 1, start
    while i < len(text):
        if text[i] == "„":
            depth += 1
        elif text[i] == "”":
            depth -= 1
            if depth == 0:
                return text[start:i].strip()
        i += 1
    return text[start:].strip().rstrip("”;.")


def interpret(ctx, own):
    """[{"op", "path", ...}] for one instruction.

    For additions, "after" tells whether the path ends at the unit the new
    ones follow ("po pkt 40 dodaje się pkt 41") or at their parent
    ("w art. 7 dodaje się ust. 1aa").
    """
    full = f"{ctx} {own}".strip()
    # "w dodawanej lit. f" - a unit added by another amendment or change
    pending = bool(re.search(r"\bdodawan\w*", full))
    ops = []
    if m := _REPLACE_RE.search(full):
        ops.append({"op": "replace", "path": address(full[: m.start()]), "new": _quoted(full, m.end())})
    elif words := _WORDS_RE.findall(full):
        first = _WORDS_RE.search(full)
        ops.append({"op": "words", "path": address(full[: first.start()]), "words": words})
    elif m := _ADD_RE.search(full):
        before = full[: m.start()]
        path = address(before)
        what = address(m[1])
        punct = _PUNCT_RE.search(before)
        ops.append({
            "op": "add", "path": path, "what": m[1], "new": _quoted(full, m.end()),
            # "po pkt 40 dodaje się pkt 41", or "w pkt 40 ... dodaje się pkt 41"
            "after": bool(_AFTER_RE.search(before)) or bool(path and what and path[-1][0] == what[0][0]),
            "punct": (_punct(punct[1]), _punct(punct[2])) if punct else None,
        })
    elif m := _REPEAL_RE.search(full):
        before, after = address(full[: m.start()]), address(full[m.end():])
        merged = [p for p in before if not after or _RANK[p[0]] < _RANK[after[0][0]]] + after
        ops.append({"op": "repeal", "path": merged})
    for op in ops:
        op["pending"] = pending
        cut = {"replace": _REPLACE_RE, "words": _WORDS_RE, "add": _ADD_RE, "repeal": _REPEAL_RE}[op["op"]].search(full)
        op["tokens"] = tokens(full[: cut.start()]) if cut else []
        if op["op"] == "repeal" and cut:
            op["tokens"] += tokens(full[cut.end():])  # "skreślić art. 26", "w art. 5 uchyla się pkt 2"
    return ops


_ART_HEAD_RE = re.compile(r"^\s*Art\.\s*\d+[a-z]*\.\s")


def amending_articles(text):
    """[{"cite": match dict, "changes": [(label, ctx, own)]}] in a bill or amendment text."""
    lines = clean_bill_lines(text)
    flat = "\n".join(lines)
    # start offset of every line, for mapping matches to lines
    starts, pos = [], 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1
    out = []
    for m in CITE_RE.finditer(flat):
        first = bisect_right(starts, m.end()) - 1
        tail = [flat[m.end(): starts[first] + len(lines[first])]]
        if m["list"]:
            # the change list runs until the next top-level article
            depth = 0
            for line in lines[first + 1:]:
                if depth <= 0 and _ART_HEAD_RE.match(line):
                    break
                tail.append(line)
                depth += _depth_delta(line)
            changes = instructions(tail)
        else:
            # single change: "W ustawie ... (Dz. U. ...) w art. 5 ust. 2 otrzymuje brzmienie: „...”."
            for line in lines[first + 1: first + 60]:
                if _ART_HEAD_RE.match(line):
                    break
                tail.append(line)
                if re.search(r"”\s*[.;]\s*$", line):
                    break
            changes = [("", "", _flat(tail))]
        out.append({"cite": {k: (v or "").strip() for k, v in m.groupdict().items()}, "changes": changes})
    return out


# ------------------------------------------------------------ comparisons

def act_id(cite):
    """ELI id "DU/2026/524" of the text a bill cites (first position listed)."""
    return f"DU/{cite['year'] or cite['ayear']}/{cite['pos']}"


@cache
def load_act(eli_id):
    """(meta, {article: Unit}) from data/acts, or (None, None) if not fetched."""
    base = ACTS / eli_id.replace("/", "-")
    txt, meta = base.with_suffix(".txt"), base.with_suffix(".json")
    if not txt.exists():
        return None, None
    return (json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {},
            parse_act(clean_act_text(txt.read_text(encoding="utf-8"))))


def _norm(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    # PDFs mix en dashes and hyphens between words ("Szczecin - Świnoujście")
    return re.sub(r"(?<=\S) [-–] (?=\S)", " – ", re.sub(r"^- ", "– ", text))


def _key(line):
    """Comparison key ignoring the unit label, dash style and punctuation."""
    line = re.sub(r"^(Art\.\s*\d+[a-z]*\.|§\s*\d+[a-z]*\.|\d+[a-z]*[.)]|[a-z]{1,2}\)|[–-])\s*", "", line)
    return re.sub(r"[\s–\-,.;:„”\"]+", " ", line).strip().lower()


# Unit labels at the start of a line of new text, and their nesting rank.
_LABEL_KINDS = [
    (re.compile(r"Art\.\s*\d+[a-z]*\."), 0), (re.compile(r"§\s*\d+[a-z]*\."), 1),
    (re.compile(r"\d+[a-z]*\.(?=\s)"), 1), (re.compile(r"\d+[a-z]*\)"), 2),
    (re.compile(r"[a-z]{1,2}\)"), 3), (re.compile(r"[–-](?=\s)"), 4),
]
_SPLIT_RE = re.compile(
    r"(?<=[;:,.])\s+(?=(?:Art\.\s*\d+[a-z]*\.|§\s*\d+[a-z]*\.|\d+[a-z]*\.\s|\d+[a-z]*\)|[a-z]{1,2}\)|[–-]\s))"
)


def _rank_of(line):
    for rx, rank in _LABEL_KINDS:
        if rx.match(line):
            return rank
    return None


_ABBREV_END_RE = re.compile(r"\b(?:Art|art|ust|pkt|lit|nr|poz|r|Dz|U|zm)\.$|§$")


def split_units(text):
    """[(depth, line)] for quoted legal text, one line per unit.

    Splits only outside nested quotes (quoted provisions stay with the unit
    that quotes them) and never right after an abbreviation ("Art.", "r.").
    """
    lines, depth = [], 0
    for piece in _SPLIT_RE.split(_norm(text)):
        piece = piece.strip()
        if not piece:
            continue
        if lines and (depth > 0 or _ABBREV_END_RE.search(lines[-1])):
            lines[-1] += " " + piece
        else:
            lines.append(piece)
        depth += piece.count("„") - piece.count("”")
    ranks = [_rank_of(l) for l in lines]
    base = next((r for r in ranks if r is not None), 0)
    out, last = [], 0
    for line, rank in zip(lines, ranks):
        depth = max(0, rank - base) if rank is not None else last
        out.append((depth, line))
        last = depth
    return out


def _rows_diff(old, new):
    """Line-aligned diff of [(depth, text)] lists into rows.

    Lines are aligned on a key without labels and punctuation, so a point
    that only changes its label or list style still lines up with its old
    version; within unaligned blocks, only similar lines are paired.
    """
    rows = []
    a, b = [_norm(t) for _, t in old], [_norm(t) for _, t in new]
    ka, kb = [_key(t) for t in a], [_key(t) for t in b]

    def row(depth, state, html):
        rows.append({"depth": depth, "state": state, "html": html})

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if a[i] == b[j]:
                    row(new[j][0], "same", escape(b[j]))
                else:
                    row(new[j][0], "changed", word_diff_html(a[i], b[j]))
            continue
        i, j = i1, j1
        while i < i2 or j < j2:
            if i < i2 and j < j2 and difflib.SequenceMatcher(None, ka[i], kb[j]).ratio() >= 0.5:
                row(new[j][0], "changed", word_diff_html(a[i], b[j]))
                i, j = i + 1, j + 1
            elif i < i2 and (j >= j2 or (i2 - i) >= (j2 - j)):
                row(old[i][0], "removed", escape(a[i]))
                i += 1
            else:
                row(new[j][0], "added", escape(b[j]))
                j += 1
    return rows


CONTEXT = 2  # sibling units shown before and after a change


def _siblings(articles, path):
    """(siblings list, parent) of the unit at `path`."""
    if len(path) == 1:
        return list(articles.values()), None
    parent = lookup(articles, path[:-1])
    if parent is None:
        return [], None
    kind = path[-1][0]
    return [c for c in parent.children if c.kind == kind] or parent.children, parent


def _context(units):
    return [{"depth": 0, "state": "context", "html": escape(u.summary())} for u in units]


def _gap():
    return {"depth": 0, "state": "gap", "html": "…"}


def _anchor_row(unit, punct):
    """The unit new ones follow, with its final punctuation changed if asked."""
    text = _norm(unit.summary(10_000) if not unit.children else unit.lines()[-1][1])
    if punct and text.endswith(punct[0]):
        return {"depth": 0, "state": "changed", "html": word_diff_html(text, text[:-1] + punct[1])}
    return {"depth": 0, "state": "context", "html": escape(unit.summary())}


def _around(articles, path, body_rows, include_target=False, anchor=None):
    """Body rows framed by up to CONTEXT siblings on each side of path's unit."""
    sibs, parent = _siblings(articles, path)
    idx = next((i for i, u in enumerate(sibs) if u.kind == path[-1][0] and u.label == path[-1][1]), None)
    rows = []
    if parent is not None:
        rows.append({"depth": 0, "state": "parent", "html": escape(parent.summary(160))})
    if idx is None:
        return rows + body_rows
    before = sibs[max(0, idx - CONTEXT): idx + (1 if include_target else 0)]
    after = sibs[idx + 1: idx + 1 + CONTEXT]
    if idx - CONTEXT > 0:
        rows.append(_gap())
    before_rows = _context(before)
    if include_target and anchor is not None and before:
        before_rows[-1] = anchor  # the anchor itself, e.g. with "." -> ";"
    rows += before_rows + body_rows + _context(after)
    if idx + 1 + CONTEXT < len(sibs):
        rows.append(_gap())
    return rows


def rows_html(rows):
    return "".join(
        f'<div class="r r-{r["state"]}" style="--d:{r["depth"]}">{r["html"]}</div>' for r in rows
    )


def compare(articles, op):
    """{"where", "op", "rows", "html", "found"} for one parsed instruction, in context."""
    path = op["path"]
    unit = lookup(articles, path) if articles and path else None
    nested_parent = None
    if unit is None and articles and op.get("tokens"):
        unit, nested_parent = resolve(articles, op["tokens"])
    where = where_label(op.get("tokens") or path) if nested_parent is not None else where_label(path)
    found = unit is not None
    if op["op"] == "add":
        new_rows = [{"depth": d, "state": "added", "html": escape(t)} for d, t in split_units(op["new"])]
        if op.get("after"):
            parent = where_label(path[:-1])
            where = f"{parent}: po {where_label(path[-1:])} dodaje się {op['what']}".lstrip(": ")
            rows = (_around(articles, path, new_rows, include_target=True, anchor=_anchor_row(unit, op.get("punct")))
                    if found else new_rows)
        else:
            where = f"{where}: dodaje się {op['what']}".lstrip(": ")
            if found:
                tail = unit.children[-CONTEXT:]
                rows = ([{"depth": 0, "state": "parent", "html": escape(unit.summary(160))}]
                        + ([_gap()] if len(unit.children) > CONTEXT else []) + _context(tail) + new_rows)
            else:
                rows = new_rows
        found = found or not articles
    elif not found:
        new = op.get("new") or "".join(f"„{a}” → „{b}” " for a, b in op.get("words", []))
        rows = [{"depth": d, "state": "added", "html": escape(t)} for d, t in split_units(new)] if new else []
    else:
        old = unit.lines()
        if op["op"] == "replace":
            body = _rows_diff(old, split_units(op["new"]))
        elif op["op"] == "words":
            new = []
            for d, t in old:
                for a, b in op["words"]:
                    t = _norm(t).replace(_norm(a), _norm(b))
                new.append((d, t))
            body = _rows_diff(old, new)
        else:  # repeal
            body = [{"depth": d, "state": "removed", "html": escape(t)} for d, t in old]
        if nested_parent is not None:
            # inside quoted text: show the quoting bill provision as context
            rows = [{"depth": 0, "state": "parent", "html": escape(nested_parent.summary(160))}] + body
        else:
            rows = _around(articles, path, body)
    return {"where": where, "op": op["op"], "rows": rows, "html": rows_html(rows), "found": found,
            "pending": not found and bool(op.get("pending"))}


def changes_against(articles, text):
    """Compare every instruction in `text` (e.g. an amendment) with `articles`."""
    out = []
    for label, ctx, own in instructions(normalize_quotes(text or "").split("\n")):
        for op in interpret(ctx, own):
            out.append({"label": label, **compare(articles, op)})
    return out


@cache
def bill_changes(text):
    """[{"cite", "eli", "meta", "changes": [compare(...) + label]}] for a bill or amendment text."""
    out = []
    for art in amending_articles(text or ""):
        eli = act_id(art["cite"])
        meta, articles = load_act(eli)
        changes = []
        for label, ctx, own in art["changes"]:
            for op in interpret(ctx, own):
                changes.append({"label": label, **compare(articles, op)})
        if changes:
            out.append({"cite": art["cite"], "eli": eli, "meta": meta, "loaded": articles is not None,
                        "changes": changes})
    return out
