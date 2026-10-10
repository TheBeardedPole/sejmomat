"""Render the static site from data/ into site/."""
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import analysis
from .config import DATA, SITE, SITE_URL, STATIC, TEMPLATES, TERM
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
            "switches": sum(1 for h in history.get(mp_id, [])[1:] if not h.get("rename")),
        })
    mp_rows.sort(key=lambda r: r["mp"]["firstLastName"].split()[-1])

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
            "law_source": src, "law": bill_changes(print_text(src)) if src else [],
            "root": root, "title": meta.get("title") or votings[0]["agenda"],
            "votings": votings, "amend_count": len(amend_votes),
            "last": max(v["date"] for v in votings),
            "prints": sorted({p for v in votings for p in v["prints"]}, key=lambda p: (len(p), p)),
            "by_author": sorted(by_author.items(), key=lambda kv: -sum(kv[1].values())),
        })
    bill_rows.sort(key=lambda b: b["last"], reverse=True)

    club_rows = build_clubs(clubs, mps, by_id, mp_rows)
    adopted, proposers, mp_proposers = build_adopted(by_id)

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

    linked = sum(1 for v in by_id.values() for a in v["amendments"] if a["item"])
    total = sum(1 for v in by_id.values() for a in v["amendments"])
    return {
        "mps": mps, "clubs": clubs, "sittings": sittings, "by_id": by_id,
        "mp_rows": mp_rows, "mp_by_id": {r["mp"]["id"]: r for r in mp_rows},
        "club_rows": club_rows, "club_slug": club_slug,
        "adopted": adopted, "proposers": proposers, "mp_proposers": mp_proposers,
        "transfers": [(pair, n, pair in renames) for pair, n in transfers.most_common()],
        "bills": bill_rows, "bill_by_root": {b["root"]: b for b in bill_rows},
        "coverage": (linked, total),
        "printed": set(printed), "printed_list": printed,
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


def build_clubs(clubs, mps, by_id, mp_rows):
    """Per-club cohesion, effectiveness, agreement with other clubs, members."""
    stats = defaultdict(lambda: {"votes": 0, "shares": [], "split": [], "rebellions": 0,
                                 "decided": 0, "won": 0, "first": None, "last": None})
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
            if voted >= analysis.MIN_CLUB_VOTERS:
                st["shares"].append(c["share"])
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
        rows.append({
            "id": club, "slug": club_slug(club), "name": clubs.get(club, club),
            "votes": st["votes"], "first": st["first"], "last": st["last"],
            "cohesion": sum(st["shares"]) / len(st["shares"]) if st["shares"] else 0,
            "split": st["split"], "rebellions": st["rebellions"],
            "effectiveness": st["won"] / st["decided"] if st["decided"] else 0,
            "agreement": others, "members": members,
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
    env.filters["who"] = lambda name: t(name) if name in ("Senat", "(nieustalony)") else name
    env.globals.update(
        _=t, lang=lang, SITE_URL=SITE_URL,
        sitting_name=sitting_name(lang), term_name=f"{TERM}. kadencja" if lang == "pl" else f"{TERM}th term",
        anchor=anchor, source_items=source_items, print_paragraphs=print_paragraphs, print_too_big=print_too_big,
        VOTE_LABEL=VOTE_LABEL, LINE_LABEL=LINE_LABEL, MAJORITY_LABEL=MAJORITY_LABEL, KIND_LABEL=KIND_LABEL,
        print_url=print_url, pdf_url=pdf_url, act_url=act_url, TERM=TERM,
    )
    return env, t


def _pages(ctx):
    """(template, path, extra context) for every page of one language."""
    yield "index.html", "index.html", {}
    yield "sittings.html", "posiedzenia.html", {}
    yield "bills.html", "ustawy.html", {}
    yield "mps.html", "poslowie.html", {}
    yield "clubs.html", "kluby.html", {}
    yield "adopted.html", "skuteczne-poprawki.html", {}
    yield "method.html", "metodologia.html", {}
    yield "search.html", "szukaj.html", {}
    yield "api.html", "api.html", {}
    for c in ctx["club_rows"]:
        yield "club.html", f"klub/{c['slug']}.html", {"c": c}
    for s, votings in ctx["sittings"].items():
        yield "sitting.html", f"posiedzenie/{s}.html", {"sitting": s, "votings": votings}
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
    (SITE / "static").mkdir(parents=True)
    for f in STATIC.iterdir():
        shutil.copy(f, SITE / "static" / f.name)

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
        "<IfModule mod_expires.c>\n  ExpiresActive On\n  ExpiresByType text/css \"access plus 1 day\"\n"
        "  ExpiresByType application/javascript \"access plus 1 day\"\n</IfModule>\n")

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
