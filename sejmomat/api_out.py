"""Static JSON API written next to the site (site/api/v1/).

Every endpoint is a plain file, so any website can fetch it (GitHub Pages
sends Access-Control-Allow-Origin: *). Field names are English; labels and
legal texts are in Polish as published by the Sejm.
"""
import json

from .config import DATA, SITE, TERM

VERSION = "v1"
VOTE = {"Y": "yes", "N": "no", "A": "abstain", "X": "absent"}


def _write(path, obj):
    out = SITE / "api" / VERSION / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")


def _amendment(a, full):
    item = a["item"] or {}
    out = {
        "kind": a["kind"], "number": a["number"], "sourcePrint": a["source"], "linked": bool(a["item"]),
        "authors": item.get("authors", []), "committeeRecommendation": item.get("recommendation"),
    }
    if full and item:
        out.update({
            "text": item["text"], "notes": item["notes"],
            "wordChanges": [{"where": c["where"], "diffHtml": c["html"]} for c in item["changes"]],
            "lawChanges": _law(item.get("law") or []),
            "billComparison": _bill_diff(item.get("bill_diff")),
        })
    return out


def _author(a, full):
    """Who submitted the bill; for MPs' bills also the signatories' clubs."""
    if not a:
        return None
    out = {"kind": a["kind"], "label": a["label"], "clubs": [{"club": c, "signatures": n} for c, n in a["clubs"]]}
    if full:
        out["signatories"] = a["mps"]
    return out


def _change(c):
    return {"label": c.get("label"), "where": c["where"], "operation": c["op"], "provisionFound": c["found"],
            "rows": c["rows"], "diffHtml": c["html"]}


def _bill_diff(bd):
    """Amendment vs the bill text it amends; rows carry depth and state
    (same / changed / added / removed / context / parent / gap)."""
    if not bd:
        return None
    return {"basePrint": bd["base"], "changes": [_change(c) for c in bd["changes"]]}


def _law(blocks):
    return [{
        "act": b["cite"].get("name"), "eli": b["eli"], "textAvailable": b["loaded"],
        "changes": [_change(c) for c in b["changes"]],
    } for b in blocks]


def _vote(v, full=False):
    out = {
        "sitting": v["sitting"], "votingNumber": v["votingNumber"], "date": v["date"],
        "title": v.get("title"), "topic": v.get("topic"), "agenda": v["agenda"],
        "bill": v["bill"], "prints": v["prints"],
        "result": {"passed": v["passed"], "outcome": v["outcome_class"], "label": v["outcome"],
                   "againstCommitteeRecommendation": v["against_rec"]},
        "motion": v["motion"][0] if v["motion"] else None,
        "majority": {"type": v.get("majorityType"), "votes": v.get("majorityVotes")},
        "totals": {"yes": v["yes"], "no": v["no"], "abstain": v["abstain"], "absent": v["notParticipating"]},
        "proposer": {"clubs": sorted(v["proposer"]["clubs"]), "mps": v["proposer"]["mps"]} if v["proposer"] else None,
        "amendments": [_amendment(a, full) for a in v["amendments"]],
        "url": f"glosowanie/{v['sitting']}-{v['votingNumber']}.html",
    }
    if full:
        out["clubs"] = {
            club: {"yes": c["Y"], "no": c["N"], "abstain": c["A"], "absent": c["X"],
                   "line": VOTE.get(c["line"]), "lineShare": round(c["share"], 4),
                   "brokeLine": [{"mp": mp, "vote": VOTE[code]} for mp, code in c["rebels"]]}
            for club, c in v["clubs"].items()
        }
        out["ballots"] = {club: {VOTE[k]: ids for k, ids in groups.items()} for club, groups in v["ballots"].items()}
    return out


