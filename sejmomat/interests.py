"""Interests on the home page: what happened lately in the topics a reader
follows, and MPs whose documented work is on those topics.

data/interests.json lists a handful of broad interests (health, education,
...), each a set of tags from data/tags.json, committees and the ministers
interpellations are addressed to. Everything here is matched through that one
file, so finer tagging later changes the data, not the page:

- a bill matches an interest when it has one of its tags or was sent to one
  of its committees (the processes' stages); its votes, stages and agenda
  items match with it. Amendment votes are not matched one by one (their
  descriptions do not say what an amendment is about): a bill's amendment
  votes at a sitting are counted together and shown as such, the topic taken
  from the bill and marked as taken from it.
- an MP matches through a role in one of its committees, interpellations and
  written questions to its ministers, and bills with its tags that the MP
  signed or presents.

The page (static/home.js) reads the result, dane/zainteresowania.json, only
for a reader who has picked interests; the choice stays in their browser.
Every match carries its reason, shown next to it.
"""
import json
from collections import defaultdict
from datetime import date, timedelta

from .config import DATA, TERM

PATH = DATA / "interests.json"
DAYS = 30            # events shown: the last 30 days
MP_DAYS = 90         # an MP's recent work counts more
MP_MIN_SCORE = 3     # below this an MP is not suggested: too little to go on
MP_PER_INTEREST = 12
# stages worth showing on their own (the rest are steps on the way)
STAGES = {
    "Projekt wpłynął do Sejmu", "I czytanie na posiedzeniu Sejmu", "I czytanie w komisjach",
    "II czytanie na posiedzeniu Sejmu", "III czytanie na posiedzeniu Sejmu", "Uchwalono", "Odrzucono",
    "Stanowisko Senatu", "Prezydent podpisał ustawę", "Wniosek Prezydenta (weto)", "Wycofano",
    "Prezydent skierował ustawę do Trybunału Konstytucyjnego", "nie uchwalona ponownie po wecie Prezydenta",
}
WHOLE = ("final", "reject_bill", "reject_senate")   # votes on a bill as a whole
# committee roles, as the API names them, and their weight
ROLES = {"przewodniczący": 4, "przewodnicząca": 4, "zastępca przewodniczącego": 3, "zastępczyni przewodniczącego": 3}
MEMBER = 2


def load():
    data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    return data.get("interests") or []


def bill_matches(tags, committees, spec):
    """{interest id: [reason]} for a bill with these tags and committees; a
    reason is ("tag", tag) or ("committee", code)."""
    out = {}
    for i in spec:
        why = [("tag", t) for t in tags if t in i["tags"]] + [("committee", c) for c in committees if c in i["committees"]]
        if why:
            out[i["id"]] = why
    return out


def _stage_committees(proc):
    return sorted({s["committee"] for s in (proc or {}).get("stages", []) if s.get("committee") and s["committee"] != "Sejm"})


