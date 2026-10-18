"""Graphics and captions to post by hand, one folder per day.

    python -m sejmomat.posts                 # today's posts
    python -m sejmomat.posts 2026-10-21      # a given day
    python -m sejmomat.posts --days 7        # today and the six days after

Each day gets posts/<date>/: the images, and posts.txt with a caption and
an image description (alt text) for each. The folder is not in git and not
on the site. What a day holds:

- "MPs from A to Z": every MP serving when the series started, by surname,
  one on one day and two on the next (about 1.5 a day, so the series ends
  well before the end of the term). The order is fixed in
  data/posts_order.json, so it never shifts; an MP who has left the Sejm by
  their day is skipped, and MPs who join later are added at the end.
- once a week a club (the current ones, largest first, in turn) and once a
  week a minister (those asked most, in turn): how they answer MPs'
  questions.
- the morning after a voting day, that day's summary (as on podsumowania.html).

Every figure comes straight from the data, drawn on the day it is made.
Run it after `git pull`, so data/ has the latest votes.
"""
import json
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from .config import CACHE, DATA, SITE_URL, TERM

START = date(2026, 10, 18)   # the first day of the series
ORDER = DATA / "posts_order.json"
OUT = Path(__file__).resolve().parent.parent / "posts"
SITE = SITE_URL or "https://sejmomat.pl/"
CLUB_DAY, MINISTER_DAY = 3, 6   # days of the series' week (0-6)
MIN_QUESTIONS = 100   # ministers with fewer questions are not featured
_ALPHABET = "aąbcćdeęfghijklłmnńoóprsśtuvwxyzźż"


def polish_key(text):
    """Sort key in Polish alphabetical order (ą after a, ł after l, …)."""
    return [(_ALPHABET.index(ch) if ch in _ALPHABET else 100 + ord(ch)) for ch in (text or "").lower()]


def order(mp_rows):
    """MP ids in the series' order, fixed in ORDER; new MPs go to the end."""
    ids = json.loads(ORDER.read_text(encoding="utf-8")) if ORDER.exists() else []
    if not ids:
        serving = [r["mp"] for r in mp_rows if r["mp"].get("active")]
        ids = [m["id"] for m in sorted(serving, key=lambda m: (polish_key(m.get("lastName")), polish_key(m["firstLastName"])))]
    known = set(ids)
    ids += [r["mp"]["id"] for r in mp_rows if r["mp"].get("active") and r["mp"]["id"] not in known]
    ORDER.write_text(json.dumps(ids) + "\n", encoding="utf-8")
    return ids


