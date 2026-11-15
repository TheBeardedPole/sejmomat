"""The President's vetoes: every law of the term the President refused to sign,
his reasons, and what the Sejm did with it.

A veto reaches the Sejm as a print, "Wniosek Prezydenta RP o ponowne
rozpatrzenie ustawy z dnia ... o ...": a cover letter and the reasons
("Uzasadnienie"), which are scanned pages. `fetch()` finds those prints in the
API's list, OCRs each new one once (Tesseract, Polish, as for other scanned
prints) and keeps data/vetoes.json: {print: {"number", "title", "date"
(documentDate), "process" (processPrint), "law_date", "law" ("o ..."),
"pages", "paragraphs" (the reasons, from "Uzasadnienie" on)}}.

`build()` puts the processes' stages (sejmomat/processes.py: "Wniosek
Prezydenta (weto)", "Rozpatrywanie na forum Sejmu wniosku Prezydenta") together
with the votes to pass the law again (3/5 of the votes cast, at least half of
the MPs present). Bills considered jointly are one law and one veto.
"""
import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from . import api
from .config import DATA
from .plaintext import reflow
from .textract import ocr_available, ocr_pdf_text, pdf_text

PATH = DATA / "vetoes.json"
VETO_STAGE = "Wniosek Prezydenta (weto)"
TK_STAGE = "Prezydent skierował ustawę do Trybunału Konstytucyjnego"
SENT_STAGE = "Ustawę przekazano Prezydentowi do podpisu"
SEJM_STAGE = "Rozpatrywanie na forum Sejmu wniosku Prezydenta"
COMMITTEE_STAGE = "Praca w komisjach nad wnioskiem Prezydenta"
# Andrzej Duda's second term ended on 6 August 2025, when Karol Nawrocki was sworn in
PRESIDENTS = [("2025-08-06", "Karol Nawrocki"), ("0000-00-00", "Andrzej Duda")]
TITLE_RE = re.compile(r"^Wniosek Prezydenta.*ponowne rozpatrzenie ustawy\s+z\s+dnia\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s*r\.\s*(.*?)\.?\s*$", re.S)
MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
          "sierpnia", "września", "października", "listopada", "grudnia"]
# votes on passing a vetoed law again (the wording varies from sitting to sitting)
OVERRIDE_RE = re.compile(r"ponown\w* uchwaleni|wniosku o ponowne rozpatrzenie ustawy")


def president(day):
    return next(name for start, name in PRESIDENTS if (day or "") >= start)


def parse_title(title):
    """(law date "YYYY-MM-DD", "o rynku kryptoaktywów") from a veto print's title, or (None, None)."""
    m = TITLE_RE.match(" ".join((title or "").split()))
    if not m or m[2] not in MONTHS:
        return None, None
    law = re.sub(r"^[-–\s]+", "", m[4]).strip()
    return f"{m[3]}-{MONTHS.index(m[2]) + 1:02d}-{int(m[1]):02d}", law


