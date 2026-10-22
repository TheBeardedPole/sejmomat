"""Who submitted a bill: read from its title and, for MPs' bills, from the
signatures on the print ("(-) Jan Kowalski")."""
import re
from collections import Counter

# (title pattern, kind, label). Labels are Polish; the site translates them.
_KINDS = [
    (r"^Rządowy projekt", "government", "Rada Ministrów"),
    (r"^Poselski projekt", "mps", "Posłowie"),
    (r"^Senacki projekt", "senate", "Senat"),
    (r"^Obywatelski projekt", "citizens", "Obywatele (inicjatywa obywatelska)"),
    (r"^Komisyjny projekt", "committee", "Komisja sejmowa"),
    (r"^Przedstawiony przez Prezydenta", "president", "Prezydent RP"),
    (r"^Przedstawiony przez Prezydium Sejmu", "presidium", "Prezydium Sejmu"),
]
_SIGNATURE_RE = re.compile(
    r"\(\s*[-–—]\s*\)\s*([A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż]+(?:[ -]+[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż-]+){1,4})"
)


def _fold(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def name_index(mps):
    """(first name, surname) -> [MP ids]; the surname is everything after the first name."""
    index = {}
    for m in mps.values():
        parts = (m.get("firstLastName") or "").split()
        if len(parts) >= 2:
            index.setdefault((_fold(parts[0]), _fold(" ".join(parts[1:]))), []).append(m["id"])
    return index


def _match(name, index):
    """MP id for a signature; signatures may carry a second name ("Iwona Ewa Arent")."""
    parts = name.split()
    for cut in range(1, len(parts)):          # surname = last 1, 2, ... words
        hit = index.get((_fold(parts[0]), _fold(" ".join(parts[cut:]))))
        if hit:
            return hit[0]
    return None


# "Do reprezentowania wnioskodawców ... upoważniamy panią poseł Marcelinę
# Zawiszę": the MP who leads an MPs' bill (the signatures are often in
# alphabetical order, so the first of them says little). The name is declined.
_REPRESENTATIVE_RE = re.compile(
    r"upoważnia\w*\s+(?:(?:pan|pani|panią|pana|panie|panów)\s+)?(?:(?:posła|poseł|posłankę|posłanki|posłanka|posłów)\s+)?"
    r"([A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż]+(?:[ -]+[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż-]+){1,3})", re.I)


def representative(text, mps):
    """The MP id named as the sponsors' representative, or None. The name is
    in another case ("Marcelinę Zawiszę"), so names are matched on their
    beginnings: the first name and the surname (hyphened ones part by part)."""
    m = _REPRESENTATIVE_RE.search(re.sub(r"\s+", " ", (text or "")[:20000]))
    if not m:
        return None
    # the first named, when there are several ("Monikę Rosę i Monikę Wielichowską")
    words = re.split(r"\s+(?:i|oraz)\s+|,", m.group(1))[0].split()
    if len(words) < 2:
        return None
    # a short name loses one letter in another case (Ewa, Ewę), a longer one up to two
    stem = lambda name: name[:len(name) - 1 if len(name) <= 4 else max(3, len(name) - 2)].lower()
    first, last = words[0].lower(), words[-1].lower()
    common = lambda a, b: next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    # surnames that change inside (Fogiel, Fogla) only on a second, looser pass; of
    # the MPs that fit, the one sharing the most letters (Horała over Hok for "Horałę")
    for loose in (False, True):
        best = None
        for mp in mps.values():
            parts = (mp.get("firstLastName") or "").split()
            if len(parts) < 2 or not first.startswith(stem(parts[0])):
                continue
            surname, given = [x.lower() for x in parts[-1].split("-")], last.split("-")
            sure = lambda s: s[:3] if loose else stem(s)
            if len(surname) == len(given) and all(g.startswith(sure(s)) for s, g in zip(surname, given)):
                score = common(first, parts[0].lower()) + sum(common(g, s) for s, g in zip(surname, given))
                if not best or score > best[0]:
                    best = (score, mp["id"])
        if best:
            return best[1]
    return None


def club_on(history, day):
    """Club an MP sat in on `day` (YYYY-MM-DD), from the club history."""
    if not history:
        return None
    for h in history:
        if h["from"][:10] <= day <= h["to"][:10]:
            return h["club"]
    earlier = [h for h in history if h["to"][:10] < day]
    return (earlier[-1] if earlier else history[0])["club"]


def bill_author(title, text, day, index, histories):
    """{"kind", "label", "mps": [ids], "clubs": [(club, n)], "unmatched": n} or None."""
    for pattern, kind, label in _KINDS:
        if re.search(pattern, title or ""):
            break
    else:
        return None
    author = {"kind": kind, "label": label, "mps": [], "clubs": [], "unmatched": 0}
    if kind != "mps" or not text:
        return author
    # signatures sit on the cover letter, before the bill itself
    head = text[: text.find("uzasadnienie") if 0 < text.lower().find("uzasadnienie") else len(text)]
    seen, clubs = [], Counter()
    for name in _SIGNATURE_RE.findall(head[:20000]):
        mp = _match(name, index)
        if mp is None:
            author["unmatched"] += 1
        elif mp not in seen:
            seen.append(mp)
            clubs[club_on(histories.get(mp), day or "9999") or "?"] += 1
    author["mps"] = seen
    author["clubs"] = clubs.most_common()
    if clubs:
        top = [c for c, n in author["clubs"] if n >= max(2, 0.15 * len(seen))] or [author["clubs"][0][0]]
        author["label"] = f"Posłowie: {', '.join(top)}"
    return author