def events(spec, bills, by_id, procs, upcoming, today):
    """The last DAYS days' events that match an interest, newest first:
    whole-bill votes, a bill's amendment votes at a sitting (counted together),
    a bill's stages, and items on the next sitting's agenda. Each names the
    sitting ("p") when it happened on a sitting's day.

    bills: {root: {"title", "tags"}}; by_id: votes with "date", "sitting",
    "votingNumber", "bill", "motion", "outcome", "outcome_class"; procs: the
    processes (sejmomat/processes.py); upcoming: the next sitting's agenda
    (sejmomat/agenda.py) with each item's "bill" (a root with a page here) and
    "root" (the process its prints belong to)."""
    since = (today - timedelta(days=DAYS)).isoformat()
    match = {}

    def matches(root):
        if root not in match:
            b = bills.get(root) or {}
            match[root] = bill_matches(b.get("tags", []), _stage_committees(procs.get(root)), spec)
        return match[root]

    def title(root):
        return (bills.get(root) or {}).get("title") or (procs.get(root) or {}).get("title") or ""

    recent = [v for v in by_id.values() if (v.get("date") or "")[:10] >= since]
    day_sitting = {v["date"][:10]: v["sitting"] for v in recent}
    if upcoming and upcoming.get("number"):
        day_sitting.update({d: upcoming["number"] for d in upcoming["dates"]})
    # a bill's amendment votes per sitting: [count, adopted, last day, first vote]
    amended = {}
    for v in sorted(recent, key=lambda v: (v["date"], v["votingNumber"])):
        if v.get("amendments") and v.get("bill"):
            a = amended.setdefault((v["bill"], v["sitting"]), [0, 0, "", v])
            a[0] += 1
            a[1] += v.get("outcome_class") == "adopted"
            a[2] = v["date"][:10]

    out = []
    for v in recent:
        root = v.get("bill")
        if not root or not v.get("motion") or v["motion"][0] not in WHOLE:
            continue
        if m := matches(root):
            n, adopted, _, _ = amended.get((root, v["sitting"]), (0, 0, "", None))
            out.append({"k": "vote", "d": v["date"][:10], "t": title(root), "root": root,
                        "url": f"glosowanie/{v['sitting']}-{v['votingNumber']}.html", "bill": root in bills,
                        "s": v.get("outcome") or "", "o": v.get("outcome_class") or "", "m": m,
                        "p": v["sitting"], "n": v["votingNumber"], "mo": v["motion"][0],
                        "c": [v.get("yes", 0), v.get("no", 0), v.get("abstain", 0)], "a": [n, adopted]})
    for (root, sitting), (n, adopted, day, first) in amended.items():
        if m := matches(root):
            url = f"ustawa/{root}.html#poprawki" if root in bills else f"glosowanie/{sitting}-{first['votingNumber']}.html"
            out.append({"k": "amend", "d": day, "t": title(root), "root": root, "url": url, "bill": root in bills,
                        "s": "", "o": "", "m": m, "p": sitting, "a": [n, adopted]})
    for root, p in procs.items():
        stages = [s for s in p.get("stages", [])
                  if s.get("depth") == 0 and s.get("name") in STAGES and (s.get("date") or "") >= since]
        if stages and (m := matches(root)):
            # a bill with no page here (no vote yet) links to its process on the Sejm's site
            url = f"ustawa/{root}.html" if root in bills else f"https://www.sejm.gov.pl/Sejm{TERM}.nsf/PrzebiegProc.xsp?nr={root}"
            for s in stages:
                out.append({"k": "stage", "d": s["date"], "t": p.get("title") or title(root), "root": root,
                            "url": url, "bill": root in bills, "s": s["name"], "o": "", "m": m,
                            **({"p": day_sitting[s["date"]]} if s["date"] in day_sitting else {})})
    if upcoming:
        day = upcoming["dates"][0]
        for g in upcoming.get("groups", []):
            for item in g["items"]:
                root = item.get("bill") or item.get("root")
                if root and (m := matches(root)):
                    out.append({"k": "agenda", "d": day, "t": f"{item.get('kind', '')} {item.get('rest', '')}".strip(),
                                "root": root, "url": f"nadchodzace-posiedzenie.html#punkt-{item['n']}", "bill": root in bills,
                                "s": "", "o": "", "m": m, "n": item["n"],
                                **({"p": upcoming["number"]} if upcoming.get("number") else {})})
    # one stage per bill and day (several on a day: the last is the furthest along)
    seen, kept = set(), []
    for e in sorted(out, key=lambda e: (e["d"], e["k"] != "stage"), reverse=True):
        key = (e["k"], e["root"], e["d"]) if e["k"] == "stage" else id(e)
        if key not in seen:
            seen.add(key)
            kept.append(e)
    return kept


def question_points(recent, older):
    """3 for five or more questions in the last MP_DAYS days, 2 for any, 1 for
    five or more older ones, else 0."""
    return 3 if recent >= 5 else 2 if recent else 1 if older >= 5 else 0


