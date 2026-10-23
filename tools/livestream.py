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
import textwrap
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sejmomat import agenda as agenda_mod  # noqa: E402  (the site's agenda parser)
from sejmomat.model import link_amendments  # noqa: E402  (what an amendment changes, as on vote pages)
from live_overlay import H, W, Overlay  # noqa: E402

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


def variant(url, quality):
    """The address of one quality of the stream: the largest picture no taller than
    `quality`, else the smallest. (Live playlists list 1080p, 720p and 384p, archived
    ones 720p to 360p; the best is more than a 720p picture needs and heavy on slow links.)"""
    with urllib.request.urlopen(url, timeout=60) as r:
        base, lines = r.geturl().rsplit("/", 1)[0], r.read().decode().splitlines()
    found = []
    for i, line in enumerate(lines):
        m = re.search(r"RESOLUTION=\d+x(\d+)", line)
        if line.startswith("#EXT-X-STREAM-INF") and m and i + 1 < len(lines):
            found.append((int(m[1]), lines[i + 1].strip()))
    if not found:
        return url
    fit = [f for f in found if f[0] <= quality]
    height, path = max(fit) if fit else min(found)
    return path if path.startswith("http") else f"{base}/{path}"


def sitting_number(title):
    m = re.match(r"\s*(\d+)\.", title)
    return int(m[1]) if m else None


def agenda_items(n):
    """{item number: (text, [prints])} of a sitting, numbered as votes number them ("Pkt. 17")."""
    p = get_or_none(f"proceedings/{n}") or {}
    a = agenda_mod.number(agenda_mod.parse(p.get("agenda") or ""))
    return {i["n"]: (f"{i['kind']} {i['rest']}".strip(), i["prints"]) for g in a["groups"] for i in g["items"]}


def load_tags():
    path = ROOT / "data" / "tags.json"
    return json.loads(path.read_text(encoding="utf-8")).get("bills", {}) if path.exists() else {}


def passed(v):
    return v["yes"] > v["no"] if v.get("majorityType") == "SIMPLE_MAJORITY" else v["yes"] >= (v.get("majorityVotes") or 0)


def captions(shown, items, tags, title):
    """(item lines, topic line, vote line) for the latest vote the picture has reached."""
    if not shown:
        return f"{title}", " ", "Głosowania pojawią się tutaj, gdy zaczną się na sali."
    v = shown[-1]
    m = re.match(r"\s*Pkt\.?\s*(\d+)", v.get("title") or "")
    n = m[1] if m else None
    text, prints = items.get(n, (re.sub(r"^\s*Pkt\.?\s*\d+\.?\s*", "", v.get("title") or ""), []))
    topic = next((", ".join(tags[p]) for p in prints if p in tags), "")
    head = f"Punkt {n} · {text}" if n else text
    lines = textwrap.wrap(head, 78)[:2]
    if len(textwrap.wrap(head, 78)) > 2:
        lines[-1] = lines[-1][:75].rstrip() + "…"
    result = "PRZYJĘTO" if passed(v) else "ODRZUCONO"
    vote = f"Głosowanie nr {v['votingNumber']} · {v.get('topic') or ''} · {result}: {v['yes']} za / {v['no']} przeciw / {v['abstain']} wstrz."
    return "\n".join(lines), (f"Temat: {topic}" if topic else " "), textwrap.shorten(vote, 110, placeholder="…")


DIFF_LINES = 12                                         # lines of the panel with what an amendment changes
DIFF_SLOTS = DIFF_LINES + 4                             # with PAGE_STRETCH below: lines the panel can hold
PAGE_SECONDS = 8                                        # a longer change is shown in pages, in turn
MAX_PAGES = 6
PAGE_STRETCH = 4                                        # a page may run this many lines over to keep a passage whole
QUIET = 300                                             # seconds without a vote: the panel shows fun facts
FACT_SECONDS = 15
FACTS_URL = "https://sejmomat.pl/api/v1/ciekawostki.json"


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
    if key in _diffs:
        return _diffs[key]
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
    _diffs[key] = out
    return out


FPS = 25


