"""Loads data/ and links each voting to the amendments it concerns."""
import json
import re
from functools import cache

from . import amendments as am
from .acts import bill_changes, changes_against, clean_act_text, parse_act
from .analysis import club_breakdown, passed
from .changes import extract
from .config import DATA
from .plaintext import reflow
from .refs import AMENDMENT, MINORITY, parse_topic, prints_in_title


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def print_meta(num):
    path = DATA / "prints" / f"{num}.json"
    return _load(path) if path.exists() else None


@cache
def print_text(num):
    path = DATA / "prints" / f"{num}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None


def _title(num):
    return ((print_meta(num) or {}).get("title") or "").strip()


@cache
def _report_items(num, section):
    text = print_text(num)
    return {a.number: a for a in am.parse_report(text, section)} if text else {}


@cache
def _senate_items(resolution, report):
    path = DATA / "prints" / f"{resolution}.docx.json"
    items = {a.number: a for a in am.parse_senate_resolution(_load(path))} if path.exists() else {}
    recs = am.parse_senate_report(print_text(report) or "") if report else {}
    for n, (rec, notes) in recs.items():
        if n in items:
            items[n].recommendation = rec
            items[n].notes = notes
    return items


@cache
def bill_articles(num):
    """The bill attached to a committee report, parsed into articles."""
    text = print_text(num) if num else None
    if not text:
        return None
    articles = parse_act(clean_act_text(text, bill=True))
    # a report without the bill attached yields at most stray quoted articles
    return articles if len(articles) >= 2 and "1" in articles else None


def amendment_base(src, kind):
    """Print holding the bill text an amendment refers to: the committee
    report it belongs to, or - when the report's PDF has no bill text - the
    bill as submitted (the first print of the process)."""
    if not src or kind == "senate":
        return None  # Senate amendments refer to the act as passed, not a print
    report = re.sub(r"-[A-Z]+$", "", src) if kind == AMENDMENT else src
    if bill_articles(report):
        return report
    roots = (print_meta(report) or {}).get("processPrint") or []
    return next((r for r in roots if bill_articles(r)), None)


@cache
def bill_diff(src, kind, text):
    """Amendment compared with the bill it amends: {"base", "changes"} or None."""
    base = amendment_base(src, kind)
    articles = bill_articles(base)
    if not articles:
        return None
    changes = changes_against(articles, text)
    if not any(c["found"] for c in changes):
        return None
    return {"base": base, "changes": changes}


def _sources(nums, senate):
    """(amendment source, minority source, senate report) print numbers.

    Chosen by print title rather than number: an "NNNN-A" print can also be
    the sponsor's own correction (autopoprawka), not the committee report.
    """
    if senate:
        res = next((n for n in nums if _title(n).startswith("Uchwała Senatu")), None)
        rep = next((n for n in nums if n != res and "prawozdanie" in _title(n)), None)
        return res, None, rep
    # Additional reports are not always cited; fetch.py probes "NNNN-A".
    candidates = nums + [f"{n}-A" for n in nums if "-" not in n and f"{n}-A" not in nums]
    extra = [n for n in candidates if _title(n).lower().startswith("dodatkowe sprawozdanie")]
    reports = [n for n in nums if "prawozdanie" in _title(n) and n not in extra]
    return (extra[-1] if extra else None), (reports[-1] if reports else None), None


SENATE_RE = re.compile(r"uchwa\w+\s+Senatu", re.I)


def link_amendments(v):
    """[{"kind", "number", "source", "item": dict|None}] for an amendment voting."""
    refs = parse_topic(v.get("topic"))
    if not refs:
        return []
    nums = prints_in_title(v.get("title"))
    senate = bool(SENATE_RE.search(v.get("title") or ""))
    amend_src, minority_src, senate_rep = _sources(nums, senate)
    out = []
    for ref in refs:
        if senate:
            src, items = amend_src, _senate_items(amend_src, senate_rep) if amend_src else {}
        elif ref.kind == AMENDMENT:
            src, items = amend_src, _report_items(amend_src, "amendments") if amend_src else {}
        else:
            src, items = minority_src, _report_items(minority_src, "minority") if minority_src else {}
        for n in ref.numbers:
            item = items.get(n)
            d = None
            if item:
                d = item.as_dict()
                d["changes"] = extract(item.text)
                d["law"] = bill_changes(item.text)
                d["bill_diff"] = bill_diff(src, "senate" if senate else ref.kind, item.text)
            out.append({"kind": "senate" if senate else ref.kind, "number": n, "source": src,
                        "report": senate_rep, "item": d})
    return out


@cache
def source_items(src, kind, report=None):
    """All items of an amendment source print, as linked amendments carry them."""
    if kind == "senate":
        items = _senate_items(src, report)
    else:
        items = _report_items(src, "amendments" if kind == AMENDMENT else "minority")
    return [{**a.as_dict(), "changes": extract(a.text), "law": bill_changes(a.text),
             "bill_diff": bill_diff(src, kind, a.text)} for a in items.values()]