def write_api(ctx, generated):
    endpoints = {
        "sittings": "sittings.json", "sitting": "sittings/{sitting}.json",
        "vote": "votes/{sitting}/{votingNumber}.json", "bills": "bills.json", "bill": "bills/{print}.json",
        "mps": "mps.json", "mp": "mps/{id}.json", "clubs": "clubs.json", "print": "prints/{print}.json",
        "adoptedAmendments": "adopted-amendments.json", "games": "games.json", "summaries": "summaries.json",
    }
    _write("index.json", {"version": VERSION, "term": TERM, "generated": generated, "endpoints": endpoints,
                          "source": "https://api.sejm.gov.pl", "documentation": "../../api.html"})
    _write("sittings.json", [
        {"sitting": s, "from": vs[0]["date"], "to": vs[-1]["date"], "votes": len(vs),
         "amendmentVotes": sum(1 for v in vs if v["amendments"])}
        for s, vs in sorted(ctx["sittings"].items())
    ])
    for s, vs in ctx["sittings"].items():
        _write(f"sittings/{s}.json", [_vote(v) for v in vs])
        for v in vs:
            _write(f"votes/{s}/{v['votingNumber']}.json", _vote(v, full=True))
    _write("bills.json", [
        {"print": b["root"], "title": b["title"], "lastVote": b["last"], "votes": len(b["votings"]),
         "amendmentVotes": b["amend_count"], "author": _author(b["author"], False)} for b in ctx["bills"]
    ])
    for b in ctx["bills"]:
        _write(f"bills/{b['root']}.json", {
            "print": b["root"], "title": b["title"], "prints": b["prints"],
            "author": _author(b["author"], True),
            "lawChangesSourcePrint": b["law_source"], "lawChanges": _law(b["law"]),
            "proposers": [{"proposer": k, "adopted": c["adopted"], "rejected": c["rejected"]} for k, c in b["by_author"]],
            "votes": [{"sitting": v["sitting"], "votingNumber": v["votingNumber"], "topic": v.get("topic"),
                       "outcome": v["outcome_class"]} for v in b["votings"]],
        })
    _write("mps.json", [_mp(r, False) for r in ctx["mp_rows"]])
    for r in ctx["mp_rows"]:
        _write(f"mps/{r['mp']['id']}.json", _mp(r, True))
    _write("clubs.json", [
        {"id": c["id"], "name": c["name"], "exists": c["current"], "members": [r["mp"]["id"] for r in c["members"]],
         "cohesion": round(c["cohesion"], 4), "effectiveness": round(c["effectiveness"], 4),
         "splitVotes": len(c["split"]), "brokeLine": c["rebellions"],
         "agreement": [{"club": o["club"], "rate": round(o["rate"], 4), "sharedVotes": o["both"]} for o in c["agreement"]]}
        for c in ctx["club_rows"]
    ])
    for num in ctx["printed_list"]:
        meta = ctx["print_meta"](num) or {}
        items = {kind: [{**{k: it[k] for k in ("number", "text", "authors", "recommendation", "notes")},
                         "lawChanges": _law(it.get("law") or []), "billComparison": _bill_diff(it.get("bill_diff"))}
                        for it in ctx["source_items"](num, kind, report)]
                 for kind, report in (ctx["sources"].get(num) or {}).items()}
        _write(f"prints/{num}.json", {"number": num, "title": meta.get("title"), "date": meta.get("documentDate"),
                                      "processPrint": meta.get("processPrint"), "items": items})
    _write("games.json", _games(ctx))
    _write("summaries.json", ctx["summaries"])
    _write("adopted-amendments.json", {
        "byProposer": ctx["proposers"],
        "byMp": ctx["mp_proposers"],
        "votes": [{"sitting": row["v"]["sitting"], "votingNumber": row["v"]["votingNumber"],
                   "proposer": row["proposer"]} for row in ctx["adopted"]],
    })


# Left-to-right order of clubs for the guessing game. An editorial judgment,
# not data: adjust here. Clubs not listed (and independents) have no position.
# Left to right, as used by the "Zgadnij posła" game. "Demokracja" is the
# circle around Paweł Kukiz (Demokracja Bezpośrednia, earlier Kukiz'15).
CLUB_AXIS = ["Razem", "Lewica", "Polska2050", "KO", "Centrum", "PSL-TD", "RozwojPlus", "PiS",
             "Demokracja", "Konfederacja", "Konfederacja_KP"]
GAME_TEXT_MAX = 700
GAME_FINALS = 150


GAME_CONTEXT_MAX = 3000


def _game_context(item):
    """Comparison with the bill for the first change the amendment makes, if
    it was found and is short enough to show in a game."""
    for change in (item.get("bill_diff") or {}).get("changes", []):
        if change["found"] and len(change["html"]) <= GAME_CONTEXT_MAX:
            return {"where": change["where"], "html": change["html"]}
    return None