def ffmpeg_command(src, out):
    """The ffmpeg command: the stream read at normal speed and scaled to 1280x720,
    with the overlay (RGBA frames from this script, on stdin) laid over it."""
    inputs = ["-re", "-i", src,
              "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-framerate", str(FPS), "-thread_queue_size", "64", "-i", "pipe:0"]
    v = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS}[base];"
         f"[base][1:v]overlay=0:0:format=auto[v]")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", *inputs, "-filter_complex", v, "-map", "[v]", "-map", "0:a?"]
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
           "-pix_fmt", "yuv420p", "-g", "50", "-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
    if out == "preview":
        return cmd + enc + ["-f", "matroska", "-"], True
    if out == "rtmp":
        url = os.environ.get("SEJMOMAT_RTMP")
        if not url:
            sys.exit("Set SEJMOMAT_RTMP to the platform's address with your stream key.")
        return cmd + enc + ["-f", "flv", url], False
    return cmd + enc + ["-y", out], False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", help='replay from this Warsaw time, e.g. "2026-10-22 17:40"')
    ap.add_argument("--delay", type=int, default=100, help="live: seconds behind live (default 100)")
    ap.add_argument("--out", default="preview", help='"preview" (window), "rtmp" (SEJMOMAT_RTMP), or a file name')
    ap.add_argument("--seconds", type=int, help="stop after this many seconds")
    ap.add_argument("--quality", type=int, default=720, help="stream quality to read: picture height, e.g. 1080, 720, 384 (default 720)")
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
        title, base, _, end = plenary("today")
        start = datetime.now(WARSAW).replace(microsecond=0) - timedelta(seconds=args.delay)
        mode = f"Na żywo, ~{round(args.delay / 60)} min opóźnienia"
    # without "stop": with it the server answers from its archive, whose playlists start at the
    # day's beginning whatever "start" says; this way the picture starts where asked
    src = variant(f"{base}?start={ms(start)}", args.quality)
    n = sitting_number(title)
    items, tags, facts = agenda_items(n) if n else {}, load_tags(), load_facts()
    print(f"{title} · from {start:%H:%M:%S} · sitting {n}, {len(items)} agenda items")

    overlay = Overlay(args.font_bold or font(True), args.font or font(False), ROOT / "static" / "logo-white.png",
                      f"SEJMOMAT · {mode} · {title}")
    for card in facts:   # the photos, before the first frame needs them
        if card.get("kind") == "mp":
            overlay.photo(card["mp"])
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
    time.sleep(1)

    def frame(clock):
        """The overlay for the picture at `clock`."""
        with lock:
            shown = [v for v in votes if warsaw(v["date"]) <= clock]
        item, topic, vote = captions(shown, items, tags, title)
        recent = shown and (clock - warsaw(shown[-1]["date"])).total_seconds() < QUIET
        panel = card = None
        if recent:
            head, pages = diff_panel(shown[-1])
            if pages:
                page = int((clock - warsaw(shown[-1]["date"])).total_seconds() // PAGE_SECONDS) % len(pages)
                panel = (f"{head} · {page + 1}/{len(pages)}" if len(pages) > 1 else head, pages[page])
        elif facts:
            # no vote for a while (a debate, a break): a fun-fact card, a new one every FACT_SECONDS
            ts = clock.timestamp()
            c = facts[int(ts // FACT_SECONDS) % len(facts)]
            card = overlay.card(c, ts % FACT_SECONDS, FACT_SECONDS)
        return overlay.frame(item, topic, vote, panel, card)

    cmd, preview = ffmpeg_command(src, args.out)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE if preview else None)
    viewer = subprocess.Popen(["ffplay", "-hide_banner", "-loglevel", "warning", "-window_title", "Sejmomat", "-"],
                              stdin=proc.stdout) if preview else None
    try:
        # one overlay frame per video frame, each drawn for the moment of the picture it goes on;
        # ffmpeg takes them as it needs them, so this loop keeps pace with the stream by itself
        i = 0
        while proc.poll() is None:
            t = i / FPS
            if args.seconds and t > args.seconds:
                break
            proc.stdin.write(frame(start + timedelta(seconds=t)))
            i += 1
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        try:
            proc.stdin.close()
        except Exception:
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

if __name__ == "__main__":
    main()
