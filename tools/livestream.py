"""The Sejm's plenary stream with Sejmomat captions: the agenda item and the
latest vote with its result, as they come up on screen. Run on your own
computer (needs ffmpeg; ffplay for the preview window):

    python tools/livestream.py                       # live, ~100 s behind, preview window
    python tools/livestream.py --out obrady.mkv      # live, to a file
    python tools/livestream.py --at "2026-10-22 17:40"   # replay from that moment
    SEJMOMAT_RTMP=rtmp://a.rtmp.youtube.com/live2/KEY python tools/livestream.py --out rtmp

How it keeps in step: ffmpeg reads the stream from a start moment (live: now
minus --delay; replay: --at) at normal speed, so the picture shows start +
time elapsed. The captions follow that clock: a vote (from the Sejm's API,
about a minute after it is taken; hence the delay live) appears when the
picture reaches the moment it was taken, and for a vote on an amendment or a
minority motion a panel on the right shows what it changes in the bill (red
removed, green added; from the report prints in data/prints, as on the site's
vote pages). ffmpeg re-reads the caption files every frame; this script
rewrites them.

The Sejm's broadcast is public; before streaming it to a platform, check the
Sejm's terms for rebroadcasting its feed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sejmomat import model  # noqa: E402
from sejmomat.model import link_amendments  # noqa: E402  (what an amendment changes, as on vote pages)
from live_overlay import H, W, Overlay  # noqa: E402
from live_speaker import BAND, Recogniser, load_mps, read  # noqa: E402
from sejmomat.facts import spread  # noqa: E402

API = "https://api.sejm.gov.pl/sejm/term10"
WARSAW = ZoneInfo("Europe/Warsaw")


def get(path):
    with urllib.request.urlopen(f"{API}/{path}", timeout=60) as r:
        return json.load(r)


def get_or_none(path):
    try:
        return get(path)
    except Exception:
        return None


def ms(dt):
    return int(dt.timestamp() * 1000)


def warsaw(text):
    return datetime.fromisoformat(text).replace(tzinfo=WARSAW)


def font(bold):
    """A Noto Sans (or any sans) font file, for ffmpeg's drawtext."""
    pattern = "Noto Sans:bold" if bold else "Noto Sans"
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True).stdout.strip()
        if path:
            return path
    except FileNotFoundError:
        pass
    sys.exit("No font found: install Noto Sans (or pass --font / --font-bold).")


def plenary(day):
    """The plenary stream of a day: (title, base HLS address, start, end or None)."""
    videos = get(f"videos/{day}" if day != "today" else "videos/today") or []
    v = next((v for v in videos if v.get("type") == "posiedzenie" and v.get("videoLink")), None)
    if not v:
        sys.exit("No plenary stream for that day.")
    return v["title"], v["videoLink"].split("?")[0], warsaw(v["startDateTime"]), v.get("endDateTime") and warsaw(v["endDateTime"])


def load_transcript(day):
    """[{start, end, mp}] of the MPs' spoken speeches that day (data/speeches), longer than 15 s."""
    path = ROOT / "data" / "speeches" / f"{day}.json"
    if not path.exists():
        sys.exit(f"No transcript for {day} in data/speeches.")
    out = []
    for x in json.loads(path.read_text(encoding="utf-8"))["statements"]:
        if x.get("mp") and x.get("function") == "Poseł" and not x.get("unspoken") and x.get("start") and x.get("end"):
            start, end = (datetime.fromisoformat(x[k]).replace(tzinfo=WARSAW) for k in ("start", "end"))
            if (end - start).total_seconds() >= 15:
                out.append({"start": start, "end": end, "mp": x["mp"]})
    return sorted(out, key=lambda x: x["start"])


