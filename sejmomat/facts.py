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
"club", "value"}] of five MPs}. "topic" names what a card counts
(speeches, questions…), so cards about the same thing are kept apart. Top 5s
with "for_club" rank one club's MPs; they come last and are not in the
general turn: the stream shows them while an MP of that club speaks.
"""
import re
from itertools import zip_longest
from datetime import date

from .card import pct

TOP_EVERY = 4   # a Top 5 after this many other cards
SPREAD = 3      # no two cards about the same thing within this many of each other


def _speeches(r):
    sp = r.get("speeches") or {}
    return (sp.get("spoken") or 0) + (sp.get("written") or 0)


def _mp(r, title, value, unit, text, topic):
    return {"kind": "mp", "topic": topic, "mp": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club") or "niez.",
            "title": title, "value": value, "unit": unit, "text": text,
            "stats": [["frekwencja", pct(r["turnout"])], ["wyłamania", str(r["rebel_count"])],
                      ["wystąpienia", str(_speeches(r))], ["interpelacje", str(len(r["questions"]))]]}


def _age(birth, today):
    b = date.fromisoformat(birth[:10])
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


BOTTOM_CLUB = 10   # a club this big or bigger has its own "Ostatnia piątka" cards


def facts(ctx, today=None):
    today = today or date.today()
    out = []
    mps = [r for r in ctx["mp_rows"] if r["mp"].get("active")]
    steady = [r for r in mps if r["eligible"] >= 1000]
    who = lambda r: f"{r['mp']['firstLastName']} ({r['mp'].get('club') or 'niez.'})"

    r = max(mps, key=_speeches)
    out.append(_mp(r, "Najwięcej wystąpień na sali", _speeches(r), "wystąpień",
                   f"Najwięcej wystąpień na sali w tej kadencji: {who(r)}, {_speeches(r)}.", "speeches"))
    r = max(mps, key=lambda r: len(r["questions"]))
    out.append(_mp(r, "Mistrz interpelacji", len(r["questions"]), "interpelacji i zapytań",
                   f"Najwięcej interpelacji i zapytań: {who(r)}, {len(r['questions'])}.", "questions"))
    r = max(steady, key=lambda r: (r["turnout"], r["eligible"]))
    out.append(_mp(r, "Żelazna frekwencja", pct(r["turnout"]), f"z {r['eligible']} głosowań",
                   f"Najwyższa frekwencja w głosowaniach: {who(r)}, {pct(r['turnout'])}.", "turnout"))
    r = max(steady, key=lambda r: r["rebel_count"])
    out.append(_mp(r, "Najczęściej wbrew klubowi", r["rebel_count"], "wyłamań z linii klubu",
                   f"Najczęściej wyłamuje się z linii swojego klubu: {who(r)}, {r['rebel_count']} razy.", "rebels"))
    r = max(mps, key=lambda r: r["mp"].get("numberOfVotes") or 0)
    out.append(_mp(r, "Rekordzista wyborów", f"{r['mp']['numberOfVotes']:,}".replace(",", " "), "głosów w wyborach",
                   f"Najwięcej głosów w wyborach do Sejmu dostał(a) {who(r)}: {r['mp']['numberOfVotes']}.", "election"))
    born = [r for r in mps if r["mp"].get("birthDate")]
    if born:
        r = max(born, key=lambda r: r["mp"]["birthDate"])
        out.append(_mp(r, "Najmłodszy w Sejmie", _age(r["mp"]["birthDate"], today), "lat",
                       f"Najmłodszy obecny poseł: {who(r)}, {_age(r['mp']['birthDate'], today)} lat.", "age"))
        r = min(born, key=lambda r: r["mp"]["birthDate"])
        out.append(_mp(r, "Najstarszy w Sejmie", _age(r["mp"]["birthDate"], today), "lat",
                       f"Najstarszy obecny poseł: {who(r)}, {_age(r['mp']['birthDate'], today)} lat.", "age"))
    switched = max(mps, key=lambda r: r["switches"])
    if switched["switches"] >= 2:
        out.append(_mp(switched, "Wędrowiec", switched["switches"], "zmiany klubu",
                       f"Najwięcej zmian klubu w tej kadencji: {who(switched)}, {switched['switches']}.", "switches"))

    def fact(title, value, unit, text, club=None, topic=None):
        out.append({"kind": "fact", "title": title, "value": value, "unit": unit, "text": text, "club": club, "topic": topic})

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
             f"Najbliższe rozstrzygnięcie kadencji: {v['topic']} ({v['yes']} za, {v['no']} przeciw).", topic="close")
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
             f"Jedno z najbliższych rozstrzygnięć: {v['topic']} ({v['yes']} za, {v['no']} przeciw).", topic="close")
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
                    # the name without "Klub Parlamentarny" and the like: the card says it is a club
                    "unit": re.sub(r"^(Klub Parlamentarny|Klub Poselski|Koło Poselskie|Koło Parlamentarne)\s+", "", c["name"])
                    if c["name"] != c["id"] else "",
                    "club": c["id"], "text": f"{c['name']}: spójność {pct(c['cohesion'])}, wygrane głosowania {pct(c['effectiveness'])}.",
                    "stats": [["posłów", str(len(c["members"]))], ["spójność", pct(c["cohesion"])],
                              ["wygrane", pct(c["effectiveness"])], ["wystąpienia", f"{(sp.get('spoken') or 0) + (sp.get('written') or 0):,}".replace(",", " ")]]})
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
    def top5(title, rows, key, show, text, topic, club=None):
        best = [r for r in sorted(rows, key=key, reverse=True)[:5]]
        top = "Top 5" if len(best) == 5 else f"Top {len(best)}"   # a club of fewer than five: all of them
        card = {"kind": "top5", "topic": topic, "title": f"{top}: {title}", "text": text,
                "rows": [{"mp": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club") or "niez.",
                          "value": show(r)} for r in best]}
        if club:
            card.update(title=f"{top} w {club}: {title}", club=club, for_club=club)
        return card

    def categories(rows, steady_rows):
        return [
            ("najwięcej wystąpień", rows, _speeches, lambda r: str(_speeches(r)), "Najwięcej wystąpień na sali w tej kadencji.", "speeches"),
            ("interpelacje i zapytania", rows, lambda r: len(r["questions"]), lambda r: str(len(r["questions"])),
             "Najwięcej interpelacji i zapytań poselskich.", "questions"),
            ("głosy w wyborach", rows, lambda r: r["mp"].get("numberOfVotes") or 0,
             lambda r: f"{r['mp'].get('numberOfVotes') or 0:,}".replace(",", " "), "Najwięcej głosów w wyborach do Sejmu.", "election"),
            ("frekwencja", steady_rows, lambda r: (r["turnout"], r["eligible"]), lambda r: pct(r["turnout"]),
             "Najwyższa frekwencja w głosowaniach (posłowie z co najmniej 1000 głosowań).", "turnout"),
            ("wbrew klubowi", steady_rows, lambda r: r["rebel_count"], lambda r: str(r["rebel_count"]),
             "Najwięcej wyłamań z linii własnego klubu.", "rebels"),
            ("skuteczne poprawki", rows, lambda r: r["signed_adopted"], lambda r: str(r["signed_adopted"]),
             "Najwięcej przyjętych poprawek i wniosków, pod którymi się podpisali.", "amendments"),
        ]
    tops = [top5(*c) for c in categories(mps, steady)]
    tops.append(top5("zmiany klubu", mps, lambda r: (r["switches"], -len(r["mp"]["firstLastName"])), lambda r: str(r["switches"]),
                     "Najwięcej zmian klubu w tej kadencji.", "switches"))

    # the same for each club, shown while one of its MPs speaks (tools/livestream.py); a club or
    # circle of two to four MPs (Razem, Demokracja, ...) ranks all of them
    per_club = []
    ranked = [c for c in ctx["club_rows"] if c["current"] and len(c["members"]) >= 2]
    for c in sorted(ranked, key=lambda c: -len(c["members"])):
        rows = [r for r in mps if r["mp"].get("club") == c["id"]]
        for title, pool, key, show, text, topic in categories(rows, [r for r in steady if r["mp"].get("club") == c["id"]]):
            # a ranking only where at least two of them have something to count (not "1 · 0 · 0 · 0")
            if len(pool) >= 2 and sum(1 for r in pool if key(r) not in (0, (0, 0))) >= 2:
                per_club.append(top5(title, pool, key, show, f"{text} Klub {c['id']}.", topic, c["id"]))
    # The other end: the five lowest, among MPs who served (near enough) the whole term, else a
    # newcomer of the spring would always come last; in the general turn and, for clubs of
    # BOTTOM_CLUB or more MPs, among the club's own (a club of four has no "bottom five")
    most = max((r["eligible"] for r in mps), default=0)
    whole = [r for r in mps if r["eligible"] >= 0.9 * most]

    def bottom5(title, rows, key, show, text, topic, club=None):
        low = sorted(rows, key=key)[:5]
        card = {"kind": "top5", "bottom": True, "topic": f"{topic}-low", "title": f"Ostatnia piątka: {title}", "text": text,
                "rows": [{"mp": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club") or "niez.",
                          "value": show(r)} for r in low]}
        if club:
            card.update(title=f"Ostatnia piątka w {club}: {title}", club=club, for_club=club)
        return card

    def lows(rows):
        return [("najmniej wystąpień", rows, _speeches, lambda r: str(_speeches(r)),
                 "Najmniej wystąpień na sali (posłowie obecni przez całą kadencję).", "speeches"),
                ("najmniej interpelacji i zapytań", rows, lambda r: len(r["questions"]), lambda r: str(len(r["questions"])),
                 "Najmniej interpelacji i zapytań poselskich (posłowie obecni przez całą kadencję).", "questions"),
                ("najniższa frekwencja", rows, lambda r: r["turnout"], lambda r: pct(r["turnout"]),
                 "Najniższa frekwencja w głosowaniach (posłowie obecni przez całą kadencję).", "turnout"),
                ("najmniej głosów w wyborach", rows, lambda r: r["mp"].get("numberOfVotes") or 0,
                 lambda r: f"{r['mp'].get('numberOfVotes') or 0:,}".replace(",", " "),
                 "Najmniej głosów w wyborach do Sejmu (posłowie obecni przez całą kadencję).", "election")]
    def clear_cut(rows, key):
        """A bottom five means something only when no more than five share its last value (dozens
        of ministers on 0 interpellations — the government cannot file them — would be an
        alphabetical pick)."""
        low = sorted(rows, key=key)[:5]
        return len(low) == 5 and sum(1 for r in rows if key(r) <= key(low[-1])) <= 5
    tops += [bottom5(*c) for c in lows(whole) if clear_cut(c[1], c[2])]
    for c in ctx["club_rows"]:
        if c["current"] and len(c["members"]) >= BOTTOM_CLUB:
            mine = [r for r in whole if r["mp"].get("club") == c["id"]]
            if len(mine) >= 6:   # more than the five to show, or "the lowest" is simply the club
                per_club += [bottom5(t, rows, key, show, f"{text} Klub {c['id']}.", topic, c["id"])
                             for t, rows, key, show, text, topic in lows(mine) if clear_cut(rows, key)]
    # MPs, figures and clubs taking turns, rather than each in a run
    groups = [[c for c in out if c["kind"] == "mp"], [c for c in out if c["kind"] == "fact" and not c.get("stats")],
              [c for c in out if c["kind"] == "fact" and c.get("stats")]]
    mixed = [c for row in zip_longest(*groups) for c in row if c]
    return spread(mixed, tops) + per_club + comparisons(ctx, mps) + regions(mps)


def regions(mps):
    """Posłowie z regionu: for each constituency its MPs, club by club, the most active first;
    shown while one of them speaks (tools/livestream.py), in pages when there are many.
    A card: {"kind": "region", "title", "district", "num", "mps": [ids], "rows": [{"mp", "name",
    "club", "value"}], "unit"}."""
    out = []
    for num in sorted({r["mp"].get("districtNum") for r in mps if r["mp"].get("districtNum")}):
        here = [r for r in mps if r["mp"].get("districtNum") == num]
        sizes = {}
        for r in here:
            sizes[r["mp"].get("club") or "niez."] = sizes.get(r["mp"].get("club") or "niez.", 0) + 1
        here.sort(key=lambda r: (-sizes[r["mp"].get("club") or "niez."], r["mp"].get("club") or "", -_speeches(r)))
        name = here[0]["mp"].get("districtName") or ""
        out.append({"kind": "region", "topic": "region", "title": f"Posłowie z okręgu {num} · {name}", "district": name, "num": num,
                    "mps": [r["mp"]["id"] for r in here], "unit": "wystąpień",
                    "rows": [{"mp": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club") or "niez.",
                              "value": f"{_speeches(r)} wyst."} for r in here]})
    return out


def mp_compare(k, o):
    """A comparison of two MPs from the pool (comparisons, "mp_pool"): k from the coalition, o
    from the opposition, usually of one constituency."""
    same = k["num"] == o["num"]
    return {"kind": "compare", "topic": "mps", "title": f"{k['name']} kontra {o['name']}",
            "sides": [{"name": m["name"], "club": m["club"], "tag": m["tag"], "mp": m["id"],
                       "sub": f"okręg {m['num']} · {m['district']}"} for m in (k, o)],
            "rows": [_row("wystąpienia na sali", k["speeches"], o["speeches"], str),
                     _row("interpelacje i zapytania", k["questions"], o["questions"], str),
                     _row("frekwencja", k["turnout"], o["turnout"], pct),
                     _row("głosy w wyborach", k["votes"], o["votes"], _num),
                     _row("przyjęte poprawki (podpisane)", k["adopted"], o["adopted"], str),
                     _row("wyłamania z linii klubu", k["rebels"], o["rebels"], str, "less")],
            "headline": f"Ten sam okręg: {k['district']}" if same else "Koalicja kontra opozycja",
            "sub": "Poseł koalicji i poseł opozycji · cała kadencja"}


def _num(n):
    return f"{n:,}".replace(",", " ")


def _row(label, a, b, show, better="more"):
    return {"label": label, "a": a, "b": b, "show": [show(a), show(b)], "better": better}


def comparisons(ctx, mps):
    """Full-screen comparisons for a break in the sitting (tools/livestream.py): club against
    club (the coalition's and the opposition's clubs paired by size, the closest allies and the
    furthest apart) and, per constituency, its most active coalition and opposition speakers.
    A card: {"kind": "compare", "sides": [{"name", "club", "tag", "mp"?, "sub"}] * 2,
    "rows": [{"label", "a", "b", "show": [a, b], "better": "more" | "less"}], "headline", "sub"}."""
    from .stats import COALITION
    tag = lambda club: "Koalicja" if club in COALITION else "Opozycja"   # noqa: E731
    out = []
    clubs = {c["id"]: c for c in ctx["club_rows"] if c["current"] and len(c["members"]) >= 5}

    def questions(c):
        q = c.get("questions") or {}
        return (q.get("int") or 0) + (q.get("zap") or 0)

    def club_card(a, b, headline, sub):
        rate = next((x["rate"] for x in a["agreement"] if x["club"] == b["id"]), None)
        out.append({"kind": "compare", "topic": "clubs", "title": f"{a['id']} kontra {b['id']}",
                    "sides": [{"name": c["id"], "club": c["id"], "tag": tag(c["id"]), "sub": f"{len(c['members'])} posłów"} for c in (a, b)],
                    "rows": [_row("posłów", len(a["members"]), len(b["members"]), str),
                             _row("spójność głosowania", a["cohesion"], b["cohesion"], pct),
                             _row("po stronie zwycięskiej", a["effectiveness"], b["effectiveness"], pct),
                             _row("wystąpienia", _speeches(a), _speeches(b), _num),
                             _row("interpelacje i zapytania", questions(a), questions(b), _num),
                             _row("wyłamania z linii klubu", a["rebellions"], b["rebellions"], _num, "less")],
                    "headline": headline or (f"Głosują tak samo w {pct(rate)} głosowań" if rate is not None else ""),
                    "sub": sub})

    ours = sorted((c for c in clubs.values() if c["id"] in COALITION), key=lambda c: -len(c["members"]))
    theirs = sorted((c for c in clubs.values() if c["id"] not in COALITION), key=lambda c: -len(c["members"]))
    seen = set()
    for a, b in zip(ours, theirs):
        seen.add(frozenset((a["id"], b["id"])))
        club_card(a, b, None, "Koalicja i opozycja · linia klubu: jak głosowała większość jego posłów · cała kadencja")
    pairs = [(a, b, r) for a in clubs.values() for b in clubs.values() if a["id"] < b["id"]
             for r in [next((x["rate"] for x in a["agreement"] if x["club"] == b["id"]), None)] if r is not None]
    if pairs:
        for (a, b, r), what in ((max(pairs, key=lambda p: p[2]), "Najbliżsi sojusznicy"), (min(pairs, key=lambda p: p[2]), "Ogień i woda")):
            if frozenset((a["id"], b["id"])) not in seen:
                seen.add(frozenset((a["id"], b["id"])))
                club_card(a, b, f"{what}: tak samo w {pct(r)} głosowań", "Linia klubu: jak głosowała większość jego posłów · cała kadencja")

    # MPs: not a fixed few (the busiest ran out soon) but a pool of every MP's figures, from which
    # the stream draws a pair each time (mp_compare): a constituency's coalition and opposition MP
    out.append({"kind": "mp_pool", "topic": "mps", "title": "Posłowie do porównań",
                "mps": [{"id": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club") or "niez.",
                         "tag": tag(r["mp"].get("club")), "num": r["mp"].get("districtNum"), "district": r["mp"].get("districtName") or "",
                         "speeches": _speeches(r), "questions": len(r["questions"]), "turnout": r["turnout"],
                         "votes": r["mp"].get("numberOfVotes") or 0, "adopted": r["signed_adopted"], "rebels": r["rebel_count"]}
                        for r in mps if r["mp"].get("districtNum")]})
    return out


def _keys(card):
    """What a card is about: its topic, its MPs, its club (for club facts)."""
    keys = set()
    if card.get("topic"):
        keys.add(("topic", card["topic"]))
    if card.get("mp"):
        keys.add(("mp", card["mp"]))
    keys |= {("mp", r["mp"]) for r in card.get("rows") or []}
    if card["kind"] == "fact" and card.get("club"):
        keys.add(("club", card["club"]))
    return keys


def spread(cards, tops, gap=SPREAD):
    """The cards in turn, a Top 5 after every TOP_EVERY others, each card chosen so
    that none of the `gap` before it is about the same thing (the most speeches
    and the Top 5 of speeches, the same MP or club) where that can be helped."""
    cards, tops, done = list(cards), list(tops), []
    while cards or tops:
        due = tops and (not cards or (len(done) + 1) % (TOP_EVERY + 1) == 0)
        pool = tops if due else cards
        recent = set().union(*[_keys(c) for c in done[-gap:]]) if done else set()
        pick = next((c for c in pool if not (_keys(c) & recent)), pool[0])
        pool.remove(pick)
        done.append(pick)
    return done
