"""The Sejm's calendar and the agenda of the next sitting.

The API lists every sitting of the term with its dates, past and planned;
planned ones have number 0 and no agenda until it is published, about a week
before. The agenda is HTML: numbered lists of items (a second list for
possible Senate resolutions), each with the prints it concerns and a line on
who presents it. `fetch()` keeps the calendar in data/proceedings.json, with
the agenda of sittings not yet over; `parse()` turns an agenda into items.
"""
import re
from datetime import date
from html import unescape
from html.parser import HTMLParser

from . import api
from .config import DATA

PATH = DATA / "proceedings.json"


def fetch(today=None):
    from .fetch import _write_json
    today = today or date.today()
    out = []
    for p in api.get("proceedings") or []:
        keep = {k: p.get(k) for k in ("number", "title", "dates", "current")}
        # agendas of past sittings are not used; their votes tell the story
        if p.get("number") and p.get("dates") and p["dates"][-1] >= today.isoformat():
            full = api.get(f"proceedings/{p['number']}") or {}
            keep["agenda"] = full.get("agenda") or ""
        out.append(keep)
    _write_json(PATH, out)
    print(f"proceedings: {len(out)} sittings in the calendar")


class _Agenda(HTMLParser):
    """Collects the items of every <ol>, each list with the italic heading
    before it, and the closing note ("Uwaga: …")."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.groups, self.note = [], ""
        self.item = None      # the <li> being read
        self.depth = 0        # nesting of <ol>
        self.em = None        # italic text outside items: a heading or the note
        self.in_strong = self.in_a = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "ol":
            self.depth += 1
            if self.depth == 1:
                heading = re.sub(r"\s+", " ", (self.em or "").replace("\xa0", " ")).strip(" :")
                # "oraz o ewentualne uchwały Senatu…" continues the sentence above the list
                heading = re.sub(r"^oraz (o )?", "", heading)
                heading = heading[:1].upper() + heading[1:] or None
                self.groups.append({"heading": heading, "items": []})
                self.em = None
        elif tag == "li" and self.depth == 1:
            self.item = {"n": a.get("value"), "lines": [""], "kind": "", "prints": [], "eu": False}
        elif self.item is not None:
            if tag == "br":
                self.item["lines"].append("")
            elif tag == "strong":
                self.in_strong = True
            elif tag == "a":
                self.in_a = True
            elif tag == "span" and "icon-ue" in (a.get("class") or ""):
                self.item["eu"] = True
        elif tag == "em":
            self.em = ""

    def handle_endtag(self, tag):
        if tag == "ol":
            self.depth -= 1
        elif tag == "li" and self.item is not None and self.depth == 1:
            self.groups[-1]["items"].append(self._finish(self.item))
            self.item = None
        elif tag == "strong":
            self.in_strong = False
        elif tag == "a":
            self.in_a = False

    def handle_data(self, data):
        if self.item is not None:
            self.item["lines"][-1] += data
            if self.in_strong and not self.item["kind"]:
                self.item["kind"] = data.strip()
            if self.in_a and re.fullmatch(r"\s*\d+(-[A-Za-z0-9]+)?\s*", data):
                self.item["prints"].append(data.strip())
        elif self.em is not None:
            self.em += data
            if "Uwaga" in self.em:
                self.note = self.em

    @staticmethod
    def _finish(item):
        lines = [re.sub(r"\s+", " ", unescape(l).replace("\xa0", " ")).strip() for l in item["lines"]]
        lines = [l for l in lines if l]
        # the prints are listed apart, as links; "(druki nr 611 i )" and
        # "(druk nr ...)" only say a print is not out yet
        text = re.sub(r"\s*\(druki? nr[^()]*\)", "", lines[0] if lines else "")
        notes = [l.lstrip("- ").strip() for l in lines[1:]]
        # "sprawozdawca poseł" with no name yet
        notes = [n for n in notes if not re.fullmatch(r"(sprawozdawca|uzasadnia)( pose[łl]| posłanka)?\.?", n)]
        return {"n": item["n"], "kind": item["kind"], "text": text,
                "rest": text[len(item["kind"]):].strip() if text.startswith(item["kind"]) else text,
                "notes": notes,
                "prints": list(dict.fromkeys(item["prints"])), "eu": item["eu"]}


def parse(html):
    """{"groups": [{"heading", "items": [{"n", "kind", "text", "rest", "notes",
    "prints", "eu"}]}], "note"} from the agenda's HTML."""
    p = _Agenda()
    p.feed(html or "")
    note = re.sub(r"\s+", " ", p.note.replace("\xa0", " ")).strip()
    return {"groups": [g for g in p.groups if g["items"]], "note": note}


def upcoming(today=None):
    """(the next sitting or the one under way with its parsed agenda, the
    planned sittings after it), or (None, planned) when no agenda is out."""
    if not PATH.exists():
        return None, []
    import json
    today = (today or date.today()).isoformat()
    ahead = [p for p in json.loads(PATH.read_text(encoding="utf-8")) if p.get("dates") and p["dates"][-1] >= today]
    ahead.sort(key=lambda p: p["dates"][0])
    nxt = next((p for p in ahead if p.get("number") and p.get("agenda")), None)
    if nxt:
        nxt = {**nxt, **parse(nxt["agenda"]), "under_way": nxt["dates"][0] <= today}
        del nxt["agenda"]
    later = [p for p in ahead if p is not None and (not nxt or p["dates"][0] > nxt["dates"][-1])]
    return nxt, later
