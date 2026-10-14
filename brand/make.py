"""Draws the Sejmomat logo and the social media images from it.

The wordmark is set in Monoton (SIL Open Font License, see OFL.txt) and saved
as outlines, so the SVGs need no font installed. Run from the repository root:

    python brand/make.py

Needs fontTools, and Inkscape for the PNGs.
"""
import subprocess
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = Path(__file__).parent
OUT = HERE / "out"
MONOTON = HERE / "Monoton-Regular.ttf"
NOTO = "/usr/share/fonts/google-noto/NotoSans-SemiBold.ttf"

# the site's palette (static/style.css)
BLUE, LIGHT_BLUE = "#1d5fc4", "#7db8ff"
PAPER, INK = "#fbfaf8", "#1d1d1f"

TAGLINE = "Głosowania w Sejmie: pokazane jak należy."


def text_path(font_file, text, size, x=0.0, y=0.0, tracking=0.0):
    """SVG path data for text with its baseline at y.

    Returns (d, width, ascent, descent): the advance width, and how far the
    ink reaches above and below the baseline.
    """
    font = TTFont(font_file)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    pen, bounds = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip(".")), BoundsPen(glyphs)
    cursor = 0.0
    for i, ch in enumerate(text):
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x + cursor, y)))
        glyphs[name].draw(TransformPen(bounds, (scale, 0, 0, scale, cursor, 0)))
        cursor += glyphs[name].width * scale + (tracking * size if i < len(text) - 1 else 0)
    _, y_min, _, y_max = bounds.bounds
    return pen.getCommands(), cursor, y_max, -y_min


def svg(w, h, body, bg=None):
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">{rect}{body}</svg>\n')


def centred(font_file, text, size, cx, baseline, fill, tracking=0.0):
    width = text_path(font_file, text, size, tracking=tracking)[1]
    d = text_path(font_file, text, size, cx - width / 2, baseline, tracking)[0]
    return f'<path d="{d}" fill="{fill}"/>'


def wordmark(fill, size=200, pad=0.12):
    """The logo on its own, cropped to the letters with a little margin."""
    _, width, up, down = text_path(MONOTON, "Sejmomat", size)
    m = round(size * pad)
    w, h = round(width + 2 * m), round(up + down + 2 * m)
    d = text_path(MONOTON, "Sejmomat", size, m, m + up)[0]
    return svg(w, h, f'<path d="{d}" fill="{fill}"/>')


def banner(w, h, bg, fg, sub, logo_share=0.62, safe=1.0):
    """Wordmark with the tagline under it, centred; `safe` narrows to the middle."""
    _, unit_w, unit_up, unit_down = text_path(MONOTON, "Sejmomat", 100)
    size = w * safe * logo_share / unit_w * 100
    up, down = unit_up * size / 100, unit_down * size / 100
    tag_size = size * 0.22
    _, _, tag_up, tag_down = text_path(NOTO, TAGLINE, tag_size)
    gap = size * 0.2
    top = (h - (up + down + gap + tag_up + tag_down)) / 2
    body = centred(MONOTON, "Sejmomat", size, w / 2, top + up, fg)
    body += centred(NOTO, TAGLINE, tag_size, w / 2, top + up + down + gap + tag_up, sub)
    return svg(w, h, body, bg)


def avatar(w, bg, fg, text="S", share=0.56):
    """Square profile picture; the letter sits well inside the circle crop."""
    _, unit_w, unit_up, unit_down = text_path(MONOTON, text, 100)
    size = min(w * share / unit_w, w * share / (unit_up + unit_down)) * 100
    up, down = unit_up * size / 100, unit_down * size / 100
    return svg(w, w, centred(MONOTON, text, size, w / 2, (w + up - down) / 2, fg), bg)


def stacked_avatar(w, bg, fg):
    """Square profile picture with the name in two lines: SEJMO / MAT."""
    _, unit_w, unit_up, unit_down = text_path(MONOTON, "Sejmo", 100)
    size = w * 0.66 / unit_w * 100
    up, down = unit_up * size / 100, unit_down * size / 100
    gap = up * 0.18
    # the second line has no descender, so the block ends at its baseline
    top = (w - (2 * up + down + gap)) / 2
    body = centred(MONOTON, "Sejmo", size, w / 2, top + up, fg)
    body += centred(MONOTON, "mat", size, w / 2, top + 2 * up + down + gap, fg)
    return svg(w, w, body, bg)


IMAGES = {
    # the logo itself
    "logo-blue.svg": wordmark(BLUE),
    "logo-ink.svg": wordmark(INK),
    "logo-white.svg": wordmark("#ffffff"),
    "logo-light-blue.svg": wordmark(LIGHT_BLUE),
    # profile pictures (X 400×400, Bluesky, Facebook, Mastodon: shown as a circle)
    "avatar-s-blue.svg": avatar(1000, BLUE, "#ffffff"),
    "avatar-s-paper.svg": avatar(1000, PAPER, BLUE),
    "avatar-stacked-blue.svg": stacked_avatar(1000, BLUE, "#ffffff"),
    "avatar-stacked-paper.svg": stacked_avatar(1000, PAPER, BLUE),
    # headers; X and Bluesky crop the top and bottom on phones and the profile
    # picture covers the bottom left, so the text stays in the middle
    "header-x-1500x500.svg": banner(1500, 500, BLUE, "#ffffff", "#dbe7fa", logo_share=0.55),
    "header-bluesky-3000x1000.svg": banner(3000, 1000, BLUE, "#ffffff", "#dbe7fa", logo_share=0.55),
    "cover-facebook-1640x624.svg": banner(1640, 624, BLUE, "#ffffff", "#dbe7fa", logo_share=0.55),
    # link preview (og:image)
    "og-1200x630.svg": banner(1200, 630, PAPER, BLUE, INK, logo_share=0.74),
}

PNG_WIDTH = {"logo": 2400}


def main():
    # the site header shows this as a CSS mask, coloured by the theme
    (HERE.parent / "static" / "logo.svg").write_text(wordmark("#000", pad=0))
    OUT.mkdir(exist_ok=True)
    for name, data in IMAGES.items():
        path = OUT / name
        path.write_text(data)
        width = PNG_WIDTH.get(name.split("-")[0])
        args = ["inkscape", str(path), "--export-type=png",
                f"--export-filename={path.with_suffix('.png')}"]
        if width:
            args.append(f"--export-width={width}")
        subprocess.run(args, check=True, capture_output=True)
        print(path.with_suffix(".png").relative_to(HERE))


if __name__ == "__main__":
    main()
