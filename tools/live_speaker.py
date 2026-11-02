"""Who is speaking, from the broadcast's own name caption: when the camera
cuts to a close-up of a speaker (about 10-15 s into a speech) the Sejm's
picture carries, for a few seconds, their name in white (the surname in
capitals) and their club below, centred low in the frame. ffmpeg saves that
band of the picture every 2 seconds (tools/livestream.py); Tesseract reads
it; the surname in capitals is matched to an MP, allowing for OCR slips, and
the first name or the club confirms it. Speakers who are not MPs (ministers,
guests) are not shown.
"""
import difflib
import json
import os
import re
import subprocess
import unicodedata
import urllib.request
from pathlib import Path

from PIL import Image

MPS_URL = "https://sejmomat.pl/api/v1/mps.json"
# the caption's band in the 1280x720 picture: (x, y, width, height)
BAND = (192, 518, 896, 144)


def load_mps(root):
    """The site's MP list (api/v1/mps.json): from a local build if there is one, else the site."""
    local = Path(root) / "site" / "api" / "v1" / "mps.json"
    try:
        if local.exists():
            return json.loads(local.read_text(encoding="utf-8"))
        with urllib.request.urlopen(MPS_URL, timeout=30) as r:
            return json.load(r)
    except Exception:
        return []


def _fold(s):
    s = unicodedata.normalize("NFD", s.upper().replace("Ł", "L"))
    return re.sub(r"[^A-Z\- ]", "", "".join(c for c in s if not unicodedata.combining(c))).strip()


def read(path):
    """The caption band's text: bright letters kept, the rest dropped, read by Tesseract."""
    try:
        im = Image.open(path).convert("L")
    except Exception:
        return ""
    # only near-white kept: the caption's letters; at 190 a white shirt or papers behind the
    # chair's caption (the Marshal at the desk) came through too and buried it
    bw = im.point(lambda p: 0 if p > 245 else 255).resize((im.width * 2, im.height * 2), Image.LANCZOS)
    out = Path(path).with_suffix(".ocr.png")
    bw.save(out)
    try:
        # one thread, below the stream: by itself Tesseract spreads one small picture over every
        # core, at the stream's priority, taking turns from the encoder once a second
        return subprocess.run(["nice", "-n", "10", "tesseract", str(out), "-", "-l", "pol", "--psm", "6"],
                              capture_output=True, text=True, timeout=20,
                              env={**os.environ, "OMP_THREAD_LIMIT": "1"}).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


class Recogniser:
    def __init__(self, mps):
        self.mps = [m for m in mps if m.get("active")]

    def match(self, text):
        """The MP the caption names, or None."""
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return None
        caps = [w for w in re.findall(r"[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ\-]{2,}", text)]
        if not caps:
            return None
        folded = _fold(text)
        best, score = None, 0.0
        for m in self.mps:
            parts = m["name"].split()
            surname, first = _fold(parts[-1]), _fold(parts[0])
            s = max(difflib.SequenceMatcher(None, surname, _fold(w)).ratio() for w in caps)
            if s < 0.8:
                continue
            # the first name or the club seen too
            bonus = 0.0
            if first and first in folded:
                bonus += 0.15
            club = _fold(m.get("club") or "").replace("-", " ")
            if club and club.split()[0] in set(folded.replace("-", " ").split()):
                bonus += 0.1
            total = s + bonus
            if total > score:
                best, score = m, total
        # a near-exact surname, or a close one confirmed by first name or club
        return best if best and score >= 0.95 else None
