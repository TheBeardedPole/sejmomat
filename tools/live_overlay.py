"""The picture laid over the Sejm's stream (tools/livestream.py), drawn with
Pillow, one RGBA frame per video frame: the caption bar (agenda item, topic,
latest vote), the label and logo, the panel with what an amendment changes,
and the fun-fact cards, sports-broadcast style: the card slides in with a
little overshoot, the MP's photo pops, the number counts up, a shine sweeps
across, and it slides out again.

Static parts are drawn once and cached; a frame only redraws what moves.
"""
import math
import re
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
# club colours as on the stats page (the brighter, dark-background set)
CLUBS = {"KO": "#f07a45", "PiS": "#4a90e8", "RozwojPlus": "#22c08a", "Polska2050": "#f2b01c", "Polska2050-TD": "#f2b01c",
         "PSL-TD": "#2aa52a", "Lewica": "#e0457f", "Konfederacja": "#8f84ee", "Centrum": "#b39af0", "Razem": "#d063aa",
         "Demokracja": "#79acc4", "Republikanie": "#5a86d8", "Konfederacja_KP": "#a99cf0", "Kukiz15": "#9a9a9a"}


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

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(self.bold_path if bold else self.regular_path, size)
        return self._fonts[key]

    # ---- the caption bar, the label and the logo: redrawn only when the text changes
    def base(self, item, topic, vote):
        key = (item, topic, vote)
        if self._base[0] == key:
            return self._base[1]
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        bar = 172
        d.rectangle((0, H - bar, W, H), fill=(0, 0, 0, 184))
        d.rectangle((0, H - bar, 6, H), fill=ACCENT + (255,))
        y = H - bar + 14
        for line in item.split("\n"):
            d.text((28, y), line, font=self.font(25, True), fill="white")
            y += 34
        if topic.strip():
            d.text((28, H - bar + 88), topic, font=self.font(20), fill=LIGHT_BLUE)
        d.text((28, H - 40), vote, font=self.font(22), fill=YELLOW)
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
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                req = urllib.request.Request(PHOTO.format(mp), headers={"User-Agent": "sejmomat-live"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    path.write_bytes(r.read())
            im = Image.open(path).convert("RGB")
        except Exception:
            im = None
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
        if card["kind"] == "mp":
            x0 = 176
            d.text((x0, 58), card["name"], font=self.font(27, True), fill="white")
            chip = card["club"]
            cb = d.textbbox((x0, 98), chip, font=self.font(16, True))
            d.rounded_rectangle((cb[0] - 8, cb[1] - 4, cb[2] + 8, cb[3] + 5), 10, fill=colour + (255,))
            d.text((x0, 98), chip, font=self.font(16, True), fill="white")
            # small stats along the bottom
            stats = card.get("stats") or []
            sx = x0
            for label, value in stats[:4]:
                d.text((sx, h - 50), value, font=self.font(19, True), fill="white")
                d.text((sx, h - 26), label, font=self.font(13), fill=(170, 180, 196))
                sx += 92
        else:
            for i, line in enumerate(textwrap.wrap(card.get("text") or "", 52)[:3]):
                d.text((24, h - 84 + i * 24), line, font=self.font(17), fill=(205, 212, 225))
        self._cards[key] = im
        return im

    def card(self, card, t, length):
        """The card at time t (seconds) of its turn on screen: (image, x, y), or None."""
        base = self.card_base(card).copy()
        d = ImageDraw.Draw(base)
        width, h = base.size
        # the number counts up (numbers only; "99,1%" or "261:172" are shown as they are)
        value = card["value"]
        shown = str(value)
        if isinstance(value, int):
            k = clamp((t - 0.35) / 1.1)
            shown = str(round(value * (1 - (1 - k) ** 3)))
        mp = card["kind"] == "mp"
        nx, ny = (176, 128) if mp else (24, 56)
        d.text((nx, ny), shown, font=self.font(58 if mp else 66, True), fill=YELLOW)
        nb = d.textbbox((nx, ny), shown, font=self.font(58 if mp else 66, True))
        unit_lines = textwrap.wrap(card.get("unit") or "", 26)[:2]
        for i, line in enumerate(unit_lines):
            d.text((nb[2] + 14, ny + 14 + i * 22), line, font=self.font(18), fill=(205, 212, 225))
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
        # a shine sweeps across once
        k = (t - 0.9) / 0.6
        if 0 <= k <= 1:
            shine = Image.new("RGBA", base.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(shine)
            x = -120 + k * (width + 240)
            sd.polygon([(x, 0), (x + 50, 0), (x - 30, h), (x - 80, h)], fill=(255, 255, 255, 46))
            alpha = base.getchannel("A")
            shine.putalpha(Image.composite(shine.getchannel("A"), Image.new("L", base.size, 0), alpha))
            base.alpha_composite(shine)
        # slide in from the right with an overshoot, slide out at the end
        x_end, y = W - width - 24, 86
        if t < 0.6:
            x = W + 10 - (W + 10 - x_end) * ease_out_back(clamp(t / 0.6))
        elif t > length - 0.5:
            x = x_end + (W + 10 - x_end) * ease_in(clamp((t - (length - 0.5)) / 0.5))
        else:
            x = x_end
        return base, round(x), y

    def frame(self, item, topic, vote, panel=None, card=None):
        """One frame: the bar, then the amendment panel or the card. Returns RGBA bytes."""
        im = self.base(item, topic, vote).copy()
        if panel:
            p = self.panel(*panel)
            im.alpha_composite(p, (W - p.width - 24, 70))
        if card:
            c, x, y = card
            if x < W:
                # the part of the card already on screen
                im.alpha_composite(c.crop((0, 0, min(c.width, W - x), c.height)), (x, y))
        return im.tobytes()
