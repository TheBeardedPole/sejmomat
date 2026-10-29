"""The picture laid over the Sejm's stream (tools/livestream.py), drawn with
Pillow, one RGBA frame per video frame: the caption bar (agenda item, topic,
latest vote), the label and logo, the panel with what an amendment changes,
and the fun-fact cards, sports-broadcast style: the card slides in with a
little overshoot, the MP's photo pops, the number counts up, a shine sweeps
across, and it slides out again.

Static parts are drawn once and cached; a frame only redraws what moves.
"""
import io
import math
import re
import sys
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
CACHE = Path.home() / ".cache" / "sejmomat-live"
PHOTO = "https://api.sejm.gov.pl/sejm/term10/MP/{}/photo"
LOGO = "https://api.sejm.gov.pl/sejm/term10/clubs/{}/logo"   # a club's logo, small, often on white
ACCENT = (29, 95, 196)
YELLOW = (255, 212, 121)
LIGHT_BLUE = (156, 195, 255)
RED, GREEN = (255, 154, 154), (155, 232, 171)
PANEL = (10, 16, 28, 214)
CMP_BOX = (80, 72, W - 80, H - 36)   # a break's comparison: the hall stays visible around it
TEXT_SIZE, TEXT_STEP = 24, 34          # the full-screen amendment: its lines' font size and step
MINI_W, MINI_H = 360, 236              # a vote's result, small, bottom right, once the picture is back
MINI_BOX = (W - 20 - MINI_W, H - 18 - MINI_H, W - 20, H - 18)
CMP_ROWS, CMP_STEP = 214, 50          # its rows: the first label's height in the panel, and the step
BOX_MIN, BOX_MAX = 460, 820   # the caption box in the bottom left: its width, as its text needs
STILL = 1.7          # seconds into its turn after which a card stops moving
CARD_SCALE = 0.7     # cards are drawn at full size, then shrunk, so they stay out of the way
# club colours as on the stats page (the brighter, dark-background set)
CLUBS = {"KO": "#f07a45", "PiS": "#4a90e8", "RozwojPlus": "#22c08a", "Polska2050": "#f2b01c", "Polska2050-TD": "#f2b01c",
         "PSL-TD": "#2aa52a", "Lewica": "#e0457f", "Konfederacja": "#8f84ee", "Centrum": "#b39af0", "Razem": "#d063aa",
         "Demokracja": "#79acc4", "Republikanie": "#5a86d8", "Konfederacja_KP": "#a99cf0", "Kukiz15": "#9a9a9a"}


# the governing coalition (as in sejmomat/stats.py); every other club is in opposition,
# independents are neither
COALITION = {"KO", "Lewica", "Polska2050", "Polska2050-TD", "Centrum", "PSL-TD"}


def side(club):
    if not club or club.startswith("niez"):
        return None
    return "Koalicja" if club in COALITION else "Opozycja"


OPPOSITION_PILL = (54, 64, 86)   # solid: the tag must not show the video through it


