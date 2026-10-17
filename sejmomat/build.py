"""Render the static site from data/ into site/."""
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import cache

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import agenda, analysis, authors, committees, questions, social, speeches
from .stamp import stamp
from .config import DATA, ROOT, SITE, SITE_URL, STATIC, TEMPLATES, TERM
from .i18n import LANGS, date_fmt, pct_fmt, translator
from .acts import bill_changes
from .api_out import write_api
from .model import anchor, law_source, load, print_meta, print_paragraphs, print_text, print_too_big, source_items

VOTE_LABEL = {"Y": "za", "N": "przeciw", "A": "wstrzymał(a) się", "X": "nie głosował(a)"}
LINE_LABEL = {"Y": "za", "N": "przeciw", "A": "wstrzymanie się"}
MAJORITY_LABEL = {
    "SIMPLE_MAJORITY": "zwykła większość",
    "ABSOLUTE_MAJORITY": "bezwzględna większość",
    "ABSOLUTE_STATUTORY_MAJORITY": "bezwzględna większość ustawowej liczby posłów",
    "MAJORITY_THREE_FIFTHS": "większość 3/5",
    "STATUTORY_MAJORITY": "większość ustawowej liczby posłów",
}
KIND_LABEL = {"amendment": "Poprawka", "minority": "Wniosek mniejszości", "senate": "Poprawka Senatu"}


# Votes on motions where "for" does not mean "for the bill": an explanation
# and outcome wording per kind. Patterns are matched against the lowercased topic.
MOTIONS = [
    ("reject_info", r"odrzuceni\w* (informacji|sprawozdania|dokumentu)",
     "Głosowanie nad wnioskiem o odrzucenie informacji lub sprawozdania: „za” oznacza odrzucenie dokumentu, „przeciw” — jego przyjęcie do wiadomości.",
     ("Wniosek przyjęty — dokument odrzucony", "Wniosek odrzucony — dokument nie został odrzucony")),
    ("reject_bill", r"odrzuceni\w*|wniosek o odrzucenie",
     "Głosowanie nad wnioskiem o odrzucenie projektu: „za” oznacza odrzucenie projektu i koniec prac nad nim, „przeciw” — że projekt trafia do dalszych prac.",
     ("Wniosek przyjęty — projekt odrzucony", "Wniosek odrzucony — projekt trafia do dalszych prac")),
    ("no_confidence", r"wotum nieufności",
     "Głosowanie nad wotum nieufności: „za” oznacza poparcie dla odwołania. Konstruktywne wotum nieufności wobec rządu wymaga większości ustawowej liczby posłów (231 głosów).",
     ("Wotum nieufności uchwalone", "Wotum nieufności nieuchwalone")),
    ("confidence", r"wotum zaufania",
     "Głosowanie nad wotum zaufania: „za” oznacza poparcie dla rządu.",
     ("Wotum zaufania udzielone", "Wotum zaufania nieudzielone")),
    ("skip_committee", r"bez (kierowania|odsyłania)|niezwłoczne przystąpienie|przejście do drugiego czytania",
     "Głosowanie nad wnioskiem o przyspieszenie prac: „za” oznacza, że projekt od razu przechodzi do kolejnego etapu bez prac w komisji.",
     ("Wniosek przyjęty — bez kierowania do komisji", "Wniosek odrzucony")),
    ("adjourn", r"wniosek o (przerwę|odroczenie posiedzenia|zamknięcie posiedzenia)",
     "Wniosek formalny o przerwę, odroczenie lub zamknięcie posiedzenia: „za” oznacza przerwanie obrad.",
     ("Wniosek przyjęty", "Wniosek odrzucony")),
    ("final", r"całością projektu",
     "Głosowanie nad całością projektu: „za” oznacza uchwalenie ustawy lub uchwały w całości. Uchwalona ustawa trafia następnie do Senatu.",
     ("Projekt przyjęty", "Projekt odrzucony")),
]


def motion(v):
    """(kind, note, (outcome if passed, outcome if not)) or None."""
    if v["amendments"]:
        return None
    topic = (v.get("topic") or "").lower()
    if v["senate"] and "odrzuc" in topic:
        return ("reject_senate",
                "Senat zaproponował odrzucenie ustawy. „Za” oznacza odrzucenie uchwały Senatu — ustawa zostaje przyjęta; "
                "potrzebna jest bezwzględna większość. W przeciwnym razie ustawa upada.",
                ("Uchwała Senatu odrzucona — ustawa przyjęta", "Uchwała Senatu utrzymana — ustawa odrzucona"))
    for kind, pattern, note, outcomes in MOTIONS:
        if re.search(pattern, topic):
            return kind, note, outcomes
    return None


def outcome(v):
    """Human-readable result, phrased for what was actually decided."""
    if m := motion(v):
        return (m[2][0], "adopted") if v["passed"] else (m[2][1], "rejected")
    if v["senate"] and v["amendments"]:
        # The Sejm votes on *rejecting* a Senate amendment, which needs an
        # absolute majority; otherwise the amendment stands.
        return ("Poprawka Senatu odrzucona", "rejected") if v["passed"] else ("Poprawka Senatu przyjęta", "adopted")
    if v["amendments"]:
        minority = all(a["kind"] == "minority" for a in v["amendments"])
        plural = len(v["amendments"]) > 1
        noun, yes, no = {
            (False, False): ("Poprawka", "przyjęta", "odrzucona"),
            (False, True): ("Poprawki", "przyjęte", "odrzucone"),
            (True, False): ("Wniosek mniejszości", "przyjęty", "odrzucony"),
            (True, True): ("Wnioski mniejszości", "przyjęte", "odrzucone"),
        }[(minority, plural)]
        return (f"{noun} {yes}", "adopted") if v["passed"] else (f"{noun} {no}", "rejected")
    return ("Przyjęto", "adopted") if v["passed"] else ("Odrzucono", "rejected")


