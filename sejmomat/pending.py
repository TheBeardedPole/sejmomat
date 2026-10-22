"""What is waiting in the Sejm: amendments no vote has dealt with yet, and
bills held up before the second reading ("zamrażarka").

Amendments wait in three kinds of print, fetched before any vote cites
them (fetch.PENDING_PRINT_RE): a committee report (minority motions, voted
in the third reading), an additional report (amendments from the second
reading, likewise) and a Senate resolution (with the committee's report on
it). They are waiting while no vote cites the print and the bill's process
(processes.py) shows no later third reading, vote on the Senate's position,
rejection or withdrawal.

A bill is held up where its process stopped: with the Marshal (not sent to
a first reading, or the first or second reading not put on the agenda) or in
committee (no first reading there, or no report). Bills past the second
reading are not counted.
"""
import re
from collections import Counter, defaultdict
from datetime import date

from .model import print_meta, source_items
from .refs import AMENDMENT, MINORITY

STALLED_DAYS = 180   # waiting longer than this: marked as stuck
# stages after which nothing that came before is waiting any more
SETTLED = {"Odrzucono", "Wycofano", "Ustawę przekazano Prezydentowi do podpisu", "Prezydent podpisał ustawę"}

# where a bill stands, from its last stage on the top level: (place, who holds it)
WAITING = {
    "Projekt wpłynął do Sejmu": ("referral", "marshal"),
    "Opinia organizacji samorządowej": ("referral", "marshal"),
    "Wpłynęło stanowisko rządu": ("referral", "marshal"),
    "Skierowano do I czytania na posiedzeniu Sejmu": ("reading1_plenary", "marshal"),
    "Skierowano do I czytania w komisjach": ("reading1_committee", "committee"),
    "I czytanie w komisjach": ("report", "committee"),
    "I czytanie na posiedzeniu Sejmu": ("report", "committee"),
    "Praca w komisjach po I czytaniu": ("report", "committee"),
}
SPONSORS = ["Rządowy", "Poselski", "Obywatelski", "Senacki", "Prezydencki", "Komisyjny"]


def _days(since, today):
    return (today - date.fromisoformat(since[:10])).days if since else None


def _top(process):
    return [s for s in process["stages"] if s["depth"] == 0]


def _settled_after(process, day, names):
    """Has the process gone through one of `names` (or ended) on or after `day`?"""
    return any(s["date"] and s["date"][:10] >= day[:10] and (s["name"] in names or s["name"] in SETTLED)
               for s in _top(process))


def amendments(printed, cited, processes, agenda_prints, today=None):
    """[{"root", "title", "kind", "print", "report", "date", "days", "stalled",
    "on_agenda", "items"}] newest first: amendments in prints no vote has cited,
    whose bill's process has not moved past them."""
    today = today or date.today()
    metas = {n: print_meta(n) or {} for n in printed}
    root = lambda n: (metas[n].get("processPrint") or [n])[0]
    out = []
    for n, m in metas.items():
        title = m.get("title") or ""
        if n in cited or not m.get("documentDate"):
            continue
        process = processes.get(root(n))
        if title.startswith("Uchwała Senatu w sprawie ustawy"):
            # the committee's report on the resolution, if out, gives its recommendations
            report = next((r for r, rm in metas.items() if root(r) == root(n) and r not in cited
                           and "o uchwale Senatu" in (rm.get("title") or "")), None)
            kind, items, settle = "senate", source_items(n, "senate", report), {"Rozpatrywanie na forum Sejmu stanowiska Senatu"}
        elif title.startswith("Dodatkowe sprawozdanie Komisji"):
            kind, report, items, settle = AMENDMENT, None, source_items(n, AMENDMENT), {"III czytanie na posiedzeniu Sejmu"}
        elif title.startswith("Sprawozdanie Komisji") and "Senatu" not in title:
            kind, report, items, settle = MINORITY, None, source_items(n, MINORITY), {"III czytanie na posiedzeniu Sejmu"}
        else:
            continue
        if not items or (process and _settled_after(process, m["documentDate"], settle)):
            continue
        days = _days(m["documentDate"], today)
        out.append({"root": root(n), "title": (process or {}).get("title") or title, "kind": kind, "print": n,
                    "report": report, "date": m["documentDate"], "days": days, "stalled": days > STALLED_DAYS,
                    "on_agenda": n in agenda_prints or (report in agenda_prints if report else False),
                    "items": items})
    out.sort(key=lambda g: (g["date"], g["print"]), reverse=True)
    return out


