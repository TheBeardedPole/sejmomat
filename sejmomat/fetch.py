"""Download votings and prints into data/ (committed) and cache/ (not)."""
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from . import api
from .acts import CITE_RE, act_id, clean_bill_lines
from .config import ACTS, CACHE, DATA, REFRESH_LAST_SITTINGS
from .refs import is_amendment_topic, prints_in_title
from .textract import docx_paragraphs, docx_text, ocr_available, ocr_pdf_text, pdf_text

VOTE_CODES = {"YES": "Y", "NO": "N", "ABSTAIN": "A", "ABSENT": "X"}
WORKERS = 6


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def _compact_voting(d):
    """Keep the summary fields and group individual ballots by club and vote.

    ballots = {club: {"Y": [mp ids], "N": [...], "A": [...], "X": [...]}}
    Club is the MP's club at the time of the vote.
    """
    ballots = {}
    for b in d.get("votes") or []:
        code = VOTE_CODES.get(b.get("vote"))
        if code is None:  # ON_LIST votings (elections) have no yes/no ballots
            continue
        ballots.setdefault(b.get("club") or "?", {}).setdefault(code, []).append(b["MP"])
    keep = ("votingNumber", "date", "sittingDay", "kind", "title", "topic",
            "description", "majorityType", "majorityVotes", "yes", "no",
            "abstain", "notParticipating", "totalVoted")
    out = {k: d.get(k) for k in keep if d.get(k) is not None}
    out["ballots"] = ballots
    return out


def fetch_sittings():
    days = api.get("votings")
    sittings = sorted({d["proceeding"] for d in days})
    newest = max(sittings)
    for s in sittings:
        path = DATA / "votings" / f"{s}.json"
        if path.exists() and s <= newest - REFRESH_LAST_SITTINGS:
            continue
        summaries = api.get(f"votings/{s}") or []
        with ThreadPoolExecutor(WORKERS) as pool:
            details = list(pool.map(lambda v: api.get(f"votings/{s}/{v['votingNumber']}"), summaries))
        votings = [_compact_voting(d) for d in details if d]
        votings.sort(key=lambda v: v["votingNumber"])
        _write_json(path, {"sitting": s, "votings": votings})
        print(f"sitting {s}: {len(votings)} votings")


def fetch_people():
    mps = api.get("MP")
    _write_json(DATA / "mps.json", [
        {k: m.get(k) for k in ("id", "firstLastName", "lastName", "club", "active", "districtName", "districtNum",
                               "voivodeship", "birthDate", "educationLevel", "profession", "numberOfVotes")}
        for m in mps
    ])
    clubs = api.get("clubs")
    _write_json(DATA / "clubs.json", [{k: c.get(k) for k in ("id", "name")} for c in clubs])
    # Committee membership (used by the games; "function" is set for chairs and deputies).
    committees = api.get("committees") or []
    _write_json(DATA / "committees.json", [
        {"code": c.get("code"), "name": c.get("name"), "type": c.get("type"),
         "members": [{"id": m["id"], "function": m.get("function")} for m in c.get("members") or []]}
        for c in committees
    ])


def _referenced_prints():
    """(print numbers to fetch, of which probed candidates).

    For amendment votings the additional report ("NNNN-A") is sometimes not
    cited in the title, so it is probed for every cited print.
    """
    every, probed = set(), set()
    for f in (DATA / "votings").glob("*.json"):
        for v in json.loads(f.read_text(encoding="utf-8"))["votings"]:
            nums = prints_in_title(v.get("title"))
            every.update(nums)
            if is_amendment_topic(v.get("topic")):
                probed.update(f"{n}-A" for n in nums if "-" not in n)
    probed -= every
    return every | probed, probed


def _download(num, name):
    path = CACHE / "prints" / num / name
    if not path.exists():
        content = api.get(f"prints/{num}/{name}", binary=True)
        if content is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return path