def against_recommendation(v):
    """True when the Sejm's decision differs from the committee's recommendation."""
    recs = {a["item"]["recommendation"] for a in v["amendments"] if a["item"] and a["item"]["recommendation"]}
    if len(recs) != 1:
        return False
    adopted = outcome(v)[1] == "adopted"
    return adopted != (recs.pop() == "przyjąć")


def print_url(num):
    """Official page of a print on sejm.gov.pl."""
    return f"https://www.sejm.gov.pl/Sejm{TERM}.nsf/druk.xsp?nr={num}"


def act_url(eli):
    """ISAP page of a Dziennik Ustaw position ("DU/2026/524")."""
    _, year, pos = eli.split("/")
    return f"https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU{year}{int(pos):07d}"


def pdf_url(num, attachment):
    return f"https://api.sejm.gov.pl/sejm/term{TERM}/prints/{num}/{attachment}"


def build_context():
    mps, clubs, sittings = load()
    stats = analysis.mp_stats(sittings)

    by_id = {(v["sitting"], v["votingNumber"]): v for vs in sittings.values() for v in vs}
    mp_ids = _mp_name_index(mps)
    bills = defaultdict(list)
    for s, votings in sittings.items():
        for v in votings:
            v["outcome"], v["outcome_class"] = outcome(v)
            v["motion"] = motion(v)
            v["proposer"] = proposer(v, mp_ids) if v["amendments"] else None
            v["against_rec"] = against_recommendation(v)
            if v["bill"]:
                bills[v["bill"]].append(v)

    # Club membership history from the club recorded with each ballot.
    history = defaultdict(list)  # mp -> [{"club", "from", "to", "votes"}]
    for v in sorted(by_id.values(), key=lambda v: (v["date"], v["votingNumber"])):
        for club, groups in v["ballots"].items():
            for ids in groups.values():
                for mp in ids:
                    h = history[mp]
                    if h and h[-1]["club"] == club:
                        h[-1]["to"] = v["date"]
                        h[-1]["votes"] += 1
                    else:
                        h.append({"club": club, "from": v["date"], "to": v["date"], "votes": 1})
    transfers = Counter(
        (a["club"], b["club"]) for h in history.values() for a, b in zip(h, h[1:])
    )
    # A whole club changing its id at once (PSL -> PSL-TD) is a rename or
    # reorganisation, not MPs switching sides: the old id is gone at the vote
    # where its members first appear under the new one. A group leaving a club
    # that carries on (PiS -> RozwojPlus) is a real switch.
    clubs_at = defaultdict(set)
    for v in by_id.values():
        clubs_at[v["date"]].update(v["ballots"])
    moved_at = defaultdict(Counter)
    for h in history.values():
        for a, b in zip(h, h[1:]):
            moved_at[(a["club"], b["club"])][b["from"]] += 1
    renames = {
        (old_id, new_id) for (old_id, new_id), dates in moved_at.items()
        if (when := dates.most_common(1)[0])[1] >= 5 and old_id not in clubs_at[when[0]]
    }
    for h in history.values():
        for a, b in zip(h, h[1:]):
            b["rename"] = (a["club"], b["club"]) in renames

    signed = defaultdict(list)
    for v in by_id.values():
        for mp in (v["proposer"] or {}).get("mps", []):
            signed[mp].append(v)

    mp_rows = []
    for mp_id, st in stats.items():
        m = mps.get(mp_id, {"id": mp_id, "firstLastName": f"Poseł #{mp_id}", "club": "?"})
        mp_rows.append({
            "mp": m, "eligible": st["eligible"], "cast": st["cast"],
            "turnout": st["cast"] / st["eligible"] if st["eligible"] else 0,
            "rebellions": st["rebellions"], "rebel_count": len(st["rebellions"]),
            "signed": sorted(signed.get(mp_id, []), key=lambda v: v["date"], reverse=True),
            "signed_adopted": sum(1 for v in signed.get(mp_id, []) if v["outcome_class"] == "adopted"),
            "rebel_rate": len(st["rebellions"]) / st["with_line"] if st["with_line"] else 0,
            "clubs": sorted(st["clubs"]),
            "history": history.get(mp_id, []),
            # newest first: {"sitting", "Y", "N", "A", "X", "rebel", "total"}
            "sittings": [{"sitting": s, **{k: c[k] for k in ("Y", "N", "A", "X", "rebel")},
                          "total": c["Y"] + c["N"] + c["A"] + c["X"]}
                         for s, c in sorted(st["sittings"].items(), reverse=True)],
            "switches": sum(1 for h in history.get(mp_id, [])[1:] if not h.get("rename")),
        })
    mp_rows.sort(key=lambda r: r["mp"]["firstLastName"].split()[-1])

    sign_index = authors.name_index(mps)
    bill_rows = []
    for root, votings in bills.items():
        meta = print_meta(root) or {}
        amend_votes = [v for v in votings if v["amendments"]]
        by_author = defaultdict(Counter)
        for v in amend_votes:
            for club in v["proposer"]["clubs"]:
                by_author[club][v["outcome_class"]] += 1
        prints = sorted({p for v in votings for p in v["prints"]}, key=lambda p: (len(p), p))
        src = law_source(root, prints)
        bill_rows.append({
            "author": authors.bill_author(meta.get("title"), print_text(root), meta.get("documentDate"),
                                          sign_index, history),
            "law_source": src, "law": bill_changes(print_text(src)) if src else [],
            "root": root, "title": meta.get("title") or votings[0]["agenda"],
            "votings": votings, "amend_count": len(amend_votes),
            "last": max(v["date"] for v in votings),
            "prints": sorted({p for v in votings for p in v["prints"]}, key=lambda p: (len(p), p)),
            # name as tie-break: club sets iterate in a different order each run
            "by_author": sorted(by_author.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])),
        })
    bill_rows.sort(key=lambda b: b["last"], reverse=True)

    club_rows = build_clubs(clubs, mps, by_id, mp_rows)
    adopted, proposers, mp_proposers = build_adopted(by_id)
    bill_by_root = {b["root"]: b for b in bill_rows}
    # government bills: their number and page at the Government Legislation Centre
    rcl_path = DATA / "rcl.json"
    rcl = json.loads(rcl_path.read_text(encoding="utf-8")) if rcl_path.exists() else {}
    for b in bill_rows:
        b["rcl"] = rcl.get(b["root"])

    # Speeches in the chamber. Figures and word clouds go into the MP, club
    # and bill pages; the lists and texts into dane/wystapienia/ (per MP) and
    # dane/debaty/ (per bill), loaded when asked for. Each speech on a bill
    # links to the vote that settled the bill at that sitting.
    def bill_of_print(num):
        root = ((print_meta(num) or {}).get("processPrint") or [num])[0]
        return root if root in bill_by_root else None
    en = translator("en")
    settled_at = {}
    for root, b in bill_by_root.items():
        for v in b["votings"]:
            kind = v["motion"][0] if v["motion"] else None
            rank = (kind == "final", kind in ("reject_bill", "reject_senate"), v["votingNumber"])
            key = (root, v["sitting"])
            if key not in settled_at or rank > settled_at[key][0]:
                settled_at[key] = (rank, {"s": v["sitting"], "n": v["votingNumber"], "o": v["outcome_class"],
                                          "l": [v["outcome"], en(v["outcome"])], "yes": v["yes"], "no": v["no"]})
    vote_for = lambda bill, sitting: (settled_at.get((bill, sitting)) or (None, None))[1]

    def club_at(mp, day):
        """The MP's club on that day, from the clubs recorded with their votes."""
        spells = history.get(mp) or []
        for h in spells:
            if h["from"][:10] <= day <= h["to"][:10]:
                return h["club"]
        before = [h for h in spells if h["from"][:10] <= day]  # between two votes: the club of the earlier one
        return (before[-1] if before else spells[0])["club"] if spells else None

    days = speeches.load()
    speeches_by_mp = speeches.by_mp(days, bill_of_print, vote_for)
    speeches_by_bill = speeches.by_bill(days, bill_of_print, vote_for, club_at)
    vocabulary = speeches.Vocabulary(st["text"] for d in days for st in d["statements"])
    del days

    def speech_figures(items):
        return {
            "spoken": sum(1 for x in items if not x["unspoken"]), "written": sum(1 for x in items if x["unspoken"]),
            "seconds": sum(x["seconds"] or 0 for x in items),
            "topics": Counter((x["topic"], x["bill"]) for x in items if x["topic"] != "—").most_common(5),
        }
    # a club's own name says nothing about what it talks about ("Razem" even
    # came out as "raz"), so it is left out of its cloud and its MPs' clouds
    def club_words(club):
        return re.findall(r"[^\W_]+", f"{club} {clubs.get(club, '')}")

    by_club = defaultdict(list)
    for r in mp_rows:
        mine = speeches_by_mp.get(r["mp"]["id"], [])
        own = (r["mp"].get("firstLastName") or "").split()
        own += [w for club in {h["club"] for h in r["history"]} | {r["mp"].get("club") or ""} for w in club_words(club)]
        r["speeches"] = {**speech_figures(mine), "cloud": vocabulary.cloud([x["text"] for x in mine], exclude=own)}
        for x in mine:
            by_club[club_at(r["mp"]["id"], x["date"])].append((r["mp"]["id"], x))
    for c in club_rows:
        mine = by_club.get(c["id"], [])
        speakers = Counter(mp for mp, _ in mine)
        c["speeches"] = {**speech_figures([x for _, x in mine]),
                         "speakers": speakers.most_common(10),
                         "cloud": vocabulary.cloud([x["text"] for _, x in mine], min_count=10, min_texts=5,
                                                   exclude=club_words(c["id"]))}
    for root, items in speeches_by_bill.items():
        bill_by_root[root]["speeches"] = {
            "count": len(items), "others": sum(1 for x in items if not x["mp"]),
            "by_club": Counter(x["club"] for x in items if x["mp"]).most_common()}
    questions_summary = build_questions(mp_rows, club_rows, club_at)
    all_amendments = [v for v in sorted(by_id.values(), key=lambda v: (v["date"], v["votingNumber"]), reverse=True)
                      if v["amendments"]]

    # Latest sitting: figures and the bills decided as a whole (no amendment votes).
    last_sitting = max(sittings)
    last_votes = sittings[last_sitting]
    whole = [v for v in last_votes if v["motion"] and v["motion"][0] in ("final", "reject_bill", "reject_senate")]
    decided_bills = {}
    for v in whole:  # the last vote on the whole bill is the one that settled it
        decided_bills[v["bill"] or v["agenda"]] = v
    latest = {
        "sitting": last_sitting, "votes": last_votes,
        "amendment_votes": [v for v in last_votes if v["amendments"]],
        "adopted_amendments": sum(1 for v in last_votes if v["amendments"] and v["outcome_class"] == "adopted"),
        "against_rec": [v for v in last_votes if v["against_rec"]],
        "bills": [{"v": v, "bill": bill_by_root.get(v["bill"]),
                   "amendment_votes": sum(1 for x in last_votes if x["amendments"] and x["bill"] == v["bill"] and v["bill"])}
                  for v in sorted(decided_bills.values(), key=lambda v: v["votingNumber"])],
    }
    latest["passed"] = sum(1 for b in latest["bills"] if b["v"]["motion"][0] == "final" and b["v"]["passed"])

    # Every amendment vote (adopted or not) by proposer, newest first.
    by_proposer = defaultdict(list)
    for v in sorted(by_id.values(), key=lambda v: (v["date"], v["votingNumber"]), reverse=True):
        if v["amendments"]:
            for club in sorted(v["proposer"]["clubs"]):
                by_proposer[club].append(v)

    # Prints: which votings cite them, and which voting decided each item.
    votes_by_print, decided, sources = defaultdict(list), defaultdict(list), {}
    for v in by_id.values():
        for p in v["prints"]:
            votes_by_print[p].append(v)
        for a in v["amendments"]:
            if a["source"]:
                sources.setdefault(a["source"], {}).setdefault(a["kind"], a["report"])
                decided[(a["source"], anchor(a["kind"], a["number"]))].append(v)
    printed = sorted(
        (p.stem for p in (DATA / "prints").glob("*.json") if not p.stem.startswith("_") and "." not in p.stem),
        key=lambda n: (int(n.split("-")[0]), n),
    )

    # The next sitting's agenda, its items linked to bills, prints and the
    # MPs who present them.
    upcoming, planned = agenda.upcoming()
    if upcoming:
        mp_ids = {r["mp"]["firstLastName"]: r["mp"]["id"] for r in mp_rows}
        name_re = re.compile("|".join(map(re.escape, sorted(mp_ids, key=len, reverse=True))))
        for g in upcoming["groups"]:
            for item in g["items"]:
                item["bill"] = next((b for b in map(bill_of_print, item["prints"]) if b), None)
                # each note as pieces: (text, MP id when the text is an MP's name)
                item["notes"] = [[(part, mp_ids.get(part)) for part in re.split(f"({name_re.pattern})", note) if part]
                                 for note in item["notes"]]

    committee_rows = build_committees(mp_rows, bill_of_print, bill_by_root)

    linked = sum(1 for v in by_id.values() for a in v["amendments"] if a["item"])
    total = sum(1 for v in by_id.values() for a in v["amendments"])
    return {
        "mps": mps, "clubs": clubs, "sittings": sittings, "by_id": by_id,
        "mp_rows": mp_rows, "mp_by_id": {r["mp"]["id"]: r for r in mp_rows},
        "club_rows": club_rows, "club_slug": club_slug,
        "adopted": adopted, "proposers": proposers, "mp_proposers": mp_proposers,
        "by_proposer": by_proposer,
        "all_amendments": all_amendments, "latest": latest,
        "transfers": [(pair, n, pair in renames) for pair, n in transfers.most_common()],
        "bills": bill_rows, "bill_by_root": bill_by_root, "speeches_by_mp": speeches_by_mp,
        "speeches_by_bill": speeches_by_bill,
        "coverage": (linked, total),
        "summaries": social.summaries({"by_id": by_id, "bill_by_root": bill_by_root}),
        "printed": set(printed), "printed_list": printed, "upcoming": upcoming, "planned": planned,
        "committee_rows": committee_rows, "questions_summary": questions_summary, "committee_names": {c["code"]: c["name"] for c in committee_rows},
        "votes_by_print": votes_by_print, "decided": decided, "sources": sources,
        "generated": datetime.now(),
    }


