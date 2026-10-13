"""A voting day's summary as an image (PNG) for social media.

The card shows what the text posts say (see social.py): the day's figures,
the most contested vote on a law and whose amendments passed, with the
site's address in the footer. Needs Pillow and one of the fonts in FONTS.
"""
from functools import cache

from PIL import Image, ImageDraw, ImageFont

from .i18n import date_fmt
from .config import SITE_URL
from .social import CARD_DIR, LINE_LABELS, PROPOSER_ROWS, club_short, short_title

# Tried in order; the first one installed is used.
FONTS = {
    "regular": ("NotoSans-Regular.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"),
    "bold": ("NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"),
}
W, MIN_H = 1200, 675   # at least 16:9; taller when the day has more to show
PAD, GAP, FOOT = 64, 20, 132
# the site's light theme (static/style.css)
BG, SURFACE, TEXT, MUTED, LINE = "#fbfaf8", "#ffffff", "#1d1d1f", "#6b6b70", "#e4e2dd"
YES, NO, ABSTAIN, SPLIT = "#1f7a4d", "#b3261e", "#9a6b00", "#8a8a8f"
FOOT_BG, FOOT_TEXT, FOOT_MUTED = "#1d5fc4", "#ffffff", "#d3e2f8"   # the site's accent colour
LINE_COLOR = {"Y": YES, "N": NO, "A": ABSTAIN, "split": SPLIT}


@cache
def font(weight, size):
    for name in FONTS[weight]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise RuntimeError(f"no font for the summary images; install one of: {', '.join(FONTS[weight])}")


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


def render(s):
    """The card for one summary (as built by social.summarize)."""
    img = Image.new("RGB", (W, 3000), BG)
    d = ImageDraw.Draw(img)
    inner = W - 2 * PAD

    # header
    y = PAD - 8
    d.text((PAD, y), "PODSUMOWANIE DNIA W SEJMIE", font=font("bold", 24), fill=MUTED)
    y += 40
    d.text((PAD, y), date_fmt("pl")(s["day"]), font=font("bold", 68), fill=TEXT)
    y += 92
    d.text((PAD, y), f"{s['sitting']}. posiedzenie Sejmu", font=font("regular", 30), fill=MUTED)
    y += 64

    # figures, three to a row
    tile_w, tile_h = (inner - 2 * GAP) // 3, 172
    for i, (number, label, color) in enumerate(_tiles(s)):
        x, ty = PAD + (i % 3) * (tile_w + GAP), y + (i // 3) * (tile_h + GAP)
        d.rounded_rectangle((x, ty, x + tile_w, ty + tile_h), 18, fill=SURFACE, outline=LINE, width=2)
        d.text((x + 24, ty + 12), str(number), font=font("bold", 60), fill=color)
        for k, line in enumerate(wrap(label, font("regular", 24), tile_w - 48, max_lines=2)):
            d.text((x + 24, ty + 94 + k * 31), line, font=font("regular", 24), fill=MUTED)
    y += -(-len(_tiles(s)) // 3) * (tile_h + GAP) + GAP

    def panel(height):
        d.rounded_rectangle((PAD, y, W - PAD, y + height), 18, fill=SURFACE, outline=LINE, width=2)

    # the most contested vote on a law
    law = s["mostContestedLaw"]
    if law:
        x, width = PAD + 28, inner - 56
        title = wrap(short_title(law["title"]), font("bold", 34), width, max_lines=2)
        sides = [(k, label, ", ".join(law["lines"][k])) for k, label in LINE_LABELS if law["lines"].get(k)]
        side_lines = [wrap(clubs, font("regular", 26), width, first_indent=font("bold", 26).getlength(f"{label}: "))
                      for _, label, clubs in sides]
        panel(28 + 38 + len(title) * 46 + 14 + 26 + 16 + 40 + 10 + sum(len(l) for l in side_lines) * 36 + 22)
        ty = y + 28
        d.text((x, ty), "NAJBARDZIEJ SPORNE GŁOSOWANIE NAD USTAWĄ", font=font("bold", 22), fill=MUTED)
        ty += 38
        for line in title:
            d.text((x, ty), line, font=font("bold", 34), fill=TEXT)
            ty += 46
        ty += 14
        # the result as a bar: for, against, abstained
        parts = [(law["yes"], YES, "za"), (law["no"], NO, "przeciw"), (law["abstain"], ABSTAIN, "wstrz.")]
        total, bx = sum(p[0] for p in parts) or 1, 0
        bar, mask = Image.new("RGB", (width, 26), LINE), Image.new("L", (width, 26), 0)
        for n, color, _ in parts:
            seg = round(width * n / total)
            ImageDraw.Draw(bar).rectangle((bx, 0, bx + seg, 26), fill=color)
            bx += seg
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, 25), 13, fill=255)
        img.paste(bar, (x, ty), mask)
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
        d.text((x, ty), "CZYJE POPRAWKI PRZESZŁY?", font=font("bold", 22), fill=MUTED)
        d.text((x + width, ty), "przyjęte / głosowane", font=font("regular", 22), fill=MUTED, anchor="ra")
        ty += 44
        for i, (name, adopted, voted) in enumerate(shown):
            cx, cy = x + (i // per_col) * (col_w + 48), ty + (i % per_col) * 46
            value = f"{adopted}/{voted}"
            d.text((cx + col_w, cy), value, font=font("bold", 26), fill=TEXT, anchor="ra")
            bar_x, bar_w = cx + col_w - 110 - 150, 150
            d.text((cx, cy), wrap(name, font("regular", 26), bar_x - cx - 16, max_lines=1)[0], font=font("regular", 26), fill=TEXT)
            d.rounded_rectangle((bar_x, cy + 13, bar_x + bar_w, cy + 25), 6, fill=LINE)
            if adopted:
                d.rounded_rectangle((bar_x, cy + 13, bar_x + max(12, round(bar_w * adopted / voted)), cy + 25), 6, fill=YES)
        y = ty + per_col * 46 + 18 + GAP

    # footer: a band in the site's colour that says where to find the rest
    height = max(MIN_H, y + PAD - GAP + FOOT)
    img = img.crop((0, 0, W, height))
    d = ImageDraw.Draw(img)
    d.rectangle((0, height - FOOT, W, height), fill=FOOT_BG)
    mid, lead = height - FOOT // 2 + 16, "Zobacz więcej na "   # the text's baseline
    d.text((PAD, mid), lead, font=font("regular", 36), fill=FOOT_TEXT, anchor="ls")
    d.text((PAD + font("regular", 36).getlength(lead), mid), "sejmomat.pl", font=font("bold", 50), fill=FOOT_TEXT, anchor="ls")
    d.text((W - PAD, mid), "Dane: API Sejmu RP", font=font("regular", 24), fill=FOOT_MUTED, anchor="rs")
    return img


def write_cards(summaries, site):
    """Write CARD_DIR/<day>.png for every summary and note it in the summary
    as "image" (its address) and "imageSize"."""
    (site / CARD_DIR).mkdir(parents=True, exist_ok=True)
    for s in summaries:
        img = render(s)
        img.save(site / CARD_DIR / f"{s['day']}.png", optimize=True)
        s["image"], s["imageSize"] = f"{SITE_URL}{CARD_DIR}/{s['day']}.png", list(img.size)
