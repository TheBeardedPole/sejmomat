"""Committee meetings: agenda, the bills discussed, the recording and the
transcript.

One request per committee lists all its meetings of the term, with the agenda
(lines of HTML with an indent level), the committees it met jointly with and
the video, cut to the meeting. The transcript is a PDF the Sejm publishes
days or weeks later, and not at all for some closed meetings, so whether it
is out is checked (a HEAD request, nothing downloaded): once for every past
meeting, then only for recent ones still without it. Kept in
data/committee_sittings.json as {committee code: [meeting, ...]}.
"""
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html import unescape

from . import api
from .config import DATA, TERM

PATH = DATA / "committee_sittings.json"
RECHECK_DAYS = 60   # how long to keep looking for a transcript that is not out yet
WORKERS = 6
_LINE_RE = re.compile(r'<div class="agenda-indent-(\d)">(.*?)</div>', re.S)
# "druk nr 1964", "druki 1604 i 1669", "(druki nr: 270, 271 i 273)"; never "nr 1313/2013/UE"
_PRINTS_RE = re.compile(r"druk(?:i|ów)?\s+(?:sejmow[ye]\s+)?(?:nr\s*)?:?\s*((?:\d+(?:-[A-Z])?(?:\s*(?:,|i|oraz)\s*)?)+)")


def transcript_url(code, num):
    return f"https://api.sejm.gov.pl/sejm/term{TERM}/committees/{code}/sittings/{num}/pdf"


def _plain(fragment):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ")).strip()


def compact(s):
    """A meeting as kept: agenda lines as [indent, text], prints, video link."""
    lines = [[int(i), _plain(t)] for i, t in _LINE_RE.findall(s.get("agenda") or "")]
    lines = [l for l in lines if l[1]]
    prints = []
    for _, text in lines:
        for group in _PRINTS_RE.findall(text):
            prints += re.findall(r"\d+(?:-[A-Z])?", group)
    video = next((v for v in s.get("video") or [] if v and (v.get("videoLink") or v.get("playerLink"))), None)
    return {
        "num": s["num"], "date": s["date"], "start": s.get("startDateTime"), "end": s.get("endDateTime"),
        "status": s.get("status"), "closed": bool(s.get("closed")), "remote": bool(s.get("remote")),
        "joint": [j["code"] for j in s.get("jointWith") or [] if j.get("code")],
        "agenda": lines, "prints": list(dict.fromkeys(prints)),
        # the Sejm's player page, and the stream itself (HLS), which starts
        # and stops with the meeting
        "video": video.get("playerLink") if video else None,
        "stream": video.get("videoLink") if video else None,
    }


def _has_transcript(code, num):
    req = urllib.request.Request(transcript_url(code, num), method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def fetch(today=None):
    today = today or date.today()
    codes = [c["code"] for c in json.loads((DATA / "committees.json").read_text(encoding="utf-8"))]
    old = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    known = {(code, m["num"]): m.get("transcript") for code, ms in old.items() for m in ms}
    with ThreadPoolExecutor(WORKERS) as pool:
        lists = dict(zip(codes, pool.map(lambda c: api.get(f"committees/{c}/sittings") or [], codes)))
    out = {code: [compact(s) for s in sorted(lists[code], key=lambda s: s["num"])] for code in codes}

    recent = (today - timedelta(days=RECHECK_DAYS)).isoformat()
    todo = []
    for code, meetings in out.items():
        for m in meetings:
            had = known.get((code, m["num"]))
            m["transcript"] = had
            if m["status"] == "FINISHED" and not had and (had is None or m["date"] >= recent):
                todo.append((code, m))

    def check(item):
        code, m = item
        try:
            m["transcript"] = _has_transcript(code, m["num"])
        except Exception:  # left unknown, tried again next time
            m["transcript"] = None

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(check, todo))
    from .fetch import _write_json
    _write_json(PATH, out)
    n = sum(len(ms) for ms in out.values())
    print(f"committees: {n} meetings of {len(out)} committees, {len(todo)} transcripts checked")


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