# Club names as written in reports ("KP Koalicja Obywatelska", "KP PSL –
# Trzecia Droga") -> club ids used in voting records. Order matters.
CLUB_ALIASES = [
    (r"Polska\s*2050\W*Trzecia", "Polska2050-TD"),
    (r"Polska\s*2050", "Polska2050"),
    (r"PSL", "PSL-TD"),
    (r"\bKO\b|Koalicj\w* Obywatelsk", "KO"),
    (r"PiS|Prawo i Sprawiedliwość", "PiS"),
    (r"Lewic", "Lewica"),
    (r"Konfederacj[a-ząę]*\s*Koron", "Konfederacja_KP"),
    (r"Konfederacj", "Konfederacja"),
    (r"Razem", "Razem"),
    (r"Centrum", "Centrum"),
    (r"Rozw[oó]j", "RozwojPlus"),
    (r"Demokracj", "Demokracja"),
    (r"Kukiz", "Kukiz15"),
    (r"Republikan", "Republikanie"),
]
_MP_NAME_RE = re.compile(r"([A-ZĄĆĘŁŃÓŚŹŻ])\.\s*(?:[A-ZĄĆĘŁŃÓŚŹŻ]\.\s*)*([A-ZĄĆĘŁŃÓŚŹŻ][\w-]+)")


