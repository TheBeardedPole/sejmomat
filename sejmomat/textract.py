"""Text extraction from print attachments."""
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_text(paragraphs):
    """Plain text from docx_paragraphs(), with Word numbering written out
    ("1)", "a)") so it parses like PDF text."""
    lines, counters = [], {}
    for p in paragraphs:
        level, text = p["level"], p["text"]
        if level is not None:
            counters[level] = counters.get(level, 0) + 1
            for deeper in [k for k in counters if k > level]:
                del counters[deeper]
            n = counters[level]
            mark = f"{n})" if level == 0 else f"{chr(ord('a') + (n - 1) % 26)})"
            text = f"{mark} {text}".strip()
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def ocr_available():
    return bool(shutil.which("tesseract") and shutil.which("pdftoppm"))


def ocr_pdf_text(path):
    """OCR a scanned PDF (Polish) page by page."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"],
                       check=True, capture_output=True)
        pages = []
        for img in sorted(Path(tmp).glob("p-*.png")):
            # one thread per process: callers parallelise across documents
            out = subprocess.run(["tesseract", str(img), "-", "-l", "pol", "--psm", "4"],
                                 check=True, capture_output=True, text=True,
                                 env={**os.environ, "OMP_THREAD_LIMIT": "1"})
            pages.append(out.stdout)
    text = "\f".join(pages)
    # Tesseract output: typographic quotes/dashes vary; normalise to what the
    # parsers expect (opening „, closing ”, en dash between words).
    text = re.sub(r"[“”]", "”", text).replace("—", "–")
    text = re.sub(r"(^|\s),,", r"\1„", text, flags=re.M)
    return _fix_ocr(text)


def _fix_ocr(text):
    """Systematic Tesseract misreads in Polish legislative text."""
    text = re.sub(r"\bwart\.", "w art.", text)                  # "w art." run together
    text = text.replace("$", "§")
    text = re.sub(r"(?<=[\w.;,)])\*(?=[;.,*]|$)", "”", text, flags=re.M)  # closing quote read as "*"
    # unit labels: "la)" / "łc)" / "l)" for "1a)" / "1c)" / "1)"
    text = re.sub(r"(^|„|\s)[lł]([a-z]?\))", r"\g<1>1\2", text, flags=re.M)
    # "pkt la", "art. l", "ust. l" ("lit. l" is a real letter, so not there)
    text = re.sub(r"\b(art\.|ust\.|pkt)\s+[lł]([a-z]?)\b", r"\1 1\2", text)
    return text


def pdf_text(path):
    """Layout-preserving text via poppler's pdftotext."""
    out = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True, capture_output=True, text=True,
    )
    return out.stdout


def _style_numbering(z):
    """styleId -> ilvl for paragraph styles that carry their own numbering."""
    try:
        root = ET.fromstring(z.read("word/styles.xml"))
    except KeyError:
        return {}
    out = {}
    for st in root.iter(f"{W}style"):
        num = st.find(f"{W}pPr/{W}numPr")
        if num is not None:
            ilvl = num.find(f"{W}ilvl")
            out[st.get(f"{W}styleId")] = int(ilvl.get(f"{W}val")) if ilvl is not None else 0
    return out


def docx_paragraphs(path):
    """Paragraphs as [{"level": int|None, "text": str}].

    `level` is the Word list level (0 = top-level "1)", 1 = "a)") or None for
    unnumbered paragraphs. Word renders this numbering itself, so it is not part
    of the paragraph text and has to be recovered from the markup.
    """
    with zipfile.ZipFile(path) as z:
        styles = _style_numbering(z)
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(f"{W}p"):
        text = "".join(
            (el.text or "") if el.tag == f"{W}t" else "\t"
            for el in p.iter() if el.tag in (f"{W}t", f"{W}tab")
        ).strip()
        level = None
        ppr = p.find(f"{W}pPr")
        if ppr is not None:
            num = ppr.find(f"{W}numPr")
            style = ppr.find(f"{W}pStyle")
            if num is not None:
                num_id = num.find(f"{W}numId")
                # numId 0 explicitly switches numbering off
                if num_id is None or num_id.get(f"{W}val") != "0":
                    ilvl = num.find(f"{W}ilvl")
                    level = int(ilvl.get(f"{W}val")) if ilvl is not None else 0
            elif style is not None and style.get(f"{W}val") in styles:
                level = styles[style.get(f"{W}val")]
        # Senate templates put the item number in its own empty paragraph
        # ("OZNACZENIE PUNKTU"), so numbered empty paragraphs are kept.
        if not text and level is None:
            continue
        # Collapse spaces, but keep tabs as a wide gap so that
        # "– KP PiS<tab>– odrzucić" stays separable like in PDF layout text.
        text = re.sub(r"\s*\t\s*", "    ", re.sub(r" +", " ", text))
        out.append({"level": level, "text": text})
    return out
