"""The AI summaries of bills (data/ai/bills.json, written by a language model from the bill's print)
for the stream: which bill a vote or an agenda item is about, the cards shown in a debate and the
pages shown full screen before a vote. Every place they appear says that a model wrote them."""
import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTE = "streszczenie AI: napisał model językowy na podstawie druku projektu, nie redakcja"


class Summaries:
    """{root print: summary}, found from any print of the bill: the print itself, a committee
    report's process print (data/prints/N.json "processPrint"), or a bill considered jointly
    (data/processes.json "prints"; the site keys a joint bill by one of them)."""

    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.by_root, self.alias = {}, {}
        self.load()

    def load(self):
        try:
            got = json.loads((self.root / "data" / "ai" / "bills.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            got = {}
        by_root = {k: v for k, v in got.items() if v.get("summary") and not v.get("insufficient")}
        alias = {}
        try:
            procs = json.loads((self.root / "data" / "processes.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            procs = {}
        for num, p in procs.items():
            group = [num] + [str(x) for x in p.get("prints") or []]
            hit = next((g for g in group if g in by_root), None)
            if hit:
                for g in group:
                    alias.setdefault(g, hit)
        self.by_root, self.alias = by_root, alias
        return len(by_root)

    def _process_prints(self, num):
        try:
            meta = json.loads((self.root / "data" / "prints" / f"{num}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [str(x) for x in meta.get("processPrint") or []]

    def root_of(self, prints):
        """The root print with a summary for any of `prints`, or None."""
        for p in prints or []:
            for q in [str(p)] + self._process_prints(p):
                if q in self.by_root:
                    return q
                if q in self.alias:
                    return self.alias[q]
        return None

    def get(self, prints):
        """(root, summary) for the bill of `prints`, or None."""
        root = self.root_of(prints)
        return (root, self.by_root[root]) if root else None


CARD_CHARS = 380   # about what nine lines of a card hold


def cards(root, entry, headline):
    """The debate's cards, shown in turn: what the bill does, then its main changes, as many
    to a card as fit (a point is never split)."""
    url = f"sejmomat.pl/{root}"
    out = [{"kind": "ai", "title": "Streszczenie AI · w debacie", "headline": headline,
            "text": entry["summary"], "url": url}]
    group = []
    for pt in entry.get("points") or []:
        if group and sum(len(x) + 40 for x in group + [pt]) > CARD_CHARS:
            out.append(group)
            group = []
        group.append(pt)
    if group:
        out.append(group)
    return out[:1] + [{"kind": "ai", "title": "Streszczenie AI · w debacie", "headline": "Najważniejsze zmiany",
                       "points": g, "url": url} for g in out[1:]]


def pages(entry, width=84, lines=10):
    """The full-screen pages before a vote: rows of (colour, line) for the overlay's text scene,
    the summary first, then the main changes as bullets, a bullet never split across pages."""
    blocks = [[("w", line) for line in textwrap.wrap(entry["summary"], width)]]
    if entry.get("who"):
        blocks[0] += [("w", "")] + [("y", line) for line in textwrap.wrap(entry["who"], width)]
    for pt in entry.get("points") or []:
        wrapped = textwrap.wrap(pt, width - 2)
        blocks.append([("w", ("• " if i == 0 else "  ") + line) for i, line in enumerate(wrapped)])
    out, page = [], []
    for block in blocks:
        if page and len(page) + len(block) > lines:
            out.append(page)
            page = []
        # a block longer than a page (a very long summary) is cut into pages of its own
        while len(block) > lines:
            out.append(block[:lines])
            block = block[lines:]
        page += block
    if page:
        out.append(page)
    return out