MISSING_PATH = DATA / "prints" / "_missing.json"


def _fetch_print(num, missing):
    meta_path = DATA / "prints" / f"{num}.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    elif num in missing:
        return
    else:
        raw = api.get(f"prints/{num}")
        if raw is None:
            missing.add(num)
            return
        meta = {k: raw.get(k) for k in ("number", "title", "documentDate", "processPrint", "attachments")}
        _write_json(meta_path, meta)
    attachments = meta.get("attachments") or []
    text_path = DATA / "prints" / f"{num}.txt"
    # Near-empty text means a scanned PDF; retry while it can be improved.
    scanned = text_path.exists() and text_path.stat().st_size < MIN_TEXT_BYTES
    has_docx = any(a.lower().startswith(num.lower()) and a.lower().endswith(".docx") for a in attachments)
    if not text_path.exists() or (scanned and (has_docx or ocr_available())):
        text = _print_text(num, attachments)
        if text is not None:
            tmp = text_path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(text_path)
    # Senate resolutions: the amendment text lives in the .docx; the PDF is
    # often only the Marshal's cover letter.
    docx_path = DATA / "prints" / f"{num}.docx.json"
    if (meta.get("title") or "").startswith("Uchwała Senatu") and not docx_path.exists():
        docs = [a for a in attachments if a.lower().endswith(".docx")]
        if docs and (p := _download(num, docs[0])):
            _write_json(docx_path, docx_paragraphs(p))


MIN_TEXT_BYTES = 300


def _print_text(num, attachments):
    """Text of a print: the PDF's text layer, else its .docx, else OCR."""
    pdfs = [a for a in attachments if a.lower().endswith(".pdf")]
    docs = [a for a in attachments if a.lower().endswith(".docx")]
    main = f"{num}.pdf" if f"{num}.pdf" in pdfs else (pdfs[0] if pdfs else None)
    pdf = _download(num, main) if main else None
    text = pdf_text(pdf) if pdf else ""
    if len(text.strip()) >= MIN_TEXT_BYTES:
        return text
    # Scanned PDF: prefer a .docx with the same content (but not a Senate
    # resolution's docx attached to a cover letter, handled separately).
    same = [d for d in docs if d.lower().startswith(num.lower())]
    if same and (p := _download(num, same[0])):
        return docx_text(docx_paragraphs(p))
    if pdf and ocr_available():
        return ocr_pdf_text(pdf)
    return text if pdf else None


def fetch_prints():
    every, probed = _referenced_prints()
    todo = sorted(every, key=lambda n: (int(re.match(r"\d+", n)[0]), n))
    # Print numbers known not to exist (mostly probed "NNNN-A" candidates).
    missing = set(json.loads(MISSING_PATH.read_text())) if MISSING_PATH.exists() else set()
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(lambda n: _fetch_print(n, missing), todo))
        # Root prints of each legislative process name the bill; votings at
        # the Senate stage often do not cite them.
        roots = set()
        for n in todo:
            path = DATA / "prints" / f"{n}.json"
            if path.exists():
                roots.update(json.loads(path.read_text(encoding="utf-8")).get("processPrint") or [])
        list(pool.map(lambda n: _fetch_print(n, missing), sorted(roots - every)))
    _write_json(MISSING_PATH, sorted(missing))
    print(f"prints: {len(todo)} referenced (incl. {len(probed)} probed), {len(roots - every)} process roots")


def _fetch_act(eli_id):
    base = ACTS / eli_id.replace("/", "-")
    if base.with_suffix(".txt").exists():
        return
    meta = api.get(f"acts/{eli_id}", base=api.ELI)
    if meta is None:
        return
    keep = {k: meta.get(k) for k in ("ELI", "title", "type", "status", "announcementDate", "references")}
    pdf = api.get(f"acts/{eli_id}/text.pdf", base=api.ELI, binary=True) if meta.get("textPDF") else None
    if pdf is None:
        return
    base.parent.mkdir(parents=True, exist_ok=True)
    tmp = base.with_suffix(".pdf")
    tmp.write_bytes(pdf)
    text = pdf_text(tmp)
    tmp.unlink()
    _write_json(base.with_suffix(".json"), keep)
    base.with_suffix(".txt").write_text(text, encoding="utf-8")