def _mp_name_index(mps):
    """(first initial, surname part) -> [MP ids], for resolving "poseł M. Horała".

    Every capitalised part after the first name is indexed, so compound
    surnames ("Wojciechowska van Heukelom", "Dąbkowska-Banaszek") resolve.
    """
    index = defaultdict(list)
    for m in mps.values():
        parts = (m.get("firstLastName") or "").split()
        for part in parts[1:]:
            if part[:1].isupper():
                index[(parts[0][0], part)].append(m["id"])
    return index


def _club_at(v, mp_id):
    return next((c for c, groups in v["ballots"].items() if any(mp_id in ids for ids in groups.values())), None)


def proposer(v, mp_ids):
    """Who proposed what a voting decided, from the signatories of every
    amendment it covers: {"label", "clubs": set, "mps": [ids]}.

    Clubs are written as such ("KP PiS") or derived from the MPs who signed
    (minority motions), using each MP's club at the time of the vote.
    """
    if v["senate"]:
        return {"label": "Senat", "clubs": {"Senat"}, "mps": []}
    authors = [x for a in v["amendments"] if a["item"] for x in a["item"]["authors"]]
    if not authors:
        return {"label": "(nieustalony)", "clubs": {"(nieustalony)"}, "mps": []}
    clubs, mps, other = set(), [], []
    for piece in re.split(r",\s*", ", ".join(authors)):
        club = None
        if re.match(r"(KP|KKP|KK|Koło|Klub)\b", piece):
            club = next((cid for pat, cid in CLUB_ALIASES if re.search(pat, piece)), None)
        elif m := _MP_NAME_RE.search(piece):
            candidates = mp_ids.get((m[1], m[2]), [])
            # prefer the namesake who took part in this vote
            present = [i for i in candidates if _club_at(v, i)]
            mp = (present or candidates or [None])[0]
            if mp is not None:
                if mp not in mps:
                    mps.append(mp)
                club = _club_at(v, mp)
        if club:
            clubs.add(club)
        elif piece.strip() and piece.strip() not in other:
            other.append(piece.strip())
    if not clubs:
        # unresolved: keep the text, e.g. "Rada Ministrów" (leftovers next to
        # resolved clubs are fragments of comma-containing club names)
        clubs = {", ".join(other) or ", ".join(dict.fromkeys(authors))}
    return {"label": " + ".join(sorted(clubs)), "clubs": clubs, "mps": mps}