def wait_for_plenary(delay):
    """Unattended (--wait): today's plenary stream once it has been on for `delay` seconds,
    checking every few minutes until then; on a day without one, or once it has ended,
    it waits for the next day's."""
    while True:
        videos = get_or_none("videos/today") or []
        v = next((v for v in videos if v.get("type") == "posiedzenie" and v.get("videoLink")), None)
        now = datetime.now(WARSAW)
        if v:
            start, end = warsaw(v["startDateTime"]), v.get("endDateTime") and warsaw(v["endDateTime"])
            if not (end and end < now):
                ready = start + timedelta(seconds=delay)
                if ready <= now:
                    return v["title"], v["videoLink"].split("?")[0], start, end
                print(f"{now:%H:%M} {v['title']}: starts {start:%H:%M}", flush=True)
                time.sleep(min(300, max(10, (ready - now).total_seconds())))
                continue
        time.sleep(300)


# The Sejm's video CDN sends viewers to an edge server; some of its edges sit inside
# Polish home providers' networks (Vectra's tvo-18-*) and do not answer servers in a
# data centre. If the edge given does not answer, the same path is asked of these.
FALLBACK_EDGES = ("tvo-1-1.e.blueonline.tv",)
# The CDN answers only Polish addresses: a server elsewhere fetches the video through
# an HTTP proxy in Poland (tools/vps/proxy-setup.sh), e.g. http://203.0.113.5:8888
VIDEO_PROXY = os.environ.get("SEJMOMAT_VIDEO_PROXY", "").strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def fetch_playlist(url):
    """(final address, text) of a playlist, following the CDN's redirects one by one so
    that an edge that does not answer can be swapped for one that does."""
    proxy = [urllib.request.ProxyHandler({"http": VIDEO_PROXY, "https": VIDEO_PROXY})] if VIDEO_PROXY else []
    opener = urllib.request.build_opener(_NoRedirect, *proxy)
    for _ in range(6):
        host = urllib.parse.urlsplit(url).hostname or ""
        edge = host.endswith(".e.blueonline.tv") and host != "r.e.blueonline.tv"
        tries = [url] + ([urllib.parse.urlsplit(url)._replace(netloc=h).geturl() for h in FALLBACK_EDGES if h != host] if edge else [])
        for i, u in enumerate(tries):
            try:
                with opener.open(u, timeout=8 if edge and i < len(tries) - 1 else 60) as r:
                    if i:
                        print(f"video edge {host} does not answer; using {urllib.parse.urlsplit(u).hostname}", file=sys.stderr)
                    return r.geturl(), r.read().decode()
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                    url = urllib.parse.urljoin(u, e.headers["Location"])
                    break
                raise
            except (urllib.error.URLError, TimeoutError, OSError):
                if i == len(tries) - 1:
                    raise
    raise RuntimeError(f"too many redirects: {url}")


def variant(url, quality):
    """The address of one quality of the stream: the largest picture no taller than
    `quality`, else the smallest. (Live playlists list 1080p, 720p and 384p, archived
    ones 720p to 360p; the best is more than a 720p picture needs and heavy on slow links.)"""
    final, text = fetch_playlist(url)
    base, lines = final.rsplit("/", 1)[0], text.splitlines()
    found = []
    for i, line in enumerate(lines):
        m = re.search(r"RESOLUTION=\d+x(\d+)", line)
        if line.startswith("#EXT-X-STREAM-INF") and m and i + 1 < len(lines):
            found.append((int(m[1]), lines[i + 1].strip()))
    if not found:
        return final
    fit = [f for f in found if f[0] <= quality]
    height, path = max(fit) if fit else min(found)
    return path if path.startswith("http") else f"{base}/{path}"


def sitting_number(title):
    m = re.match(r"\s*(\d+)\.", title)
    return int(m[1]) if m else None


def load_tags():
    path = ROOT / "data" / "tags.json"
    return json.loads(path.read_text(encoding="utf-8")).get("bills", {}) if path.exists() else {}


def passed(v):
    return v["yes"] > v["no"] if v.get("majorityType") == "SIMPLE_MAJORITY" else v["yes"] >= (v.get("majorityVotes") or 0)


