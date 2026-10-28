"""Images (PNG) for social media: a voting day's summary, and a club's term
or latest sitting.

The day's card shows what the text posts say (see social.py): the day's
figures, the most contested vote on a law and whose amendments passed. All
cards have the site's address in the footer. Uses Pillow and the locally hosted Source font families. MP cards are drawn in the reader's browser instead
(static/card.js), in the same layout.
"""
from collections import Counter
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .i18n import ORDINALS, date_fmt
from .config import SITE_URL, TERM
from .social import CARD_DIR, LINE_LABELS, PROPOSER_ROWS, club_short, short_title

FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
FONTS = {"regular": "SourceSans3.woff2", "bold": "SourceSans3.woff2", "heading": "SourceSerif4.woff2"}
W, MIN_H = 1200, 675
PAD, GAP, FOOT = 64, 24, 96
BG, SURFACE, TEXT, MUTED, LINE = "#ffffff", "#f3f3f3", "#0b0c0c", "#484949", "#cecece"
YES, NO, ABSTAIN, SPLIT = "#1f7a4d", "#b3261e", "#9a6b00", "#6b6b70"
BRAND, LINK = "#1d70b8", "#1a65a6"
FOOT_BG, FOOT_TEXT = "#0b0c0c", "#ffffff"
LINE_COLOR = {"Y": YES, "N": NO, "A": ABSTAIN, "split": SPLIT}


@cache
def font(weight, size):
    result = ImageFont.truetype(str(FONT_DIR / FONTS[weight]), size)
    axes = result.get_variation_axes()
    result.set_variation_by_axes([
        min(axis["maximum"], max(axis["minimum"],
            (700 if weight in ("bold", "heading") else 400) if axis["name"] == b"Weight" else size))
        for axis in axes
    ])
    return result


def wrap(text, fnt, width, first_indent=0, max_lines=None):
    """Break text into lines no wider than `width` (the first one shorter by
    `first_indent`); beyond `max_lines` the last line ends with an ellipsis."""
    lines, line = [], ""
    for word in text.split():
        room = width - (first_indent if not lines else 0)
        if line and fnt.getlength(f"{line} {word}") > room:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and fnt.getlength(lines[-1] + "…") > width:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] = lines[-1].rstrip(",;:-–") + "…"
    return lines


def _tiles(s):
    """(number, label, colour) for every figure of the day that is not zero."""
    rows = [(s["votes"], "Głosowania", TEXT),
            (s["lawsPassed"], "Uchwalone ustawy", YES),
            (s["resolutionsPassed"], "Podjęte uchwały", YES),
            (s["billsRejected"], "Odrzucone projekty ustaw", NO),
            (s["amendmentVotes"], "Głosowania nad poprawkami", TEXT),
            (s["amendmentVotesAdopted"], "Przyjęte poprawki i wnioski", YES),
            (s["againstCommitteeRecommendation"], "Rozstrzygnięcia wbrew rekomendacji komisji", ABSTAIN)]
    return [r for r in rows if r[0]]


