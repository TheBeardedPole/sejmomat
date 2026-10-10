"""Static JSON API written next to the site (site/api/v1/).

Every endpoint is a plain file, so any website can fetch it (GitHub Pages
sends Access-Control-Allow-Origin: *). Field names are English; labels and
legal texts are in Polish as published by the Sejm.
"""
import json

from .config import SITE, TERM

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
        "adoptedAmendments": "adopted-amendments.json",
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
         "amendmentVotes": b["amend_count"]} for b in ctx["bills"]
    ])
    for b in ctx["bills"]:
        _write(f"bills/{b['root']}.json", {
            "print": b["root"], "title": b["title"], "prints": b["prints"],
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
    _write("adopted-amendments.json", {
        "byProposer": ctx["proposers"],
        "byMp": ctx["mp_proposers"],
        "votes": [{"sitting": row["v"]["sitting"], "votingNumber": row["v"]["votingNumber"],
                   "proposer": row["proposer"]} for row in ctx["adopted"]],
    })


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
