"""Word-level before/after views for amendments that spell out both texts.

Polish amendment instructions often contain the old and new wording directly:
  w art. 3 w ust. 2 wyrazy „po tym dniu” zastąpić wyrazami „nie wcześniej niż tego dnia”
Those can be shown as a diff without access to the bill text. Instructions
that only give a new wording ("nadać brzmienie") need the current text of the
bill or act and are not handled here.
"""
import difflib
import re
from html import escape

_Q = r"[„\"]([^”\"„]*)[”\"]"
_UNIT = r"(?:wyraz\w*|oznaczeni\w*|liczb\w*|kwot\w*|dat\w*|cyfr\w*|zdani\w*|symbol\w*|odesłani\w*)"

_REPLACE_RE = re.compile(rf"{_UNIT}\s+{_Q}\s+(?:zastąpić|zastępuje\s+się)\s+\w+\s+{_Q}")
_DELETE_RE = re.compile(
    rf"(?:skreślić|skreśla\s+się)\s+{_UNIT}\s+{_Q}|{_UNIT}\s+{_Q}\s+(?:skreślić|skreśla\s+się)"
)
_INSERT_RE = re.compile(
    rf"po\s+{_UNIT}\s+{_Q}\s+(?:dodać|dodaje\s+się)\s+(?:przecinek\s+i\s+)?{_UNIT}\s+{_Q}"
)
_TOKEN_RE = re.compile(r"\w+|[^\w\s]|\s+")


def word_diff_html(old, new):
    a, b = _TOKEN_RE.findall(old), _TOKEN_RE.findall(new)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    whole = f"<del>{escape(old)}</del> <ins>{escape(new)}</ins>" if old else f"<ins>{escape(new)}</ins>"
    if matcher.ratio() < 0.35:
        return whole
    # Merge changes separated only by whitespace into one del/ins pair.
    ops = []
    for op in matcher.get_opcodes():
        tag, i1, i2, j1, j2 = op
        if tag == "equal" and not "".join(a[i1:i2]).strip() and ops and ops[-1][0] != "equal":
            ops[-1] = ("replace", ops[-1][1], i2, ops[-1][3], j2)
        elif tag != "equal" and ops and ops[-1][0] != "equal":
            ops[-1] = ("replace", ops[-1][1], i2, ops[-1][3], j2)
        else:
            ops.append(op)
    out = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            out.append(escape("".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(f"<del>{escape(''.join(a[i1:i2]))}</del>")
        if j2 > j1:
            out.append(f"<ins>{escape(''.join(b[j1:j2]))}</ins>")
    return "".join(out)


def _where(text, start):
    """The unit reference preceding a match ("w art. 3 w ust. 2")."""
    head = text[:start]
    head = re.split(r"[\n;:]|^\s*[a-z]\)", head)[-1] if head else ""
    head = re.sub(r"^\s*[a-z]\)\s*", "", head)
    return head.strip(" ,")


def extract(text):
    """[{"where": str, "html": str}] for each diffable instruction in `text`."""
    found = []
    for m in _REPLACE_RE.finditer(text):
        found.append((m.start(), m[1], m[2]))
    for m in _DELETE_RE.finditer(text):
        found.append((m.start(), m[1] or m[2], ""))
    for m in _INSERT_RE.finditer(text):
        found.append((m.start(), m[1], f"{m[1]} {m[2]}"))
    found.sort()
    return [
        {"where": _where(text, start), "html": word_diff_html(old, new)}
        for start, old, new in found
    ]