def anchor(kind, number):
    return f"{'wniosek' if kind == MINORITY else 'poprawka'}-{number}"


FULL_TEXT_MAX = 500 * 1024  # larger prints (budgets, codes) link to the PDF instead


def print_too_big(num):
    path = DATA / "prints" / f"{num}.txt"
    return path.exists() and path.stat().st_size > FULL_TEXT_MAX


def print_paragraphs(num):
    """Readable paragraphs of a print: the Senate .docx if present, else the PDF text."""
    path = DATA / "prints" / f"{num}.docx.json"
    if path.exists():
        out, n = [], 0
        for p in _load(path):
            if p["level"] == 0:
                n += 1
                out.append(f"{n}) {p['text']}".strip())
            elif out and re.fullmatch(r"\d+\)", out[-1]):
                out[-1] += " " + p["text"]  # bare item marker joins its text
            elif p["text"]:
                out.append(p["text"])
        return out
    if print_too_big(num):
        return []
    text = print_text(num)
    return reflow(text) if text else []


def law_source(root, prints):
    """Print whose bill text best reflects what the Sejm voted on: the latest
    committee report in the process (before second-reading amendments),
    else the bill as submitted."""
    reports = [
        n for n in prints
        if re.match(r"(Poprawione )?[Ss]prawozdanie", _title(n))
        and root in ((print_meta(n) or {}).get("processPrint") or [])
    ]
    reports.sort(key=lambda n: (int(n.split("-")[0]), n))
    return reports[-1] if reports else (root if print_text(root) else None)


def bill_key(v):
    """Root print of the legislative process this voting belongs to."""
    for n in prints_in_title(v.get("title")):
        meta = print_meta(n)
        if meta and meta.get("processPrint"):
            return meta["processPrint"][0]
    return None


def agenda_label(title):
    t = re.sub(r"^\s*Pkt\.?\s*\d+\.?\s*", "", title or "")
    t = re.sub(r"\s*\(\s*druk\w*\s+nr[^)]*\)", "", t)
    t = re.sub(r"\s*-\s*trzecie czytanie\s*$", "", t)
    return t.strip()


def merge_opening_ids(votes, max_votes=20, share=0.8):
    """On the term's first day some clubs voted under a provisional id (PSL,
    Nowa_Lewica, Polska2050) and switched to their lasting one (PSL-TD,
    Lewica, Polska2050-TD) the next day. Those first votes are counted under
    the lasting id, so a club is not split in two by a day's paperwork. An id
    qualifies when its first run starts on the first day, lasts at most
    `max_votes` votes, and at least `share` of its MPs appear together right
    after under one id that did not exist during the run. Returns {old: new}."""
    # elections by list (the Speaker's, on the first day) have no ballots by club
    votes = sorted((v for v in votes if v["ballots"]), key=lambda v: (v["date"], v["votingNumber"]))
    if not votes:
        return {}
    first_day = votes[0]["date"][:10]
    opening = [i for i, v in enumerate(votes) if v["date"][:10] == first_day]
    merged = {}
    for club in sorted({c for i in opening for c in votes[i]["ballots"]}):
        start = next(i for i in opening if club in votes[i]["ballots"])
        end = start
        while end < len(votes) and club in votes[end]["ballots"]:
            end += 1
        run = votes[start:end]
        if len(run) > max_votes or end == len(votes):
            continue
        members = {mp for ids in run[-1]["ballots"][club].values() for mp in ids}
        after = votes[end]
        seen = {c for v in run for c in v["ballots"]}
        for new, groups in after["ballots"].items():
            moved = members & {mp for ids in groups.values() for mp in ids}
            if new not in seen and members and len(moved) >= share * len(members):
                for v in run:
                    v["ballots"][new] = v["ballots"].pop(club)
                merged[club] = new
                break
    return merged


def load():
    mps = {m["id"]: m for m in _load(DATA / "mps.json")}
    clubs = {c["id"]: c["name"] for c in _load(DATA / "clubs.json")}
    sittings = {}
    for f in sorted((DATA / "votings").glob("*.json"), key=lambda p: int(p.stem)):
        data = _load(f)
        sittings[data["sitting"]] = data["votings"]
        for v in data["votings"]:
            v["sitting"] = data["sitting"]
    merge_opening_ids([v for vs in sittings.values() for v in vs])
    for s, votings in sittings.items():
        for v in votings:
            v["clubs"] = club_breakdown(v)
            v["passed"] = passed(v)
            v["senate"] = bool(SENATE_RE.search(v.get("title") or ""))
            v["amendments"] = link_amendments(v)
            v["bill"] = bill_key(v)
            v["prints"] = prints_in_title(v.get("title"))
            v["agenda"] = agenda_label(v.get("title"))
    return mps, clubs, sittings
