"""Fun facts from the site's figures, for the stream's quiet moments
(tools/livestream.py shows them as cards, sports-broadcast style, when there
has been no vote for a while). Written by the build to
api/v1/ciekawostki.json. Facts about MPs name only sitting MPs; every figure
comes from the data, as elsewhere.

A card: {"kind": "mp" | "fact", "title": what it is about, "value": the big
number (or text), "unit": what the number counts, "text": the same as one
sentence; for "mp" also "mp" (id), "name", "club" and "stats": [[label,
value], ...]; for "fact" an optional "club" for its colour}.
"""
from datetime import date

from .card import pct


def _speeches(r):
    sp = r.get("speeches") or {}
    return (sp.get("spoken") or 0) + (sp.get("written") or 0)


def _mp(r, title, value, unit, text):
    return {"kind": "mp", "mp": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club") or "niez.",
            "title": title, "value": value, "unit": unit, "text": text,
            "stats": [["frekwencja", pct(r["turnout"])], ["wyłamania", str(r["rebel_count"])],
                      ["wystąpienia", str(_speeches(r))], ["interpelacje", str(len(r["questions"]))]]}


def _age(birth, today):
    b = date.fromisoformat(birth[:10])
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


def facts(ctx, today=None):
    today = today or date.today()
    out = []
    mps = [r for r in ctx["mp_rows"] if r["mp"].get("active")]
    steady = [r for r in mps if r["eligible"] >= 1000]
    who = lambda r: f"{r['mp']['firstLastName']} ({r['mp'].get('club') or 'niez.'})"

    r = max(mps, key=_speeches)
    out.append(_mp(r, "Najwięcej wystąpień na sali", _speeches(r), "wystąpień",
                   f"Najwięcej wystąpień na sali w tej kadencji: {who(r)}, {_speeches(r)}."))
    r = max(mps, key=lambda r: len(r["questions"]))
    out.append(_mp(r, "Mistrz interpelacji", len(r["questions"]), "interpelacji i zapytań",
                   f"Najwięcej interpelacji i zapytań: {who(r)}, {len(r['questions'])}."))
    r = max(steady, key=lambda r: (r["turnout"], r["eligible"]))
    out.append(_mp(r, "Żelazna frekwencja", pct(r["turnout"]), f"z {r['eligible']} głosowań",
                   f"Najwyższa frekwencja w głosowaniach: {who(r)}, {pct(r['turnout'])}."))
    r = max(steady, key=lambda r: r["rebel_count"])
    out.append(_mp(r, "Najczęściej wbrew klubowi", r["rebel_count"], "wyłamań z linii klubu",
                   f"Najczęściej wyłamuje się z linii swojego klubu: {who(r)}, {r['rebel_count']} razy."))
    r = max(mps, key=lambda r: r["mp"].get("numberOfVotes") or 0)
    out.append(_mp(r, "Rekordzista wyborów", f"{r['mp']['numberOfVotes']:,}".replace(",", " "), "głosów w wyborach",
                   f"Najwięcej głosów w wyborach do Sejmu dostał(a) {who(r)}: {r['mp']['numberOfVotes']}."))
    born = [r for r in mps if r["mp"].get("birthDate")]
    if born:
        r = max(born, key=lambda r: r["mp"]["birthDate"])
        out.append(_mp(r, "Najmłodszy w Sejmie", _age(r["mp"]["birthDate"], today), "lat",
                       f"Najmłodszy obecny poseł: {who(r)}, {_age(r['mp']['birthDate'], today)} lat."))
        r = min(born, key=lambda r: r["mp"]["birthDate"])
        out.append(_mp(r, "Najstarszy w Sejmie", _age(r["mp"]["birthDate"], today), "lat",
                       f"Najstarszy obecny poseł: {who(r)}, {_age(r['mp']['birthDate'], today)} lat."))
    switched = max(mps, key=lambda r: r["switches"])
    if switched["switches"] >= 2:
        out.append(_mp(switched, "Wędrowiec", switched["switches"], "zmiany klubu",
                       f"Najwięcej zmian klubu w tej kadencji: {who(switched)}, {switched['switches']}."))

    def fact(title, value, unit, text, club=None):
        out.append({"kind": "fact", "title": title, "value": value, "unit": unit, "text": text, "club": club})

    silent = [r for r in mps if _speeches(r) == 0]
    if silent:
        fact("Milczący", len(silent), "posłów nie przemówiło ani razu", f"{len(silent)} posłów nie zabrało w tej kadencji głosu na sali ani razu.")
    moved = [r for r in mps if r["switches"]]
    fact("Transfery", len(moved), "posłów zmieniło klub", f"{len(moved)} obecnych posłów zmieniło w tej kadencji klub przynajmniej raz.")

    clubs = [c for c in ctx["club_rows"] if c["current"] and len(c["members"]) >= 5]
    if clubs:
        c = max(clubs, key=lambda c: c["cohesion"])
        fact("Najbardziej zgrany klub", pct(c["cohesion"]), f"zgodności w {c['id']}",
             f"Najbardziej zgodnie głosujący klub: {c['id']}, {pct(c['cohesion'])}.", c["id"])
        c = max(clubs, key=lambda c: c["effectiveness"])
        fact("Najczęściej wygrywa", pct(c["effectiveness"]), f"głosowań wygrywa {c['id']}",
             f"Najczęściej po stronie zwycięskiej: {c['id']}, {pct(c['effectiveness'])} głosowań.", c["id"])

    votes = [v for vs in ctx["sittings"].values() for v in vs]
    fact("Licznik głosowań", len(votes), f"głosowań na {len(ctx['sittings'])} posiedzeniach",
         f"W tej kadencji Sejm głosował już {len(votes)} razy na {len(ctx['sittings'])} posiedzeniach.")
    st = ctx.get("voting_stats") or {}
    if st.get("term_between") is not None:
        fact("Ponad podziałami", pct(st["term_between"]), "głosowań koalicja i opozycja razem",
             f"Poseł koalicji i poseł opozycji głosują tak samo średnio w {pct(st['term_between'])} głosowań.")
    if st.get("close"):
        v = st["close"][0]
        fact("Na włosku", f"{v['yes']}:{v['no']}", v["topic"][:60],
             f"Najbliższe rozstrzygnięcie kadencji: {v['topic']} ({v['yes']} za, {v['no']} przeciw).")
    passed = sum(1 for v in votes if v.get("motion") and v["motion"][0] == "final" and v["passed"])
    if passed:
        fact("Uchwalone", passed, "projektów przyjętych w całości", f"Sejm tej kadencji uchwalił w głosowaniu nad całością {passed} projektów.")

    frozen = (ctx.get("frozen") or {}).get("bills") or []
    if frozen:
        fact("Zamrażarka", len(frozen), "projektów czeka u Marszałka lub w komisjach",
             f"{len(frozen)} projektów ustaw i uchwał czeka u Marszałka Sejmu albo w komisjach.")
        b = frozen[0]
        fact("Rekord zamrażarki", b["days"], "dni bez ruchu", f"Najdłużej czekający projekt: {b['title'][:110]} — {b['days']} dni.")
    pending = ctx.get("pending_amendments") or []
    if pending:
        n = sum(len(g["items"]) for g in pending)
        fact("W kolejce", n, "poprawek czeka na głosowanie", f"{n} poprawek i wniosków mniejszości czeka na głosowanie.")
    q = ctx.get("questions_summary") or {}
    if q.get("mp_median") is not None:
        fact("Typowy poseł", q["mp_median"], "interpelacji i zapytań", f"Typowy poseł złożył w tej kadencji {q['mp_median']} interpelacji i zapytań.")
    return out