def fetch_acts():
    """Consolidated texts of acts that committee reports and amendments change.

    Kept in data/acts and committed, like the print texts, so every build
    has them without re-downloading from the slow ELI API.
    """
    wanted = set()
    for meta_path in (DATA / "prints").glob("*.json"):
        if "." in meta_path.stem or meta_path.stem.startswith("_"):
            continue
        title = json.loads(meta_path.read_text(encoding="utf-8")).get("title") or ""
        text_path = meta_path.with_suffix(".txt")
        if "prawozdanie" not in title or not text_path.exists():
            continue
        flat = "\n".join(clean_bill_lines(text_path.read_text(encoding="utf-8")))
        wanted.update(act_id(m.groupdict()) for m in CITE_RE.finditer(flat))
    missing = sorted(e for e in wanted if not (ACTS / f"{e.replace('/', '-')}.txt").exists())
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(_fetch_act, missing))
    have = sum(1 for e in wanted if (ACTS / f"{e.replace('/', '-')}.txt").exists())
    print(f"acts: {have}/{len(wanted)} cited acts available")


def ocr_scanned():
    """OCR every print whose PDF had no text layer (and no usable .docx)."""
    if not ocr_available():
        raise SystemExit("Tesseract not found: install tesseract with Polish data "
                         "(dnf install tesseract tesseract-langpack-pol)")
    todo = sorted(
        p.stem for p in (DATA / "prints").glob("*.txt")
        if p.stat().st_size < MIN_TEXT_BYTES and "." not in p.stem
    )
    print(f"OCR: {len(todo)} scanned prints")
    done = 0

    def one(num):
        nonlocal done
        meta = json.loads((DATA / "prints" / f"{num}.json").read_text(encoding="utf-8"))
        text = _print_text(num, meta.get("attachments") or [])
        if text and len(text.strip()) >= MIN_TEXT_BYTES:
            path = DATA / "prints" / f"{num}.txt"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
        done += 1
        print(f"  [{done}/{len(todo)}] {num}: {len((text or '').strip())} chars", flush=True)

    # Tesseract is CPU-bound; one worker per core is plenty.
    with ThreadPoolExecutor(max(1, (os.cpu_count() or 2) // 2)) as pool:
        list(pool.map(one, todo))


def _data_state():
    """Fingerprint of the votings and the set of print texts on disk."""
    digest = hashlib.sha256()
    for path in sorted((DATA / "votings").glob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    for path in sorted((DATA / "prints").glob("*.txt")):
        digest.update(path.name.encode())
    return digest.hexdigest()


ACTS_SCANNED = ACTS / "_scanned.txt"  # data fingerprint at the last completed acts scan


def run():
    """Fetch votings and prints; look for newly amended acts only when there
    is something new since the last completed acts scan (a new sitting, new
    votes or new prints). Between sittings nothing changes, so the scan and
    the slow ELI API are skipped. `python -m sejmomat acts` forces the step."""
    from . import agenda, speeches  # they build on this module
    try:
        agenda.fetch()
    except Exception as e:  # the calendar is a nice-to-have; votes come first
        print(f"proceedings: not updated ({e})")
    fetch_people()
    fetch_sittings()
    fetch_prints()
    speeches.fetch()
    state = _data_state()
    if ACTS_SCANNED.exists() and ACTS_SCANNED.read_text().strip() == state:
        print("acts: no new votings or prints since the last scan, skipping")
        return
    fetch_acts()
    # recorded only after a scan that ran to the end, so a failed one is retried
    ACTS_SCANNED.write_text(state + "\n")