def captions(shown, tags, title):
    """(item lines, topic line, vote line) for the latest vote the picture has reached."""
    if not shown:
        return f"{title}", " ", "Głosowania pojawią się tutaj, gdy zaczną się na sali."
    v = shown[-1]
    # the vote's own title names its item ("Pkt. 2 Sprawozdanie … (druki nr 611, 3202 i 3202-A)");
    # the published agenda is the planned one, in lists each numbered from 1, and the
    # items are renumbered at the sitting, so its numbers cannot be trusted
    m = re.match(r"\s*Pkt\.?\s*(\d+)", v.get("title") or "")
    n = m[1] if m else None
    text = re.sub(r"^\s*Pkt\.?\s*\d+\.?\s*", "", v.get("title") or "")
    text = re.sub(r"\s*-\s*(pierwsze|drugie|trzecie) czytanie\s*$", "", text)
    prints = [p for m in re.finditer(r"druk(?:i|ów)?\s+nr\s+([\d\-A-Za-z ,i]+)", text)
              for p in re.findall(r"\d+(?:-[A-Za-z0-9]+)?", m[1])]
    topic = next((", ".join(tags[p]) for p in prints if p in tags), "")
    head = f"Punkt {n} · {text}" if n else text
    lines = [textwrap.shorten(head, 220, placeholder="…")]   # the caption box fits it to two lines
    result = "PRZYJĘTO" if passed(v) else "ODRZUCONO"
    vote = f"Głosowanie nr {v['votingNumber']} · {v.get('topic') or ''} · {result}: {v['yes']} za / {v['no']} przeciw / {v['abstain']} wstrz."
    return "\n".join(lines), (f"Temat: {topic}" if topic else " "), textwrap.shorten(vote, 110, placeholder="…")


DIFF_LINES = 12                                         # lines of the panel with what an amendment changes
DIFF_SLOTS = DIFF_LINES + 4                             # with PAGE_STRETCH below: lines the panel can hold
PAGE_SECONDS = 8                                        # a longer change is shown in pages, in turn, at most this long each…
PAGE_CYCLE = 30                                         # …and faster when there are many, so all pass while the next vote is
PAGE_MIN = 5                                            # called and held (about half a minute), but no faster than this
MAX_PAGES = 6
PAGE_STRETCH = 4                                        # a page may run this many lines over to keep a passage whole
QUIET = 300                                             # seconds without a vote: the panel shows fun facts
SPEAKER_SECONDS = 20                                    # how long the card of a speaker who has just begun stays
SPEAKER_BAR = 600                                       # how long the bar names a speaker (until the next one)
FACT_SECONDS = 12                                       # a fact card is on screen this long…
FACT_EVERY = 90                                         # …once in this many seconds, so a long day does not run through them
CLUB_AFTER = 40                                         # a speech this far in: the cards are the speaker's club's Top 5s
TOP_SECONDS = 16                                        # a Top 5 card, longer to read
FACTS_URL = "https://sejmomat.pl/api/v1/ciekawostki.json"
PROMO_EVERY = 8                                         # one card in this many (of the general turn) is about the site
PROMOS = [
    {"kind": "promo", "title": "Zagraj w Sejmdle", "headline": "Codzienne gry o Sejmie",
     "text": "Zgadnij posła, uzupełnij słowo z mównicy, rozpoznaj jak najwięcej twarzy w minutę.",
     "url": "sejmomat.pl/sejmdle"},
    {"kind": "promo", "title": "Wesprzyj Sejmomat", "headline": "Sejmomat jest darmowy i niezależny",
     "text": "Jeśli Ci się przydaje, możesz postawić twórcy kawę.",
     "url": "buycoffee.to/adamkoscielak"},
]


