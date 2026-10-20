"""The Sejm's calendar and the agenda of the next sitting.

The API lists every sitting of the term with its dates, past and planned;
planned ones have number 0 and no agenda until it is published, about a week
before. The agenda is HTML: numbered lists of items (a second list for
possible Senate resolutions), each with the prints it concerns and a line on
who presents it. `fetch()` keeps the calendar in data/proceedings.json with
the agenda of every numbered sitting (fetched again until REFRESH_DAYS after
the sitting, as items are added while it runs); `parse()` turns an agenda
into items. Item numbers are the "punkt porządku dziennego" of the speeches.
"""
import json
import re
from datetime import date, timedelta
from html import unescape
from html.parser import HTMLParser

from . import api
from .config import DATA

PATH = DATA / "proceedings.json"
REFRESH_DAYS = 3


def fetch(today=None):
    from .fetch import _write_json
    today = today or date.today()
    stored = {p["number"]: p.get("agenda") for p in _stored() if p.get("number")}
    fresh = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    out, fetched = [], 0
    for p in api.get("proceedings") or []:
        keep = {k: p.get(k) for k in ("number", "title", "dates", "current")}
        n = p.get("number")
        if n and p.get("dates"):
            if p["dates"][-1] >= fresh or not stored.get(n):
                full = api.get(f"proceedings/{n}") or {}
                keep["agenda"] = full.get("agenda") or stored.get(n) or ""
                fetched += 1
            else:
                keep["agenda"] = stored[n]
        out.append(keep)
    _write_json(PATH, out)
    print(f"proceedings: {len(out)} sittings in the calendar, {fetched} agendas fetched")


def _stored():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else []


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
                start = a.get("start") or ""
                self.groups.append({"heading": heading, "items": [], "start": int(start) if start.isdigit() else None})
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
            # a link's text is one print or several ("3030, 3080 i 3080-A")
            if self.in_a and re.fullmatch(r"\s*\d+(-[A-Za-z0-9]+)?((\s*,\s*|\s+i\s+)\d+(-[A-Za-z0-9]+)?)*\s*", data):
                self.item["prints"] += re.findall(r"\d+(?:-[A-Za-z0-9]+)?", data)
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
    """{"groups": [{"heading", "start" (the list's first number, if given),
    "items": [{"n", "kind", "text", "rest", "notes", "prints", "eu"}]}],
    "note"} from the agenda's HTML."""
    p = _Agenda()
    p.feed(html or "")
    note = re.sub(r"\s+", " ", p.note.replace("\xa0", " ")).strip()
    return {"groups": [g for g in p.groups if g["items"]], "note": note}


def upcoming(today=None):
    """(the next sitting or the one under way with its parsed agenda, the
    planned sittings after it), or (None, planned) when no agenda is out."""
    today = (today or date.today()).isoformat()
    ahead = [p for p in _stored() if p.get("dates") and p["dates"][-1] >= today]
    ahead.sort(key=lambda p: p["dates"][0])
    nxt = next((p for p in ahead if p.get("number") and p.get("agenda")), None)
    if nxt:
        nxt = {**nxt, **parse(nxt["agenda"]), "under_way": nxt["dates"][0] <= today}
        del nxt["agenda"]
    later = [p for p in ahead if p is not None and (not nxt or p["dates"][0] > nxt["dates"][-1])]
    return nxt, later


def by_sitting():
    """{sitting number: parsed agenda} for every sitting with an agenda; items
    without a number in the HTML get their place in the list, which is how
    the transcripts number them ("punkt 29. porządku dziennego")."""
    out = {}
    for p in _stored():
        if p.get("number") and p.get("agenda"):
            a = parse(p["agenda"])
            place = 1
            for g in a["groups"]:
                # a later list goes on from its "start", or from where the one before ended
                place = g["start"] or place
                for item in g["items"]:
                    item["n"] = item["n"] or str(place)
                    place = int(item["n"]) + 1 if item["n"].isdigit() else place + 1
            out[p["number"]] = a
    return out
