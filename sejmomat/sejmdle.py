"""Sejmdle's pages under the site's header: the catalog (index.html) and a page per game,
written from games/sejmdle/game.html. Needs only Jinja and the templates, not the site's
data, so the quick publish (.github/workflows/assets.yml) makes the same pages as the build:

    python -m sejmomat.sejmdle <folder>    # a copy of games/sejmdle, rewritten in place
"""
import hashlib
import html
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import STATIC, TEMPLATES
from .i18n import translator
from .stamp import stamp

# the games: the game's id in sejmdle.js, its page (also in sejmdle.js and index.html, PAGES),
# title and description
GAMES = [
    ("posel", "zgadnij-posla", "Zgadnij posła",
     "Odgadnij posła dnia w 8 próbach: po każdej widzisz, czy zgadza się klub, okręg, wiek i inne cechy."),
    ("przeszlo", "czy-przeszlo", "Czy przeszło?",
     "Pięć poprawek do ustaw: zgadnij, czy Sejm je przyjął, i zobacz wynik głosowania."),
    ("kim", "kim-jestem", "Kim jestem?",
     "Jak głosował tajemniczy poseł? Zgadnij, kto to, z podpowiedziami: wiek, komisje, klub, zdjęcie."),
    ("prezydium", "prezydium", "Prezydium",
     "Obsadź siedem miejsc w Prezydium Sejmu posłami, którzy spełniają podane warunki."),
    ("siatka", "siatka", "Siatka",
     "Wypełnij dziewięć pól posłami, którzy pasują do warunku z wiersza i z kolumny."),
    ("uzupelnij", "uzupelnij-slowo", "Uzupełnij słowo",
     "Trzy fragmenty prawdziwych wystąpień z sali, z lukami: wpisz brakujące słowa."),
    ("twarze", "twarze-w-minute", "Twarze w minutę",
     "60 sekund na rozpoznanie jak najwięcej posłów ze zdjęć, z rankingiem dnia i wszech czasów."),
]


def header():
    """The site's header for the sejmdle/ folder (templates/_header.html)."""
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.globals.update(_=translator("pl"), lang="pl")
    return env.get_template("_header.html").render(
        root="../", site_root="../", path="sejmdle/", full_path="sejmdle/", lang="pl",
        alternates={"pl": "../index.html", "en": "../en/index.html"}).strip()


def write(folder):
    """Rewrites a copy of games/sejmdle in `folder`: scripts and styles stamped with their
    version, the header put in, a page per game made from game.html (which is removed)."""
    folder = Path(folder)
    stamp(folder)   # so a new script or stylesheet loads at once, despite CDN caching
    template = (folder / "game.html").read_text(encoding="utf-8")
    (folder / "game.html").unlink()
    pages = {"index": (folder / "index.html").read_text(encoding="utf-8")}
    for game, page, title, description in GAMES:
        text = template
        for key, value in (("game", game), ("page", page), ("title", title), ("description", description)):
            text = text.replace("{{%s}}" % key, html.escape(value))
        pages[page] = text
    top = header()
    for page, text in pages.items():
        text = text.replace("<!-- sejmomat-header -->", top, 1)
        for name in ("header.css", "header.js"):   # versioned, as on the site's pages
            version = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]
            text = text.replace(f'"../static/{name}"', f'"../static/{name}?v={version}"')
        (folder / f"{page}.html").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    write(sys.argv[1])
