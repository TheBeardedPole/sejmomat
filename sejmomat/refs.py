"""Parsing of the free-text references in voting records.

A voting's `title` names the agenda item and the prints (druki) it concerns,
e.g. "Pkt. 2 Sprawozdanie Komisji o ... (druki nr 3030, 3080 i 3080-A)".
Its `topic` names what is being voted, e.g. "poprawki nr 1, 30 oraz 63-65".
"""
import re
from dataclasses import dataclass, field

_DRUKI_RE = re.compile(r"\(\s*druk(?:i|u)?\s+nr\s+([^)]*)\)", re.IGNORECASE)
_PRINT_NUM_RE = re.compile(r"\d+(?:-[A-Z]{1,2})?")


def prints_in_title(title):
    """Print numbers cited in a voting title, in order of appearance."""
    out = []
    for group in _DRUKI_RE.findall(title or ""):
        for num in _PRINT_NUM_RE.findall(group):
            if num not in out:
                out.append(num)
    return out


AMENDMENT = "amendment"
MINORITY = "minority"

_TOPIC_START_RE = re.compile(r"^\s*(poprawk|wnios\w*\s+mniejszo)", re.IGNORECASE)
_TOKEN_RE = re.compile(
    r"(?P<kw_am>poprawk\w*)"
    r"|(?P<kw_min>wnios\w*\s+mniejszo\w*)"
    r"|(?P<a>\d+)\s*[-–]\s*(?P<b>\d+)"
    r"|(?P<n>\d+)",
    re.IGNORECASE,
)


@dataclass
class TopicRef:
    kind: str  # AMENDMENT or MINORITY
    numbers: list = field(default_factory=list)


def is_amendment_topic(topic):
    return bool(_TOPIC_START_RE.match(topic or ""))


def parse_topic(topic):
    """Split an amendment/minority-motion topic into typed number lists.

    "poprawka nr 3, wniosek mniejszości nr 2" -> [amendment [3], minority [2]]
    Returns [] for topics that are not about amendments.
    """
    if not is_amendment_topic(topic):
        return []
    refs = []
    current = None
    for m in _TOKEN_RE.finditer(topic):
        if m["kw_am"] or m["kw_min"]:
            kind = AMENDMENT if m["kw_am"] else MINORITY
            current = TopicRef(kind)
            refs.append(current)
        elif current is not None:
            if m["a"]:
                a, b = int(m["a"]), int(m["b"])
                current.numbers.extend(range(a, b + 1) if a <= b else [a, b])
            else:
                current.numbers.append(int(m["n"]))
    return refs