def suggested_mps(spec, mp_rows, committees, bills, today):
    """{interest id: [{"id", "score", "why": [reason]}]}, best first, for MPs in
    office: the best MP_PER_INTEREST and the best of each club not among them; a reason is {"k": "committee", "code", "fn"}, {"k": "questions",
    "n", "recent", "to"} or {"k": "bills", "n", "root"} (the latest bill)."""
    recent = (today - timedelta(days=MP_DAYS)).isoformat()
    roles = defaultdict(dict)   # mp -> {committee code: function}
    for c in committees:
        for m in c.get("members", []):
            roles[m["id"]][c["code"]] = m.get("function") or ""
    signed = defaultdict(list)   # mp -> [(date, root, tags)]
    for root, b in bills.items():
        for mp in b.get("mps", []):
            signed[mp].append((b.get("date") or "", root, b.get("tags", [])))

    out = {}
    for i in spec:
        ministers, rows = set(i["ministers"]), []
        for r in mp_rows:
            mp = r["mp"]
            if not mp.get("active", True):
                continue
            score, why = 0.0, []
            for code, fn in sorted(roles.get(mp["id"], {}).items()):
                if code in i["committees"]:
                    score += ROLES.get(fn, MEMBER)
                    why.append({"k": "committee", "code": code, "fn": fn})
            qs = [q for q in r.get("questions", []) if ministers & set(q.get("to", []))]
            if qs:
                n_recent = sum(1 for q in qs if (q.get("date") or "") >= recent)
                # in tiers, like a committee role, not one point a question: counted one by one,
                # questions (an opposition tool far more than a governing side's) outweighed everything
                score += question_points(n_recent, len(qs) - n_recent)
                to = sorted({t for q in qs for t in q["to"] if t in ministers})
                why.append({"k": "questions", "n": len(qs), "recent": n_recent, "to": to})
            mine = sorted((x for x in signed.get(mp["id"], []) if set(x[2]) & set(i["tags"])), reverse=True)
            if mine:
                score += min(3, len(mine))
                why.append({"k": "bills", "n": len(mine), "root": mine[0][1]})
            if score >= MP_MIN_SCORE:
                rows.append({"id": mp["id"], "score": round(score, 2), "why": why})
        rows.sort(key=lambda x: (-x["score"], x["id"]))
        # the best of every club too, so that the page can suggest one MP from each
        club = {r["mp"]["id"]: r["mp"].get("club") or "" for r in mp_rows}
        kept, clubs = rows[:MP_PER_INTEREST], {club[x["id"]] for x in rows[:MP_PER_INTEREST]}
        for x in rows[MP_PER_INTEREST:]:
            if club[x["id"]] not in clubs:
                clubs.add(club[x["id"]])
                kept.append(x)
        out[i["id"]] = kept
    return out


def build(ctx, procs, committees, spec=None, today=None, en=None):
    """dane/zainteresowania.json: the interests, the events and the MPs; `en`
    translates a status (vote outcome, stage) for the English pages."""
    spec = load() if spec is None else spec
    today = today or date.today()
    bills = {b["root"]: {"title": b["title"], "tags": b.get("tags", []), "date": b.get("last") or "",
                         "mps": ((b.get("author") or {}).get("mps") or [])} for b in ctx["bills"]}
    names = ctx.get("committee_names", {})
    mps = {r["mp"]["id"]: r["mp"] for r in ctx["mp_rows"]}
    suggested = suggested_mps(spec, ctx["mp_rows"], committees, bills, today)
    found = events(spec, bills, ctx["by_id"], procs, ctx.get("upcoming"), today)
    for e in found:
        e["se"] = en(e["s"]) if en and e["s"] else e["s"]
    # the days of the sittings events name, for the page's headings
    days = defaultdict(set)
    for v in ctx["by_id"].values():
        days[v["sitting"]].add(v["date"][:10])
    if (u := ctx.get("upcoming")) and u.get("number"):
        days[u["number"]].update(u["dates"])
    return {
        "generated": today.isoformat(), "days": DAYS,
        "interests": [{"id": i["id"], "pl": i["pl"], "en": i["en"]} for i in spec],
        "committees": {c: names.get(c, c) for i in spec for c in i["committees"]},
        "events": found,
        "sittings": {p: [min(days[p]), max(days[p])] for p in sorted({e["p"] for e in found if "p" in e})},
        "upcoming": u["number"] if (u := ctx.get("upcoming")) and not u.get("under_way") else None,
        "mps": {mid: {"name": mps[mid]["firstLastName"], "club": mps[mid].get("club") or "",
                      "district": mps[mid].get("districtName") or "", "districtNum": mps[mid].get("districtNum")}
                for rows in suggested.values() for mid in (x["id"] for x in rows)},
        "bills": {x["root"]: bills[x["root"]]["title"] for rows in suggested.values() for y in rows
                  for x in y["why"] if x["k"] == "bills" and x["root"] in bills},
        "suggested": suggested,
    }