def plan(day, ids, clubs, ministers):
    """What goes out on `day`: (MP ids with their place in the series, club or None, minister or None)."""
    i = (day - START).days
    if i < 0:
        return [], None, None
    before = i + i // 2            # one MP on even days, two on odd ones
    count = 1 if i % 2 == 0 else 2
    mps = [(mp, before + k + 1) for k, mp in enumerate(ids[before:before + count])]
    club = clubs[(i // 7) % len(clubs)] if clubs and i % 7 == CLUB_DAY else None
    minister = ministers[(i // 7) % len(ministers)] if ministers and i % 7 == MINISTER_DAY else None
    return mps, club, minister


def photo(mp_id):
    """An MP's photo from the Sejm's API, kept in cache/photos/; None if unavailable."""
    from PIL import Image
    path = CACHE / "photos" / f"{mp_id}.jpg"
    if not path.exists():
        try:
            req = urllib.request.Request(f"https://api.sejm.gov.pl/sejm/term{TERM}/MP/{mp_id}/photo",
                                         headers={"User-Agent": "sejmomat"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except Exception:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    try:
        return Image.open(path)
    except Exception:
        return None


def _fit(lines, tail):
    """Caption from bullet lines and a closing line, dropping bullets until it fits a post."""
    from .social import LIMIT, weight
    while True:
        text = "\n".join(lines) + "\n\n" + tail
        if weight(text) <= LIMIT or len(lines) <= 1:
            return text
        lines = lines[:-1]


def mp_post(r, place, total):
    from .card import pct
    from .social import club_short
    mp, sp, q = r["mp"], r.get("speeches") or {}, r.get("q_stats") or {}
    who = ", ".join(x for x in (club_short(mp.get("club") or ""), mp.get("districtName") and f"okręg {mp['districtName']}") if x)
    speeches = (sp.get("spoken") or 0) + (sp.get("written") or 0)
    questions = q.get("int", 0) + q.get("zap", 0)
    lines = [f"{mp['firstLastName']} ({who}) w {TERM}. kadencji Sejmu:",
             f"• udział w głosowaniach: {pct(r['turnout'])}",
             f"• wyłamania z linii klubu: {r['rebel_count']}",
             f"• wystąpienia na sali: {speeches}",
             f"• interpelacje i zapytania: {questions}"]
    caption = _fit(lines, f"Posłowie od A do Ż, {place}/{total} → {SITE}posel/{mp['id']}.html")
    alt = (f"Podsumowanie kadencji: {mp['firstLastName']}, {who}. Udział w głosowaniach {pct(r['turnout'])} "
           f"({r['cast']} z {r['eligible']}), opuszczonych głosowań {r['eligible'] - r['cast']}, wyłamań z linii klubu "
           f"{r['rebel_count']}, wystąpień {speeches}, interpelacji i zapytań {questions}. sejmomat.pl")
    return caption, alt


def club_post(c, label, proposed):
    from .card import pct
    sp = c.get("speeches") or {}
    adopted = sum(1 for v in proposed if v["outcome_class"] == "adopted")
    lines = [f"{label} w {TERM}. kadencji Sejmu:",
             f"• spójność w głosowaniach: {pct(c['cohesion'])}",
             f"• skuteczność (wygrane głosowania): {pct(c['effectiveness'])}",
             f"• wystąpienia na sali: {(sp.get('spoken') or 0) + (sp.get('written') or 0)}",
             f"• przyjęte poprawki i wnioski: {adopted}/{len(proposed)}"]
    caption = _fit(lines, f"→ {SITE}klub/{c['slug']}.html")
    alt = (f"Podsumowanie kadencji klubu {label}: spójność {pct(c['cohesion'])}, skuteczność {pct(c['effectiveness'])}, "
           f"przyjętych poprawek i wniosków {adopted} z {len(proposed)}, oraz kluby, z którymi głosuje najczęściej. sejmomat.pl")
    return caption, alt


def minister_post(t, deadline):
    from .card import pct
    name = t["name"]
    lines = [f"Jak {name} odpowiada na pytania posłów ({TERM}. kadencja):",
             f"• pytania: {t['received']}, z odpowiedzią: {pct(t['answered'] / (t['received'] or 1))}",
             f"• typowy czas odpowiedzi: {t['median']} dni (termin: {deadline})" if t["median"] is not None else "",
             f"• odpowiedzi po terminie: {t['late']}",
             f"• bez odpowiedzi po terminie: {t['overdue']}"]
    caption = _fit([l for l in lines if l], f"→ {SITE}interpelacje.html")
    alt = (f"Jak {name} odpowiada na interpelacje i zapytania poselskie: {t['received']} pytań, "
           f"{pct(t['answered'] / (t['received'] or 1))} z odpowiedzią, mediana {t['median']} dni, "
           f"{t['late']} odpowiedzi po terminie, {t['prolonged']} przedłużeń, {t['overdue']} bez odpowiedzi po terminie. sejmomat.pl")
    return caption, alt


def make(days):
    from .build import build_context
    from .card import club_labels, club_term, minister, mp_term, render
    from .social import summary_post
    ctx = build_context()
    rows = {r["mp"]["id"]: r for r in ctx["mp_rows"]}
    ids = order(ctx["mp_rows"])
    clubs = sorted((c for c in ctx["club_rows"] if c["current"] and c["members"]), key=lambda c: -len(c["members"]))
    Q = ctx["questions_summary"]
    ministers = [t for t in Q["recipients"] if t["received"] >= MIN_QUESTIONS]
    label = club_labels(ctx["club_rows"])
    summaries = {s["day"]: s for s in ctx["summaries"]}
    for day in days:
        mps, club, mn = plan(day, ids, clubs, ministers)
        posts = []   # (file name, image, caption, alt)
        yesterday = (day - timedelta(days=1)).isoformat()
        if yesterday in summaries:
            s = summaries[yesterday]
            # outside CI the site's address is not set, so the link is relative
            caption = s["caption"] if s["url"].startswith("http") else s["caption"].replace(s["url"], SITE + s["url"])
            posts.append(("podsumowanie-dnia", render(s), caption, s["alt"]))
        for mp_id, place in mps:
            r = rows.get(mp_id)
            if not r or not r["mp"].get("active"):
                continue  # left the Sejm since the series began
            caption, alt = mp_post(r, place, len(ids))
            posts.append((f"posel-{place:03d}-{mp_id}", mp_term(r, photo(mp_id)), caption, alt))
        if club:
            caption, alt = club_post(club, label(club["id"]), ctx["by_proposer"].get(club["id"], []))
            posts.append((f"klub-{club['slug']}", club_term(club, ctx["by_proposer"].get(club["id"], []), label), caption, alt))
        if mn:
            caption, alt = minister_post(mn, Q["deadline"])
            posts.append(("minister", minister(mn, Q["deadline"]), caption, alt))
        folder = OUT / day.isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        notes = []
        for n, (name, img, caption, alt) in enumerate(posts, 1):
            file = f"{n:02d}-{name}.png"
            img.save(folder / file, optimize=True)
            notes.append(f"=== {file}\n\n{caption}\n\n--- Opis obrazka (alt):\n{alt}\n")
        (folder / "posts.txt").write_text("\n".join(notes) or "Brak postów na ten dzień.\n", encoding="utf-8")
        print(f"{folder.relative_to(OUT.parent)}: {len(posts)} post(s)")


if __name__ == "__main__":
    args = sys.argv[1:]
    first = date.fromisoformat(next((a for a in args if a[:1].isdigit()), date.today().isoformat()))
    n = int(args[args.index("--days") + 1]) if "--days" in args else 1
    make([first + timedelta(days=k) for k in range(n)])
