"""Changes in committee membership, read from the Presidium's motions.

The Sejm's API gives a committee's members as they are now, with no history.
Who joined or left a committee and when is in the prints of the Presidium's
motions ("wniosek w sprawie zmian w składach osobowych komisji sejmowych",
"wyboru uzupełniającego do składu…", "wyboru (nowego) składu osobowego…"),
which the Sejm adopts by a vote. Their text is already kept in data/prints/,
so nothing is fetched: this module reads them, matches each name (in the
accusative, "posła Waldemara Budę (PiS)") to an MP, each committee heading to
a committee, and dates every change by the vote that adopted it.

Three kinds of print:
- changes: committee headings, each with "wybiera się do składu Komisji:" and
  "odwołuje się ze składu Komisji:" followed by one MP per line;
- a by-election ("wybór uzupełniający"): MPs added to the committee in the title;
- a whole membership ("wybór składu", "nowego składu", "powołania i wyboru
  składu"): the full list, as at the start of the term or for a new committee.
  A new list for a committee that already had one replaces it, so the change
  is the difference.

Replaying them in order gives each committee's membership over time; MPs who
left the Sejm drop out of committees without a motion (the mandate ends).
"""
import difflib
import json
import re
from collections import defaultdict

from .config import DATA

KIND_CHANGES, KIND_ADD, KIND_FULL = "changes", "add", "full"
_TITLE_RE = re.compile(r"sk[łl]ad\w*\s.*komisj", re.I)
_ADD_RE = re.compile(r"wybiera się do składu|wybiera\s+się\s+do\s+składu", re.I)
_DROP_RE = re.compile(r"odwołuje się ze składu", re.I)
_HEADING_RE = re.compile(r"^\s*(Komisja\s.+?):?\s*$")
# "- posła Waldemara Budę (PiS)", "— Tomasza Kostusia (KO).", "1. Bochenek Mateusz   KO",
# "4. Tomasza Głogowskiego KO", "1.Barbarę Bartuś PiS"
_ITEM_RE = re.compile(r"^\s*(?:[-—–•]|\d+\.)\s*(.+?)\s*$")
_CLUB_TAIL_RE = re.compile(r"\s*\(?\s*([A-Za-z0-9_.\-]+(?:-TD)?)\s*\)?\s*[.;,]?\s*$")
_HONORIFIC = {"posla", "posel", "poslanke", "poslanka", "pana", "pania"}


def is_motion(title):
    """A print that is one of the Presidium's motions on committee membership."""
    return title.startswith("Przedstawiony przez Prezydium") and bool(_TITLE_RE.search(title))


