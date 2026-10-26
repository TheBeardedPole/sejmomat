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
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
CACHE = Path.home() / ".cache" / "sejmomat-live"
PHOTO = "https://api.sejm.gov.pl/sejm/term10/MP/{}/photo"
ACCENT = (29, 95, 196)
YELLOW = (255, 212, 121)
LIGHT_BLUE = (156, 195, 255)
RED, GREEN = (255, 154, 154), (155, 232, 171)
PANEL = (10, 16, 28, 214)
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
            # a club card: small stats along the bottom
            sx = 24
            for label, value in card["stats"][:4]:
                d.text((sx, h - 50), value, font=self.font(19, True), fill="white")
                d.text((sx, h - 26), label, font=self.font(13), fill=(170, 180, 196))
                sx += 128
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
            width, h = 560, 44 + 12 + 5 * 54 + 8
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
        size = 58 if mp else 66
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
