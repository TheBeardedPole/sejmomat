"""What a government bill says about itself: its Ocena Skutków Regulacji (OSR), the fixed form at
the end of every government bill's print. Three of its sections are read, as written, no language
model:
  1. "Jaki problem jest rozwiązywany?"                      -> the bill in short
  2. "Rekomendowane rozwiązanie, … i oczekiwany efekt"      -> what it does
  5. "Informacje na temat zakresu, czasu trwania i podsumowanie wyników konsultacji"
                                                            -> the consultations before the Sejm
The text comes from pdftotext with the PDF's layout, so lines are joined back into paragraphs, page
numbers and footnotes dropped, words split at line ends rejoined.
"""
import re

_START = re.compile(r"OCENA\s+SKUTKÓW\s+REGULACJI")
# a section heading: "1. Jaki problem…" on a line of its own, with the form's own wording
_HEADS = {
    "problem": r"1\.\s*Jaki\s+problem\s+jest\s+rozwiązywany\??",
    "solution": r"2\.\s*Rekomendowane\s+rozwiązanie[^\n]*",
    "abroad": r"3\.\s*Jak\s+problem\s+został\s+rozwiązany[^\n]*",
    "consult": r"\d+\.\s*Informacje\s+na\s+temat\s+zakresu,\s+czasu\s+trwania\s+i\s+podsumowanie\s+wyników\s+konsultacji",
    "finance": r"\d+\.\s*Wpływ\s+na\s+sektor\s+finansów\s+publicznych",
}
_HEAD_RE = {k: re.compile(rf"^[ \t\f]*{v}\.?[ \t]*$", re.M | re.I) for k, v in _HEADS.items()}
_ANY_HEAD = re.compile(r"^[ \t\f]*\d{1,2}\.\s+(?:Jaki|Rekomendowane|Jak\s+problem|Podmioty|Informacje\s+na\s+temat|Wpływ|"
                       r"Zmiana\s+obciążeń|Planowane\s+wykonanie|W\s+jaki\s+sposób|Załączniki|Dane\s+i\s+wskaźniki)\b", re.M)

# a lead that says no public consultation was held
# "public" or "social" consultations: the forms use both words for the same step
_PUB = r"(?:publiczn|społeczn)"
_SKIPPED = re.compile(r"odstąpiono\s+od\s+(?:przeprowadz\w+\s+)?(?:pre-?\s*konsultacji\s+i\s+)?(?:opiniowania\s+i\s+)?konsultacji"
                      rf"|nie\s+był\w*\s+przedmiotem\s+konsultacji\s+{_PUB}"
                      rf"|nie\s+podlega\w*\s+konsultacjom\s+{_PUB}|bez\s+przeprowadz\w+\s+konsultacji"
                      rf"|nie\s+wymaga\w*\s+(?:przeprowadz\w+\s+)?konsultacji\s+{_PUB}"
                      r"|z\s+pominięciem\s+(?:etapu\s+)?(?:\w+\s+){0,2}?konsultacji|rezygnacj\w+\s+z\s+(?:prowadzenia\s+)?(?:opiniowania\s+i\s+)?konsultacji", re.I)
_DAYS = re.compile(rf"(\d+)[\s-]*(?:dniow\w+|dni\w*)\s+(?:\w+\s+){{0,3}}?konsultacj\w*\s+{_PUB}", re.I)
_DAYS_TOO = re.compile(rf"konsultacj\w*\s+{_PUB}\w*\s+(?:\w+\s+){{0,4}}?(?:w\s+terminie|trwał\w*|przez\s+okres|na\s+okres|z\s+terminem)\s+(\d+)\s+dni", re.I)


def _section(text, key):
    m = _HEAD_RE[key].search(text)
    if not m:
        return None
    rest = text[m.end():]
    end = _ANY_HEAD.search(rest)
    return rest[:end.start()] if end else rest[:8000]


def _paragraphs(raw):
    """pdftotext lines as paragraphs: blank lines and list items start a new one; page numbers,
    footnote blocks and footnote marks go."""
    lines, skip = [], False
    for line in raw.split("\n"):
        s = line.strip()
        if re.fullmatch(r"\d{1,3}\)", s):            # a footnote's number on its own line: its block
            skip = True
            continue
        if skip:
            if not s or re.fullmatch(r"\d{1,3}", s):
                skip = False
            continue
        if re.fullmatch(r"\d{1,3}|–\s*\d+\s*–|-\s*\d+\s*-", s):   # page number
            continue
        lines.append(s)
    paras, cur = [], ""
    for s in lines:
        if not s:
            if cur and re.search(r"[.:;!?”)]$", cur):
                paras.append(cur)
                cur = ""
            continue
        item = re.match(r"(?:\d{1,2}\)|[a-z]\)|[–•-])\s", s)
        if cur and item:
            paras.append(cur)
            cur = s
        elif cur.endswith("-") and not cur.endswith(" -") and re.match(r"[a-ząćęłńóśźż]", s):
            cur = cur[:-1] + s                       # a word split at the line end
        else:
            cur = f"{cur} {s}" if cur else s
    if cur:
        paras.append(cur)
    out = []
    for p in paras:
        p = re.sub(r"(?<=[a-ząćęłńóśźżA-Z”])\d{1,2}\)(?=[\s.,;:]|$)", "", p)   # footnote marks: "OSR1)"
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p)
    return out


