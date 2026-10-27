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


def club_chip(d, x, y, club, font, tag_font, now=None):
    """A club's chip in its colour, then a "Koalicja"/"Opozycja" tag, then, for a past day
    when the MP has since moved, "(obecnie: <club>)"; returns where they end."""
    cb = d.textbbox((x, y), club, font=font)
    d.rounded_rectangle((cb[0] - 8, cb[1] - 4, cb[2] + 8, cb[3] + 5), 10, fill=club_colour(club) + (255,))
    d.text((x, y), club, font=font, fill="white")
    end = cb[2] + 8
    s = side(club)
    if s:
        tx, mid = end + 14, (cb[1] + cb[3]) / 2 + 0.5
        tb = d.textbbox((tx, mid), s.upper(), font=tag_font, anchor="lm")
        coalition = s == "Koalicja"
        d.rounded_rectangle((tb[0] - 7, cb[1] - 4, tb[2] + 7, cb[3] + 5), 10,
                            fill=(255, 255, 255, 235) if coalition else (0, 0, 0, 0), outline=(255, 255, 255, 235), width=2)
        d.text((tx, mid), s.upper(), font=tag_font, fill=(12, 20, 36) if coalition else "white", anchor="lm")
        end = tb[2] + 7
    if now:
        mid = (cb[1] + cb[3]) / 2 + 0.5
        note = f"(obecnie: {now})"
        d.text((end + 10, mid), note, font=font, fill=LIGHT_BLUE, anchor="lm")
        end = d.textbbox((end + 10, mid), note, font=font, anchor="lm")[2]
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

    def base(self, item, topic, vote, chip=None, note=None):
        """A lower third in the bottom left, in the cards' style: a strip with what is on
        ("Punkt 17", "Na mównicy"), then the headline (the item, or the speaker with their
        club's chip), the topic and the vote. chip: the speaker's club."""
        key = (item, topic, vote, chip, note)
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
            tags = club_chip(ImageDraw.Draw(Image.new("RGBA", (600, 40))), 0, 8, chip, self.font(16, True), self.font(13, True), note) + 14
        want = max([f_head.getlength(headline) + tags] + [f.getlength(t) for t, f, _ in lines])
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
        y = top
        for line in heads:
            b.text((pad, y), line, font=f_head, fill="white")
            y += 30
        if chip:
            club_chip(b, pad + round(f_head.getlength(heads[0])) + 14, top + 4, chip, self.font(16, True), self.font(13, True), note)
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
        """The card without what moves (the number), drawn once."""
        key = id(card)
        if key in self._cards:
            return self._cards[key]
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
            d.text((x0, 58), card["name"], font=self.font(27, True), fill="white")
            club_chip(d, x0, 98, card["club"], self.font(16, True), self.font(13, True), card.get("now"))
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
        self._cards[key] = im
        return im

    # ---- Top 5 cards: five MPs, the rows coming in one after another
    def top5_rows(self, card):
        key = ("rows", id(card))
        if key in self._cards:
            return self._cards[key]
        rows = []
        medals = [(240, 196, 64), (196, 204, 214), (205, 127, 50)]
        for i, r in enumerate(card["rows"]):
            im = Image.new("RGBA", (528, 50), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, 527, 49), 10, fill=(255, 255, 255, 18 if i % 2 else 30))
            badge = medals[i] if i < 3 else (90, 104, 128)
            d.ellipse((8, 9, 40, 41), fill=badge + (255,))
            d.text((24, 25), str(i + 1), font=self.font(18, True), fill=(12, 20, 36) if i < 3 else "white", anchor="mm")
            photo = self.photo(r["mp"])
            if photo:
                pw, ph = 34, 42
                scale = max(pw / photo.width, ph / photo.height)
                p = photo.resize((max(1, round(photo.width * scale)), max(1, round(photo.height * scale))), Image.LANCZOS)
                p = p.crop(((p.width - pw) // 2, 0, (p.width - pw) // 2 + pw, ph))
                mask = Image.new("L", (pw, ph), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), 7, fill=255)
                im.paste(p, (50, 4), mask)
            d.text((96, 7), r["name"], font=self.font(19, True), fill="white")
            cb = d.textbbox((96, 30), r["club"], font=self.font(12, True))
            d.rounded_rectangle((cb[0] - 6, cb[1] - 2, cb[2] + 6, cb[3] + 3), 7, fill=club_colour(r["club"]) + (255,))
            d.text((96, 30), r["club"], font=self.font(12, True), fill="white")
            d.text((514, 25), r["value"], font=self.font(24, True), fill=YELLOW, anchor="rm")
            rows.append(im)
        self._cards[key] = rows
        return rows

    def top5(self, card, t, length):
        key = ("top5", id(card))
        if key not in self._cards:
            width, h = 560, 44 + 12 + len(card["rows"]) * 54 + 8   # a small club's has fewer rows
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
            else:
                d.text((width - 50, 12), "TOP", font=self.font(18, True), fill=YELLOW)
            self._cards[key] = im
        base = self._cards[key].copy()
        # each row slides in from the right, one after another
        for i, row in enumerate(self.top5_rows(card)):
            k = clamp((t - 0.5 - i * 0.18) / 0.35)
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
        still = STILL <= t <= length - 0.6
        key = (id(card), length)
        if still and key in self._stills:
            return self._stills[key]
        out = self._card(card, t, length)
        if still:
            if len(self._stills) > 20:
                self._stills.clear()
            self._stills[key] = out
        return out

    def _card(self, card, t, length):
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
            name, size = side_["name"], 40
            while size > 24 and self.font(size, True).getlength(name) > cx - 120 - (pic.width if pic else 0):
                size -= 2
            d.text((tx, 34), name, font=self.font(size, True), fill="white", anchor=anchor)
            chip = f"{side_['club']} · {side_['tag'].upper()}" if side_.get("mp") else side_["tag"].upper()
            f_chip = self.font(15, True)
            wdt = f_chip.getlength(chip)
            cx0 = tx if sign < 0 else tx - wdt
            d.rounded_rectangle((cx0 - 9, 92, cx0 + wdt + 9, 116), 9, fill=club_colour(side_["club"]) + (255,))
            d.text((cx0, 104), chip, font=f_chip, fill="white", anchor="lm")
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
        if still and key in self._stills:
            return self._stills[key]
        out = self._compare(card, t, length)
        if still:
            self._stills[key] = out
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
            win_a = va > vb if row["better"] == "more" else va < vb
            win_b = vb > va if row["better"] == "more" else vb < va
            d.rounded_rectangle((cx - 10 - la, y - 7, cx - 10, y + 7), 6, fill=(ca if win_a else mix(bg, ca, 0.45)) + (255,))
            d.rounded_rectangle((cx + 10, y - 7, cx + 10 + lb, y + 7), 6, fill=(cb if win_b else mix(bg, cb, 0.45)) + (255,))
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

    def list_scene(self, title, subtitle, rows, t, length):
        """A list over the hall in a break (the agenda, today's votes): a heading strip and up to
        nine rows of (number, text, badge, state); state "done" is dimmed, "next" lit, "adopted" /
        "rejected" colour the badge. Rows come in one after another; it fades at the end."""
        x0, y0, x1, y1 = CMP_BOX
        pw, ph = x1 - x0, y1 - y0
        key = ("list", title, subtitle, tuple(tuple(r) for r in rows))
        if key not in self._cards:
            lists = [k for k in self._cards if isinstance(k, tuple) and k[0] == "list"]
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
        base = im.copy()
        for i, r in enumerate(rows_im):
            k = clamp((t - 0.4 - i * 0.08) / 0.35)
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
        return base, x0, y0

    def frame_scene(self, scene):
        """A frame of a break: the comparison over the hall, the Sejmomat logo top right."""
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if self.logo:
            im.alpha_composite(self.logo, (W - self.logo.width - 24, 22))
        pill = self._cards.get("break-pill")
        if pill is None:
            f = self.font(17, True)
            text = "PRZERWA W OBRADACH"
            pill = Image.new("RGBA", (round(f.getlength(text)) + 40, 36), (0, 0, 0, 0))
            pd = ImageDraw.Draw(pill)
            pd.rounded_rectangle((0, 0, pill.width - 1, 35), 12, fill=(255, 212, 121, 255))
            pd.text((20, 18), text, font=f, fill=(12, 20, 36), anchor="lm")
            self._cards["break-pill"] = pill
        im.alpha_composite(pill, (CMP_BOX[0], 22))
        img, x, y = scene
        im.alpha_composite(img, (x, y))
        return im.tobytes()

    def frame(self, item, topic, vote, panel=None, card=None, chip=None, note=None):
        """One frame: the bar, then the amendment panel or the card. Returns RGBA bytes.
        Most frames are the same as the one before (nothing moves): those are not redrawn."""
        which = None if card is None else next((k for k, c in self._stills.items() if c is card), False)
        key = ((item, topic, vote, chip, note), panel and (panel[0], tuple(panel[1])), which) if which is not False else None
        if key is not None and self._last[0] == key:
            return self._last[1]
        im = self.base(item, topic, vote, chip, note).copy()
        if panel:
            p = self.panel(*panel)
            im.alpha_composite(p, (W - p.width - 24, 70))
        if card:
            c, x, y = card
            if x < W:
                # the part of the card already on screen
                im.alpha_composite(c.crop((0, 0, min(c.width, W - x), c.height)), (x, y))
        out = im.tobytes()
        self._last = (key, out)
        return out