def build_adopted(by_id):
    """(adopted amendment votings newest first, per-proposer tallies, per-MP tallies).

    Each club among a voting's proposers is credited once for that voting,
    so joint proposals count for every club involved.
    """
    adopted, tally, mp_tally = [], defaultdict(Counter), defaultdict(Counter)
    for v in sorted(by_id.values(), key=lambda v: v["date"], reverse=True):
        if not v["amendments"]:
            continue
        who = v["proposer"]
        for club in who["clubs"]:
            tally[club][v["outcome_class"]] += 1
        for mp in who["mps"]:
            mp_tally[mp][v["outcome_class"]] += 1
        if v["outcome_class"] == "adopted":
            adopted.append({"v": v, "proposer": who["label"]})
    def rows(t):
        return sorted(
            ({"name": k, "adopted": c["adopted"], "voted": c["adopted"] + c["rejected"]} for k, c in t.items()),
            key=lambda r: (r["name"] == "(nieustalony)", -r["voted"], str(r["name"])),
        )
    return adopted, rows(tally), rows(mp_tally)


def groupby_consecutive(items, attr):
    """Like groupby, but only merges neighbours (agenda items recur in a sitting)."""
    out = []
    for it in items:
        key = it.get(attr)
        if out and out[-1][0] == key:
            out[-1][1].append(it)
        else:
            out.append((key, [it]))
    return out


def club_slug(club):
    return re.sub(r"[^\w-]", "", club) or "klub"


ANSWER_DAYS = 21   # a minister's deadline for answering an interpellation or a written question
QUESTIONS_SHOWN = 100   # on an MP's page; the rest load on request