def sponsor(title):
    first = (title or "").split(" ", 1)[0]
    return first if first in SPONSORS else "Inny"


def frozen(processes, committee_names, author=lambda p: None, today=None):
    """{"bills": [{"number", "title", "sponsor", "type", "submitted", "since",
    "days", "place", "holder", "committees", "stalled", "club"}] longest
    waiting first, "counts": {(place, sponsor): n}}: bills and draft
    resolutions not yet past the first reading or the committee report, and
    where they wait. author(process) gives an MPs' bill's club, or None."""
    today = today or date.today()
    last_step = lambda p: max((s["date"] for s in p["stages"] if s["date"]), default=p["submitted"] or "")
    # a bill considered jointly with another goes on with it: skipped once the other has moved on
    joined = defaultdict(list)
    for p in processes.values():
        for j in p["prints"]:
            joined[j].append(p)
    bills = []
    for p in processes.values():
        if any(last_step(o) > last_step(p) for o in joined.get(p["number"], [])):
            continue
        top = _top(p)
        # closed before the second reading: rejected, withdrawn, or not taken further
        if p["closed"] or not top or any(s["name"] in SETTLED or s["name"] == "Uchwalono" for s in top) \
                or any(s["decision"].startswith("odrzuc") for s in p["stages"]):
            continue
        last = top[-1]
        place = WAITING.get(last["name"])
        if last["name"] == "Praca w komisjach po I czytaniu" and any(
                s["name"] == "Sprawozdanie komisji" for s in p["stages"] if s["date"] and s["date"] >= (last["date"] or "")):
            place = ("reading2", "marshal")   # the report is out: the second reading is up to the Marshal
        if not place:
            continue
        since = last_step(p)
        # "Sejm" is a referral to the chamber, not a committee
        committees = list(dict.fromkeys(s["committee"] for s in p["stages"] if s["committee"] and s["committee"] != "Sejm"))
        days = _days(since, today)
        bills.append({
            "number": p["number"], "title": p["title"], "description": p.get("description") or "",
            "sponsor": sponsor(p["title"]), "type": p["type"],
            "submitted": p["submitted"], "since": since, "days": days, "place": place[0], "holder": place[1],
            "committees": [(c, committee_names.get(c, c)) for c in committees], "stalled": days is not None and days > STALLED_DAYS,
            # MPs' bills: the club of the first signatory, when the signatures could be read
            "club": author(p) if sponsor(p["title"]) == "Poselski" else None,
        })
    bills.sort(key=lambda b: -(b["days"] or 0))
    counts = Counter((b["place"], b["sponsor"]) for b in bills)
    by_club = defaultdict(list)
    for b in bills:
        if b["club"]:
            by_club[b["club"]].append(b)
    return {"bills": bills, "counts": counts, "by_club": sorted(by_club.items(), key=lambda kv: (-len(kv[1]), kv[0]))}


def committees(bills, sittings, names, today=None):
    """[{"code", "name", "held", "held_long", "longest", "meetings", "last",
    "since_last", "gap", "gap_from", "gap_to"}] for every committee holding a
    frozen bill or with meetings: the bills waiting in it, and its breaks
    between meetings (the longest this term, and the time since the last)."""
    today = today or date.today()
    held = defaultdict(list)
    for b in bills:
        if b["holder"] == "committee":
            for code, _ in b["committees"]:
                held[code].append(b)
    out = []
    for code in set(held) | set(sittings):
        days = sorted({m["date"] for m in sittings.get(code, []) if m.get("date") and m.get("status") == "FINISHED"})
        gap, gap_from, gap_to = 0, None, None
        for a, b in zip(days, days[1:]):
            d = _days(a, date.fromisoformat(b))
            if d > gap:
                gap, gap_from, gap_to = d, a, b
        waiting = held.get(code, [])
        out.append({"code": code, "name": names.get(code, code), "held": len(waiting),
                    "held_long": sum(1 for b in waiting if b["stalled"]),
                    "longest": max((b["days"] or 0 for b in waiting), default=0),
                    "meetings": len(days), "last": days[-1] if days else None,
                    "since_last": _days(days[-1], today) if days else None,
                    "gap": gap, "gap_from": gap_from, "gap_to": gap_to})
    out.sort(key=lambda c: (-c["held"], -(c["since_last"] or 0)))
    return out
