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
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sejmomat import agenda as agenda_mod  # noqa: E402  (the site's agenda parser)
from sejmomat.model import link_amendments  # noqa: E402  (what an amendment changes, as on vote pages)

API = "https://api.sejm.gov.pl/sejm/term10"
WARSAW = ZoneInfo("Europe/Warsaw")
W, H = 1280, 720


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


def write(path, text):
    """Replace a caption file in one step, so ffmpeg never reads half of it."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
PAGE_SECONDS = 8                                        # a longer change is shown in pages, in turn
MAX_PAGES = 6
DIFF_COLOURS = {"w": "white", "r": "0xff9a9a", "g": "0x9be8ab"}  # text, removed, added
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
        rows = []
        def wrap(text, mark):
            return textwrap.wrap(f"{mark} {text}", 46, subsequent_indent="   ") or [mark]
        changes = (it.get("bill_diff") or {}).get("changes") or []
        for ch in changes:
            if ch.get("where"):
                rows += [("w", line) for line in textwrap.wrap(ch["where"], 46)]
            for r in ch.get("rows", []):
                html = r["html"]
                if r["state"] == "removed":
                    rows += [("r", line) for line in wrap(_plain(html), "−")]
                elif r["state"] == "added":
                    rows += [("g", line) for line in wrap(_plain(html), "+")]
                elif r["state"] == "changed":
                    rows += [("r", line) for line in wrap(_plain(re.sub(r"<ins>.*?</ins>", "", html)), "−")]
                    rows += [("g", line) for line in wrap(_plain(re.sub(r"<del>.*?</del>", "", html)), "+")]
        if not rows:
            # no comparison with the bill: the amendment's own words
            rows = [("w", line) for line in textwrap.wrap(_plain(it.get("text") or ""), 46)]
        per = DIFF_LINES - 1
        pages = [rows[i:i + per] for i in range(0, len(rows), per)]
        if len(pages) > MAX_PAGES:
            pages = pages[:MAX_PAGES]
            pages[-1] = pages[-1][:per - 1] + [("w", f"… dalej w druku nr {a['source']}")]
        out = (f"Co zmienia {what} {a['number']}" + (f" (druk {a['source']})" if a["source"] else ""), pages)
    _diffs[key] = out
    return out


def ffmpeg_command(src, files, out, fonts, logo, diff_files):
    """The ffmpeg command: the stream read at normal speed, scaled to 1280x720,
    with a bar along the bottom carrying the two caption files and a label at
    the top left."""
    item, topic, vote, label = (str(f).replace(":", r"\:") for f in files)
    bold, regular = (f.replace(":", r"\:") for f in fonts)
    bar_h = 172
    v = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
         f"drawbox=x=0:y={H - bar_h}:w={W}:h={bar_h}:color=black@0.72:t=fill,"
         f"drawbox=x=0:y={H - bar_h}:w=6:h={bar_h}:color=0x1d5fc4@1:t=fill,"
         f"drawtext=fontfile='{bold}':textfile='{item}':reload=1:fontsize=25:fontcolor=white:line_spacing=6:x=28:y={H - bar_h + 14},"
         f"drawtext=fontfile='{regular}':textfile='{topic}':reload=1:fontsize=20:fontcolor=0x9cc3ff:x=28:y={H - bar_h + 88},"
         f"drawtext=fontfile='{regular}':textfile='{vote}':reload=1:fontsize=22:fontcolor=0xffd479:x=28:y={H - 38},"
         f"drawtext=fontfile='{regular}':textfile='{label}':reload=1:fontsize=18:fontcolor=white:x=28:y=24:box=1:boxcolor=black@0.6:boxborderw=8")
    # the panel on the right: what the amendment being voted on changes, outlined like subtitles;
    # a line comes in three colours, each its own file, and only one of them holds text
    head, slots = (str(f).replace(":", r"\:") for f in diff_files[:1]), diff_files[1]
    x0, y0, step = W - 540, 76, 25
    v += (f",drawtext=fontfile='{bold}':textfile='{next(head)}':reload=1:fontsize=20:fontcolor=0xffd479:"
          f"borderw=2:bordercolor=black@0.85:x={x0}:y={y0}")
    for (i, colour), path in slots.items():
        v += (f",drawtext=fontfile='{regular}':textfile='{str(path).replace(':', chr(92) + ':')}':reload=1:fontsize=19:"
              f"fontcolor={DIFF_COLOURS[colour]}:borderw=2:bordercolor=black@0.85:x={x0}:y={y0 + 32 + i * step}")
    inputs = ["-re", "-i", src]
    if logo:
        inputs += ["-i", str(logo)]
        v += f"[v0];[1:v]scale=-1:30[logo];[v0][logo]overlay=W-w-24:22"
    v += "[v]"
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
    items, tags = agenda_items(n) if n else {}, load_tags()
    print(f"{title} · from {start:%H:%M:%S} · sitting {n}, {len(items)} agenda items")

    work = Path(tempfile.mkdtemp(prefix="sejmomat-live-"))
    files = (work / "item.txt", work / "topic.txt", work / "vote.txt", work / "label.txt")
    write(files[3], f"SEJMOMAT · {mode} · {title}")
    diff_head = work / "diff-head.txt"
    diff_slots = {(i, c): work / f"diff-{i}-{c}.txt" for i in range(DIFF_LINES) for c in DIFF_COLOURS}
    votes = []

    def refresh(clock):
        nonlocal votes
        if n:
            got = get_or_none(f"votings/{n}") or []
            if len(got) >= len(votes):
                votes = sorted(got, key=lambda v: v["votingNumber"])
        show(clock)

    def show(clock):
        shown = [v for v in votes if warsaw(v["date"]) <= clock]
        for f, text in zip(files, captions(shown, items, tags, title)):
            write(f, text)
        # drawtext refuses an empty file, so a blank line is a space
        head, pages = diff_panel(shown[-1]) if shown else ("", [])
        rows = []
        if pages:
            # the pages in turn, from the moment the vote came up on screen
            page = int((clock - warsaw(shown[-1]["date"])).total_seconds() // PAGE_SECONDS) % len(pages)
            rows = pages[page]
            if len(pages) > 1:
                head = f"{head} · {page + 1}/{len(pages)}"
        write(diff_head, head or " ")
        for (i, c), path in diff_slots.items():
            write(path, rows[i][1] if i < len(rows) and rows[i][0] == c else " ")

    refresh(start)
    fonts = (args.font_bold or font(True), args.font or font(False))
    logo = ROOT / "static" / "logo-white.png"
    cmd, preview = ffmpeg_command(src, files, args.out, fonts, logo if logo.exists() else None, (diff_head, diff_slots))
    # ffmpeg reports how far into the stream it is: the captions follow that, not the wall clock,
    # so they stay with the picture even when the download is slower than real time
    progress = work / "progress.txt"
    cmd[1:1] = ["-progress", str(progress), "-stats_period", "1"]
    began = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE if preview else None)
    viewer = subprocess.Popen(["ffplay", "-hide_banner", "-loglevel", "warning", "-window_title", "Sejmomat", "-"],
                              stdin=proc.stdout) if preview else None
    last_poll = last_warning = 0

    def position():
        """Seconds of stream ffmpeg has put out so far."""
        try:
            found = re.findall(r"out_time_us=(\d+)", progress.read_text())
            return int(found[-1]) / 1e6 if found else 0.0
        except (OSError, ValueError):
            return 0.0

    try:
        while proc.poll() is None:
            elapsed = time.monotonic() - began
            if args.seconds and elapsed > args.seconds:
                break
            pos = position()
            clock = start + timedelta(seconds=pos)
            if elapsed > 30 and elapsed - pos > 20 and time.monotonic() - last_warning > 60:
                last_warning = time.monotonic()
                print(f"the stream arrives slower than real time ({pos:.0f} s of video in {elapsed:.0f} s): "
                      f"try --quality 384", file=sys.stderr)
            # the API every 20 s; the captions follow the clock every second
            if time.monotonic() - last_poll > 20:
                last_poll = time.monotonic()
                refresh(clock)
            else:
                show(clock)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (viewer, proc):
            if p and p.poll() is None:
                p.terminate()
        # ffmpeg reads the caption files until it has finished writing
        for p in (viewer, proc):
            if p:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