def build_questions(mp_rows, club_rows, club_at):
    """Interpellations and written questions: each MP's (co-signed ones count
    for every signer), each club's (by the MP's club on the day), and how each
    recipient (minister) answers. Adds "questions" and "q_stats" to MP rows
    and "questions" to club rows; returns the term's summary."""
    data = questions.load()
    today = date.today()
    by_id = {r["mp"]["id"]: r for r in mp_rows}
    for r in mp_rows:
        r["questions"] = []
    clubs = defaultdict(lambda: {"int": 0, "zap": 0, "askers": Counter(), "to": Counter()})
    recipients = defaultdict(lambda: {"received": 0, "answered": 0, "days": [], "late": 0, "prolonged": 0, "overdue": 0})
    items = []
    for kind, short in questions.KINDS.items():
        for q in data.get(kind, []):
            when = q["sent"] or q["received"]
            ok = questions.answered(q)
            item = {"kind": short, "num": q["num"], "title": q["title"], "to": q["to"], "date": when,
                    "cosigned": len(q["from"]) > 1,
                    "answered": ok, "days": questions.days_to_answer(q), "web": q["web"],
                    "late": any(v > 0 for v in q["late"].values()),
                    "prolonged": any(r["prolongation"] for r in q["replies"]),
                    # no answer, and the deadline is past
                    "overdue": not ok and bool(when) and (today - date.fromisoformat(when)).days > ANSWER_DAYS}
            items.append(item)
            for mp in q["from"]:
                if mp in by_id:
                    by_id[mp]["questions"].append(item)
            for club in {club_at(mp, when) for mp in q["from"] if when} - {None}:
                clubs[club][short] += 1
                clubs[club]["to"].update(q["to"])
                clubs[club]["askers"].update(mp for mp in q["from"] if club_at(mp, when) == club)
            for name in q["to"]:
                t = recipients[name]
                t["received"] += 1
                t["answered"] += ok
                if item["days"] is not None:
                    t["days"].append(item["days"])
                t["late"] += q["late"].get(name, 0) > 0
                t["prolonged"] += item["prolonged"]
                t["overdue"] += item["overdue"]

    def median(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else None

    for r in mp_rows:
        mine = sorted(r["questions"], key=lambda i: (i["date"] or "", i["num"]), reverse=True)
        r["questions"] = mine
        r["q_stats"] = {"int": sum(1 for i in mine if i["kind"] == "int"), "zap": sum(1 for i in mine if i["kind"] == "zap"),
                        "answered": sum(1 for i in mine if i["answered"]), "late": sum(1 for i in mine if i["late"]),
                        "overdue": sum(1 for i in mine if i["overdue"]),
                        "sole": sum(1 for i in mine if not i["cosigned"]),
                        "median": median([i["days"] for i in mine if i["days"] is not None])}
    # where each MP stands: rank by how many questions (ties share a rank), and the middle MP
    totals = sorted((len(r["questions"]) for r in mp_rows), reverse=True)
    first_at = {}
    for place, n in enumerate(totals, 1):
        first_at.setdefault(n, place)
    for r in mp_rows:
        r["q_stats"]["rank"] = first_at[len(r["questions"])]
    mp_median = median(totals)
    for c in club_rows:
        q = clubs.get(c["id"])
        c["questions"] = q and {"int": q["int"], "zap": q["zap"],
                                "askers": [(by_id[mp], n) for mp, n in q["askers"].most_common(10) if mp in by_id],
                                "to": q["to"].most_common(8)}
    return {
        "int": sum(1 for i in items if i["kind"] == "int"), "zap": sum(1 for i in items if i["kind"] == "zap"),
        "answered": sum(1 for i in items if i["answered"]), "total": len(items),
        "late": sum(1 for i in items if i["late"]), "overdue": sum(1 for i in items if i["overdue"]),
        "median": median([i["days"] for i in items if i["days"] is not None]),
        "recipients": sorted(({"name": n, **t, "median": median(t["days"])} for n, t in recipients.items()),
                             key=lambda t: -t["received"]),
        "clubs": sorted(((c, clubs[c["id"]]["int"], clubs[c["id"]]["zap"]) for c in club_rows if c["id"] in clubs),
                        key=lambda x: -(x[1] + x[2])),
        "top": sorted(mp_rows, key=lambda r: -(r["q_stats"]["int"] + r["q_stats"]["zap"]))[:20],
        "deadline": ANSWER_DAYS, "mp_median": mp_median, "mps": len(mp_rows),
        "none": sum(1 for r in mp_rows if not r["questions"]),
    }


COMMITTEE_TYPE = {"STANDING": "stała", "EXTRAORDINARY": "nadzwyczajna", "INVESTIGATIVE": "śledcza"}


def build_committees(mp_rows, bill_of_print, bill_by_root):
    """Committees with their members (chairs first), meetings held (newest
    first) and planned, and the bills discussed. Adds "committees" to every MP
    row and "committee_meetings" to the bills discussed in committee."""
    path = DATA / "committees.json"
    listed = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    meetings = committees.load()
    names = {c["code"]: c["name"] for c in listed}
    by_id = {r["mp"]["id"]: r for r in mp_rows}
    for r in mp_rows:
        r["committees"] = []

    def rank(function):
        f = function or ""
        return 0 if f.startswith("przewodnicz") else 1 if f.startswith("zastęp") else 2

    rows, seen = [], {}
    for c in listed:
        code, ms = c["code"], meetings.get(c["code"], [])
        for m in ms:
            # each line's bills, so a bill's page can quote the line about it
            m["bill_lines"] = {}
            for _, text in m["agenda"]:
                for group in committees._PRINTS_RE.findall(text):
                    for num in re.findall(r"\d+(?:-[A-Z])?", group):
                        bill = bill_of_print(num)
                        if bill:
                            m["bill_lines"].setdefault(bill, text)
        members = sorted(((by_id[x["id"]], x["function"]) for x in c["members"] if x["id"] in by_id),
                         key=lambda rf: (rank(rf[1]), rf[0]["mp"]["firstLastName"].split()[-1]))
        for r, function in members:
            r["committees"].append({"code": code, "name": c["name"], "function": function})
        held = [m for m in reversed(ms) if m["status"] == "FINISHED"]
        bills = Counter(b for m in held for b in m["bill_lines"])
        rows.append({"code": code, "name": c["name"], "type": COMMITTEE_TYPE.get(c["type"], c["type"]),
                     "members": members, "held": held, "planned": sorted((m for m in ms if m["status"] != "FINISHED"), key=lambda m: (m["date"], m["start"] or "")),
                     "bills": [(bill_by_root[b], n) for b, n in bills.most_common()]})
        # a joint meeting is listed under every committee; on a bill's page once
        for m in held:
            key = (m["date"], m["start"], frozenset([code, *m["joint"]]))
            for b in m["bill_lines"]:
                if (b, key) not in seen:
                    seen[(b, key)] = True
                    bill_by_root[b].setdefault("committee_meetings", []).append((code, m))
    for b in bill_by_root.values():
        b.get("committee_meetings", []).sort(key=lambda cm: (cm[1]["date"], cm[1]["start"] or ""), reverse=True)
    for r in mp_rows:
        r["committees"].sort(key=lambda x: (rank(x["function"]), x["name"]))
    rows.sort(key=lambda c: ({"stała": 0, "nadzwyczajna": 1, "śledcza": 2}.get(c["type"], 3), c["name"]))
    return rows


def build_clubs(clubs, mps, by_id, mp_rows):
    """Per-club cohesion, effectiveness, agreement with other clubs, members."""
    stats = defaultdict(lambda: {"votes": 0, "shares": [], "split": [], "rebellions": 0,
                                 "decided": 0, "won": 0, "first": None, "last": None,
                                 "sittings": defaultdict(Counter)})
    agree = defaultdict(Counter)  # (a, b) -> {"same": n, "both": n}
    for v in sorted(by_id.values(), key=lambda v: v["date"]):
        lines = {}
        for club, c in v["clubs"].items():
            if club in analysis.NO_CLUB:
                continue
            st = stats[club]
            st["votes"] += 1
            st["first"] = st["first"] or v["date"]
            st["last"] = v["date"]
            voted = c["Y"] + c["N"] + c["A"]
            # per sitting: votes, the club's line in them, ballots cast and not cast
            here = st["sittings"][v["sitting"]]
            here.update({"votes": 1, "cast": voted, "X": c["X"], "rebels": len(c["rebels"])})
            if voted >= analysis.MIN_CLUB_VOTERS:
                st["shares"].append(c["share"])
                here[c["line"] or "split"] += 1
                if not c["line"]:
                    st["split"].append(v)
            st["rebellions"] += len(c["rebels"])
            if c["line"] in ("Y", "N"):
                st["decided"] += 1
                st["won"] += (c["line"] == "Y") == v["passed"]
            if c["line"]:
                lines[club] = c["line"]
        for a in lines:
            for b in lines:
                if a != b:
                    agree[(a, b)]["both"] += 1
                    agree[(a, b)]["same"] += lines[a] == lines[b]
    rows = []
    for club, st in stats.items():
        others = sorted(
            ({"club": b, "rate": c["same"] / c["both"], "both": c["both"]}
             for (a, b), c in agree.items() if a == club and c["both"] >= 20),
            key=lambda x: -x["rate"],
        )
        members = sorted(
            (r for r in mp_rows if r["mp"].get("club") == club and r["mp"].get("active")),
            key=lambda r: r["mp"]["firstLastName"].split()[-1],
        )
        # MPs who voted as members of the club but are not in it now
        current = {id(r) for r in members}
        former = sorted(
            (r for r in mp_rows if id(r) not in current and any(h["club"] == club for h in r["history"])),
            key=lambda r: r["mp"]["firstLastName"].split()[-1],
        )
        rows.append({
            "id": club, "slug": club_slug(club), "name": clubs.get(club, club),
            "votes": st["votes"], "first": st["first"], "last": st["last"],
            "cohesion": sum(st["shares"]) / len(st["shares"]) if st["shares"] else 0,
            "split": st["split"], "rebellions": st["rebellions"],
            "effectiveness": st["won"] / st["decided"] if st["decided"] else 0,
            "agreement": others, "members": members, "former": former,
            # newest first: {"sitting", "votes", "Y", "N", "A", "split", "cast", "X", "rebels"}
            "sittings": [{"sitting": s, **{k: c[k] for k in ("votes", "Y", "N", "A", "split", "cast", "X", "rebels")}}
                         for s, c in sorted(st["sittings"].items(), reverse=True)],
            "current": club in clubs,
        })
    rows.sort(key=lambda r: (not r["current"], -len(r["members"]), r["id"]))
    return rows


def sitting_name(lang):
    def name(n, long=False):
        if lang == "pl":
            return f"{n}. posiedzenie Sejmu" if long else f"{n}. posiedzenie"
        return f"Sejm sitting {n}" if long else f"Sitting {n}"
    return name


def asset_version():
    """Content version of the shared stylesheet and script.

    Pages load them as "static/app.js?v=<this>". The host's CDN keeps scripts
    and styles for a while (and once kept them for a week), so without a
    version in the address visitors could get an old script long after a
    deploy. Changing either file changes the address in every page.
    """
    digest = hashlib.sha256()
    for name in ("style.css", "app.js"):
        digest.update((STATIC / name).read_bytes())
    return digest.hexdigest()[:10]


@cache
def static_version(name):
    """Content version of one script in static/ that only some pages load
    ("static/breakdown.js?v=<this>"), so that changing it does not change
    every page as a new asset_version() would."""
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]