def pill(d, x, cy, text, font, fill, fg="white", h=None, outline=None):
    """A pill of fixed height centred on cy, its text's capitals centred in it whatever the
    letters (a box drawn round the ink sat "KO" and "PSL-TD" differently); returns its right edge."""
    h = h or round(font.size * 1.6)
    pad = round(h * 0.38)
    w = font.getlength(text)
    top, bottom = round(cy - h / 2), round(cy - h / 2) + h
    d.rounded_rectangle((x, top, x + w + 2 * pad, bottom), h // 2, fill=fill, outline=outline, width=2 if outline else 0)
    cap = font.getbbox("H")
    d.text((x + pad, cy + (cap[3] - cap[1]) / 2), text, font=font, fill=fg, anchor="ls")
    return x + w + 2 * pad


def club_chip(d, x, cy, club, font, tag_font, now=None):
    """A club's pill in its colour, then a "Koalicja"/"Opozycja" one, then, for a past day when
    the MP has since moved, "(obecnie: <club>)", all centred on cy; returns where they end."""
    h = round(font.size * 1.6)
    end = pill(d, x, cy, club, font, club_colour(club) + (255,), h=h)
    s_ = side(club)
    if s_:
        coalition = s_ == "Koalicja"
        end = pill(d, end + 8, cy, s_.upper(), tag_font, (255, 255, 255, 255) if coalition else OPPOSITION_PILL + (255,),
                   fg=(12, 20, 36) if coalition else "white", h=h,
                   outline=None if coalition else (150, 162, 186, 255))
    if now:
        note = f"(obecnie: {now})"
        d.text((end + 10, cy), note, font=font, fill=LIGHT_BLUE, anchor="lm")
        end = d.textbbox((end + 10, cy), note, font=font, anchor="lm")[2]
    return end


def mix(a, b, k):
    """Colour a moved k of the way towards b (solid, so it can be drawn without holes)."""
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def club_colour(club):
    h = CLUBS.get(club, "#7d8794").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ease_out_back(x, s=1.70158):
    x -= 1
    return x * x * ((s + 1) * x + s) + 1


def ease_in(x):
    return x * x * x


def clamp(x):
    return max(0.0, min(1.0, x))


class Overlay:
    def __init__(self, bold, regular, logo, label):
        self._fonts = {}
        self.bold_path, self.regular_path = bold, regular
        self.logo = None
        if logo and Path(logo).exists():
            im = Image.open(logo).convert("RGBA")
            self.logo = im.resize((round(im.width * 30 / im.height), 30), Image.LANCZOS)
        self.label = label
        self._base = (None, None)
        self._panels = {}
        self._cards = {}
        self._photos = {}
        self._stills = {}       # cards in their still middle part, drawn once
        self._last = (None, None)   # (what the last frame showed, its bytes)

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(self.bold_path if bold else self.regular_path, size)
        return self._fonts[key]

    # ---- the caption box, the label and the logo: redrawn only when the text changes
    def fit(self, text, font, width):
        """The text, cut short with "…" to fit the width."""
        if font.getlength(text) <= width:
            return text
        while text and font.getlength(text + "…") > width:
            text = text[:-1]
        return text.rstrip(" ·,:") + "…"

    def name_fit(self, name, size, width, smallest=None):
        """An MP's name that fits the width: in full; else without middle names ("Magdalena
        Małgorzata Kołodziejczak" -> "Magdalena Kołodziejczak"); else smaller, down to
        `smallest`; else cut short. Returns (text, font)."""
        parts = name.split()
        tries = [name] + ([f"{parts[0]} {' '.join(parts[2:])}" if parts[1].lower() == "vel" else f"{parts[0]} {parts[-1]}"]
                          if len(parts) > 2 else [])
        # "Szymon Szynkowski vel Sęk": the double surname is kept whole
        if len(parts) > 3 and "vel" in [p.lower() for p in parts]:
            i = [p.lower() for p in parts].index("vel")
            tries = [name, f"{parts[0]} {' '.join(parts[i - 1:])}"]
        smallest = smallest or round(size * 0.8)
        for s_ in range(size, smallest - 1, -1):
            f = self.font(s_, True)
            for t in tries:
                if f.getlength(t) <= width:
                    return t, f
        f = self.font(smallest, True)
        return self.fit(tries[-1], f, width), f

    def wrap(self, text, font, width, lines=2):
        """The text in at most `lines` lines of the width, the last cut short if need be."""
        out, words = [], text.split()
        while words and len(out) < lines - 1:
            n = len(words)
            while n > 1 and font.getlength(" ".join(words[:n])) > width:
                n -= 1
            out.append(" ".join(words[:n]))
            words = words[n:]
        if words:
            out.append(self.fit(" ".join(words), font, width))
        return out

    def base(self, item, topic, vote, chip=None, note=None, chair=None):
        """A lower third in the bottom left, in the cards' style: a strip with what is on
        ("Punkt 17", "Na mównicy"), then the headline (the item, or the speaker with their
        club's chip), the topic and the vote. chip: the speaker's club."""
        key = (item, topic, vote, chip, note, chair)
        if self._base[0] == key:
            return self._base[1]
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        first = item.split("\n")[0]
        if chip:
            kicker, headline = "Na mównicy", first
        elif " · " in first:
            kicker, headline = first.split(" · ", 1)
        else:
            kicker, headline = "Debata", first
        f_head, f_line, f_kick = self.font(21, True), self.font(16), self.font(15, True)
        pad, top = 20, 44
        lines = [(t, f_line, c) for t, c in ((topic, LIGHT_BLUE), (vote, YELLOW)) if t and t.strip()]
        tags = 0
        if chip:
            # the chip and tag, drawn off-image first to measure them
            tags = club_chip(ImageDraw.Draw(Image.new("RGBA", (600, 40))), 0, 20, chip, self.font(16, True), self.font(13, True), note) + 16
        want = max([f_head.getlength(headline) + tags] + [f.getlength(t) for t, f, _ in lines])
        f_chair = self.font(13, True)
        if chair:   # the strip holds the kicker and, at its right end, who runs the sitting
            want = max(want, f_kick.getlength(kicker.upper()) + 70 + 24 + f_chair.getlength(chair.upper()))
        width = round(min(BOX_MAX, max(BOX_MIN, want + 2 * pad + 2)))
        inner = width - 2 * pad
        # a long agenda item takes two lines; a speaker's name one, with the chip after it
        heads = [self.fit(headline, f_head, inner - tags)] if chip else self.wrap(headline, f_head, inner)
        height = top + 30 * len(heads) + 2 + 24 * len(lines) + 12
        x0, y0 = 20, H - height - 18
        box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        b = ImageDraw.Draw(box)
        colour = club_colour(chip) if chip else ACCENT
        b.rounded_rectangle((0, 0, width - 1, height - 1), 16, fill=(12, 20, 36, 230))
        kick = kicker.upper()
        sw = round(f_kick.getlength(kick)) + 70
        b.polygon([(0, 0), (sw, 0), (sw - 22, 32), (0, 32)], fill=colour + (255,))
        b.rounded_rectangle((0, 0, 40, 32), 16, fill=colour + (255,))
        b.rectangle((0, 16, 40, 32), fill=colour + (255,))
        b.text((pad, 16), kick, font=f_kick, fill="white", anchor="lm")
        if chair:
            cap = f_chair.getbbox("H")
            b.text((width - pad, 16 + (cap[3] - cap[1]) / 2), self.fit(chair.upper(), f_chair, width - sw - 2 * pad),
                   font=f_chair, fill=(170, 180, 196), anchor="rs")
        y = top
        for line in heads:
            b.text((pad, y), line, font=f_head, fill="white")
            y += 30
        if chip:
            # on the name's line, centred on its capitals, a little apart from it
            cap = f_head.getbbox("H")
            club_chip(b, pad + round(f_head.getlength(heads[0])) + 16, top + (cap[1] + cap[3]) / 2, chip,
                      self.font(16, True), self.font(13, True), note)
        y += 2
        for text, f, c in lines:
            b.text((pad, y), self.fit(text, f, inner), font=f, fill=c)
            y += 24
        im.alpha_composite(box, (x0, y0))
        f = self.font(18)
        box = d.textbbox((28, 24), self.label, font=f)
        d.rounded_rectangle((box[0] - 8, box[1] - 7, box[2] + 8, box[3] + 7), 6, fill=(0, 0, 0, 153))
        d.text((28, 24), self.label, font=f, fill="white")
        if self.logo:
            im.alpha_composite(self.logo, (W - self.logo.width - 24, 22))
        self._base = (key, im)
        return im

    # ---- the panel with what an amendment changes, on a dark background
    def panel(self, head, rows):
        key = (head, tuple(rows))
        if key not in self._panels:
            if len(self._panels) > 50:
                self._panels.clear()
            width, step = 540, 25
            h = 24 + 30 + len(rows) * step + 16
            im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, width - 1, h - 1), 14, fill=PANEL)
            d.rectangle((0, 14, 4, h - 14), fill=YELLOW + (255,))
            d.text((20, 14), head, font=self.font(20, True), fill=YELLOW)
            colours = {"w": (235, 238, 245), "r": RED, "g": GREEN}
            for i, (c, line) in enumerate(rows):
                d.text((20, 50 + i * step), line, font=self.font(19), fill=colours[c])
            self._panels[key] = im
        return self._panels[key]

    # ---- fun-fact cards
    def photo(self, mp):
        if mp in self._photos:
            return self._photos[mp]
        path = CACHE / "photos" / f"{mp}.jpg"
        im = None
        try:
            if path.exists():
                im = Image.open(path).convert("RGB")
            else:
                req = urllib.request.Request(PHOTO.format(mp), headers={"User-Agent": "sejmomat-live"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = r.read()
                im = Image.open(io.BytesIO(data)).convert("RGB")
                try:   # kept for the next run; without the cache the photo is still used
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                except OSError:
                    pass
        except Exception as e:
            print(f"no photo for MP {mp}: {e}", file=sys.stderr)
        self._photos[mp] = im
        return im

    def club_logo(self, club):
        """The club's logo from the Sejm's API (kept on disk, as the photos are), or None."""
        key = ("logo", club)
        if key in self._photos:
            return self._photos[key]
        # a better logo kept in the repository (tools/logos/README.md) comes first
        local = Path(__file__).resolve().parent / "logos" / f"{club}.png"
        path = CACHE / "logos" / f"{club}.jpg"
        im = None
        try:
            if local.exists():
                im = Image.open(local).convert("RGBA")
            elif path.exists():
                im = Image.open(path).convert("RGBA")
            else:
                req = urllib.request.Request(LOGO.format(urllib.parse.quote(club)), headers={"User-Agent": "sejmomat-live"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = r.read()
                im = Image.open(io.BytesIO(data)).convert("RGBA")
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                except OSError:
                    pass
        except Exception as e:
            print(f"no logo for {club}: {e}", file=sys.stderr)
        self._photos[key] = im
        return im

    def logo_badge(self, club, size):
        """The logo on a white rounded tile `size` px square (logos come on white), or None."""
        logo = self.club_logo(club) if club else None
        if not logo:
            return None
        tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(tile).rounded_rectangle((0, 0, size - 1, size - 1), round(size * 0.2), fill=(255, 255, 255, 255))
        inner = size - round(size * 0.16)
        scale = min(inner / logo.width, inner / logo.height)
        lg = logo.resize((max(1, round(logo.width * scale)), max(1, round(logo.height * scale))), Image.LANCZOS)
        tile.alpha_composite(lg, ((size - lg.width) // 2, (size - lg.height) // 2))   # a transparent PNG too
        return tile

    def card_base(self, card):
        """The card without what moves (the number), drawn once. Kept with the card itself: an
        id is reused once its object is gone, and a new speaker's card got the last one's picture."""
        key = id(card)
        hit = self._cards.get(key)
        if hit and hit[0] is card:
            return hit[1]
        width, h = 560, 268
        im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        colour = club_colour(card.get("club")) if card.get("club") else ACCENT
        d.rounded_rectangle((0, 0, width - 1, h - 1), 16, fill=(12, 20, 36, 236))
        # the title strip in the club's colour, with a slanted end, as on a scoreboard
        d.polygon([(0, 0), (width - 60, 0), (width - 90, 44), (0, 44)], fill=colour + (255,))
        d.rounded_rectangle((0, 0, 40, 44), 16, fill=colour + (255,))
        d.text((20, 9), card["title"].upper(), font=self.font(21, True), fill="white")
        d.text((width - 50, 12), "?!", font=self.font(20, True), fill=YELLOW)
        if card["kind"] == "promo":
            # a word about the site: a headline, a line or two, the address in yellow
            d.text((24, 60), card["headline"], font=self.font(28, True), fill="white")
            for i, line in enumerate(textwrap.wrap(card.get("text") or "", 54)[:3]):
                d.text((24, 104 + i * 24), line, font=self.font(18), fill=(205, 212, 225))
            d.text((24, h - 58), card["url"], font=self.font(30, True), fill=YELLOW)
        elif card["kind"] == "mp":
            x0 = 176
            name, f_name = self.name_fit(card["name"], 27, width - x0 - 24, 22)
            d.text((x0, 58), name, font=f_name, fill="white")
            low = f_name.getbbox("gjpyŁ")[3]   # the name's lowest ink
            club_chip(d, x0, 58 + low + 12 + 13, card["club"], self.font(16, True), self.font(13, True), card.get("now"))
            # small stats along the bottom
            stats = card.get("stats") or []
            sx = x0
            for label, value in stats[:4]:
                d.text((sx, h - 50), value, font=self.font(19, True), fill="white")
                d.text((sx, h - 26), label, font=self.font(13), fill=(170, 180, 196))
                sx += 92
        elif card.get("stats"):
            # a club card: its logo beside the name (drawn with the name, _card), and its
            # figures as four tiles across the card, a large number over its label
            badge = self.logo_badge(card.get("club"), 64)
            if badge:
                im.alpha_composite(badge, (24, 54))
            stats = card["stats"][:4]
            gap, top, bottom = 10, 128, h - 18
            tile = (width - 48 - gap * (len(stats) - 1)) / max(1, len(stats))
            for i, (label, value) in enumerate(stats):
                x = 24 + i * (tile + gap)
                # solid: drawing replaces pixels rather than blending, so a see-through white would
                # punch a hole in the card down to the video; this is the card's colour lightened
                d.rounded_rectangle((x, top, x + tile, bottom), 12, fill=(30, 38, 54, 236))
                size = 34
                while size > 20 and self.font(size, True).getlength(value) > tile - 16:
                    size -= 2
                cx = x + tile / 2
                d.text((cx, top + (bottom - top) * 0.42), value, font=self.font(size, True), fill="white", anchor="mm")
                d.text((cx, top + (bottom - top) * 0.78), label.upper(), font=self.font(13, True), fill=(170, 180, 196), anchor="mm")
        else:
            for i, line in enumerate(textwrap.wrap(card.get("text") or "", 52)[:3]):
                d.text((24, h - 84 + i * 24), line, font=self.font(17), fill=(205, 212, 225))
        self._cards[key] = (card, im)
        return im

    # ---- Top 5 cards: five MPs, the rows coming in one after another
    def top5_rows(self, card):
        """A Top 5's rows, or a region card's (no ranking there: a dot in the club's colour)."""
        ranked = card.get("kind") != "region"
        key = ("rows", id(card))
        if key in self._cards:
            return self._cards[key]
        rows = []
        medals = [(240, 196, 64), (196, 204, 214), (205, 127, 50)]
        for i, r in enumerate(card["rows"]):
            im = Image.new("RGBA", (528, 50), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, 527, 49), 10, fill=(255, 255, 255, 18 if i % 2 else 30))
            if ranked:
                badge = medals[i] if i < 3 else (90, 104, 128)
                d.ellipse((8, 9, 40, 41), fill=badge + (255,))
                d.text((24, 25), str(i + 1), font=self.font(18, True), fill=(12, 20, 36) if i < 3 else "white", anchor="mm")
            else:
                d.ellipse((14, 15, 34, 35), fill=club_colour(r["club"]) + (255,))
            photo = self.photo(r["mp"])
            if photo:
                pw, ph = 34, 42
                scale = max(pw / photo.width, ph / photo.height)
                p = photo.resize((max(1, round(photo.width * scale)), max(1, round(photo.height * scale))), Image.LANCZOS)
                p = p.crop(((p.width - pw) // 2, 0, (p.width - pw) // 2 + pw, ph))
                mask = Image.new("L", (pw, ph), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), 7, fill=255)
                im.paste(p, (50, 4), mask)
            # the name, up to the number on the right
            # the name, then its club's pill on the same line, both up to the number on the right
            f_club = self.font(13, True)
            club_w = f_club.getlength(r["club"]) + 2 * round(21 * 0.38) + 12
            name, f_name = self.name_fit(r["name"], 19, 514 - 96 - 16 - club_w - self.font(24, True).getlength(r["value"]), 15)
            cap = f_name.getbbox("H")
            d.text((96, 25 + (cap[3] - cap[1]) / 2), name, font=f_name, fill="white", anchor="ls")
            pill(d, 96 + f_name.getlength(name) + 12, 25, r["club"], f_club, club_colour(r["club"]) + (255,), h=21)
            d.text((514, 25), r["value"], font=self.font(24, True), fill=YELLOW, anchor="rm")
            rows.append(im)
        self._cards[key] = rows
        return rows

    def region(self, card, t, length):
        """Posłowie z regionu: a Top 5's look, its MPs five at a time, the pages in turn (the
        card slides in and out once; each page's rows come in as a Top 5's do)."""
        pages = [card["rows"][i:i + 5] for i in range(0, len(card["rows"]), 5)] or [[]]
        per = length / len(pages)
        page = min(len(pages) - 1, int(t // per))
        key = ("region-page", id(card), page)
        if key not in self._cards:
            self._cards[key] = {**card, "rows": pages[page], "_page": f"{page + 1}/{len(pages)}" if len(pages) > 1 else ""}
        return self.top5(self._cards[key], t, length, rows_t=t - page * per if page else t)

    def top5(self, card, t, length, rows_t=None):
        key = ("top5", id(card))
        if key not in self._cards:
            width, h = 560, 44 + 12 + max(len(card["rows"]), 5 if card.get("kind") == "region" else 0) * 54 + 8   # a small club's has fewer rows
            im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, width - 1, h - 1), 16, fill=(12, 20, 36, 236))
            colour = club_colour(card["for_club"]) if card.get("for_club") else ACCENT
            d.polygon([(0, 0), (width - 60, 0), (width - 90, 44), (0, 44)], fill=colour + (255,))
            d.rounded_rectangle((0, 0, 40, 44), 16, fill=colour + (255,))
            title, size = card["title"].upper(), 21
            while size > 14 and self.font(size, True).getlength(title) > width - 120:
                size -= 1
            d.text((20, 22), title, font=self.font(size, True), fill="white", anchor="lm")
            badge = self.logo_badge(card.get("for_club"), 36) if card.get("for_club") else None
            if badge:
                im.alpha_composite(badge, (width - 50, 4))
            elif card.get("kind") == "region":
                d.text((width - 24, 22), card.get("_page") or "", font=self.font(17, True), fill=YELLOW, anchor="rm")
            else:   # a bottom five says so: it is no Top 5
                d.text((width - 50, 12), "MIN" if card.get("bottom") else "TOP", font=self.font(18, True), fill=YELLOW)
            self._cards[key] = im
        base = self._cards[key].copy()
        # each row slides in from the right, one after another
        rt = t if rows_t is None else rows_t
        for i, row in enumerate(self.top5_rows(card)):
            k = clamp((rt - 0.5 - i * 0.18) / 0.35)
            if k <= 0:
                continue
            x = 16 + round((1 - ease_out_back(k)) * 300)
            piece = row.copy()
            if k < 1:
                piece.putalpha(piece.getchannel("A").point(lambda a, k=k: round(a * min(1, k * 1.6))))
            base.alpha_composite(piece.crop((0, 0, min(piece.width, base.width - x), piece.height)), (x, 56 + i * 54))
        return self._place(base, t, length)

    def _place(self, base, t, length):
        """Shrunk, in the bottom right corner, beside the caption box, sliding in and out."""
        base = base.resize((round(base.width * CARD_SCALE), round(base.height * CARD_SCALE)), Image.LANCZOS)
        width, h = base.size
        x_end, y = W - width - 20, H - h - 18
        if t < 0.6:
            x = W + 10 - (W + 10 - x_end) * ease_out_back(clamp(t / 0.6))
        elif t > length - 0.5:
            x = x_end + (W + 10 - x_end) * ease_in(clamp((t - (length - 0.5)) / 0.5))
        else:
            x = x_end
        return base, round(x), y

    def card(self, card, t, length):
        """The card at time t (seconds) of its turn on screen: (image, x, y), or None.
        Between its entrance (number counted, photo in, shine gone, rows in: STILL s)
        and its exit a card does not move, so that part is drawn once."""
        # still between its entrance and its exit, except a card in pages (Posłowie z regionu)
        still = STILL <= t <= length - 0.6 and card.get("kind") != "region"
        key = (id(card), length)
        hit = self._stills.get(key)
        if still and hit and hit[0] is card:   # the very card, not one that came to have its id
            return hit[1]
        out = self._card(card, t, length)
        if still:
            if len(self._stills) > 20:
                self._stills.clear()
            self._stills[key] = (card, out)
        return out

    def _card(self, card, t, length):
        if card.get("kind") == "region":
            return self.region(card, t, length)
        if card.get("kind") == "top5":
            return self.top5(card, t, length)
        base = self.card_base(card).copy()
        d = ImageDraw.Draw(base)
        width, h = base.size
        if card["kind"] == "promo":
            return self._shine(base, t, length)
        # the number counts up (numbers only; "99,1%" or "261:172" are shown as they are)
        value = card["value"]
        shown = str(value)
        if isinstance(value, int):
            k = clamp((t - 0.35) / 1.1)
            shown = str(round(value * (1 - (1 - k) ** 3)))
        mp = card["kind"] == "mp"
        nx, ny = (176, 128) if mp else (24, 56)
        if card.get("stats") and not mp and self.club_logo(card.get("club")):
            nx, ny = 102, 58   # right of the club's logo
        # a club card's name, above its tiles, is a heading rather than a figure
        size = 58 if mp else 44 if card.get("stats") else 66
        # the unit sits right of the value, in at most two lines measured in pixels (a
        # count of characters let "Klub Parlamentarny Centrum" run off the card); a long
        # value (a club's name) is set smaller until the unit fits whole
        unit, f_unit = card.get("unit") or "", self.font(18)

        def unit_lines(size):
            room = width - 24 - (nx + self.font(size, True).getlength(shown) + 14)
            lines = self.wrap(unit, f_unit, room) if unit and room > 0 else []
            whole = room >= 90 and not (lines and lines[-1].endswith("…") and not unit.endswith("…"))
            return lines, whole

        lines, whole = unit_lines(size)
        while size > 30 and (not whole or self.font(size, True).getlength(shown) > width - nx - 24):
            size -= 4
            lines, whole = unit_lines(size)
        d.text((nx, ny), shown, font=self.font(size, True), fill=YELLOW)
        nb = d.textbbox((nx, ny), shown, font=self.font(size, True))
        for i, line in enumerate(lines):
            d.text((nb[2] + 14, ny + 14 + i * 22), line, font=f_unit, fill=(205, 212, 225))
        # the photo pops in with a little overshoot
        if mp:
            photo = self.photo(card["mp"])
            if photo:
                s = 0.6 + 0.4 * ease_out_back(clamp((t - 0.25) / 0.45), 2.4) if t < 0.7 else 1.0
                pw, ph = max(1, round(132 * s)), max(1, round(166 * s))
                scale = max(pw / photo.width, ph / photo.height)
                p = photo.resize((max(1, round(photo.width * scale)), max(1, round(photo.height * scale))), Image.LANCZOS)
                p = p.crop(((p.width - pw) // 2, 0, (p.width - pw) // 2 + pw, ph))
                mask = Image.new("L", (pw, ph), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), 12, fill=255)
                cx, cy = 22 + 66, 58 + 83
                base.paste(p, (cx - pw // 2, cy - ph // 2), mask)
        return self._shine(base, t, length)

    def _shine(self, base, t, length):
        """A shine sweeps across once, then the card is placed."""
        width, h = base.size
        k = (t - 0.9) / 0.6
        if 0 <= k <= 1:
            shine = Image.new("RGBA", base.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(shine)
            x = -120 + k * (width + 240)
            sd.polygon([(x, 0), (x + 50, 0), (x - 30, h), (x - 80, h)], fill=(255, 255, 255, 46))
            alpha = base.getchannel("A")
            shine.putalpha(Image.composite(shine.getchannel("A"), Image.new("L", base.size, 0), alpha))
            base.alpha_composite(shine)
        return self._place(base, t, length)

    # ---- a break in the sitting: a comparison over the hall, as a football line-up
    def compare_base(self, card):
        """The still part of a comparison: the panel, both sides, labels and headline (rows apart)."""
        key = ("compare", id(card))
        if key in self._cards:
            return self._cards[key]
        x0, y0, x1, y1 = CMP_BOX
        pw, ph = x1 - x0, y1 - y0
        im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        bg = (12, 20, 36)
        d.rounded_rectangle((0, 0, pw - 1, ph - 1), 24, fill=bg + (236,))
        cx, head = pw // 2, 172
        a, b = card["sides"]
        # the two halves of the header in the sides' colours, fading towards the middle
        for side_, sign in ((a, -1), (b, 1)):
            colour = club_colour(side_["club"])
            for i in range(cx - 40):
                k = 1 - i / (cx - 40)
                c = mix(bg, colour, 0.85 * k ** 0.8)
                x = cx - 40 - i if sign < 0 else cx + 40 + i
                d.line((x, 0, x, head), fill=c + (236,))
        d.rectangle((0, head, pw, head + 3), fill=(255, 212, 121, 255))
        for side_, sign in ((a, -1), (b, 1)):
            outer = 36 if sign < 0 else pw - 36
            anchor = "la" if sign < 0 else "ra"
            # the face or the logo, at the outer edge
            pic = None
            if side_.get("mp"):
                face = self.photo(side_["mp"])
                if face:
                    fw, fh = 104, 130
                    sc = max(fw / face.width, fh / face.height)
                    f = face.resize((max(1, round(face.width * sc)), max(1, round(face.height * sc))), Image.LANCZOS)
                    f = f.crop(((f.width - fw) // 2, 0, (f.width - fw) // 2 + fw, fh)).convert("RGBA")
                    mask = Image.new("L", (fw, fh), 0)
                    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, fh - 1), 14, fill=255)
                    pic = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
                    pic.paste(f, (0, 0), mask)
            else:
                pic = self.logo_badge(side_["club"], 112)
            px = outer if sign < 0 else outer - (pic.width if pic else 0)
            if pic:
                im.alpha_composite(pic, (px, (head - pic.height) // 2 + 4))
            tx = (outer + (pic.width + 22 if pic else 0)) if sign < 0 else (outer - (pic.width + 22 if pic else 0))
            name, f_name = self.name_fit(side_["name"], 40, cx - 120 - (pic.width if pic else 0), 26)
            d.text((tx, 34), name, font=f_name, fill="white", anchor=anchor)
            chip = f"{side_['club']} · {side_['tag'].upper()}" if side_.get("mp") else side_["tag"].upper()
            f_chip = self.font(15, True)
            wdt = f_chip.getlength(chip) + 2 * round(26 * 0.38)
            pill(d, tx if sign < 0 else tx - wdt, 104, chip, f_chip, club_colour(side_["club"]) + (255,), h=26)
            d.text((tx, 128), side_.get("sub") or "", font=self.font(17), fill=(205, 212, 225), anchor=anchor)
        # VS in a ring in the middle
        d.ellipse((cx - 40, head // 2 - 40, cx + 40, head // 2 + 40), fill=bg + (255,), outline=(255, 212, 121, 255), width=3)
        d.text((cx, head // 2), "VS", font=self.font(32, True), fill=(255, 212, 121), anchor="mm")
        for i, row in enumerate(card["rows"]):
            y = CMP_ROWS + i * CMP_STEP
            d.text((cx, y), row["label"].upper(), font=self.font(14, True), fill=(170, 180, 196), anchor="mm")
        d.text((cx, ph - 74), card.get("headline") or "", font=self.font(26, True), fill="white", anchor="mm")
        d.text((cx, ph - 40), card.get("sub") or "", font=self.font(15), fill=(170, 180, 196), anchor="mm")
        self._cards[key] = im
        return im

    def compare(self, card, t, length):
        """The comparison at time t of its turn: (image, x, y). The panel rises in, the rows
        come in one after another from the middle, and it all fades at the end; in between it
        does not move, so that part is drawn once."""
        still = 2.4 <= t <= length - 0.6
        key = ("compare-still", id(card))
        hit = self._stills.get(key)
        if still and hit and hit[0] is card:
            return hit[1]
        out = self._compare(card, t, length)
        if still:
            self._stills[key] = (card, out)
        return out

    def _compare(self, card, t, length):
        base = self.compare_base(card).copy()
        d = ImageDraw.Draw(base)
        pw = base.width
        cx, half = pw // 2, 330
        bg = (12, 20, 36)
        a, b = card["sides"]
        ca, cb = club_colour(a["club"]), club_colour(b["club"])
        if ca == cb or sum(abs(p - q) for p, q in zip(ca, cb)) < 60:
            cb = mix(cb, (255, 255, 255), 0.45)   # two sides of one colour: the right one lighter
        for i, row in enumerate(card["rows"]):
            k = ease_out_back(clamp((t - 0.45 - i * 0.12) / 0.5), 1.2)
            if k <= 0:
                continue
            y = CMP_ROWS + i * CMP_STEP + 22
            va, vb = row["a"], row["b"]
            tot = (va + vb) or 1
            la, lb = max(4, round(half * va / tot * min(1, k))), max(4, round(half * vb / tot * min(1, k)))
            # "none" (breaks of the club line): more is neither better nor worse, so no side is lit
            better = row["better"]
            win_a = better != "none" and (va > vb if better == "more" else va < vb)
            win_b = better != "none" and (vb > va if better == "more" else vb < va)
            even = 0.7 if better == "none" else 0.45
            d.rounded_rectangle((cx - 10 - la, y - 7, cx - 10, y + 7), 6, fill=(ca if win_a else mix(bg, ca, even)) + (255,))
            d.rounded_rectangle((cx + 10, y - 7, cx + 10 + lb, y + 7), 6, fill=(cb if win_b else mix(bg, cb, even)) + (255,))
            fa, fb = self.font(30, True), self.font(30, True)
            d.text((cx - half - 34, y), row["show"][0], font=fa, fill=YELLOW if win_a else (236, 238, 245), anchor="rm")
            d.text((cx + half + 34, y), row["show"][1], font=fb, fill=YELLOW if win_b else (236, 238, 245), anchor="lm")
        # in: rising and fading in; out: fading
        x0, y0, _, _ = CMP_BOX
        if t < 0.5:
            k = ease_out_back(clamp(t / 0.5), 1.0)
            y0 += round((1 - k) * 40)
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp(t / 0.35): round(v * k)))
        elif t > length - 0.6:
            k = clamp((length - t) / 0.6)
            base.putalpha(base.getchannel("A").point(lambda v, k=k: round(v * k)))
        return base, x0, y0

    def list_scene(self, title, subtitle, rows, t, length, rows_t=None):
        """A list over the hall in a break (the agenda, today's votes): a heading strip and up to
        nine rows of (number, text, badge, state); state "done" is dimmed, "next" lit, "adopted" /
        "rejected" colour the badge. Rows come in one after another; it fades at the end."""
        x0, y0, x1, y1 = CMP_BOX
        pw, ph = x1 - x0, y1 - y0
        key = ("list", title, subtitle, tuple(tuple(r) for r in rows))
        if key not in self._cards:
            lists = [k for k in self._cards if isinstance(k, tuple) and k[0] in ("list", "list-still")]
            if len(lists) > 8:   # the agenda and the votes change as the day goes: drop the old ones
                for k in lists:
                    del self._cards[k]
            im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            bg = (12, 20, 36)
            d.rounded_rectangle((0, 0, pw - 1, ph - 1), 24, fill=bg + (236,))
            for i in range(pw):   # the heading strip, the accent fading to the right
                d.line((i, 0, i, 96), fill=mix(bg, ACCENT, 0.9 * (1 - i / pw) ** 0.7) + (236,))
            d.rectangle((0, 96, pw, 99), fill=YELLOW + (255,))
            d.text((36, 30), title.upper(), font=self.font(34, True), fill="white")
            d.text((pw - 36, 48), subtitle, font=self.font(18), fill=(215, 222, 235), anchor="rm")
            rows_im = []
            for number, text, badge, state in rows[:9]:
                r = Image.new("RGBA", (pw - 48, 50), (0, 0, 0, 0))
                rd = ImageDraw.Draw(r)
                lit = state == "next"
                rd.rounded_rectangle((0, 0, r.width - 1, 49), 12, fill=(mix(bg, ACCENT, 0.55) if lit else mix(bg, (255, 255, 255), 0.06)) + (255,))
                dim = state == "done"
                rd.text((18, 25), number, font=self.font(20, True), fill=(140, 150, 168) if dim else YELLOW, anchor="lm")
                f = self.font(19, lit)
                room = r.width - 110 - (f.getlength(badge) + 40 if badge else 0)
                rd.text((96, 25), self.fit(text, f, room), font=f, fill=(150, 160, 178) if dim else (240, 242, 248), anchor="lm")
                if badge:
                    fb = self.font(15, True)
                    bw = fb.getlength(badge)
                    colour = {"adopted": (40, 150, 90), "rejected": (190, 60, 60), "next": (255, 212, 121), "done": (70, 80, 98)}.get(state, (70, 80, 98))
                    bx = r.width - 18 - bw
                    rd.rounded_rectangle((bx - 10, 12, r.width - 8, 38), 9, fill=colour + (255,))
                    rd.text((bx, 25), badge, font=fb, fill=(12, 20, 36) if state == "next" else "white", anchor="lm")
                rows_im.append(r)
            self._cards[key] = (im, rows_im)
        im, rows_im = self._cards[key]
        rt0 = t if rows_t is None else rows_t
        settled = rt0 > 0.4 + len(rows_im) * 0.08 + 0.4 and 0.5 <= t <= length - 0.6
        skey = ("list-still", key)
        if settled and skey in self._cards:
            return self._cards[skey]
        base = im.copy()
        rt = t if rows_t is None else rows_t   # a new page: its rows come in again
        for i, r in enumerate(rows_im):
            k = clamp((rt - 0.4 - i * 0.08) / 0.35)
            if k <= 0:
                continue
            piece = r.copy()
            if k < 1:
                piece.putalpha(piece.getchannel("A").point(lambda a, k=k: round(a * k)))
            base.alpha_composite(piece, (24 + round((1 - ease_out_back(k)) * 60), 118 + i * 56))
        if t < 0.5:
            y0 += round((1 - ease_out_back(clamp(t / 0.5), 1.0)) * 40)
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp(t / 0.35): round(v * k)))
        elif t > length - 0.6:
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp((length - t) / 0.6): round(v * k)))
        if settled:
            self._cards[skey] = (base, x0, y0)
        return base, x0, y0

    def hall_scene(self, key, title, subtitle, seats, order, legend, t, length, badge=None, area=None, side=None, note=None):
        """The Sejm's chamber over the hall in a break: every seat (seats: [(x, y, colour)], x and
        y from 0 to 1 as on the Chancellery's plan, colour None for an empty seat), lit one after
        another in `order` (seat indices) over the scene's first seconds, and under it a legend
        whose figures rise with them: legend(p) -> [(colour, label)] for p from 0 to 1. A frame
        draws only the seats new since the last (the panel kept between frames), and once all
        are in the same frame stands still. area: where in the panel the seats go (x0, y0, x1, y1);
        side(draw, t) draws more on each frame (the clubs beside a vote) and returns True once it
        stands still."""
        x0, y0, x1, y1 = CMP_BOX
        pw, ph = x1 - x0, y1 - y0
        GROW = 2.6   # seconds for all the seats to come in
        p = clamp((t - 0.5) / GROW)
        n = round(p * len(order))
        st = self._cards.get(("hall", key))
        if st is None:
            for k in [k for k in self._cards if isinstance(k, tuple) and k[0] in ("hall", "hall-still")]:
                del self._cards[k]
            im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            bg = (12, 20, 36)
            d.rounded_rectangle((0, 0, pw - 1, ph - 1), 24, fill=bg + (236,))
            for i in range(pw):   # the heading strip, as the lists have it
                d.line((i, 0, i, 96), fill=mix(bg, ACCENT, 0.9 * (1 - i / pw) ** 0.7) + (236,))
            d.rectangle((0, 96, pw, 99), fill=YELLOW + (255,))
            d.text((36, 12), title.upper(), font=self.font(32, True), fill="white")
            nw = round(self.font(18, True).getlength(note)) + 24 if note else 0
            d.text((36, 76), self.fit(subtitle, self.font(18), pw - 72 - max(nw, 240 if badge else 0)), font=self.font(18),
                   fill=(215, 222, 235), anchor="lm")
            if note:   # what the result means, where it reads the other way round (a motion to reject)
                d.text((pw - 36, 78), note, font=self.font(18, True), fill=YELLOW, anchor="rm")
            if badge:
                text, colour = badge
                fb = self.font(20, True)
                bw = fb.getlength(text)
                by = 14 if note else 32   # above the note, when there is one
                d.rounded_rectangle((pw - 36 - bw - 24, by, pw - 36, by + 36), 12, fill=colour + (255,))
                d.text((pw - 36 - bw - 12, by + 18), text, font=fb, fill="white", anchor="lm")
            # the seats' places: the plan fitted into the panel under the heading, above the legend
            xs, ys = [q[0] for q in seats], [q[1] for q in seats]
            ax0, ay0, ax1, ay1 = area or (40, 118, pw - 40, ph - 70)
            sx = (ax1 - ax0) / (max(xs) - min(xs))
            sy = (ay1 - ay0) / (max(ys) - min(ys))
            k = min(sx, sy * 1.0)
            ox = ax0 + ((ax1 - ax0) - (max(xs) - min(xs)) * k) / 2
            oy = ay0 + ((ay1 - ay0) - (max(ys) - min(ys)) * k) / 2
            size = max(6, round(k * 0.0095))
            boxes = [(round(ox + (x - min(xs)) * k), round(oy + (y - min(ys)) * k)) for x, y, _ in seats]
            for (bx, by), (_, _, c) in zip(boxes, seats):   # the empty plan, faint
                d.rounded_rectangle((bx - size // 2, by - size // 2, bx + size // 2, by + size // 2), 2, fill=(36, 48, 70, 255))
            st = {"im": im, "drawn": 0, "boxes": boxes, "size": size}
            self._cards[("hall", key)] = st
        if n >= len(order) and ("hall-still", key) in self._cards and 0.5 <= t <= length - 0.6:
            return self._cards[("hall-still", key)]
        d = ImageDraw.Draw(st["im"])
        half = st["size"] // 2
        for i in order[st["drawn"]:n]:   # only the seats new since the last frame
            c = seats[i][2]
            if c is None:
                continue
            bx, by = st["boxes"][i]
            d.rounded_rectangle((bx - half, by - half, bx + half, by + half), 2, fill=c + (255,))
        st["drawn"] = max(st["drawn"], n)
        base = st["im"].copy()
        bd = ImageDraw.Draw(base)
        # the legend, its figures rising with the seats
        f = self.font(19, True)
        x = 40
        for colour, label in legend(p):
            bd.rounded_rectangle((x, ph - 46, x + 16, ph - 30), 4, fill=colour + (255,))
            bd.text((x + 24, ph - 38), label, font=f, fill=(236, 238, 245), anchor="lm")
            x += 24 + round(f.getlength(label)) + 28
        done = side(bd, t) if side else True
        if t < 0.5:
            y0 += round((1 - ease_out_back(clamp(t / 0.5), 1.0)) * 40)
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp(t / 0.35): round(v * k)))
        elif t > length - 0.6:
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp((length - t) / 0.6): round(v * k)))
        elif n >= len(order) and done:
            self._cards[("hall-still", key)] = (base, x0, y0)
        return base, x0, y0

    def text_scene(self, key, title, subtitle, rows, t, length, badge=None, fade=(True, True)):
        """Lines of text over the hall, large (what an amendment changes, full screen): rows of
        (colour, line), "w" white, "r" removed, "g" added. fade: (in, out), so pages in a row do not
        each fade."""
        x0, y0, x1, y1 = CMP_BOX
        pw, ph = x1 - x0, y1 - y0
        ck = ("text", key, title, subtitle, tuple(rows), badge)
        im = self._cards.get(ck)
        if im is None:
            for k in [k for k in self._cards if isinstance(k, tuple) and k[0] == "text"]:
                del self._cards[k]
            im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            bg = (12, 20, 36)
            d.rounded_rectangle((0, 0, pw - 1, ph - 1), 24, fill=bg + (236,))
            for i in range(pw):
                d.line((i, 0, i, 96), fill=mix(bg, ACCENT, 0.9 * (1 - i / pw) ** 0.7) + (236,))
            d.rectangle((0, 96, pw, 99), fill=YELLOW + (255,))
            d.text((36, 12), self.fit(title.upper(), self.font(32, True), pw - 72 - (240 if badge else 0)),
                   font=self.font(32, True), fill="white")
            d.text((36, 76), self.fit(subtitle, self.font(18), pw - 72), font=self.font(18), fill=(215, 222, 235), anchor="lm")
            if badge:
                text, colour = badge
                fb = self.font(20, True)
                bw = fb.getlength(text)
                d.rounded_rectangle((pw - 36 - bw - 24, 32, pw - 36, 68), 12, fill=colour + (255,))
                d.text((pw - 36 - bw - 12, 50), text, font=fb, fill="white", anchor="lm")
            colours = {"w": (235, 238, 245), "r": RED, "g": GREEN}
            f = self.font(TEXT_SIZE)
            for i, (c, line) in enumerate(rows):
                if c in "rg":   # a faint band behind removed and added lines, as on the site
                    d.rectangle((24, 124 + i * TEXT_STEP - 4, pw - 24, 124 + (i + 1) * TEXT_STEP - 6),
                                fill=mix(bg, (200, 60, 60) if c == "r" else (50, 160, 80), 0.22) + (255,))
                d.text((36, 124 + i * TEXT_STEP), line, font=f, fill=colours[c])
            self._cards[ck] = im
        if fade[0] and t < 0.4:
            base = im.copy()
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp(t / 0.35): round(v * k)))
            return base, x0, y0 + round((1 - ease_out_back(clamp(t / 0.4), 1.0)) * 30)
        if fade[1] and t > length - 0.6:
            base = im.copy()
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp((length - t) / 0.6): round(v * k)))
            return base, x0, y0
        return im, x0, y0

    def mini_vote(self, key, title, subtitle, seats, totals, badge, note=None):
        """A vote's result in a small window (MINI_BOX): its number and result, the chamber seat by
        seat, the four totals. seats as for hall_scene; totals [(colour, label)]."""
        ck = ("mini", key)
        im = self._cards.get(ck)
        if im is not None:
            return im
        for k in [k for k in self._cards if isinstance(k, tuple) and k[0] == "mini"]:
            del self._cards[k]
        im = Image.new("RGBA", (MINI_W, MINI_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        bg = (12, 20, 36)
        d.rounded_rectangle((0, 0, MINI_W - 1, MINI_H - 1), 16, fill=bg + (230,))
        for i in range(MINI_W):
            d.line((i, 0, i, 50), fill=mix(bg, ACCENT, 0.9 * (1 - i / MINI_W) ** 0.7) + (230,))
        d.rectangle((0, 50, MINI_W, 52), fill=YELLOW + (255,))
        text, colour = badge
        fb = self.font(14, True)
        bw = fb.getlength(text)
        d.rounded_rectangle((MINI_W - 14 - bw - 16, 10, MINI_W - 14, 34), 8, fill=colour + (255,))
        d.text((MINI_W - 14 - bw - 8, 22), text, font=fb, fill="white", anchor="lm")
        d.text((16, 8), self.fit(title.upper(), self.font(18, True), MINI_W - 50 - bw), font=self.font(18, True), fill="white")
        d.text((16, 40), self.fit(note or subtitle, self.font(13, bool(note)), MINI_W - 32), font=self.font(13, bool(note)),
               fill=YELLOW if note else (215, 222, 235), anchor="lm")
        xs, ys = [q[0] for q in seats], [q[1] for q in seats]
        ax0, ay0, ax1, ay1 = 20, 62, MINI_W - 20, MINI_H - 52
        k = min((ax1 - ax0) / (max(xs) - min(xs)), (ay1 - ay0) / (max(ys) - min(ys)))
        ox = ax0 + ((ax1 - ax0) - (max(xs) - min(xs)) * k) / 2
        oy = ay0 + ((ay1 - ay0) - (max(ys) - min(ys)) * k) / 2
        for x, y, c in seats:
            bx, by = round(ox + (x - min(xs)) * k), round(oy + (y - min(ys)) * k)
            d.rectangle((bx - 1, by - 1, bx + 2, by + 2), fill=(c or (36, 48, 70)) + (255,))
        f = self.font(14, True)
        for i, (c, label) in enumerate(totals):   # two by two
            x, y = 18 + (i % 2) * 168, MINI_H - 42 + (i // 2) * 20
            d.rounded_rectangle((x, y - 5, x + 10, y + 5), 3, fill=c + (255,))
            d.text((x + 16, y), label, font=f, fill=(236, 238, 245), anchor="lm")
        self._cards[ck] = im
        return im

    def frame_scene(self, scene, clock=None, label="PRZERWA W OBRADACH"):
        """A frame of a break: the comparison over the hall, the Sejmomat logo top right. A scene
        standing still (the same image, from a cache) gives the same frame, not one composed anew."""
        key = ("scene", id(scene[0]), scene[1], scene[2], clock, label)
        if self._last[0] == key:
            return self._last[1]
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if self.logo:
            im.alpha_composite(self.logo, (W - self.logo.width - 24, 22))
        pill = self._cards.get(("pill", label))
        if pill is None:
            f = self.font(17, True)
            text = label
            pill = Image.new("RGBA", (round(f.getlength(text)) + 40, 36), (0, 0, 0, 0))
            pd = ImageDraw.Draw(pill)
            pd.rounded_rectangle((0, 0, pill.width - 1, 35), 12, fill=(255, 212, 121, 255))
            pd.text((20, 18), text, font=f, fill=(12, 20, 36), anchor="lm")
            self._cards[("pill", label)] = pill
        im.alpha_composite(pill, (CMP_BOX[0], 22))
        if clock:   # beside the break's pill
            d = ImageDraw.Draw(im)
            fb = self.font(18, True)
            cap = fb.getbbox("0")
            x = CMP_BOX[0] + pill.width + 10
            d.rounded_rectangle((x, 22, x + fb.getlength(clock) + 24, 58), 12, fill=(12, 20, 36, 230))
            d.text((x + 12, 40 + (cap[3] - cap[1]) / 2), clock, font=fb, fill=YELLOW, anchor="ls")
        img, x, y = scene
        im.alpha_composite(img, (x, y))
        out = im.tobytes()
        self._last = (key, out, scene)   # the scene kept, so its id stays its own
        return out

    def clock_pill(self, im, clock):
        """The picture's time, HH:MM, beside the label top left (that is the time "Na mównicy
        od" and the votes are given in; live it is the picture's, ~100 s behind the wall)."""
        if not clock:
            return
        d = ImageDraw.Draw(im)
        f = self.font(18)
        lb = d.textbbox((28, 24), self.label, font=f)
        top, bottom = lb[1] - 7, lb[3] + 7   # the label's own box (base), so the two sit in one line
        right = lb[2] + 8
        fb = self.font(18, True)
        cap = fb.getbbox("0")
        w = fb.getlength(clock)
        d.rounded_rectangle((right + 8, top, right + 8 + w + 22, bottom), 6, fill=(255, 212, 121, 255))
        d.text((right + 19, (top + bottom) / 2 + (cap[3] - cap[1]) / 2), clock, font=fb, fill=(12, 20, 36), anchor="ls")

    def promo_scene(self, card, t, length):
        """A full-screen word about the site in a break (Sejmdle, buycoffee), in the panel over
        the hall: a picture on the left, the headline, a line or two, the address."""
        x0, y0, x1, y1 = CMP_BOX
        pw, ph = x1 - x0, y1 - y0
        key = ("promo-scene", card["url"])
        if key not in self._cards:
            im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            bg = (12, 20, 36)
            d.rounded_rectangle((0, 0, pw - 1, ph - 1), 24, fill=bg + (236,))
            game = "sejmdle" in card["url"]
            accent = (39, 122, 76) if game else (201, 147, 10)
            for i in range(28, pw - 28):   # inside the rounded corners
                d.line((i, 0, i, 6), fill=mix(bg, accent, 0.9 * (1 - i / pw) ** 0.6) + (255,))
            cx, cy = 250, ph // 2
            if game:
                # the game's name as its tiles, in the clues' colours
                colours = [(39, 122, 76), (201, 147, 10), (107, 107, 112), (39, 122, 76), (184, 84, 26), (39, 121, 184), (39, 122, 76)]
                size, gap = 54, 8
                for i, (ch, c) in enumerate(zip("SEJMDLE", colours)):
                    row, col = divmod(i, 4) if i < 4 else (1, i - 4)
                    x = cx - (4 * size + 3 * gap) // 2 + col * (size + gap) + (0 if row == 0 else (size + gap) // 2)
                    y = cy - size - gap // 2 + row * (size + gap)
                    d.rounded_rectangle((x, y, x + size, y + size), 10, fill=c + (255,))
                    d.text((x + size // 2, y + size // 2), ch, font=self.font(30, True), fill="white", anchor="mm")
            else:
                # a cup of coffee, drawn
                d.rounded_rectangle((cx - 80, cy - 40, cx + 60, cy + 90), 26, fill=(236, 238, 245, 255))
                d.rounded_rectangle((cx + 40, cy - 10, cx + 110, cy + 55), 28, outline=(236, 238, 245, 255), width=14)
                d.ellipse((cx - 76, cy - 52, cx + 56, cy - 26), fill=(120, 72, 40, 255))
                for k in (-40, 0, 40):
                    d.arc((cx - 30 + k - 12, cy - 140, cx - 30 + k + 12, cy - 70), 250, 110, fill=(200, 206, 220, 255), width=5)
            tx = 470
            d.text((tx, 120), card["title"].upper(), font=self.font(18, True), fill=accent if not game else (155, 232, 171))
            for i, line in enumerate(self.wrap(card["headline"], self.font(42, True), pw - tx - 40, 2)):
                d.text((tx, 160 + i * 52), line, font=self.font(42, True), fill="white")
            for i, line in enumerate(self.wrap(card.get("text") or "", self.font(22), pw - tx - 40, 3)):
                d.text((tx, 290 + i * 32), line, font=self.font(22), fill=(205, 212, 225))
            d.text((tx, ph - 120), card["url"], font=self.font(40, True), fill=YELLOW)
            self._cards[key] = im
        if 0.5 <= t <= length - 0.6:   # standing: the image as it is, not a copy each frame
            return self._cards[key], x0, y0
        base = self._cards[key].copy()
        if t < 0.5:
            y0 += round((1 - ease_out_back(clamp(t / 0.5), 1.0)) * 40)
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp(t / 0.35): round(v * k)))
        elif t > length - 0.6:
            base.putalpha(base.getchannel("A").point(lambda v, k=clamp((length - t) / 0.6): round(v * k)))
        return base, x0, y0

    def frame(self, item, topic, vote, panel=None, card=None, chip=None, note=None, clock=None, chair=None, mini=None):
        """One frame: the bar, then the amendment panel or the card. Returns RGBA bytes.
        Most frames are the same as the one before (nothing moves): those are not redrawn."""
        which = None if card is None else next((k for k, c in self._stills.items() if c[1] is card), False)
        key = ((item, topic, vote, chip, note, clock, chair), panel and (panel[0], tuple(panel[1])), which,
               mini and (id(mini[0]), mini[1], mini[2])) if which is not False else None
        if key is not None and self._last[0] == key:
            return self._last[1]
        im = self.base(item, topic, vote, chip, note, chair).copy()
        self.clock_pill(im, clock)
        if panel:
            p = self.panel(*panel)
            im.alpha_composite(p, (W - p.width - 24, 70))
        if mini:
            m, x, y = mini
            im.alpha_composite(m, (x, y))
        if card:
            c, x, y = card
            if x < W:
                # the part of the card already on screen
                im.alpha_composite(c.crop((0, 0, min(c.width, W - x), c.height)), (x, y))
        out = im.tobytes()
        self._last = (key, out)
        return out