_AIM = re.compile(r"(?:^|(?<=[.;]\s))[^.;]*?(?:\bcel(?:em|u)?\s+(?:projektu|projektowanej|ustawy|regulacji|nowelizacji)|ma\s+na\s+celu|celem\s+jest)", re.I)


def aim(paras, limit=380):
    """The sentence that says what the bill is for ("Celem projektu jest…"), from where it starts,
    or the first paragraph."""
    for p in paras[:6]:
        m = _AIM.search(p)
        if m:
            return lead([p[m.start():].lstrip()], limit)
    return lead(paras, limit)


# "…, zwanego dalej „projektem ustawy”," and "(dalej: „ZPI”)": definitions, noise in a summary
_DALEJ = re.compile(r",?\s*(?:zwan\w+\s+dalej|dalej\s+(?:jako|zwan\w+)|dalej:?)\s*:?\s*„[^”]{1,80}”\s*(?=[,.;)])|\s*\((?:dalej|zwan\w+\s+dalej)\s*(?:jako|:)?\s*„[^”]{1,80}”\)")
_ABBR = re.compile(r"\b(?:Dz|U|M\.P|r|poz|art|ust|pkt|nr|zm|tj|in|ww|tzw|ok|np|św|im|S\.A|późn|lit|tys|mln|mld|zł)\.$")


def _from_prose(paras):
    """From the first paragraph that is not a list item on (a section may open with a stray item)."""
    for i, p in enumerate(paras):
        if not re.match(r"(?:\d{1,2}\)|[a-z]\)|[–•-])\s", p):
            return paras[i:]
    return paras


def lead(paras, limit=480):
    """The first paragraph, cut at a sentence end near `limit` characters (whole if shorter)."""
    if not paras:
        return ""
    p = _DALEJ.sub("", paras[0])
    # "Projekt przewiduje zmianę:" goes on into its list
    rest = iter(paras[1:])
    while p.endswith(":") or (p.endswith(";") and len(p) < limit):
        nxt = next(rest, None)
        if not nxt or len(p) >= limit:
            break
        p = f"{p} {_DALEJ.sub('', nxt)}"
    if len(p) <= limit:
        return p
    cut = [m.end() for m in re.finditer(r"[.;](?=\s+[A-ZĄĆĘŁŃÓŚŹŻ])", p)
           if m.end() <= limit and not _ABBR.search(p[:m.end()])]
    return p[:cut[-1]] if cut else p[:limit].rsplit(" ", 1)[0] + "…"


def consultation_status(paras):
    """("skipped", None), ("held", days or None) or (None, None) when the section does not say."""
    text = " ".join(paras)
    if not text:
        return None, None
    if _SKIPPED.search(text) and not re.search(rf"(?:skierowan|przekazan|przesłan)\w+\s+do\s+(?:\d+[\s-]*dniow\w+\s+)?konsultacji\s+{_PUB}", text, re.I):
        return "skipped", None
    m = _DAYS.search(text) or _DAYS_TOO.search(text)
    if m:
        return "held", int(m[1])
    if re.search(rf"konsultacj\w*\s+{_PUB}|opiniowani|przekazan\w*\s+do\s+(?:opinii|zaopiniowania)|uwag", text, re.I):
        return "held", None
    return None, None


# the lines every OSR has about the lobbying act and the RCL's bulletin: true of every bill, so not
# the lead of its consultations
_BOILERPLATE = re.compile(r"działalności\s+lobbingowej|Biuletynie\s+Informacji\s+Publicznej|Regulamin\s+pracy\s+Rady", re.I)


def consult_lead(paras):
    """The consultations' first paragraph that says something of its own."""
    own = [p for p in paras if not _BOILERPLATE.search(p)]
    return lead(own or paras)


def read(text):
    """A print's OSR: {"problem": [paragraphs], "solution": [...], "consult": [...], "summary":
    the problem's first paragraph, "status": "skipped"/"held"/None, "days": int or None}, or None
    when the print has no OSR."""
    if not text:
        return None
    m = _START.search(text)
    if not m:
        return None
    body = text[m.end():]
    got = {k: _paragraphs(s) for k in ("problem", "solution", "consult") if (s := _section(body, k)) is not None}
    if not got.get("problem") and not got.get("consult"):
        return None
    status, days = consultation_status(got.get("consult") or [])
    return {"problem": got.get("problem") or [], "solution": got.get("solution") or [],
            "consult": got.get("consult") or [], "summary": aim(got.get("problem") or []),
            "solution_lead": lead(_from_prose(got.get("solution") or []), 380),
            "consult_lead": consult_lead(got.get("consult") or []),
            "status": status, "days": days}