def load_facts():
    """The site's fun facts (sejmomat/facts.py): from a local build if there is one, else the site."""
    local = ROOT / "site" / "api" / "v1" / "ciekawostki.json"
    try:
        if local.exists():
            found = json.loads(local.read_text(encoding="utf-8"))
        else:
            with urllib.request.urlopen(FACTS_URL, timeout=30) as r:
                found = json.load(r)
    except Exception:
        return []
    # the site's first version had plain sentences
    return [f if isinstance(f, dict) else {"kind": "fact", "title": "Czy wiesz, że…", "value": "", "unit": "", "text": f}
            for f in found]
_diffs = {}


def _plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def diff_panel(v):
    """(heading, [page of (colour, line)]) for a vote on amendments or minority motions:
    what the first of them changes in the bill (removed lines red, added green), or its
    text, in pages of DIFF_LINES - 1 lines; ("", []) otherwise. Needs the report prints
    in data/prints (git pull)."""
    key = (v["sitting"], v["votingNumber"])
    if key in _diffs and (_diffs[key][1][1] or time.time() - _diffs[key][0] < 60):
        return _diffs[key][1]
    if key in _diffs:
        # tried before, without the print: forget what the site's code remembers of missing prints
        for f in vars(model).values():
            if hasattr(f, "cache_clear"):
                f.cache_clear()
    out = ("", [])
    try:
        linked = [a for a in link_amendments({**v, "prints": None}) if a["item"]]
    except Exception:
        linked = []
    if linked:
        a = linked[0]
        it = a["item"]
        what = {"minority": "wniosek mniejszości", "amendment": "poprawka", "senate": "poprawka Senatu"}[a["kind"]]
        passages = []   # each a list of (colour, line), kept on one page where it fits

        def wrap(text, mark, colour):
            return [(colour, line) for line in textwrap.wrap(f"{mark} {text}", 46, subsequent_indent="   ") or [mark]]
        changes = (it.get("bill_diff") or {}).get("changes") or []
        for ch in changes:
            where = [("w", line) for line in textwrap.wrap(ch.get("where") or "", 46)]
            for r in ch.get("rows", []):
                html = r["html"]
                if r["state"] == "removed":
                    passages.append(wrap(_plain(html), "−", "r"))
                elif r["state"] == "added":
                    passages.append(wrap(_plain(html), "+", "g"))
                elif r["state"] == "changed":
                    passages.append(wrap(_plain(re.sub(r"<ins>.*?</ins>", "", html)), "−", "r")
                                    + wrap(_plain(re.sub(r"<del>.*?</del>", "", html)), "+", "g"))
                else:
                    continue
                if where:   # the place in the bill goes with its first passage
                    passages[-1] = where + passages[-1]
                    where = []
        if not passages:
            # no comparison with the bill: the amendment's own words
            passages = [[("w", line)] for line in textwrap.wrap(_plain(it.get("text") or ""), 46)]
        per = DIFF_LINES - 1
        pages, page = [], []
        for passage in passages:
            # a passage that fits on a page (stretched a little) is not split across pages
            if page and len(page) + len(passage) > per + PAGE_STRETCH and len(passage) <= per + PAGE_STRETCH:
                pages.append(page)
                page = []
            for row in passage:
                if len(page) >= per + PAGE_STRETCH:
                    pages.append(page)
                    page = []
                page.append(row)
            if len(page) >= per:
                pages.append(page)
                page = []
        if page:
            # a short last page joins the one before when they fit together
            if pages and len(page) <= 3 and len(pages[-1]) + len(page) <= per + PAGE_STRETCH:
                pages[-1] += page
            else:
                pages.append(page)
        if len(pages) > MAX_PAGES:
            pages = pages[:MAX_PAGES]
            pages[-1] = pages[-1][:per - 1] + [("w", f"… dalej w druku nr {a['source']}")]
        out = (f"Co zmienia {what} {a['number']}" + (f" (druk {a['source']})" if a["source"] else ""), pages)
    # nothing found is tried again a minute later: the report print may not be pulled yet
    _diffs[key] = (time.time(), out)
    return out


FPS = 25


