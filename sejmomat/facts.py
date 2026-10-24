"""Fun facts from the site's figures, for the stream's quiet moments
(tools/livestream.py shows them as cards, sports-broadcast style, when there
has been no vote for a while). Written by the build to
api/v1/ciekawostki.json. Facts about MPs name only sitting MPs; every figure
comes from the data, as elsewhere.

A card: {"kind": "mp" | "fact", "title": what it is about, "value": the big
number (or text), "unit": what the number counts, "text": the same as one
sentence; for "mp" also "mp" (id), "name", "club" and "stats": [[label,
value], ...]; for "fact" an optional "club" for its colour and optional
"stats" (club cards); "top5": "title", "text" and "rows": [{"mp", "name",
"club", "value"}] of five MPs}.
"""
import re
from datetime import date

from .card import pct

TOP_EVERY = 4   # a Top 5 after this many other cards


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

    # ---- votes
    big = [v for v in votes if v["yes"] + v["no"] >= 100]
    # procedural votes (quorum, breaks, adjourning) say little about politics
    political = [v for v in big if not re.search(r"kworum|przerw|odrocz|zamknięcie posiedzenia", (v.get("topic") or "").lower())]
    rebels = lambda v: sum(len(c.get("rebels") or []) for c in (v.get("clubs") or {}).values())
    v = max(political, key=rebels, default=None)
    if v and rebels(v):
        fact("Największy bunt", rebels(v), "posłów wbrew swoim klubom w jednym głosowaniu",
             f"Najwięcej posłów głosowało wbrew swoim klubom ({rebels(v)}) w głosowaniu: {v['topic']} — {v['agenda'][:80]}.")
    for v in (st.get("close") or [])[1:3]:
        fact("Rozstrzygnięte o włos", f"{v['yes']}:{v['no']}", v["topic"][:60],
             f"Jedno z najbliższych rozstrzygnięć: {v['topic']} ({v['yes']} za, {v['no']} przeciw).")
    unanimous = sum(1 for v in big if v["no"] == 0 and v["abstain"] == 0)
    fact("Jednomyślnie", unanimous, "głosowań bez głosu przeciw i wstrzymań",
         f"{unanimous} głosowań tej kadencji odbyło się bez ani jednego głosu przeciw czy wstrzymującego się.")
    against = sum(1 for v in votes if v.get("against_rec"))
    if against:
        fact("Wbrew komisji", against, "rozstrzygnięć niezgodnych z rekomendacją komisji",
             f"{against} razy Sejm rozstrzygnął poprawkę lub wniosek wbrew rekomendacji komisji.")
    days = {}
    for v in votes:
        days[v["date"][:10]] = days.get(v["date"][:10], 0) + 1
    if days:
        day, n = max(days.items(), key=lambda kv: kv[1])
        fact("Maraton głosowań", n, f"głosowań w jeden dzień ({day[8:10]}.{day[5:7]}.{day[:4]})",
             f"Najwięcej głosowań w jeden dzień: {n}, {day}.")

    # ---- clubs: one card each, and pairs
    for c in sorted(clubs, key=lambda c: -len(c["members"])):
        sp = c.get("speeches") or {}
        out.append({"kind": "fact", "title": "Klub w liczbach", "value": c["id"],
                    "unit": c["name"] if c["name"] != c["id"] else "",
                    "club": c["id"], "text": f"{c['name']}: spójność {pct(c['cohesion'])}, wygrane głosowania {pct(c['effectiveness'])}.",
                    "stats": [["posłów", str(len(c["members"]))], ["spójność", pct(c["cohesion"])],
                              ["wygrane", pct(c["effectiveness"])], ["wystąpienia", str((sp.get("spoken") or 0) + (sp.get("written") or 0))]]})
    pairs = [(c["id"], o["club"], o["rate"]) for c in clubs for o in c["agreement"]
             if o["club"] in {x["id"] for x in clubs} and c["id"] < o["club"]]
    if pairs:
        a_, b_, r = max(pairs, key=lambda p: p[2])
        fact("Najbliżsi sojusznicy", pct(r), f"zgodnych linii {a_} i {b_}", f"Najczęściej tak samo głosują {a_} i {b_}: {pct(r)} głosowań.", a_)
        a_, b_, r = min(pairs, key=lambda p: p[2])
        fact("Ogień i woda", pct(r), f"zgodnych linii {a_} i {b_}", f"Najrzadziej tak samo głosują {a_} i {b_}: tylko {pct(r)} głosowań.", a_)
    proposed = ctx.get("by_proposer") or {}
    rates = [(club, sum(1 for v in vs if v["outcome_class"] == "adopted"), len(vs)) for club, vs in proposed.items()
             if len(vs) >= 20 and club in {x["id"] for x in clubs}]
    if rates:
        club, ok, n = max(rates, key=lambda r: r[1] / r[2])
        fact("Skuteczne poprawki", pct(ok / n), f"poprawek i wniosków {club} przechodzi", f"Poprawki i wnioski {club} przechodzą najczęściej: {ok} z {n}.", club)
        club, ok, n = min(rates, key=lambda r: r[1] / r[2])
        fact("Poprawki do kosza", pct(ok / n), f"poprawek i wniosków {club} przechodzi", f"Poprawki i wnioski {club} przechodzą najrzadziej: {ok} z {n}.", club)

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

    # ---- Top 5s, one after every TOP_EVERY other cards
    def top5(title, rows, key, show, text):
        best = sorted(rows, key=key, reverse=True)[:5]
        return {"kind": "top5", "title": f"Top 5: {title}", "text": text,
                "rows": [{"mp": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club") or "niez.",
                          "value": show(r)} for r in best]}
    tops = [
        top5("najwięcej wystąpień", mps, _speeches, lambda r: str(_speeches(r)), "Najwięcej wystąpień na sali w tej kadencji."),
        top5("interpelacje i zapytania", mps, lambda r: len(r["questions"]), lambda r: str(len(r["questions"])),
             "Najwięcej interpelacji i zapytań poselskich."),
        top5("głosy w wyborach", mps, lambda r: r["mp"].get("numberOfVotes") or 0,
             lambda r: f"{r['mp'].get('numberOfVotes') or 0:,}".replace(",", " "), "Najwięcej głosów w wyborach do Sejmu."),
        top5("frekwencja", steady, lambda r: (r["turnout"], r["eligible"]), lambda r: pct(r["turnout"]),
             "Najwyższa frekwencja w głosowaniach (posłowie z co najmniej 1000 głosowań)."),
        top5("wbrew klubowi", steady, lambda r: r["rebel_count"], lambda r: str(r["rebel_count"]),
             "Najwięcej wyłamań z linii własnego klubu."),
        top5("skuteczne poprawki", mps, lambda r: r["signed_adopted"], lambda r: str(r["signed_adopted"]),
             "Najwięcej przyjętych poprawek i wniosków, pod którymi się podpisali."),
        top5("zmiany klubu", mps, lambda r: (r["switches"], -len(r["mp"]["firstLastName"])), lambda r: str(r["switches"]),
             "Najwięcej zmian klubu w tej kadencji."),
    ]
    mixed = []
    for i, card in enumerate(out):
        mixed.append(card)
        if (i + 1) % TOP_EVERY == 0 and tops:
            mixed.append(tops.pop(0))
    return mixed + tops