def _env(lang):
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    t = translator(lang)
    env.filters["date_pl"] = date_fmt(lang)
    env.filters["pct"] = pct_fmt(lang)
    env.filters["groupby_consecutive"] = groupby_consecutive
    # Proposer labels are data, except these two.
    env.filters["cap"] = lambda s: s[:1].upper() + s[1:] if s else s   # "minister zdrowia" -> "Minister zdrowia"
    env.filters["who"] = lambda name: t(name) if name in ("Senat", "(nieustalony)") else name
    env.globals.update(
        _=t, lang=lang, SITE_URL=SITE_URL, asset_version=asset_version(),
        sitting_name=sitting_name(lang), term_name=f"{TERM}. kadencja" if lang == "pl" else f"{TERM}th term",
        anchor=anchor, source_items=source_items, print_paragraphs=print_paragraphs, print_too_big=print_too_big,
        VOTE_LABEL=VOTE_LABEL, LINE_LABEL=LINE_LABEL, MAJORITY_LABEL=MAJORITY_LABEL, KIND_LABEL=KIND_LABEL,
        print_url=print_url, pdf_url=pdf_url, act_url=act_url, TERM=TERM,
        post_weight=social.weight, POST_LIMIT=social.LIMIT, CARD_DIR=social.CARD_DIR,
        static_version=static_version, club_short=social.club_short, transcript_url=committees.transcript_url,
        QUESTIONS_SHOWN=QUESTIONS_SHOWN,
    )
    return env, t


def _pages(ctx):
    """(template, path, extra context) for every page of one language."""
    yield "index.html", "index.html", {}
    yield "sittings.html", "posiedzenia.html", {}
    yield "bills.html", "ustawy.html", {}
    yield "mps.html", "poslowie.html", {}
    yield "clubs.html", "kluby.html", {}
    yield "amendments.html", "poprawki.html", {}
    yield "adopted.html", "skuteczne-poprawki.html", {}
    yield "method.html", "metodologia.html", {}
    yield "search.html", "szukaj.html", {}
    yield "api.html", "api.html", {}
    yield "privacy.html", "prywatnosc.html", {}
    yield "summaries.html", "podsumowania.html", {}
    yield "upcoming.html", "nadchodzace-posiedzenie.html", {}
    yield "questions.html", "interpelacje.html", {}
    yield "committees.html", "komisje.html", {}
    for c in ctx["committee_rows"]:
        yield "committee.html", f"komisja/{c['code']}.html", {"c": c}
    for c in ctx["club_rows"]:
        yield "club.html", f"klub/{c['slug']}.html", {"c": c}
    for name, votes in ctx["by_proposer"].items():
        yield "proposer.html", f"poprawki/{club_slug(name)}.html", {"name": name, "votes": votes}
    for s, votings in ctx["sittings"].items():
        yield "sitting.html", f"posiedzenie/{s}.html", {
            "sitting": s, "votings": votings, "sitting_clubs": {club for v in votings for club in v["ballots"]}}
        for v in votings:
            yield "voting.html", f"glosowanie/{s}-{v['votingNumber']}.html", {"v": v}
    for b in ctx["bills"]:
        yield "bill.html", f"ustawa/{b['root']}.html", {"b": b}
    for r in ctx["mp_rows"]:
        yield "mp.html", f"posel/{r['mp']['id']}.html", {"r": r}
    for num in ctx["printed_list"]:
        yield "print.html", f"druk/{num}.html", {"num": num, "meta": print_meta(num)}


def _lang_path(lang, path):
    return path if lang == "pl" else f"{lang}/{path}"


def _write_sitemap(paths):
    if not SITE_URL:
        return
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for path in paths:
        alts = "".join(
            f'<xhtml:link rel="alternate" hreflang="{l}" href="{SITE_URL}{_lang_path(l, path)}"/>' for l in LANGS
        )
        for lang in LANGS:
            out.append(f"<url><loc>{SITE_URL}{_lang_path(lang, path)}</loc>{alts}</url>")
    out.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(out), encoding="utf-8")