def ffmpeg_command(src, out, snapshot, fast=False):
    """The ffmpeg command: the stream read at normal speed and scaled to 1280x720,
    with the overlay (RGBA frames from this script, on stdin) laid over it; and,
    every 2 seconds, the band where the broadcast names a speaker, saved to
    `snapshot` for the speaker recognition (tools/live_speaker.py; snapshot None:
    not needed). The picture ends when the overlay does (stdin closed), so a file
    is finished properly."""
    proxy = ["-http_proxy", VIDEO_PROXY] if VIDEO_PROXY else []
    inputs = [*([] if fast else ["-re"]), *proxy, "-i", src,
              "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-framerate", str(FPS), "-thread_queue_size", "64", "-i", "pipe:0"]
    bx, by, bw, bh = BAND
    scaled = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS}"
    if snapshot:
        v = (f"{scaled},split=2[base][cap];[base][1:v]overlay=0:0:format=auto:eof_action=endall[v];"
             f"[cap]fps=1/2,crop={bw}:{bh}:{bx}:{by}[band]")
    else:
        v = f"{scaled}[base];[base][1:v]overlay=0:0:format=auto:eof_action=endall[v]"
    # on a server (no terminal) the progress line once a minute, for the log
    quiet = [] if sys.stderr.isatty() else ["-stats_period", "60"]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", *quiet, *inputs, "-filter_complex", v, "-map", "[v]", "-map", "0:a?"]
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
           "-pix_fmt", "yuv420p", "-g", "50", "-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
    snap = ["-map", "[band]", "-f", "image2", "-update", "1", "-y", str(snapshot)] if snapshot else []
    if out == "preview":
        return cmd + enc + ["-f", "matroska", "-"] + snap, True
    if out == "rtmp":
        url = os.environ.get("SEJMOMAT_RTMP")
        if not url:
            sys.exit("Set SEJMOMAT_RTMP to the platform's address with your stream key.")
        return cmd + enc + ["-f", "flv", url] + snap, False
    # a file: compressed for upload (constant quality) rather than for a live link (constant rate)
    enc = [*enc[:4], "-crf", "23", *enc[6:]]
    return cmd + enc + ["-shortest", "-y", out] + snap, False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", help='replay from this Warsaw time, e.g. "2026-10-22 17:40"')
    ap.add_argument("--delay", type=int, default=100, help="live: seconds behind live (default 100)")
    ap.add_argument("--out", default="preview", help='"preview" (window), "rtmp" (SEJMOMAT_RTMP), or a file name')
    ap.add_argument("--seconds", type=int, help="stop after this many seconds")
    ap.add_argument("--quality", type=int, default=720, help="stream quality to read: picture height, e.g. 1080, 720, 384 (default 720)")
    ap.add_argument("--demo", action="store_true", help="for a demo recording: a card every 13 s, the liveliest ones first, no cards about the site")
    ap.add_argument("--no-speakers", action="store_true", help="no speaker recognition (needs tesseract with Polish)")
    ap.add_argument("--transcript", action="store_true", help="replay: who speaks from the day's transcript (data/speeches), not the screen")
    ap.add_argument("--fast", action="store_true", help="to a file: as fast as the computer can, not in real time")
    ap.add_argument("--wait", action="store_true", help="live, unattended: wait for the day's sitting instead of stopping when there is none")
    ap.add_argument("--font", help="regular font file")
    ap.add_argument("--font-bold", help="bold font file")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed.")

    if args.at:
        start = datetime.fromisoformat(args.at).replace(tzinfo=WARSAW)
        title, base, _, end = plenary(start.date().isoformat())
        mode = "Retransmisja"
    else:
        title, base, _, end = wait_for_plenary(args.delay) if args.wait else plenary("today")
        start = datetime.now(WARSAW).replace(microsecond=0) - timedelta(seconds=args.delay)
        mode = f"Na żywo, ~{round(args.delay / 60)} min opóźnienia"
    # without "stop": with it the server answers from its archive, whose playlists start at the
    # day's beginning whatever "start" says; this way the picture starts where asked
    src = variant(f"{base}?start={ms(start)}", args.quality)
    n = sitting_number(title)
    tags, facts = load_tags(), load_facts()
    # the general turn, and for each club its own cards (its Top 5s, its card), for while one of its MPs speaks
    by_club = {}
    for f in facts:
        if f.get("for_club") or (f.get("stats") and f.get("kind") == "fact" and f.get("club")):
            by_club.setdefault(f.get("for_club") or f["club"], []).append(f)
    for pool in by_club.values():
        pool.sort(key=lambda f: f.get("kind") != "top5")   # its Top 5s first, then the club's card
    facts = [f for f in facts if not f.get("for_club")]
    every, first, club_after, promos = FACT_EVERY, 0, CLUB_AFTER, PROMOS
    if args.demo:
        # the liveliest cards first, one after another, from the start of the recording
        kinds = {k: [f for f in facts if f.get("kind") == k] for k in ("top5", "mp", "fact")}
        club = [f for f in kinds["fact"] if f.get("stats")]
        lively = [kinds["top5"][:1], club[:1], kinds["mp"][:1], [f for f in kinds["fact"] if "bunt" in f["title"].lower()],
                  kinds["top5"][1:2], kinds["mp"][1:2]]
        picked = spread([f for group in lively for f in group if f.get("kind") != "top5"],
                        [f for group in lively for f in group if f.get("kind") == "top5"])
        facts = picked + [f for f in facts if f not in picked]
        every, first, club_after, promos = 13, start.timestamp(), SPEAKER_SECONDS, []
    print(f"{title} · from {start:%H:%M:%S} · sitting {n}")

    overlay = Overlay(args.font_bold or font(True), args.font or font(False), ROOT / "static" / "logo-white.png",
                      f"SEJMOMAT · {mode} · {title}")
    # the photos, before the first frame needs them: 8 at a time (the Sejm's API takes a
    # second or two each; afterwards they come from the cache on disk)
    mps = {mp for card in facts + [f for fs in by_club.values() for f in fs]
           for mp in [card.get("mp")] + [r["mp"] for r in card.get("rows") or []] if mp}
    began = time.monotonic()
    print(f"MP photos for the cards: {len(mps)}", flush=True)
    with ThreadPoolExecutor(8) as pool:
        for i, _ in enumerate(pool.map(overlay.photo, sorted(mps)), 1):
            if i % 20 == 0 and i < len(mps):
                print(f"  photos {i}/{len(mps)}…", flush=True)
        # those that failed (the API is slow now and then), once more
        again = [mp for mp in mps if overlay.photo(mp) is None]
        for mp in again:
            overlay._photos.pop(mp, None)
        list(pool.map(overlay.photo, again))
    got = sum(1 for mp in mps if overlay.photo(mp))
    print(f"MP photos: {got} of {len(mps)} in {time.monotonic() - began:.0f} s", flush=True)
    votes = []
    lock = threading.Lock()

    def poll():
        # new votes every 20 s, in the background
        while True:
            got = get_or_none(f"votings/{n}") if n else None
            if got:
                with lock:
                    votes[:] = sorted(got, key=lambda v: v["votingNumber"])
            time.sleep(20)
    threading.Thread(target=poll, daemon=True).start()

    # who is speaking: the broadcast's name caption, read every 2 seconds
    work = Path(tempfile.mkdtemp(prefix="sejmomat-live-"))
    snapshot = work / "band.png"
    recogniser = Recogniser(load_mps(ROOT)) if shutil.which("tesseract") and not (args.no_speakers or args.transcript) else None
    if not recogniser and not (args.no_speakers or args.transcript):
        print("tesseract not found: no speaker recognition", file=sys.stderr)
    speaker = {"card": None, "at": None, "mp": None, "until": None}
    now = {"clock": start}

    def speaker_card(m):
        return {"kind": "mp", "mp": m["id"], "name": m["name"], "club": m.get("club") or "niez.", "title": "Na mównicy",
                "value": m.get("speeches") or 0, "unit": "wystąpień w kadencji",
                "stats": [["frekwencja", f"{m.get('turnout', 0) * 100:.1f}%".replace(".", ",")],
                          ["wyłamania", str(m.get("brokeLine", 0))], ["interpelacje", str(m.get("questions", 0))],
                          ["zmiany klubu", str(m.get("clubSwitches", 0))]]}

    # a past day (--transcript): who spoke when, from the transcript, instead of reading the screen
    transcript = load_transcript(start.date().isoformat()) if args.transcript else []
    mp_by_id = {m["id"]: m for m in load_mps(ROOT)} if transcript else {}

    def follow_transcript(clock):
        on = next((x for x in transcript if x["start"] <= clock < x["end"]), None)
        if on and speaker["mp"] != on["mp"] and on["mp"] in mp_by_id:
            m = mp_by_id[on["mp"]]
            overlay.photo(m["id"])
            speaker.update(mp=m["id"], at=on["start"], until=on["end"], card=speaker_card(m))

    def watch():
        seen = 0
        while recogniser:
            time.sleep(1)
            try:
                mtime = snapshot.stat().st_mtime
            except OSError:
                continue
            if mtime == seen:
                continue
            seen = mtime
            m = recogniser.match(read(snapshot))
            if not m:
                continue
            clock = now["clock"]
            # the caption stays a few seconds: one card per speaker, not one per snapshot
            if speaker["mp"] == m["id"] and speaker["at"] and (clock - speaker["at"]).total_seconds() < 60:
                continue
            print(f"{clock:%H:%M:%S} na mównicy: {m['name']} ({m.get('club')})", flush=True)
            overlay.photo(m["id"])
            speaker.update(mp=m["id"], at=clock, until=None, card=speaker_card(m))
    if not transcript:
        threading.Thread(target=watch, daemon=True).start()
    time.sleep(1)

    picks, turns = {}, {}
    showing = {"until": 0.0, "speaker": None, "start": 0.0}   # when the card on screen goes; the speaker card's turn

    def pick(slot, clock):
        """The card for a slot, chosen once: while an MP has been speaking a while (a longer
        speech), the next of their club's cards; otherwise the next of the general turn."""
        if slot not in picks:
            sp, at = speaker["card"], speaker["at"]
            pool = by_club.get(sp["club"]) if sp else None
            if pool and club_after <= (clock - at).total_seconds() < SPEAKER_BAR and not (speaker["until"] and clock > speaker["until"]):
                i = turns[sp["club"]] = turns.get(sp["club"], -1) + 1
                picks[slot] = pool[i % len(pool)]
            else:
                i = turns["*"] = turns.get("*", -1) + 1
                if promos and i % PROMO_EVERY == PROMO_EVERY - 1:
                    picks[slot] = promos[(i // PROMO_EVERY) % len(promos)]
                else:
                    j = turns["facts"] = turns.get("facts", -1) + 1
                    picks[slot] = facts[j % len(facts)]
        return picks[slot]

    def frame(clock):
        """The overlay for the picture at `clock`."""
        if transcript:
            follow_transcript(clock)
        with lock:
            shown = [v for v in votes if warsaw(v["date"]) <= clock]
        item, topic, vote = captions(shown, tags, title)
        recent = shown and (clock - warsaw(shown[-1]["date"])).total_seconds() < QUIET
        chip = None
        if shown and not recent:
            # a debate or a break: the vote below is an earlier one
            vote = textwrap.shorten(f"Ostatnie głosowanie ({shown[-1]['date'][11:16]}): {vote.replace('Głosowanie ', '')}", 112, placeholder="…")
        if not recent:
            # no votes going on: the bar names who is speaking (the agenda item is hard to tell then)
            sp = speaker["card"]
            if sp and 0 <= (clock - speaker["at"]).total_seconds() < SPEAKER_BAR and not (speaker["until"] and clock > speaker["until"]):
                stats = dict(sp["stats"])
                item, chip = sp["name"], sp["club"]
                topic = (f"Na mównicy od {speaker['at']:%H:%M} · {sp['value']} wystąpień w kadencji · "
                         f"frekwencja {stats.get('frekwencja')} · wyłamania z linii klubu: {stats.get('wyłamania')}")
            else:
                item, topic = title, "Mówca pojawi się tu, gdy transmisja go przedstawi"
        panel = card = None
        if recent:
            head, pages = diff_panel(shown[-1])
            if pages:
                each = max(PAGE_MIN, min(PAGE_SECONDS, PAGE_CYCLE / len(pages)))
                page = int((clock - warsaw(shown[-1]["date"])).total_seconds() // each) % len(pages)
                panel = (f"{head} · {page + 1}/{len(pages)}" if len(pages) > 1 else head, pages[page])
        else:
            ts = clock.timestamp()
            # a speaker who has just come to the rostrum: their card, but only once the card on
            # screen has gone (the bar names them at once)
            if speaker["card"] and showing["speaker"] != speaker["at"]:
                showing.update(speaker=speaker["at"], start=max(speaker["at"].timestamp(), showing["until"]))
            since = ts - showing["start"] if showing["speaker"] else -1
            if speaker["card"] and 0 <= since < SPEAKER_SECONDS:
                card = overlay.card(speaker["card"], since, SPEAKER_SECONDS)
            elif facts:
                # a debate, a break: a fun-fact card, one every FACT_EVERY seconds for FACT_SECONDS;
                # one whose turn comes while the speaker's card is up is left out, not cut short
                slot, into = int((ts - first) // every), (ts - first) % every
                begun = ts - into
                if not (showing["speaker"] and showing["start"] <= begun < showing["start"] + SPEAKER_SECONDS):
                    c = pick(slot, clock)
                    length = min(TOP_SECONDS if c.get("kind") == "top5" else FACT_SECONDS, every - 1)
                    if into < length:
                        card = overlay.card(c, into, length)
                        showing["until"] = begun + length
        return overlay.frame(item, topic, vote, panel, card, chip)

    if args.fast and args.out in ("preview", "rtmp"):
        sys.exit("--fast is for a file.")
    cmd, preview = ffmpeg_command(src, args.out, snapshot if recogniser else None, args.fast)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE if preview else None)
    viewer = subprocess.Popen(["ffplay", "-hide_banner", "-loglevel", "warning", "-window_title", "Sejmomat", "-"],
                              stdin=proc.stdout) if preview else None
    try:
        # one overlay frame per video frame, each drawn for the moment of the picture it goes on;
        # ffmpeg takes them as it needs them, so this loop keeps pace with the stream by itself
        i, drawn, worst, began = 0, 0.0, 0.0, time.monotonic()
        while proc.poll() is None:
            t = i / FPS
            if args.seconds and t > args.seconds:
                break
            now["clock"] = start + timedelta(seconds=t)
            a = time.perf_counter()
            image = frame(now["clock"])
            took = time.perf_counter() - a
            drawn, worst = drawn + took, max(worst, took)
            proc.stdin.write(image)
            i += 1
            if i % (60 * FPS) == 0:
                # once a minute: how long the overlay takes, and whether the picture keeps up
                # with the clock (behind > 0: the stream is falling behind, video or CPU)
                behind = time.monotonic() - began - t
                print(f"{now['clock']:%H:%M:%S} overlay {drawn / (60 * FPS) * 1000:.1f} ms/frame (max {worst * 1000:.0f}),"
                      f" behind real time {behind:.0f} s", file=sys.stderr, flush=True)
                drawn = worst = 0.0
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        # the overlay has ended: ffmpeg finishes the file by itself (given time) unless it
        # also keeps the speaker snapshots going
        try:
            proc.wait(timeout=30 if not recogniser else 1)
        except subprocess.TimeoutExpired:
            pass
        for p in (viewer, proc):
            if p and p.poll() is None:
                p.terminate()
        for p in (viewer, proc):
            if p:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    main()