def header(img, context, title, subtitle, photo=None):
    """Wordmark masthead, serif subject title, then factual metadata."""
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 88), fill=FOOT_BG)
    d.rectangle((0, 82, W, 88), fill=BRAND)
    logo = _logo(30)
    if logo:
        img.paste(logo, (PAD, 26), logo)
    d.text((W - PAD, 42), "sejmomat.pl", font=font("bold", 26), fill=FOOT_TEXT, anchor="rm")
    photo_w = 150 if photo else 0
    room = W - 2 * PAD - (photo_w + 32 if photo else 0)
    y = 128
    for line in wrap(title, font("heading", 64), room, max_lines=2):
        d.text((PAD, y), line, font=font("heading", 64), fill=TEXT)
        y += 84
    for line in wrap(f"{context} · {subtitle}", font("regular", 26), room, max_lines=3):
        d.text((PAD, y + 8), line, font=font("regular", 26), fill=MUTED)
        y += 36
    if photo:
        h = round(photo_w * 1.25)
        scale = max(photo_w / photo.width, h / photo.height)
        pic = photo.convert("RGB").resize((round(photo.width * scale), round(photo.height * scale)))
        pic = pic.crop(((pic.width - photo_w) // 2, 0, (pic.width - photo_w) // 2 + photo_w, h))
        img.paste(pic, (W - PAD - photo_w, 132))
        y = max(y, 132 + h)
    return y + 40


def summary_rows(d, y, rows):
    """Summary-list rows with labels left, figures and factual standings right."""
    width, row_h = W - 2 * PAD, 104
    for i, (number, label, color, *badge) in enumerate(rows):
        ty = y + i * row_h
        d.rectangle((PAD, ty, W - PAD, ty + row_h), fill=SURFACE if i % 2 == 0 else BG)
        d.line((PAD, ty, W - PAD, ty), fill=LINE, width=1)
        for j, line in enumerate(wrap(label, font("regular", 28), width - 360, max_lines=2)):
            d.text((PAD + 24, ty + 22 + j * 34), line, font=font("regular", 28), fill=TEXT)
        d.text((W - PAD - 24, ty + 16), str(number), font=font("heading", 54), fill=color, anchor="ra")
        if badge and badge[0]:
            d.text((W - PAD - 24, ty + 76), f"TOP {badge[0]}%", font=font("bold", 20), fill=LINK, anchor="ra")
    d.line((PAD, y + len(rows) * row_h, W - PAD, y + len(rows) * row_h), fill=LINE, width=1)
    return y + len(rows) * row_h + 32


def result_bar(img, x, y, width, parts, height=26):
    """Shares as one rectangular bar: parts are [(number, colour)]."""
    total, bx = sum(p[0] for p in parts) or 1, 0
    bar, mask = Image.new("RGB", (width, height), LINE), Image.new("L", (width, height), 0)
    for n, color in parts:
        seg = round(width * n / total)
        ImageDraw.Draw(bar).rectangle((bx, 0, bx + seg, height), fill=color)
        bx += seg
    ImageDraw.Draw(mask).rectangle((0, 0, width - 1, height - 1), fill=255)
    img.paste(bar, (x, y), mask)


def footer(img, y):
    """Small source credit closes the reading surface without a promotional band."""
    height = max(MIN_H, y + 32 + FOOT)
    img = img.crop((0, 0, W, height))
    d = ImageDraw.Draw(img)
    d.rectangle((0, height - FOOT, W, height), fill=BG)
    d.line((PAD, height - FOOT, W - PAD, height - FOOT), fill=LINE, width=2)
    lead = "Zobacz więcej na "
    d.text((PAD, height - 44), lead, font=font("regular", 25), fill=MUTED, anchor="lm")
    d.text((PAD + font("regular", 25).getlength(lead), height - 44), "sejmomat.pl", font=font("bold", 28), fill=LINK, anchor="lm")
    d.text((W - PAD, height - 44), "Dane: API Sejmu RP", font=font("regular", 24), fill=MUTED, anchor="rm")
    return img


@cache
def _logo(height=40):
    """static/logo-white.png (made by brand/make.py) at `height`, or None."""
    path = Path(__file__).resolve().parent.parent / "static" / "logo-white.png"
    if not path.exists():
        return None
    logo = Image.open(path).convert("RGBA")
    return logo.resize((round(logo.width * height / logo.height), height), Image.LANCZOS)


def render(s):
    """The card for one summary (as built by social.summarize)."""
    img = Image.new("RGB", (W, 3000), BG)
    d = ImageDraw.Draw(img)
    inner = W - 2 * PAD
    y = header(img, "Podsumowanie dnia w Sejmie", date_fmt("pl")(s["day"]), f"{s['sitting']}. posiedzenie Sejmu")
    y = summary_rows(d, y, _tiles(s))

    def panel(height):
        d.rectangle((PAD, y, W - PAD, y + height), fill=SURFACE)

    # the most contested vote on a law
    law = s["mostContestedLaw"]
    if law:
        x, width = PAD + 28, inner - 56
        title = wrap(short_title(law["title"]), font("heading", 34), width, max_lines=2)
        sides = [(k, label, ", ".join(law["lines"][k])) for k, label in LINE_LABELS if law["lines"].get(k)]
        side_lines = [wrap(clubs, font("regular", 26), width, first_indent=font("bold", 26).getlength(f"{label}: "))
                      for _, label, clubs in sides]
        panel(28 + 38 + len(title) * 46 + 14 + 26 + 16 + 40 + 10 + sum(len(l) for l in side_lines) * 36 + 22)
        ty = y + 28
        for line in title:
            d.text((x, ty), line, font=font("heading", 34), fill=TEXT)
            ty += 46
        d.text((x, ty + 4), "Najbardziej sporne głosowanie nad ustawą", font=font("regular", 24), fill=MUTED)
        ty += 38 + 14
        # the result as a bar: for, against, abstained
        parts = [(law["yes"], YES, "za"), (law["no"], NO, "przeciw"), (law["abstain"], ABSTAIN, "wstrz.")]
        result_bar(img, x, ty, width, [(n, color) for n, color, _ in parts])
        ty += 26 + 16
        tx = x
        for i, (n, color, word) in enumerate(parts):
            text = f"{n} {word}"
            d.text((tx, ty), text, font=font("bold", 28), fill=color)
            tx += font("bold", 28).getlength(text)
            if i < 2:
                d.text((tx, ty), "  ·  ", font=font("regular", 28), fill=MUTED)
                tx += font("regular", 28).getlength("  ·  ")
        if not law["passed"]:
            d.text((x + width, ty), "projekt odrzucony", font=font("bold", 28), fill=NO, anchor="ra")
        ty += 40 + 10
        for (k, label, _), lines in zip(sides, side_lines):
            d.text((x, ty), f"{label}:", font=font("bold", 26), fill=LINE_COLOR[k])
            indent = font("bold", 26).getlength(f"{label}: ")
            for i, line in enumerate(lines):
                d.text((x + (indent if i == 0 else 0), ty), line, font=font("regular", 26), fill=TEXT)
                ty += 36
        y = ty + 22 + GAP

    # whose amendments passed: adopted / voted on, in two columns
    rows = s["amendmentProposers"]
    if any(r["proposer"] != "(nieustalony)" for r in rows):
        shown = [(club_short(r["proposer"]), r["adopted"], r["voted"]) for r in rows[:PROPOSER_ROWS]]
        rest = rows[PROPOSER_ROWS:]
        if rest:
            shown.append(("pozostali", sum(r["adopted"] for r in rest), sum(r["voted"] for r in rest)))
        x, width = PAD + 28, inner - 56
        col_w, per_col = (width - 48) // 2, -(-len(shown) // 2)
        panel(28 + 44 + per_col * 46 + 18)
        ty = y + 28
        d.text((x, ty), "Czyje poprawki przeszły?", font=font("bold", 22), fill=MUTED)
        d.text((x + width, ty), "przyjęte / głosowane", font=font("regular", 22), fill=MUTED, anchor="ra")
        ty += 44
        for i, (name, adopted, voted) in enumerate(shown):
            cx, cy = x + (i // per_col) * (col_w + 48), ty + (i % per_col) * 46
            value = f"{adopted}/{voted}"
            d.text((cx + col_w, cy), value, font=font("bold", 26), fill=TEXT, anchor="ra")
            bar_x, bar_w = cx + col_w - 110 - 150, 150
            d.text((cx, cy), wrap(name, font("regular", 26), bar_x - cx - 16, max_lines=1)[0], font=font("regular", 26), fill=TEXT)
            d.rectangle((bar_x, cy + 13, bar_x + bar_w, cy + 25), fill=LINE)
            if adopted:
                d.rectangle((bar_x, cy + 13, bar_x + max(12, round(bar_w * adopted / voted)), cy + 25), fill=YES)
        y = ty + per_col * 46 + 18 + GAP

    return footer(img, y)


def write_cards(summaries, site):
    """Write CARD_DIR/<day>.png for every summary and note it in the summary
    as "image" (its address) and "imageSize"."""
    (site / CARD_DIR).mkdir(parents=True, exist_ok=True)
    for s in summaries:
        img = render(s)
        img.save(site / CARD_DIR / f"{s['day']}.png", optimize=True)
        s["image"], s["imageSize"] = f"{SITE_URL}{CARD_DIR}/{s['day']}.png", list(img.size)


# ------------------------------------------------------------- clubs

CLUB_DIR = "dane/karty/klub"   # within the site
CLUB_CARDS = (("kadencja", "Kadencja"), ("posiedzenie", "Ostatnie posiedzenie"))  # file suffix, label


def pct(x):
    return f"{x * 100:.1f}%".replace(".", ",")


def club_term(c, proposed, label):
    """A club's term: members, cohesion, effectiveness, speeches, amendments,
    and the clubs it votes with most."""
    img = Image.new("RGB", (W, 3000), BG)
    d = ImageDraw.Draw(img)
    fmt = date_fmt("pl")
    subtitle = c["name"] if c["name"] != c["id"] else ""
    subtitle += f"{' · ' if subtitle else ''}głosowania od {fmt(c['first'])} do {fmt(c['last'])}"
    y = header(img, f"Podsumowanie kadencji · {TERM}. kadencja Sejmu", label(c["id"]), subtitle)
    sp = c.get("speeches") or {}
    adopted = sum(1 for v in proposed if v["outcome_class"] == "adopted")
    rows = [(len(c["members"]), "obecnych członków" if c["current"] else "członków (klub już nie istnieje)", TEXT),
            (pct(c["cohesion"]), "spójność w głosowaniach", TEXT),
            (pct(c["effectiveness"]), "skuteczność: wygrane głosowania", YES),
            (len(c["split"]), "głosowań z podziałem w klubie", ABSTAIN),
            ((sp.get("spoken") or 0) + (sp.get("written") or 0), "wystąpień na sali plenarnej", TEXT),
            (f"{adopted} z {len(proposed)}", "zgłoszonych poprawek i wniosków przeszło", TEXT)]
    y = summary_rows(d, y, [r for r in rows if r[0] not in (0, "0/0")])
    allies = c["agreement"][:5]
    if allies:
        x, width = PAD + 28, W - 2 * PAD - 56
        d.rectangle((PAD, y, W - PAD, y + 28 + 44 + len(allies) * 46 + 18), fill=SURFACE)
        ty = y + 28
        d.text((x, ty), "Najczęściej głosuje tak jak", font=font("bold", 22), fill=MUTED)
        d.text((x + width, ty), "zgodność linii klubów", font=font("regular", 22), fill=MUTED, anchor="ra")
        ty += 44
        for o in allies:
            bar_x, bar_w = x + 300, width - 300 - 120
            d.text((x, ty), label(o["club"]), font=font("regular", 26), fill=TEXT)
            d.rectangle((bar_x, ty + 13, bar_x + bar_w, ty + 25), fill=LINE)
            d.rectangle((bar_x, ty + 13, bar_x + max(12, round(bar_w * o["rate"])), ty + 25), fill=YES)
            d.text((x + width, ty), pct(o["rate"]), font=font("bold", 26), fill=TEXT, anchor="ra")
            ty += 46
        y = ty + 18 + GAP
    return footer(img, y)


def club_sitting(c, votes, label):
    """A club's latest sitting: its line in the votes, splits, ballots not cast, breaks of the line."""
    x = c["sittings"][0]
    img = Image.new("RGB", (W, 3000), BG)
    d = ImageDraw.Draw(img)
    fmt = date_fmt("pl")
    first, last = votes[0]["date"], votes[-1]["date"]
    when = fmt(first) if first[:10] == last[:10] else f"{fmt(first)} – {fmt(last)}"
    y = header(img, "Ostatnie posiedzenie Sejmu", label(c["id"]), f"{x['sitting']}. posiedzenie · {when}")
    missed = x["X"] / (x["X"] + x["cast"]) if x["X"] + x["cast"] else 0
    # abstaining as the club's line is rare; it shows in the bar below
    y = summary_rows(d, y, [(x["votes"], "głosowań", TEXT), (x["Y"], "razy linia klubu: za", YES),
                     (x["N"], "razy linia klubu: przeciw", NO), (x["split"], "razy klub podzielony", SPLIT),
                     (pct(missed), "głosów nieoddanych przez posłów klubu", TEXT), (x["rebels"], "wyłamań z linii klubu", TEXT)])
    width = W - 2 * PAD - 56
    d.rectangle((PAD, y, W - PAD, y + 28 + 38 + 26 + 16 + 40 + 18), fill=SURFACE)
    ty = y + 28
    d.text((PAD + 28, ty), "Linia klubu w głosowaniach", font=font("bold", 22), fill=MUTED)
    ty += 38
    parts = [(x["Y"], YES, "za"), (x["N"], NO, "przeciw"), (x["A"], ABSTAIN, "wstrz."), (x["split"], SPLIT, "podzielony")]
    result_bar(img, PAD + 28, ty, width, [(n, color) for n, color, _ in parts])
    ty += 26 + 16
    tx = PAD + 28
    for i, (n, color, word) in enumerate(parts):
        text = f"{n} {word}"
        d.text((tx, ty), text, font=font("bold", 28), fill=color)
        tx += font("bold", 28).getlength(text) + font("regular", 28).getlength("  ·  ")
        if i < len(parts) - 1:
            d.text((tx - font("regular", 28).getlength("  ·  "), ty), "  ·  ", font=font("regular", 28), fill=MUTED)
    return footer(img, ty + 40 + 18 + GAP)


def club_labels(club_rows):
    """A club's short name, or its id where two share one (Polska2050 and
    Polska2050-TD are both "Polska 2050")."""
    shorts = Counter(club_short(c["id"]) for c in club_rows)
    return lambda club: club_short(club) if shorts[club_short(club)] < 2 else club.replace("_", " ")


def write_club_cards(club_rows, by_proposer, sittings, site):
    """Write CLUB_DIR/<slug>-kadencja.png and -posiedzenie.png for every club
    and note them in the club's row as "cards": [(label, address in the site)]."""
    (site / CLUB_DIR).mkdir(parents=True, exist_ok=True)
    label = club_labels(club_rows)
    for c in club_rows:
        made = [("kadencja", club_term(c, by_proposer.get(c["id"], []), label))]
        if c["sittings"]:
            made.append(("posiedzenie", club_sitting(c, sittings[c["sittings"][0]["sitting"]], label)))
        c["cards"] = []
        for suffix, img in made:
            path = f"{CLUB_DIR}/{c['slug']}-{suffix}.png"
            img.save(site / path, optimize=True)
            c["cards"].append((dict(CLUB_CARDS)[suffix], path))


# ------------------------------------------------------------- MPs and ministers
# (an MP's card is also drawn in the browser, static/card.js, in the same layout)

def chips(img, d, y, heading, words):
    """Words as chips in a panel, as many rows as they need; returns the y below."""
    x0, width, f = PAD + 28, W - 2 * PAD - 56, font("regular", 28)
    rows, rx = [[]], 0
    for w in words:
        cw = f.getlength(w) + 36
        if rx + cw > width and rows[-1]:
            rows.append([])
            rx = 0
        rows[-1].append((w, rx, cw))
        rx += cw + 12
    d.rectangle((PAD, y, W - PAD, y + 28 + 44 + len(rows) * 58 + 14), fill=SURFACE)
    ty = y + 28
    d.text((x0, ty), heading, font=font("bold", 22), fill=MUTED)
    ty += 44
    for row in rows:
        for w, rx2, cw in row:
            d.rectangle((x0 + rx2, ty, x0 + rx2 + cw, ty + 46), fill=BG)
            d.text((x0 + rx2 + 18, ty + 7), w, font=f, fill=TEXT)
        ty += 58
    return ty + 14 + GAP


# under an MP's tiles when any carries a "TOP N%" badge (sejmomat/build.py, mp_standing)
STANDING_NOTE = "TOP N% – w gronie N% obecnych posłów z najwyższym wynikiem"

SERIES_TAG = "#SejmOdADoZ"   # the A-to-Z series of MP posts (sejmomat/posts.py)


def terms_label(terms):
    """"pierwsza kadencja", "szósta kadencja", or "ósma kadencja od 1997" when
    the record reaches back to the oldest term the API has (there may be earlier ones)."""
    n = len(terms)
    word = ORDINALS[n - 1] if n <= len(ORDINALS) else f"{n}."
    return f"{word} kadencja" + (" od 1997" if n > 1 and min(terms) <= 3 else "")


def mp_term(r, photo=None, tag=None):
    """An MP's term: turnout, missed votes, breaks of the club line, speeches,
    questions to the government, amendments signed, characteristic words."""
    img = Image.new("RGB", (W, 3000), BG)
    d = ImageDraw.Draw(img)
    mp, sp, q = r["mp"], r.get("speeches") or {}, r.get("q_stats") or {}
    subtitle = " · ".join(x for x in (club_short(mp.get("club") or ""), mp.get("districtName") and f"okręg {mp['districtName']}",
                                      r.get("terms") and terms_label(r["terms"])) if x)
    kicker = "Podsumowanie kadencji · poseł na Sejm"
    if tag:
        kicker += f" · {tag}"
    y = header(img, kicker, mp["firstLastName"], subtitle, photo)
    missed, top = r["eligible"] - r["cast"], r.get("standing") or {}
    rows = [(pct(r["turnout"]), f"udział w głosowaniach ({r['cast']} z {r['eligible']})", TEXT, top.get("turnout")),
            (missed, "opuszczonych głosowań", ABSTAIN if missed else TEXT),
            (r["rebel_count"], f"wyłamań z linii klubu ({pct(r['rebel_rate'])})", TEXT),
            ((sp.get("spoken") or 0) + (sp.get("written") or 0), "wystąpień na sali plenarnej", TEXT, top.get("speeches")),
            (q.get("int", 0) + q.get("zap", 0), "interpelacji i zapytań poselskich", TEXT, top.get("questions"))]
    if r["signed"]:
        # neutral colour: whether amendments pass says more about the majority than about the MP
        rows.append((f"{r['signed_adopted']} z {len(r['signed'])}", "podpisanych poprawek i wniosków przeszło", TEXT))
    y = summary_rows(d, y, rows)
    if top:
        d.text((PAD, y - 6), STANDING_NOTE, font=font("regular", 22), fill=MUTED)
        y += 34
    words = [w for w, _, _ in sorted(sp.get("cloud") or [], key=lambda c: -c[1])][:12]
    if words:
        y = chips(img, d, y, "Charakterystyczne słowa w wystąpieniach", words)
    return footer(img, y)


def minister(t, deadline):
    """How a minister answers MPs' interpellations and written questions."""
    img = Image.new("RGB", (W, 3000), BG)
    d = ImageDraw.Draw(img)
    name = t["name"][:1].upper() + t["name"][1:]
    y = header(img, f"Jak odpowiada rząd · {TERM}. kadencja Sejmu", name,
               f"Interpelacje i zapytania poselskie; na odpowiedź minister ma {deadline} dni")
    received = t["received"] or 1
    y = summary_rows(d, y, [(t["received"], "pytań od posłów", TEXT),
                     (pct(t["answered"] / received), "z odpowiedzią", YES),
                     (f"{t['median']} dni" if t["median"] is not None else "—", "typowy czas odpowiedzi (mediana)", TEXT),
                     (t["late"], "odpowiedzi po terminie", ABSTAIN if t["late"] else TEXT),
                     (t["prolonged"], "razy przedłużono termin", TEXT),
                     (t["overdue"], "pytań bez odpowiedzi po terminie", NO if t["overdue"] else TEXT)])
    return footer(img, y)