def _committees_by_mp():
    """{mp id: ["Finansów Publicznych (przewodniczący)", ...]}, standing committees first."""
    path = DATA / "committees.json"
    if not path.exists():
        return {}
    order = {"STANDING": 0, "EXTRAORDINARY": 1, "INVESTIGATIVE": 2}
    out = {}
    committees = json.loads(path.read_text(encoding="utf-8"))
    for c in sorted(committees, key=lambda c: (order.get(c.get("type"), 3), c.get("name") or "")):
        name = (c.get("name") or "").removeprefix("Komisja ")
        name = name[:1].upper() + name[1:]
        for m in c["members"]:
            out.setdefault(m["id"], []).append(f"{name} ({m['function']})" if m.get("function") else name)
    return out


def _games(ctx):
    """Compact data for the Sejmdle games (see games/sejmdle)."""
    committees = _committees_by_mp()
    mps = [{
        "committees": committees.get(r["mp"]["id"], []),
        "id": r["mp"]["id"], "name": r["mp"]["firstLastName"], "lastName": r["mp"].get("lastName"),
        "club": r["mp"].get("club"),
        "clubName": ctx["clubs"].get(r["mp"].get("club"), r["mp"].get("club")),
        "district": r["mp"].get("districtName"), "districtNum": r["mp"].get("districtNum"),
        "voivodeship": r["mp"].get("voivodeship"), "birthDate": r["mp"].get("birthDate"),
        "education": r["mp"].get("educationLevel"), "electionVotes": r["mp"].get("numberOfVotes"),
        "turnout": round(r["turnout"], 4), "brokeLine": r["rebel_count"],
    } for r in ctx["mp_rows"] if r["mp"].get("active") and r["mp"].get("birthDate")]
    votes = sorted(ctx["by_id"].values(), key=lambda v: (v["date"], v["votingNumber"]))

    def bill_title(v):
        bill = ctx["bill_by_root"].get(v["bill"])
        return (bill["title"] if bill else v["agenda"]).rstrip(".")

    amendments = []
    for v in votes:
        if len(v["amendments"]) != 1 or not v["amendments"][0]["item"]:
            continue
        a = v["amendments"][0]
        text = a["item"]["text"]
        if not 60 <= len(text) <= GAME_TEXT_MAX:
            continue
        amendments.append({
            "s": v["sitting"], "n": v["votingNumber"], "date": v["date"][:10], "kind": a["kind"],
            "text": text, "adopted": v["outcome_class"] == "adopted", "proposer": v["proposer"]["label"],
            "bill": bill_title(v), "yes": v["yes"], "no": v["no"],
            # shown before the answer: what the amendment changes in the bill
            "context": _game_context(a["item"]),
            "recommendation": a["item"].get("recommendation"),
        })
    finals = []
    for v in votes:
        if not v["motion"] or v["motion"][0] != "final" or min(v["yes"], v["no"]) < 60:
            continue
        merged = {}
        for groups in v["ballots"].values():
            for code, ids in groups.items():
                merged.setdefault(VOTE[code], []).extend(ids)
        finals.append({"s": v["sitting"], "n": v["votingNumber"], "date": v["date"][:10],
                       "title": bill_title(v), "passed": v["passed"], "votes": merged})
    return {"clubAxis": CLUB_AXIS, "mps": mps, "amendments": amendments, "finals": finals[-GAME_FINALS:]}


def _mp(r, full):
    out = {
        "id": r["mp"]["id"], "name": r["mp"]["firstLastName"], "club": r["mp"].get("club"),
        "active": r["mp"].get("active"), "turnout": round(r["turnout"], 4),
        "brokeLine": r["rebel_count"], "brokeLineRate": round(r["rebel_rate"], 4),
        "signedMotions": len(r["signed"]), "signedAdopted": r["signed_adopted"], "clubSwitches": r["switches"],
    }
    if full:
        out["clubHistory"] = [{"club": h["club"], "from": h["from"], "to": h["to"], "votes": h["votes"],
                               "rename": h.get("rename", False)} for h in r["history"]]
        out["brokeLineVotes"] = [{"sitting": s, "votingNumber": n, "vote": VOTE[c], "clubLine": VOTE[l], "club": club}
                                 for s, n, c, l, club in r["rebellions"]]
        out["signed"] = [{"sitting": v["sitting"], "votingNumber": v["votingNumber"], "outcome": v["outcome_class"]}
                         for v in r["signed"]]
    return out