def reasons(text):
    """The reasons as paragraphs: from the heading "Uzasadnienie" (the cover
    letter before it dropped), words split at line ends joined back."""
    text = re.sub(r"([a-ząćęłńóśźż])[-‐¬]\n\s*([a-ząćęłńóśźż])", r"\1\2", text)
    paras = [p for p in reflow(text) if p.strip()]
    # Where the reasons begin: the heading "Uzasadnienie" (not every motion has one, and OCR
    # misses some), else the sentence leading into them ("Odmowę podpisania ustawy motywuję
    # następującymi względami."), else the heading "Wniosek", else after the cover letter's
    # signature ("(-) Karol Nawrocki").
    def first(pattern, full=False):
        return next((i for i, p in enumerate(paras)
                     if (re.fullmatch if full else re.search)(pattern, p, re.I)), None)
    signed = [i for i, p in enumerate(paras) if re.match(r"\(?\s*-\s*\)\s*\w", p)]
    for start in (first(r"\W*Uzasadnienie\W*", True), first(r"motywuj\w+|następującymi względami"),
                  first(r"\W*Wniosek\W*", True), signed[0] if signed else None):
        if start is not None:
            break
    if start is not None:
        paras = paras[start + 1:]
        signed = [i - start - 1 for i in signed if i > start]
    if signed:   # a signature under the reasons, and what follows it (the printer's line)
        paras = paras[:signed[0]]
    while paras and len(paras[-1]) < 40:   # "Z poważaniem", a name, specks of the signature
        paras.pop()
    # Tesseract leaves blank lines inside paragraphs: a paragraph that does not end a
    # sentence, or one that starts in lower case, goes on the one before
    out = []
    for p in paras:
        p = re.sub(r"\b(art\.|ust\.|pkt|nr)\s+[|lI](?=[\s,.;)]|$)", r"\1 1", p)   # "ust. |" for "ust. 1"
        p = re.sub(r"(^|\s)['‘`](?=[A-ZĄĆĘŁŃÓŚŹŻ])", r"\1", p)                    # specks before a capital
        if out and (not re.search(r"[.:;!?”)]$", out[-1]) or re.match(r"[a-ząćęłńóśźż]", p)):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def _read(num, attachment):
    pdf = api.get(f"prints/{num}/{attachment}", binary=True)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / attachment
        path.write_bytes(pdf)
        text = pdf_text(path)
        if len(re.findall(r"\w+", text)) < 400 * max(1, text.count("\f")) // 2:   # scanned pages
            text = ocr_pdf_text(path)
        pages = text.count("\f") + 1
    return text, pages


def fetch():
    """New veto prints, OCR'd. Without Tesseract a new print is kept without its reasons
    (and read on a later run that has it)."""
    from .fetch import _write_json
    stored = load()
    listed = api.get("prints?limit=10000") or []
    todo = [p for p in listed if TITLE_RE.match(" ".join((p.get("title") or "").split()))
            and (p["number"] not in stored or not stored[p["number"]].get("paragraphs"))]
    can_ocr = ocr_available()

    def one(p):
        law_date, law = parse_title(p["title"])
        entry = {"number": p["number"], "title": " ".join(p["title"].split()), "date": p.get("documentDate"),
                 "process": (p.get("processPrint") or [None])[0], "law_date": law_date, "law": law,
                 "pages": None, "paragraphs": []}
        pdf = next((a for a in p.get("attachments") or [] if a.lower().endswith(".pdf")), None)
        if pdf and can_ocr:
            try:
                text, entry["pages"] = _read(p["number"], pdf)
                entry["paragraphs"] = reasons(text)
            except Exception as e:   # one bad scan should not stop the rest
                print(f"vetoes: {p['number']} not read ({e})")
        print(f"vetoes: {p['number']} {law_date} {len(entry['paragraphs'])} paragraphs", flush=True)
        return entry

    # Tesseract runs one thread per page here: a document per core
    with ThreadPoolExecutor(os.cpu_count() or 2) as pool:
        for entry in pool.map(one, todo):
            stored[entry["number"]] = entry
            _write_json(PATH, dict(sorted(stored.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)))
    print(f"vetoes: {len(stored)} veto prints, {len(todo)} read now" + ("" if can_ocr else " (no Tesseract: reasons not read)"))


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}


def _groups(procs, keys):
    """Processes considered jointly, as sets of process numbers (only among `keys`)."""
    parent = {k: k for k in keys}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    for k in keys:
        for other in procs[k].get("prints") or []:
            if other in parent:
                parent[find(other)] = find(k)
    out = {}
    for k in keys:
        out.setdefault(find(k), set()).add(k)
    return list(out.values())


def _num(k):
    return int(k) if str(k).isdigit() else 10 ** 9


def law_name(title):
    """"Rządowy projekt ustawy o X" -> "o X"."""
    t = re.sub(r"^.*?projekt\w*\s+ustaw\w*\s*", "", title or "", flags=re.I)
    return t if t != title else title