def run():
    ctx = build_context()
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(STATIC, SITE / "static")
    shutil.copy(STATIC / "favicon.ico", SITE / "favicon.ico")  # where browsers and feed readers look first
    # Sejmdle: self-contained games that read the JSON API (test bench here;
    # the folder can be served from another host by changing its API address).
    shutil.copytree(ROOT / "games" / "sejmdle", SITE / "sejmdle")
    stamp(SITE / "sejmdle")  # so a new script or stylesheet loads at once, despite CDN caching

    # Day summaries as images. They need Pillow and a font; without either
    # the summaries are still published, as text only.
    try:
        from .card import write_cards
        write_cards(ctx["summaries"], SITE)
    except (ImportError, RuntimeError) as e:
        print(f"summary images skipped: {e}")
    try:
        from .card import write_club_cards
        write_club_cards(ctx["club_rows"], ctx["by_proposer"], ctx["sittings"], SITE)
    except (ImportError, RuntimeError) as e:
        print(f"club images skipped: {e}")

    pages = list(_pages(ctx))
    for lang in LANGS:
        env, t = _env(lang)
        for template, path, extra in pages:
            full = _lang_path(lang, path)
            site_root = "../" * full.count("/")
            out = SITE / full
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(env.get_template(template).render(
                root=site_root + ("" if lang == "pl" else f"{lang}/"),
                site_root=site_root, path=path, full_path=full,
                alternates={l: site_root + _lang_path(l, path) for l in LANGS},
                **ctx, **extra,
            ), encoding="utf-8")
        if getattr(t, "missing", None):
            print(f"[{lang}] untranslated strings: {sorted(t.missing)}")

    # Named votes, loaded by voting pages on demand: one file per sitting.
    (SITE / "dane" / "glosy").mkdir(parents=True)
    for s, votings in ctx["sittings"].items():
        (SITE / "dane" / "glosy" / f"{s}.json").write_text(json.dumps(
            {v["votingNumber"]: v["ballots"] for v in votings}, separators=(",", ":")))
    # An MP's interpellations and written questions when there are more than
    # the page shows, loaded when asked for (static/questions.js).
    (SITE / "dane" / "pytania").mkdir(parents=True)
    for r in ctx["mp_rows"]:
        if len(r["questions"]) > QUESTIONS_SHOWN:
            (SITE / "dane" / "pytania" / f"{r['mp']['id']}.json").write_text(json.dumps(
                [{"d": i["date"], "k": i["kind"], "n": i["num"], "t": i["title"], "to": i["to"], "a": i["answered"],
                  "days": i["days"], "l": i["late"], "o": i["overdue"], "p": i["prolonged"], "w": i["web"]}
                 for i in r["questions"]], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # What was voted on at a sitting, its outcome (in both languages) and every
    # club's line: read, with the ballots above, by the votes-by-sitting
    # tables on MP and club pages (static/breakdown.js).
    (SITE / "dane" / "posiedzenia").mkdir(parents=True)
    en = translator("en")
    for s, votings in ctx["sittings"].items():
        (SITE / "dane" / "posiedzenia" / f"{s}.json").write_text(json.dumps([
            {"n": v["votingNumber"], "t": v.get("topic") or "", "a": v["agenda"], "o": v["outcome_class"],
             "l": [v["outcome"], en(v["outcome"])], "c": {club: c["line"] for club, c in v["clubs"].items()}}
            for v in votings], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # Each MP's speeches with their texts, for the "Wystąpienia" list (static/speeches.js).
    (SITE / "dane" / "wystapienia").mkdir(parents=True)
    for mp, items in ctx["speeches_by_mp"].items():
        for name, part in zip((f"{mp}.json", f"{mp}.tekst.json"), speeches.split_for_site(items)):
            (SITE / "dane" / "wystapienia" / name).write_text(
                json.dumps(part, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # Each bill's debate, with the texts (a debate is a few dozen speeches at most).
    (SITE / "dane" / "debaty").mkdir(parents=True)
    for root, items in ctx["speeches_by_bill"].items():
        (SITE / "dane" / "debaty" / f"{root}.json").write_text(
            json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (SITE / "dane" / "poslowie.json").write_text(json.dumps(
        {m["id"]: m["firstLastName"] for m in ctx["mps"].values()}, ensure_ascii=False, separators=(",", ":")))

    write_api({**ctx, "print_meta": print_meta, "source_items": source_items}, ctx["generated"])

    # Apache/LiteSpeed hosting (e.g. Hostinger): let other sites use the API,
    # serve JSON with the right type, compress text.
    (SITE / "api" / ".htaccess").write_text(
        '<IfModule mod_headers.c>\n  Header set Access-Control-Allow-Origin "*"\n</IfModule>\n'
        "AddType application/json .json\n")
    (SITE / ".htaccess").write_text(
        "AddDefaultCharset UTF-8\n"
        "<IfModule mod_deflate.c>\n"
        "  AddOutputFilterByType DEFLATE text/html text/css application/javascript application/json application/xml\n"
        "</IfModule>\n"
        # Scripts and styles change with deploys and carry site-wide features
        # (they are not versioned in the page URLs), so browsers and the
        # host's CDN may keep them only briefly. The host's default is 7 days.
        "<IfModule mod_expires.c>\n  ExpiresActive On\n"
        + "".join(f'  ExpiresByType {t} "access plus 10 minutes"\n' for t in (
            "text/css", "application/javascript", "application/x-javascript", "text/javascript"))
        + "</IfModule>\n"
        # Pages are checked with the server on every visit (an unchanged page
        # costs a short "not modified" answer). Without this, browsers guess
        # how long to keep a page and can show an old one after a deploy.
        '<IfModule mod_headers.c>\n  <FilesMatch "\\.html$">\n'
        '    Header set Cache-Control "no-cache"\n  </FilesMatch>\n</IfModule>\n')

    _write_sitemap([p for _, p, _ in pages])
    robots = "User-agent: *\nAllow: /\n"
    if SITE_URL:
        robots += f"Sitemap: {SITE_URL}sitemap.xml\n"
    (SITE / "robots.txt").write_text(robots)

    linked, total = ctx["coverage"]
    print(f"site built: {sum(len(v) for v in ctx['sittings'].values())} votings, "
          f"{len(ctx['bills'])} bills, {len(ctx['mp_rows'])} MPs, "
          f"{len(ctx['printed_list'])} prints, amendments linked {linked}/{total}")
    (SITE / "coverage.json").write_text(json.dumps({"linked": linked, "total": total}))