def _norm(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


_FOLD = str.maketrans("ąćęłńóśźżäöü", "acelnoszzaou")


def _tokens(name):
    """Lower-case words without diacritics: the prints have typos ("Gwoździa", "Fołtyna",
    "Schaedler") and OCR slips ("[wonę")."""
    name = re.sub(r"(^|\s)\[", r"\1I", name).lower().replace("ae", "a").translate(_FOLD)
    return [t for t in re.split(r"[\s\-]+", name) if t and t not in _HONORIFIC]


def _like(a, b):
    """Two word forms of the same name: Budę/Buda, Hoffmanna/Hoffmann, Gwóździa/Gwóźdź."""
    n, short = _common(a, b), min(len(a), len(b))
    if n < 3 and max(len(a), len(b)) - short > 2:   # Woś/Wosia, Ewa/Ewę; not Woś/Wójcika
        return False
    return n >= max(min(3, short - 1), short - 2)


def _common(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


class Matcher:
    """Names as printed (any case, any order) to MP ids."""

    def __init__(self, mps):
        self.mps = []
        for m in mps:
            last = _tokens(m.get("lastName") or m["firstLastName"].split()[-1])
            first = _tokens(m["firstLastName"])[0]
            self.mps.append((m["id"], first, last, set(_tokens(m["firstLastName"])), m.get("club")))

    def find(self, name, club=None):
        toks = _tokens(name)
        best, best_score = [], -1
        for mid, first, last, allt, mclub in self.mps:
            # every part of the surname, or one part of a double one: "Wiśniewska" for
            # "Uznańska-Wiśniewska" (a name changed during the term)
            hit = sum(1 for l in last if any(_like(t, l) for t in toks))
            if hit < len(last) and not (len(last) > 1 and hit):
                continue
            if not any(_like(t, first) for t in toks):
                continue
            score = (sum(max((_common(t, a) for a in allt if _like(t, a)), default=0) for t in toks) * 2
                     + (mclub == club) - (len(last) - hit) * 4)
            if score > best_score:
                best, best_score = [mid], score
            elif score == best_score:
                best.append(mid)
        return best[0] if len(best) == 1 else None


class Committees:
    """Committee names in the prints (nominative or genitive, wording that
    drifts: "2020 roku" / "2020 r.") to codes."""

    # former names of committees still sitting under another one
    RENAMED = {"Komisja Edukacji, Nauki i Młodzieży": "ENM", "Komisja Kultury i Środków Przekazu": "KSP"}

    def __init__(self, listed):
        names = {c["code"]: c["name"] for c in listed}
        self.items = [(c["code"], c["name"], self._key(c["name"])) for c in listed]
        self.items += [(code, old, self._key(old)) for old, code in self.RENAMED.items() if code in names]

    @staticmethod
    def _key(name):
        s = _norm(name).lower()
        s = re.sub(r"^komisj[aię]\s+", "", s)
        s = re.sub(r"\b(nadzwyczajn|śledcz)\w*", r"\1", s)
        s = s.replace("roku", "r.").replace("ilmmun", "immun")
        return re.sub(r"[^\wąćęłńóśźż]+", " ", s).strip()

    def code(self, name):
        k = self._key(name)
        best = max(self.items, key=lambda it: difflib.SequenceMatcher(None, k, it[2]).ratio(), default=None)
        if best and difflib.SequenceMatcher(None, k, best[2]).ratio() >= 0.85:
            return best[0]
        return None


def _split_item(text):
    """("Waldemara Budę", "PiS") from one list line."""
    text = _norm(text).rstrip(".;,")
    # columns run together in the text layer: "Wilk RyszardKonfederacja"
    text = re.sub(r"([a-ząćęłńóśźż])(KO|PiS|Lewica|Konfederacja\w*|PSL-TD|Polska2050(?:-TD)?|Razem)$", r"\1 \2", text)
    if not re.search(r"[A-Za-zŁŚŻ].*[a-ząćęłńóśźż]", text):
        return None
    m = _CLUB_TAIL_RE.search(text)
    club = None
    if m and (("(" in text[m.start():]) or re.search(r"\s{2,}|\s", text[:m.start()] + " ")):
        cand = m.group(1)
        if cand[0].isupper() and not re.fullmatch(r"[A-ZŁŚŻŹĆŃÓĘĄ][a-ząćęłńóśźż]+", cand) or "(" in text[m.start():]:
            club, text = cand, text[:m.start()]
    # a name broken at a hyphen across a line: "Scheuring- Wielgus"
    text = re.sub(r"-\s+", "-", text)
    return text.strip(), club


def _body(txt):
    """The motion itself, after the cover page."""
    for marker in ("WNIOSEK", "UCHWAŁA"):
        i = txt.find(marker)
        if i >= 0:
            return txt[i:]
    return txt


_PROSE_NAME_RE = re.compile(r"(?:posła|poseł|posłankę)\s+([A-ZŁŚŻŹĆÓ][^\s(;,]+(?:\s+(?:vel\s+)?[A-ZŁŚŻŹĆÓ][^\s(;,]+){1,3})\s*\(([^)]+)\)")


def _prose(lines):
    """Names in running text, each under the last "wybiera"/"odwołuje" before it."""
    flat = re.sub(r"(\w)-\s+(\w)", r"\1-\2", _norm(" ".join(lines)))
    verbs = [(m.start(), "drop" if m.group().startswith("odwoł") else "add")
             for m in re.finditer(r"odwołuje|wybiera", flat)]
    add, drop = [], []
    for m in _PROSE_NAME_RE.finditer(flat):
        mode = next((v for at, v in reversed(verbs) if at < m.start()), None)
        if mode:
            (add if mode == "add" else drop).append((m.group(1), m.group(2).strip()))
    return add, drop


def _join_headings(lines):
    """A committee heading over several lines ("Komisja Nadzwyczajna … do" / "przerywania
    ciąży:") as one line."""
    out, pending = [], None
    for line in lines:
        s = line.strip()
        if pending is not None:
            if not s:
                continue
            if _ADD_RE.search(s) or _DROP_RE.search(s) or _ITEM_RE.match(line) or len(pending) > 400:
                out.append(pending)
                pending = None
            else:
                pending = pending + " " + s
                if s.endswith(":"):
                    out.append(pending)
                    pending = None
                continue
        if re.match(r"Komisja\s", s) and not s.endswith(":"):
            pending = s
            continue
        out.append(line)
    if pending is not None:
        out.append(pending)
    return out


def _committee_of_title(title):
    m = re.search(r"(Komisji\s(?!sejmow).+?)\.?$", title)
    return m.group(1) if m else None


def parse(number, title, text):
    """A print as {"kind", "committees": [{"name", "add": [(name, club)], "drop": [...]}]}."""
    body = [l for l in _body(text).splitlines() if not re.fullmatch(r"\s*-\s*\d+\s*-\s*", l)]
    t = title.lower().replace("sklad", "skład")
    if "zmian" in t and "uchwały" not in t:
        out, cur, mode = [], None, None
        for line in _join_headings(body):
            h = _HEADING_RE.match(line)
            if h and line.rstrip().endswith(":") and not _ADD_RE.search(line):
                cur = {"name": _norm(h.group(1)).rstrip(":"), "add": [], "drop": []}
                out.append(cur)
                mode = None
                continue
            if _ADD_RE.search(line):
                mode = "add"
                continue
            if _DROP_RE.search(line):
                mode = "drop"
                continue
            it = _ITEM_RE.match(line) or re.match(r"^\s*\d+\)\s*((?:posła|poseł)\s.+?)\s*$", line)
            if cur is not None and mode and it and not re.match(r"^\s*\d+\)\s*na podstawie", line):
                cur[mode].append(_split_item(it.group(1)))
                cur[mode] = [x for x in cur[mode] if x]
        out = [c for c in out if c["add"] or c["drop"]]
        if not out and _committee_of_title(title):
            # one committee, in prose: "odwołuje się ze składu Komisji posła X (KO); … wybiera się …"
            add, drop = _prose(body)
            out = [{"name": _committee_of_title(title), "add": add, "drop": drop}] if add or drop else []
        return {"kind": KIND_CHANGES, "committees": out}
    if "uzupełniaj" in t:
        kind = KIND_ADD
    elif re.search(r"wyboru (nowego )?składu|wyboru składów|powołania i wyboru", t) and "o zmianie uchwały" not in t:
        kind = KIND_FULL
    else:
        return None
    if "składów osobowych stałych komisji" in " ".join(body[:15]) or "składów" in t:
        # the first print of the term: every standing committee, a heading per committee
        out, cur = [], None
        for line in body:
            s = line.strip()
            if re.fullmatch(r"Komisja\s.+", s) and not _ITEM_RE.match(line):
                cur = {"name": s, "add": [], "drop": []}
                out.append(cur)
            elif cur is not None and _ITEM_RE.match(line) and re.match(r"^\s*\d+\.", line):
                item = _split_item(_ITEM_RE.match(line).group(1))
                if item:
                    cur["add"].append(item)
            elif cur is not None and s and not cur["add"]:
                cur["name"] = _norm(cur["name"] + " " + s)   # a heading over two lines
        return {"kind": kind, "committees": [c for c in out if c["add"]]}
    name = _committee_of_title(title)
    items = []
    started = False
    for line in body:
        if re.search(r"wybiera|następujących posłów|posłów:", line):
            started = True
        it = _ITEM_RE.match(line)
        if started and it:
            if _split_item(it.group(1)):
                items.append(_split_item(it.group(1)))
    if not items:
        items = _prose(body)[0]
    return {"kind": kind, "committees": [{"name": name, "add": items, "drop": []}] if name and items else []}


def _vote_of_print(votings):
    """print number → the adopting vote (the last vote naming it in its title)."""
    out = {}
    for v in votings:
        for num in re.findall(r"druk(?:u|i)? nr (\d+(?:-[A-Z])?)", v.get("title") or ""):
            out[num] = v
    return out


def build(prints_meta, print_text, votings, mps, listed, passed):
    """Events in date order: {"print", "date", "vote", "kind", "title", "committees": [{"code", "name",
    "add": [mp ids], "drop": [mp ids], "unmatched": [names]}]}, and per committee the membership
    history {code: {mp id: [[from, to or None], ...]}}."""
    matcher, comms = Matcher(mps), Committees(listed)
    votes = _vote_of_print(votings)
    events = []
    for num, meta in prints_meta.items():
        title = meta.get("title") or ""
        if not is_motion(title):
            continue
        p = parse(num, title, print_text(num) or "")
        if not p or not p["committees"]:
            continue
        v = votes.get(num)
        if v is not None and not passed(v):
            continue
        ev = {"print": num, "date": (v["date"][:10] if v else meta.get("documentDate")), "kind": p["kind"],
              "title": title, "vote": (v["sitting"], v["votingNumber"]) if v else None,
              "voted": v is not None, "committees": []}
        for c in p["committees"]:
            row = {"code": comms.code(c["name"]), "name": c["name"], "add": [], "drop": [], "unmatched": []}
            for side in ("add", "drop"):
                for name, club in c[side]:
                    mid = matcher.find(name, club)
                    if mid is None:
                        row["unmatched"].append(f"{name} ({club})" if club else name)
                    else:
                        row[side].append(mid)
            ev["committees"].append(row)
        events.append(ev)
    events.sort(key=lambda e: (e["date"] or "", e["vote"] or (0, 0)))

    # replay: who sat where, from when to when
    spans = defaultdict(lambda: defaultdict(list))
    current = defaultdict(set)
    for ev in events:
        for c in ev["committees"]:
            code = c["code"] or c["name"]
            if ev["kind"] == KIND_FULL:
                new = set(c["add"])
                had = current[code]
                if had:
                    # a new list replaces the old one: record the difference
                    c["drop"] = sorted(had - new)
                    c["add"] = [m for m in c["add"] if m not in had]
                    c["replaced"] = True
                else:
                    c["initial"] = True
                for m in had - new:
                    _close(spans[code][m], ev["date"])
                for m in new - had:
                    spans[code][m].append([ev["date"], None])
                current[code] = new
                continue
            for m in c["drop"]:
                if m in current[code]:
                    current[code].discard(m)
                    _close(spans[code][m], ev["date"])
            for m in c["add"]:
                if m not in current[code]:
                    current[code].add(m)
                    spans[code][m].append([ev["date"], None])
    return events, {k: dict(v) for k, v in spans.items()}


def _close(periods, day):
    if periods and periods[-1][1] is None:
        periods[-1][1] = day


def load(prints_dir=DATA / "prints"):
    """Everything from the files in data/; used by the build and for checks."""
    from . import analysis
    meta = {}
    for f in prints_dir.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and _TITLE_RE.search(d.get("title") or ""):
            meta[d["number"]] = d

    def text(num):
        p = prints_dir / f"{num}.txt"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    votings = []
    for f in (DATA / "votings").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for v in d["votings"]:
            v.setdefault("sitting", d["sitting"])
            votings.append(v)
    mps = json.loads((DATA / "mps.json").read_text(encoding="utf-8"))
    listed = json.loads((DATA / "committees.json").read_text(encoding="utf-8"))
    return build(meta, text, votings, mps, listed, analysis.passed)


def for_site(events, spans, listed):
    """What the pages show, checked against the API's members now (the truth for today).

    Returns (events, per committee {"changes": [(event, part)], "joined": {mp: date},
    "former": [(mp, from, to)]}). A membership the motions leave open but the API no longer
    lists ended without a motion (the MP joined the government, or left the Sejm): its end
    is None. A member the API lists with no motion found keeps no start date."""
    now = {c["code"]: {m["id"] for m in c["members"]} for c in listed}
    out = {}
    for code in now:
        mine = [(ev, part) for ev in events for part in ev["committees"] if part["code"] == code]
        joined, former = {}, []
        for mp, periods in spans.get(code, {}).items():
            for i, (start, end) in enumerate(periods):
                last = i == len(periods) - 1
                if last and end is None and mp in now[code]:
                    joined[mp] = start
                else:
                    former.append((mp, start, end))
        former.sort(key=lambda f: (f[2] or "9999", f[1] or ""), reverse=True)
        out[code] = {"changes": list(reversed(mine)), "joined": joined, "former": former}
    return events, out