def title(law):
    """"o rynku kryptoaktywów" -> "Ustawa o rynku kryptoaktywów"; "zmieniająca ustawę ..." (the print's
    genitive "zmieniającej" put back in the nominative) -> "Ustawa zmieniająca ..."; a law with its own
    name ("Przepisy wprowadzające ...", "Kodeks ...") stays as it is."""
    if law[:1].islower():
        return "Ustawa " + re.sub(r"^zmieniającej\b", "zmieniająca", law)
    return law


def build(procs, votes, bill_by_root, today=None):
    """{"vetoes": [...] newest first, "tk": [...], "by_president": {name: count}}."""
    today = today or date.today()
    prints = load()
    print_by_process = {p["process"]: p for p in prints.values() if p.get("process")}
    vetoed = [k for k, p in procs.items() if any(s["name"] == VETO_STAGE for s in p["stages"])]
    override_votes = {}
    for v in votes:
        if v.get("bill") and OVERRIDE_RE.search((v.get("topic") or "").lower()):
            override_votes.setdefault(v["bill"], []).append(v)

    out = []
    for group in _groups(procs, vetoed):
        members = sorted(group, key=_num)
        pr = next((print_by_process[k] for k in members if k in print_by_process), None)
        root = pr["process"] if pr else next((k for k in members if k in bill_by_root), members[0])
        p = procs[root]
        stages = [s for s in p["stages"] if s["depth"] == 0]
        veto_at = max(s["date"] for s in stages if s["name"] == VETO_STAGE)
        sent = max((s["date"] for s in stages if s["name"] == SENT_STAGE and s["date"] and s["date"] <= veto_at), default=None)
        third = max((s["date"] for s in stages if s["name"].startswith("III czytanie") and s["date"]), default=None)
        after = [s for s in stages if s["date"] and s["date"] >= veto_at]
        decided = next((s for s in reversed(after) if s["name"] == SEJM_STAGE), None)
        vs = sorted((v for k in members for v in override_votes.get(k, [])), key=lambda v: (v["date"], v["votingNumber"]))
        vote = vs[-1] if vs else None
        if vote:
            status = "overridden" if vote["passed"] else "upheld"
        elif decided:
            status = "upheld" if decided["decision"].startswith("nie") else "overridden"
        elif any(s["name"] == COMMITTEE_STAGE for s in after):
            status = "committee"
        else:
            status = "waiting"
        bill = next((bill_by_root[k] for k in members if k in bill_by_root), None)
        law = (pr or {}).get("law") or law_name(p["title"])
        out.append({
            "root": root, "processes": members, "bill": bill, "law": law,
            "title": title(law),
            "law_date": (pr or {}).get("law_date") or third, "sent": sent, "veto": veto_at,
            "president": president(veto_at), "status": status, "vote": vote, "votes": vs,
            "short": max(0, vote["majorityVotes"] - vote["yes"]) if vote and not vote["passed"] else None,
            "waiting_days": (today - date.fromisoformat(veto_at)).days if status in ("waiting", "committee") else None,
            "print": pr, "slug": pr["number"] if pr else f"p{root}",
        })
    out.sort(key=lambda x: (x["veto"], _num(x["root"])), reverse=True)

    tk_keys = [k for k, p in procs.items() if any(s["name"] == TK_STAGE for s in p["stages"])]
    tk = []
    for group in _groups(procs, tk_keys):
        members = sorted(group, key=_num)
        root = next((k for k in members if k in bill_by_root), members[0])
        p = procs[root]
        when = max(s["date"] for s in p["stages"] if s["name"] == TK_STAGE)
        law = law_name(p["title"])
        tk.append({"root": root, "bill": bill_by_root.get(root), "date": when, "president": president(when),
                   "title": title(law)})
    tk.sort(key=lambda x: x["date"], reverse=True)

    by_president = {}
    for x in out:
        by_president[x["president"]] = by_president.get(x["president"], 0) + 1
    return {"vetoes": out, "tk": tk, "by_president": by_president,
            "by_root": {k: x for x in out for k in x["processes"]}}
