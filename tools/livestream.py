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
rewrites them. The broadcast names a speaker only some seconds into their
speech (CAPTION_LAG, measured with tools/caption_lag.py), so the name caption
is read from a second reading of the stream LOOKAHEAD seconds ahead of the
picture, and the speaker's card starts when they begin to speak.

The Sejm's broadcast is public; before streaming it to a platform, check the
Sejm's terms for rebroadcasting its feed.
"""
import argparse
import json
import os
import random
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
from itertools import zip_longest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sejmomat import model  # noqa: E402
from sejmomat.model import link_amendments  # noqa: E402  (what an amendment changes, as on vote pages)
from live_overlay import H, W, Overlay  # noqa: E402
from live_speaker import BAND, Recogniser, load_mps, read  # noqa: E402
import live_chat  # noqa: E402
from sejmomat.facts import spread  # noqa: E402
from sejmomat.social import club_short, shorten  # noqa: E402

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


def clubs_on(day):
    """{MP id: club} on a day: as in that day's last vote (or the last one before it); every
    vote lists every MP under their club, absent ones too."""
    last = None
    for f in sorted((ROOT / "data" / "votings").glob("*.json"), key=lambda f: int(f.stem)):
        for v in json.loads(f.read_text(encoding="utf-8"))["votings"]:
            if v["date"][:10] <= day and (not last or v["date"] > last["date"]):
                last = v
    if not last:
        return {}
    # the first day's provisional club ids, as the site counts them (model.merge_opening_ids)
    lasting = {"PSL": "PSL-TD", "Nowa_Lewica": "Lewica", "Polska2050": "Polska2050-TD"} if last["date"][:10] == "2023-11-13" else {}
    return {mp: lasting.get(club, club) for club, b in (last.get("ballots") or {}).items() for ids in b.values() for mp in ids}


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
# Telling the site we are on air (server/youtube-live.php), as YouTube will not tell it: every
# LIVE_EVERY seconds while streaming to the platform, with the key from /etc/sejmomat-live.env
LIVE_PING = os.environ.get("SEJMOMAT_LIVE_PING", "https://sejmomat.pl/srv/youtube-live.php").strip()
LIVE_KEY = os.environ.get("SEJMOMAT_LIVE_KEY", "").strip()
LIVE_EVERY = 30


def announce(live, title):
    """One report to the site: on air (with the title) or not. True if it was taken."""
    req = urllib.request.Request(LIVE_PING, data=json.dumps({"live": live, "title": title}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Sejmomat-Key": LIVE_KEY,
                                          "User-Agent": "sejmomat-live"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200


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


def source(base, start, end, quality):
    """The playlist to read from `start`. The server keeps two stores: a recent one (about
    two days, asked with "start" alone; also the live day) and the archive (asked with
    "start" and "stop"; a day is there some time after it ends). An older day asked with
    "start" alone gets a placeholder picture, so a finished day is asked of the archive
    first, and kept if its playlist covers the time asked for."""
    if end and end < datetime.now(WARSAW):
        try:
            url = variant(f"{base}?start={ms(start)}&stop={ms(end)}", quality)
            text = fetch_playlist(url)[1]
            covered = sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)", text))
            if covered >= (end - start).total_seconds() - 600:
                return url
        except Exception as e:
            print(f"archive: {e}", file=sys.stderr)
    return variant(f"{base}?start={ms(start)}", quality)


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


# Procedural votes under a name that says what they do (the Sejm's own is the motion's legal
# wording: "wniosek o skrócenie terminu, o którym mowa w art. 44 ust. 3 regulaminu Sejmu")
SHORT_TOPICS = [
    (r"skrócenie terminu", "przyśpieszenie ustawy"),
    (r"^wniosek o przerwę", "przerwa w obradach"),
    (r"odrzucenie projektu w pierwszym czytaniu", "odrzucenie projektu w I czytaniu"),
    (r"odrzucenie w całości projektu", "odrzucenie projektu w całości"),
    (r"odroczenie posiedzenia", "odroczenie posiedzenia"),
    (r"zamknięcie posiedzenia", "zamknięcie posiedzenia"),
    (r"kworum", "sprawdzenie kworum"),
    (r"(niezwłoczne )?przystąpienie do drugiego czytania", "od razu do II czytania, bez komisji"),
    (r"przystąpienie do trzeciego czytania", "od razu do III czytania, bez komisji"),
    (r"przystąpienie do głosowania bez kierowania", "głosowanie od razu, bez komisji"),
    (r"art\. 39 ust\. 3", "bez odsyłania do komisji"),
    (r"uzupełnienie porządku dziennego", "nowy punkt w porządku obrad"),
    (r"zmian\w* porządku dziennego", "zmiana porządku obrad"),
    (r"dodatkowe skierowanie projektu", "projekt także do innej komisji"),
    (r"odesłanie .*do komisji", "projekt z powrotem do komisji"),
    (r"reasumpcj", "powtórzenie głosowania"),
    (r"odrzucenie informacji", "odrzucenie informacji"),
]


# the chair's club, short, for the bar's strip
CHAIR_CLUB = {"Konfederacja": "Konf.", "Konfederacja_KP": "Konf. KP", "Polska2050": "Polska 2050", "RozwojPlus": "Rozwój Plus"}


def short_topic(topic):
    """A procedural vote's plain name, or the topic as it is."""
    for pattern, short in SHORT_TOPICS:
        if re.search(pattern, topic or "", re.I):
            return short
    return (topic or "").rstrip(".")


SUB_CHARS = 112   # about what a scene's subtitle line holds (18 px, the panel's width)


def vote_topic(v):
    """What a vote was on, for the scenes' subtitle: "poprawka 3 · ustawa o X", the
    procedural ones by their plain name; the bill after it unless the topic is the bill."""
    topic = short_topic(re.sub(r"^\s*Pkt\.?\s*\d+\.?\s*", "", v.get("topic") or v.get("title") or ""))
    # only an item that is a bill (a sitting's own votes, a break or the agenda, have the sitting as their item)
    bill = live_chat.item(v) if re.search(r"projek|ustaw|uchwał", v.get("title") or "", re.I) else ""
    return f"{topic} · {bill}" if bill and bill.lower() != topic.lower() else topic


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
    if not (v.get("yes") or v.get("no") or v.get("abstain")):
        # a quorum check ("Głosowanie kworum"): MPs only register as present, nothing
        # passes or fails, so no result (it used to read "ODRZUCONO: 0 za / 0 przeciw")
        present = v.get("present") or v.get("totalVoted")
        vote = f"Głosowanie nr {v['votingNumber']} · sprawdzenie kworum" + (f": obecnych {present} posłów" if present else "")
    else:
        result = "PRZYJĘTO" if passed(v) else "ODRZUCONO"
        vote = f"Głosowanie nr {v['votingNumber']} · {short_topic(v.get('topic'))} · {result}: {v['yes']} za / {v['no']} przeciw / {v['abstain']} wstrz."
    return "\n".join(lines), (f"Temat: {topic}" if topic else " "), textwrap.shorten(vote, 110, placeholder="…")


DIFF_LINES = 12                                         # lines of the panel with what an amendment changes
DIFF_SLOTS = DIFF_LINES + 4                             # with PAGE_STRETCH below: lines the panel can hold
PAGE_SECONDS = 8                                        # a longer change is shown in pages, in turn, at most this long each…
PAGE_CYCLE = 30                                         # …and faster when there are many, so all pass while the next vote is
PAGE_MIN = 5                                            # called and held (about half a minute), but no faster than this
MAX_PAGES = 6
PAGE_STRETCH = 4                                        # a page may run this many lines over to keep a passage whole
RESULT_SECONDS = 12                                     # after each vote: its result full screen, seat by seat and club by club
REACTION = 8                                            # after a vote on a whole bill: the hall's reaction, the result small, before the next amendment
SHRINK = 0.5                                            # …in its last seconds (no amendment after it) it shrinks into a small window, bottom right
FULL_WIDTH, FULL_LINES = 84, 10                         # then what an amendment changes, full screen: characters a line, lines a page
QUIET = 300                                             # seconds without a vote: the panel shows fun facts
# A break in the sitting: the broadcast holds its wide shot of the hall (tools/break/*.png,
# thumbnails of it), with nobody named and no votes. Then the screen shows comparisons
# (sejmomat/facts.py, "compare"), one after another, until the picture changes.
BREAK_REFS = sorted((Path(__file__).resolve().parent / "break").glob("*.png"))
BREAK_MATCH = 18                                        # a thumbnail this close to a reference (mean difference, 0-255) is the wide shot
BREAK_AFTER = 60                                        # the wide shot held this long: a break
BREAK_ENDS = 2                                          # this many snapshots in a row of something else end it
BREAK_NO_VOTE = 120                                     # …and none within this long of a vote (results are read out over wide shots too)
BREAK_NO_SPEAKER = 180                                  # …or of a speaker being named: a motion from the floor can be on the wide shot
CMP_SECONDS = 20                                        # each comparison on screen this long
THUMB = (64, 36)
SPEAKER_SECONDS = 20                                    # how long the card of a speaker who has just begun stays
SPEAKER_BAR = 600                                       # how long the bar names a speaker (until the next one)
CAPTION_LAG = 8                                         # the broadcast names a speaker this long after they begin, or later (10th percentile of 73 speeches, October 2026: median 12 s; tools/caption_lag.py)
LOOKAHEAD = 25                                          # the captions are read this far ahead of the picture, so a speaker's card can start when they do
SNAP_EVERY = 1                                          # a snapshot of the caption band every this many seconds (a name may be up for little more than a second)
FACT_SECONDS = 12                                       # a fact card is on screen this long…
FACT_EVERY = 60                                         # …once in this many seconds, so a long day does not run through them
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
     "url": "buycoffee.to/sejmomat"},
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


def diff_panel(v, width=46, lines=None):
    """(heading, [page of (colour, line)], print number) for a vote on amendments or minority
    motions: what the first of them changes in the bill (removed lines red, added green), or
    its text, in pages of DIFF_LINES - 1 lines; ("", [], None) otherwise. The print holds
    them all (sejmomat.pl/<print> opens its page). Needs the report prints in data/prints
    (git pull)."""
    key = (v["sitting"], v["votingNumber"], width, lines)
    if key in _diffs and (_diffs[key][1][1] or time.time() - _diffs[key][0] < 60):
        return _diffs[key][1]
    if key in _diffs:
        # tried before, without the print: forget what the site's code remembers of missing prints
        for f in vars(model).values():
            if hasattr(f, "cache_clear"):
                f.cache_clear()
    out = ("", [], None)
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
            return [(colour, line) for line in textwrap.wrap(f"{mark} {text}", width, subsequent_indent="   ") or [mark]]
        changes = (it.get("bill_diff") or {}).get("changes") or []
        for ch in changes:
            where = [("w", line) for line in textwrap.wrap(ch.get("where") or "", width)]
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
            passages = [[("w", line)] for line in textwrap.wrap(_plain(it.get("text") or ""), width)]
        per = (lines or DIFF_LINES) - 1
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
        out = (f"Co zmienia {what} {a['number']}" + (f" (druk {a['source']})" if a["source"] else ""), pages, a["source"])
    # nothing found is tried again a minute later: the report print may not be pulled yet
    _diffs[key] = (time.time(), out)
    return out


FPS = 25


# the picture fitted to 1280x720
FIT = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"


def snapshot_command(ahead, snapshot):
    """A second ffmpeg, apart from the picture's (in the same process the two readings
    held each other back): the stream from LOOKAHEAD seconds further on, read at
    normal speed, its keyframes alone (one a second in the Sejm's stream, all the
    snapshots need), the caption band saved every SNAP_EVERY seconds as numbered files."""
    proxy = ["-http_proxy", VIDEO_PROXY] if VIDEO_PROXY else []
    bx, by, bw, bh = BAND
    # and, numbered alike, a tiny grey thumbnail of the whole picture, to tell a break by
    thumbs = str(snapshot).replace("band-", "thumb-")
    graph = (f"[0:v]fps=1/{SNAP_EVERY},split=2[a][b];[a]{FIT},crop={bw}:{bh}:{bx}:{by}[band];"
             f"[b]scale={THUMB[0]}:{THUMB[1]},format=gray[thumb]")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-re", *proxy, "-skip_frame", "nokey", "-i", ahead, "-an",
            "-filter_complex", graph,
            "-map", "[band]", "-f", "image2", "-start_number", "0", "-y", str(snapshot),
            "-map", "[thumb]", "-f", "image2", "-start_number", "0", "-y", thumbs]


# x264's speed for a stream (SEJMOMAT_PRESET): superfast takes a third less of the CPU than
# veryfast, ultrafast two thirds, at some cost in picture at the same bitrate. The overlay is laid
# on in yuv420 after converting it once a frame (format=auto took a fifth more). Measured on 60 s
# of a sitting, 4 cores: x264 veryfast 7.9 s, superfast 5.0 s, ultrafast 2.8 s; the overlay 4.3 s.
PRESET = os.environ.get("SEJMOMAT_PRESET", "superfast").strip() or "superfast"


def ffmpeg_command(src, out, snapshot, fast=False):
    """The ffmpeg command: the stream read at normal speed and scaled to 1280x720,
    with the overlay (RGBA frames from this script, on stdin) laid over it; and,
    every SNAP_EVERY seconds, the band where the broadcast names a speaker, saved
    as numbered files (`snapshot`, a pattern with %d: file n is the picture SNAP_EVERY * n
    seconds in) for the speaker recognition (tools/live_speaker.py; snapshot None: not
    needed here, as when snapshot_command reads them ahead). The picture ends when the
    overlay does (stdin closed), so a file is finished properly."""
    proxy = ["-http_proxy", VIDEO_PROXY] if VIDEO_PROXY else []
    inputs = [*([] if fast else ["-re"]), *proxy, "-i", src,
              "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-framerate", str(FPS), "-thread_queue_size", "64", "-i", "pipe:0"]
    bx, by, bw, bh = BAND
    scaled = f"[0:v]{FIT},fps={FPS}"
    if snapshot:
        v = (f"{scaled},split=2[base][cap];[1:v]format=yuva420p[ovl];[base][ovl]overlay=0:0:format=yuv420:eof_action=endall[v];"
             f"[cap]fps=1/{SNAP_EVERY},crop={bw}:{bh}:{bx}:{by}[band]")
    else:
        v = f"{scaled}[base];[1:v]format=yuva420p[ovl];[base][ovl]overlay=0:0:format=yuv420:eof_action=endall[v]"
    # on a server (no terminal) the progress line once a minute, for the log
    quiet = [] if sys.stderr.isatty() else ["-stats_period", "60"]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", *quiet, *inputs, "-filter_complex", v, "-map", "[v]", "-map", "0:a?"]
    enc = ["-c:v", "libx264", "-preset", PRESET, "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
           "-pix_fmt", "yuv420p", "-g", "50", "-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
    snap = ["-map", "[band]", "-f", "image2", "-start_number", "0", "-y", str(snapshot)] if snapshot else []
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
    ap.add_argument("--no-lookahead", action="store_true", help="read the name caption from the picture itself, not a second reading of the stream ahead of it")
    ap.add_argument("--transcript", action="store_true", help="replay: who speaks from the day's transcript (data/speeches), not the screen")
    ap.add_argument("--fast", action="store_true", help="to a file: as fast as the computer can, not in real time")
    ap.add_argument("--announce", action="store_true", help="a replay to the platform: tell the site it is on air too (live streams always do, with SEJMOMAT_LIVE_KEY set)")
    ap.add_argument("--no-chat", action="store_true", help="no vote links in the YouTube chat (tools/live_chat.py)")
    ap.add_argument("--chat", action="store_true", help="a replay to the platform: vote links in its chat too (live streams always have them)")
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
    src = source(base, start, end, args.quality)
    n = sitting_number(title)
    tags, facts = load_tags(), load_facts()
    # the general turn, and for each club its own cards (its Top 5s, its card), for while one of its MPs speaks
    by_club = {}
    for f in facts:
        if f.get("for_club") or (f.get("stats") and f.get("kind") == "fact" and f.get("club")):
            by_club.setdefault(f.get("for_club") or f["club"], []).append(f)
    for pool in by_club.values():
        pool.sort(key=lambda f: f.get("kind") != "top5")   # its Top 5s first, then the club's card
    # the comparisons, for breaks only: clubs and MPs taking turns
    # clubs from the list; MPs drawn at random each time from the pool (sejmomat/facts.py, mp_compare)
    compares = [f for f in facts if f.get("kind") == "compare" and f.get("topic") == "clubs"]
    mp_pool = next((f["mps"] for f in facts if f.get("kind") == "mp_pool"), [])
    mp_pairs = {}   # the pair drawn for a slot, kept for that slot (and its drawing cached by the overlay)

    def mp_pair(slot):
        if slot not in mp_pairs:
            from sejmomat.facts import mp_compare
            # only MPs whose photos are in already (one fetched while drawing stalled the picture
            # for seconds); until enough are, a club comparison instead
            spoke = [m for m in mp_pool if m["speeches"] and overlay._photos.get(m["id"]) is not None]
            towns = sorted({m["num"] for m in spoke if any(x["num"] == m["num"] and x["tag"] != m["tag"] for x in spoke)})
            if not towns:
                return None
            num = random.choice(towns)
            k = random.choice([m for m in spoke if m["num"] == num and m["tag"] == "Koalicja"])
            o = random.choice([m for m in spoke if m["num"] == num and m["tag"] == "Opozycja"])
            for mp in (k["id"], o["id"]):
                overlay.photo(mp)
            if len(mp_pairs) > 20:
                mp_pairs.clear()
            mp_pairs[slot] = mp_compare(k, o)
        return mp_pairs[slot]
    # Posłowie z regionu: each MP's constituency, shown while they speak (with their club's cards)
    region_of = {mp: f for f in facts if f.get("kind") == "region" for mp in f.get("mps", [])}
    facts = [f for f in facts if not f.get("for_club") and f.get("kind") not in ("compare", "region", "mp_pool")]
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
    # the photos of every MP a break's comparison may draw, in the background (fetched while a
    # frame was being drawn, one stalled the picture for a second)
    def fetch_pool_photos():
        with ThreadPoolExecutor(4) as fetcher:
            list(fetcher.map(overlay.photo, sorted({m["id"] for m in mp_pool})))
    threading.Thread(target=fetch_pool_photos, daemon=True).start()
    votes = []
    ballots = {}   # vote number -> {MP id: "Y" | "N" | "A" | "X"}, for the break's chamber scene
    ballot_clubs = {}   # vote number -> {MP id: club}, as the vote records it
    want_ballots = set()   # votes the break would show seat by seat (a replay's latest is not the day's)
    lock = threading.Lock()
    VOTE_CODE = {"YES": "Y", "NO": "N", "ABSTAIN": "A", "ABSENT": "X"}

    def poll():
        # new votes every 20 s, in the background; the ballots MP by MP (the list has only totals)
        # of the latest votes and of those the screen asked for, once per vote, checked every second
        last, tried = 0, {}
        while True:
            if time.time() - last >= 20:
                last = time.time()
                got = get_or_none(f"votings/{n}") if n else None
                if got:
                    with lock:
                        votes[:] = sorted(got, key=lambda v: v["votingNumber"])
                    want_ballots.update(v["votingNumber"] for v in votes[-3:])
            for num in sorted(want_ballots - set(ballots)):
                if time.time() - tried.get(num, 0) < 10:   # not there yet: again in a while
                    continue
                tried[num] = time.time()
                one = get_or_none(f"votings/{n}/{num}")
                if one and one.get("votes"):
                    ballot_clubs[num] = {x["MP"]: x.get("club") or "niez." for x in one["votes"]}
                    ballots[num] = {x["MP"]: VOTE_CODE.get(x.get("vote"), "X") for x in one["votes"]}
            time.sleep(1)
    threading.Thread(target=poll, daemon=True).start()

    # who is speaking: the broadcast's name caption, read every SNAP_EVERY seconds
    work = Path(tempfile.mkdtemp(prefix="sejmomat-live-"))
    snapshot = work / "band-%d.png"
    recogniser = Recogniser(load_mps(ROOT)) if shutil.which("tesseract") and not (args.no_speakers or args.transcript) else None
    if not recogniser and not (args.no_speakers or args.transcript):
        print("tesseract not found: no speaker recognition", file=sys.stderr)
    # The caption comes CAPTION_LAG seconds into a speech. Read LOOKAHEAD seconds ahead (a
    # second reading of the stream), a speaker is known before the picture gets to them and
    # their card starts when they do; live, only when the delay leaves room for it, and not
    # with --fast (the two readings would not keep their distance).
    lead = LOOKAHEAD if recogniser and not (args.fast or args.no_lookahead) and (args.at or args.delay >= LOOKAHEAD + 30) else 0
    # the captions come from a reading of their own (at `lead` ahead, or level with the picture):
    # snapshots taken inside the picture's ffmpeg came too seldom to catch a caption; only with
    # --fast, where a reading at normal speed could not keep up, are they taken there
    ahead = source(base, start + timedelta(seconds=lead), end, args.quality) if recogniser and not args.fast else None
    if recogniser:
        print(f"speakers: captions read {lead} s ahead of the picture" if lead else
              "speakers: captions read level with the picture (cards start when the caption does)", flush=True)
    speaker = {"card": None, "at": None, "mp": None, "until": None}
    pending = []   # speakers recognised ahead of the picture: (moment they begin, update), applied when it gets there
    pending_chair, chair, chair_now = [], {}, {"text": None}   # who runs the sitting, as the picture shows it
    breaks = []    # [start, end or None] by the picture's clock: the comparisons' time (read ahead, so known in time)
    refs = []
    for path in BREAK_REFS:
        try:
            refs.append(Image.open(path).convert("L").resize(THUMB).tobytes())
        except OSError:
            pass
    brk = {"run": None, "misses": 0, "on": False, "first_miss": None, "quiet_from": None}

    def wide_shot(path):
        """How close the picture is to the break's wide shot: the least mean difference to a reference."""
        try:
            px = Image.open(path).convert("L").resize(THUMB).tobytes()
        except OSError:
            return None
        return min(sum(abs(a - b) for a, b in zip(px, r)) / len(px) for r in refs) if refs else None

    def follow_break(seen, score):
        if score is None:
            return
        if score <= BREAK_MATCH:
            brk["misses"], brk["first_miss"] = 0, None
            brk["run"] = brk["run"] or seen
            # the wide shot from the stream's first picture: the sitting has not begun, so at once
            opening = (brk["run"] - start).total_seconds() <= lead + 2 * SNAP_EVERY
            spoken = brk["quiet_from"] and seen < brk["quiet_from"]
            if not brk["on"] and not spoken and (opening or (seen - max(brk["run"], brk["quiet_from"] or brk["run"])).total_seconds() >= BREAK_AFTER):
                brk["on"] = True
                with lock:
                    breaks.append([brk["run"] if opening else max(brk["run"], brk["quiet_from"] or brk["run"]) + timedelta(seconds=BREAK_AFTER), None])
                print(f"{breaks[-1][0]:%H:%M:%S} przerwa: porównania na ekranie", flush=True)
        else:
            brk["misses"] += 1
            brk["first_miss"] = brk["first_miss"] or seen
            if brk["misses"] >= BREAK_ENDS:
                if brk["on"]:
                    with lock:
                        breaks[-1][1] = brk["first_miss"]
                    print(f"{brk['first_miss']:%H:%M:%S} koniec przerwy", flush=True)
                brk.update(run=None, on=False)
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
    # a past day: the club each MP had then, with today's as a note where it has changed
    clubs_then = clubs_on(start.date().isoformat()) if transcript else {}

    def follow_transcript(clock):
        on = next((x for x in transcript if x["start"] <= clock < x["end"]), None)
        if on and speaker["mp"] != on["mp"] and on["mp"] in mp_by_id:
            m = mp_by_id[on["mp"]]
            overlay.photo(m["id"])
            card = speaker_card(m)
            then = clubs_then.get(m["id"])
            if then and then != card["club"]:
                card.update(club=then, now=card["club"])
            speaker.update(mp=m["id"], at=on["start"], until=on["end"], card=card)

    def watch():
        done, last = -1, {"mp": None, "seen": None}
        while recogniser:
            time.sleep(0.5)
            # the newest file may still be being written: the ones before it, in order
            numbers = sorted(int(f.stem.split("-")[1]) for f in work.glob("band-*.png") if f.stem.count("-") == 1 and "." not in f.stem)
            todo = [x for x in numbers[:-1] if x > done]
            if not ahead:
                # from the picture itself only the latest counts (as it is on screen now); the rest
                # would be a backlog that makes every name come later
                for x in todo[:-1]:
                    (work / f"band-{x}.png").unlink(missing_ok=True)
                todo = todo[-1:]
            for i in todo:
                path = work / f"band-{i}.png"
                done = i
                text = read(path)
                m = recogniser.match(text)
                path.unlink(missing_ok=True)
                path.with_suffix(".ocr.png").unlink(missing_ok=True)
                thumb = work / f"thumb-{i}.png"
                if ahead and refs:
                    follow_break(start + timedelta(seconds=lead + SNAP_EVERY * i), wide_shot(thumb))
                thumb.unlink(missing_ok=True)
                if not m:
                    continue
                # the chair: their caption says "Marszałek / Wicemarszałek Sejmu (RP)" where a speaker's
                # names their club; who runs the sitting, not a speaker ("Sejmu" survives the OCR, "Marszałek" often not)
                if m and re.search(r"sejmu", text, re.I):
                    role = "wicemarszałek" if re.search(r"wice", text, re.I) else "marszałek"
                    seen_chair = start + timedelta(seconds=lead + SNAP_EVERY * i) if ahead else now["clock"]
                    if chair.get("mp") != m["id"]:
                        club = CHAIR_CLUB.get(m.get("club"), club_short(m.get("club") or ""))
                        print(f"{seen_chair:%H:%M:%S} obrady prowadzi: {role} {m['name']} ({club})", flush=True)
                        with lock:
                            pending_chair.append((seen_chair, {"mp": m["id"], "text": f"Obrady prowadzi: {role} {m['name']} · {club}"}))
                        chair["mp"] = m["id"]
                    continue
                # the moment of that picture: read ahead, from its number (that ffmpeg writes one
                # every SNAP_EVERY seconds of the stream); from the picture itself, the picture's
                # clock now (its file numbers run ahead at the start and do not keep time)
                seen = start + timedelta(seconds=lead + SNAP_EVERY * i) if ahead else now["clock"]
                # the caption stays a few seconds: one card per speaker, not one per snapshot
                if last["mp"] == m["id"] and (seen - last["seen"]).total_seconds() < 60:
                    continue
                last.update(mp=m["id"], seen=seen)
                # when they began; never before the picture, where a card would start halfway through
                began = max(seen - timedelta(seconds=CAPTION_LAG if lead else 0), now["clock"])
                print(f"{began:%H:%M:%S} na mównicy: {m['name']} ({m.get('club')})"
                      f"{f', napis o {seen:%H:%M:%S}' if lead else ''}", flush=True)
                overlay.photo(m["id"])
                with lock:
                    pending.append((began, {"mp": m["id"], "at": began, "until": None, "card": speaker_card(m)}))
                    # someone has the floor: a break on screen ends when they began, and none starts for a while
                    if brk["on"] and breaks and breaks[-1][1] is None:
                        breaks[-1][1] = max(began, breaks[-1][0])
                        print(f"{breaks[-1][1]:%H:%M:%S} koniec przerwy (mówca)", flush=True)
                    brk.update(on=False, run=None, misses=0, quiet_from=seen + timedelta(seconds=BREAK_NO_SPEAKER))
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
            # their constituency's MPs first (once a speech), then their club's cards in the club's turn
            region = region_of.get(sp.get("mp")) if sp else None
            pool = by_club.get(sp["club"]) if sp else None
            speaking = sp and club_after <= (clock - at).total_seconds() < SPEAKER_BAR and not (speaker["until"] and clock > speaker["until"])
            if speaking and region and ("region", at) not in turns:
                turns[("region", at)] = True
                picks[slot] = region
            elif speaking and pool:
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

    # the sitting's agenda (data/proceedings.json, kept up to date by git pull), for the breaks' list
    try:
        from sejmomat import agenda as _agenda
        planned = [it for g in (_agenda.by_sitting().get(n) or {}).get("groups", []) for it in g["items"]]
    except Exception as e:
        print(f"no agenda: {e}", file=sys.stderr)
        planned = []

    def vote_prints(v):
        return set(re.findall(r"\d+(?:-[A-Za-z0-9]+)?", " ".join(m[1] for m in re.finditer(
            r"druk(?:i|ów)?\s+nr\s+([\d\-A-Za-z ,i]+)", v.get("title") or ""))))

    agenda_turn = {"n": 0, "slot": None}

    # ---- the chamber in a break (data/seating.json, from the Chancellery's seating plan): every
    # MP's seat, coloured by club or by how they voted, lit one after another
    import math
    import live_overlay
    hall = None
    seating_path = ROOT / "data" / "seating.json"
    if seating_path.exists():
        plan = json.loads(seating_path.read_text(encoding="utf-8"))
        rows = [(s["x"], s["y"] / plan["aspect"], s["mp"]) for _, s in sorted(plan["seats"].items(), key=lambda kv: int(kv[0]))]
        club_by_mp = {m["id"]: m.get("club") or "niez." for m in load_mps(ROOT)}
        cx = sum(r[0] for r in rows) / len(rows)
        cy = max(r[1] for r in rows) + 0.04   # the rostrum, in front of the front rows
        # a sweep from the left wing to the right, and a wave from the rostrum outwards
        sweep = sorted(range(len(rows)), key=lambda i: -math.atan2(cy - rows[i][1], rows[i][0] - cx))
        wave = sorted(range(len(rows)), key=lambda i: math.hypot(rows[i][0] - cx, rows[i][1] - cy))
        hall = {"rows": rows, "club": club_by_mp, "sweep": sweep, "wave": wave}

    def stream_short(club):
        """A club's name on the stream's chamber scenes: as on the site, a few shorter still."""
        return {"Konfederacja_KP": "KKP"}.get(club) or club_short(club)

    def clubs_hall(t, length):
        """Kluby na sali: the chamber filling club by club, from the left wing to the right, the
        clubs counted as their seats come in (the largest first in the legend, every club alike)."""
        rows, club = hall["rows"], hall["club"]
        colour = [live_overlay.club_colour(club.get(mp)) if mp in club else None for _, _, mp in rows]
        seats = [(x, y, c) for (x, y, _), c in zip(rows, colour)]
        total = {}
        for _, _, mp in rows:
            if mp in club:
                total[club[mp]] = total.get(club[mp], 0) + 1
        top = sorted(total, key=lambda c: -total[c])[:6]

        def legend(p):
            lit = hall["sweep"][:round(p * len(rows))]
            n = {}
            for i in lit:
                mp = rows[i][2]
                if mp in club:
                    n[club[mp]] = n.get(club[mp], 0) + 1
            out = [(live_overlay.club_colour(c), f"{'niezrzeszeni' if c.startswith('niez') else stream_short(c)} {n.get(c, 0)}") for c in top]
            rest = sum(v for c, v in n.items() if c not in top)
            return out + ([((125, 135, 148), f"inni {rest}")] if len(total) > len(top) else [])

        return overlay.hall_scene(("clubs",), "Kluby na sali", f"{sum(total.values())} posłów · miejsca według planu sali Kancelarii Sejmu",
                                  seats, hall["sweep"], legend, t, length)

    VOTE_COLOUR = {"Y": (52, 168, 96), "N": (206, 72, 72), "A": (222, 170, 58), "X": (88, 98, 116)}

    def vote_hall(v, code, t, length):
        """Jak głosował Sejm: a vote seat by seat ({MP id: Y/N/A/X}), in a wave from the rostrum
        outwards, the four counts rising as the seats come in."""
        rows = hall["rows"]
        seats = [(x, y, VOTE_COLOUR.get(code.get(mp, ""), None) if mp else None) for x, y, mp in rows]
        names = {"Y": "za", "N": "przeciw", "A": "wstrzymało się", "X": "nie głosowało"}

        def legend(p):
            n = {}
            for i in hall["wave"][:round(p * len(rows))]:
                c = code.get(rows[i][2])
                if c:
                    n[c] = n.get(c, 0) + 1
            return [(VOTE_COLOUR[c], f"{n.get(c, 0)} {names[c]}") for c in ("Y", "N", "A", "X")]

        ok = passed(v)
        topic = vote_topic(v)
        return overlay.hall_scene(("vote", v["sitting"], v["votingNumber"]), "Jak głosował Sejm",
                                  f"Głosowanie nr {v['votingNumber']}, {v['date'][11:16]} · {topic}", seats, hall["wave"], legend, t, length,
                                  badge=("PRZYJĘTO", (40, 150, 90)) if ok else ("ODRZUCONO", (190, 60, 60)), note=reject_note(v))

    def reject_note(v, short=False):
        """A motion to reject a bill reads the other way round: rejecting it keeps the bill going."""
        if "wniosek o odrzucenie" not in (v.get("topic") or "").lower():
            return None
        if passed(v):
            return "Wniosek przyjęty: projekt odrzucony"
        return "Wniosek odrzucony: projekt idzie dalej" if short else "Wniosek odrzucony: prace nad projektem trwają dalej"

    result_from = {}   # vote number -> seconds after the vote its result came on screen
    diff_from = {}     # vote number -> seconds its amendment had on screen before it

    def vote_result(v, t, length):
        """A vote just taken, full screen: the chamber seat by seat on the left (as in a break),
        on the right every club's votes (the largest club first, every club alike), the bars
        growing once the seats are in."""
        code, clubs = ballots[v["votingNumber"]], ballot_clubs[v["votingNumber"]]
        rows = hall["rows"]
        seats = [(x, y, VOTE_COLOUR.get(code.get(mp, ""), None) if mp else None) for x, y, mp in rows]
        names = {"Y": "za", "N": "przeciw", "A": "wstrzymało się", "X": "nie głosowało"}
        per = {}
        for mp, c in code.items():
            per.setdefault(clubs.get(mp, "niez."), {"Y": 0, "N": 0, "A": 0, "X": 0})[c] += 1
        # every club, the largest first; the independents last
        order = sorted(per, key=lambda c: (c.startswith("niez"), -sum(per[c].values()), c))
        biggest = max(sum(per[c].values()) for c in order)

        def legend(p):
            n = {}
            for i in hall["wave"][:round(p * len(rows))]:
                c = code.get(rows[i][2])
                if c:
                    n[c] = n.get(c, 0) + 1
            return [(VOTE_COLOUR[c], f"{n.get(c, 0)} {names[c]}") for c in ("Y", "N", "A", "X")]

        def side(d, t):
            q = live_overlay.clamp((t - 1.0) / 2.0)
            fb, fn = overlay.font(18, True), overlay.font(18)
            x0, xb, bw = 612, 790, 126
            cols = [962, 1003, 1044, 1084]   # the four counts, right-aligned
            top, bottom = 118, (live_overlay.CMP_BOX[3] - live_overlay.CMP_BOX[1]) - 62
            step = min(44, (bottom - top - 30) / len(order))
            half = 9 if step >= 34 else 7   # the bars a little thinner when there are many clubs
            for colour, x in zip(("Y", "N", "A", "X"), cols):
                d.rounded_rectangle((x - 14, top + 2, x - 2, top + 14), 3, fill=VOTE_COLOUR[colour] + (255,))
            for i, c in enumerate(order):
                y = top + 30 + i * step + step / 2
                label = "niezrzeszeni" if c.startswith("niez") else stream_short(c)
                d.text((x0, y), overlay.fit(label, fb, xb - x0 - 10), font=fb, fill=live_overlay.club_colour(c), anchor="lm")
                x = xb
                for k in ("Y", "N", "A", "X"):
                    w = per[c][k] / biggest * bw * q
                    if w >= 1:
                        d.rectangle((round(x), round(y - half), round(x + w), round(y + half)), fill=VOTE_COLOUR[k] + (255,))
                    x += w
                for k, cx in zip(("Y", "N", "A", "X"), cols):
                    d.text((cx, y), str(round(per[c][k] * q)), font=fn if per[c][k] else fn,
                           fill=(236, 238, 245) if per[c][k] else (110, 120, 138), anchor="rm")
            return q >= 1

        ok = passed(v)
        topic = vote_topic(v)
        return overlay.hall_scene(("result", v["sitting"], v["votingNumber"]), f"Głosowanie nr {v['votingNumber']}",
                                  f"{v['date'][11:16]} · {topic}", seats, hall["wave"], legend, t, length,
                                  badge=("PRZYJĘTO", (40, 150, 90)) if ok else ("ODRZUCONO", (190, 60, 60)),
                                  area=(30, 118, 580, (live_overlay.CMP_BOX[3] - live_overlay.CMP_BOX[1]) - 70), side=side,
                                  note=reject_note(v))

    def vote_mini(v):
        """The small window of a vote's result (live_overlay.mini_vote)."""
        code = ballots[v["votingNumber"]]
        seats = [(x, y, VOTE_COLOUR.get(code.get(mp, ""), None) if mp else None) for x, y, mp in hall["rows"]]
        n = {}
        for c in code.values():
            n[c] = n.get(c, 0) + 1
        names = {"Y": "za", "N": "przeciw", "A": "wstrzymało się", "X": "nie głosowało"}
        topic = vote_topic(v)
        return overlay.mini_vote((v["sitting"], v["votingNumber"]), f"Głosowanie nr {v['votingNumber']}",
                                 f"{v['date'][11:16]} · {topic}", seats,
                                 [(VOTE_COLOUR[c], f"{n.get(c, 0)} {names[c]}") for c in ("Y", "N", "A", "X")],
                                 ("PRZYJĘTO", (40, 150, 90)) if passed(v) else ("ODRZUCONO", (190, 60, 60)), note=reject_note(v, True))

    def agenda_scene(shown, t, length, slot):
        """Porządek obrad: the whole agenda, nine items a page, a page every 10 s, going on from
        where it stopped the time before; items voted on today marked (nobody can tell from the
        data which item is on now, so none is marked as current)."""
        done = set().union(*[vote_prints(v) for v in shown]) if shown else set()
        rows = [(it["n"], f"{it.get('kind', '')} {it.get('rest', '')}".strip(),
                 "głosowano" if done & set(it.get("prints") or []) else "",
                 "done" if done & set(it.get("prints") or []) else "todo") for it in planned]
        pages = [rows[i:i + 9] for i in range(0, len(rows), 9)] or [[]]
        if agenda_turn["slot"] != slot:   # a new turn on screen: the page after the last one shown
            agenda_turn.update(slot=slot, start=agenda_turn.get("next", 0))
        per = 10
        page = (agenda_turn["start"] + int(t // per)) % len(pages)
        agenda_turn["next"] = page + 1
        sub = f"{len(planned)} punktów · {sum(1 for r in rows if r[3] == 'done')} z głosowaniami dziś"
        if len(pages) > 1:
            sub += f" · strona {page + 1}/{len(pages)}"
        return overlay.list_scene("Porządek obrad", sub, pages[page], t, length, rows_t=t % per if len(pages) > 1 else t)

    def votes_scene(shown, t, length):
        """Głosowania: today's latest, with what was decided, and the day's count."""
        today = [v for v in shown if v["date"][:10] == shown[-1]["date"][:10]]
        rows = []
        for v in reversed(today[-9:]):
            text = short_topic(re.sub(r"^\s*Pkt\.?\s*\d+\.?\s*", "", v.get("topic") or v.get("title") or ""))
            ok = passed(v)
            rows.append((f"nr {v['votingNumber']}", text, f"{'PRZYJĘTO' if ok else 'ODRZUCONO'} {v['yes']}/{v['no']}/{v['abstain']}",
                         "adopted" if ok else "rejected"))
        n_ok = sum(1 for v in today if passed(v))
        return overlay.list_scene("Głosowania", f"dziś {len(today)} · przyjęto {n_ok}, odrzucono {len(today) - n_ok}", rows, t, length)

    def frame(clock):
        """The overlay for the picture at `clock`."""
        if transcript:
            follow_transcript(clock)
        with lock:
            shown = [v for v in votes if warsaw(v["date"]) <= clock]
            nxt = next((v for v in votes if warsaw(v["date"]) > clock), None)
            # a speaker recognised ahead: theirs once the picture reaches the moment they began
            while pending and pending[0][0] <= clock:
                speaker.update(pending.pop(0)[1])
            while pending_chair and pending_chair[0][0] <= clock:
                chair_now["text"] = pending_chair.pop(0)[1]["text"]
            on_break = next((b for b in breaks if b[0] <= clock and (b[1] is None or clock < b[1])), None)
        # a break: comparisons over the hall, nothing else (not within BREAK_NO_VOTE of a vote)
        since_vote = (clock - warsaw(shown[-1]["date"])).total_seconds() if shown else 1e9
        if on_break and (compares or mp_pool) and since_vote > BREAK_NO_VOTE:
            since = (clock - on_break[0]).total_seconds()
            slot, into = int(since // CMP_SECONDS), since % CMP_SECONDS
            length = CMP_SECONDS
            if on_break[1]:   # the break's end is known ahead: the last one leaves in time
                length = min(CMP_SECONDS, (on_break[1] - on_break[0]).total_seconds() - slot * CMP_SECONDS)
            # in turn: the agenda, a comparison, the clubs in the chamber, today's votes, a comparison,
            # the latest vote seat by seat, two comparisons, a word about the site
            hhmm = f"{clock:%H:%M}"
            kind = slot % 9
            if hall and shown:
                want_ballots.add(shown[-1]["votingNumber"])
            if kind == 8 and promos:
                return overlay.frame_scene(overlay.promo_scene(promos[(slot // 9) % len(promos)], into, length), hhmm)
            if kind == 0 and planned:
                return overlay.frame_scene(agenda_scene(shown, into, length, slot), hhmm)
            if kind == 2 and hall:
                return overlay.frame_scene(clubs_hall(into, length), hhmm)
            if kind == 3 and shown:
                return overlay.frame_scene(votes_scene(shown, into, length), hhmm)
            if kind == 5 and hall and shown and ballots.get(shown[-1]["votingNumber"]):
                return overlay.frame_scene(vote_hall(shown[-1], ballots[shown[-1]["votingNumber"]], into, length), hhmm)
            k = (slot // 9) * 4 + {1: 0, 4: 1, 6: 2, 7: 3}.get(kind, 0)   # the comparisons' own count in the turns of nine
            # clubs and a random pair of MPs taking turns
            c = mp_pair((on_break[0], slot)) if (k % 2 or not compares) and mp_pool else None   # a new pair each break
            c = c or (compares[(k // 2) % len(compares)] if compares else None)
            if c:
                return overlay.frame_scene(overlay.compare(c, into, length), hhmm)
        # votes full screen: what an amendment changes, before its vote (the Marshal reads it out
        # then; live the vote is known some 40 s before the picture reaches it), then every vote's
        # result, then that result in a small window (below)
        decisive = lambda v: bool(v.get("yes") or v.get("no"))   # noqa: E731 - not a quorum check
        whole = lambda v: "nad całością" in (v.get("topic") or "").lower()   # noqa: E731 - the vote on the whole bill
        hhmm = f"{clock:%H:%M}"
        if shown and hall and decisive(shown[-1]):
            want_ballots.add(shown[-1]["votingNumber"])
        if nxt and hall:
            want_ballots.add(nxt["votingNumber"])
        if shown and hall and decisive(shown[-1]) and since_vote < 2 * RESULT_SECONDS:
            v = shown[-1]
            num = v["votingNumber"]
            # the result from when its ballots are in (a few seconds after the vote at most)
            if num in ballot_clubs and since_vote < RESULT_SECONDS:
                result_from.setdefault(num, since_vote)
            start = result_from.get(num)
            if start is not None and since_vote - start < RESULT_SECONDS:
                t = since_vote - start
                to_next = (warsaw(nxt["date"]) - clock).total_seconds() if nxt else 1e9
                amend_next = not whole(v) and nxt and decisive(nxt) and diff_panel(nxt, FULL_WIDTH, FULL_LINES)[1] and to_next < RESULT_SECONDS - t + PAGE_CYCLE
                if not amend_next and t > RESULT_SECONDS - SHRINK:
                    # nothing more full screen: the result shrinks into its small window
                    img, _, _ = vote_result(v, RESULT_SECONDS - SHRINK - 0.01, RESULT_SECONDS + 1)
                    k = live_overlay.ease_in(live_overlay.clamp((t - (RESULT_SECONDS - SHRINK)) / SHRINK))
                    box = [a + (b - a) * k for a, b in zip(live_overlay.CMP_BOX, live_overlay.MINI_BOX)]
                    small = img.resize((round(box[2] - box[0]), round(box[3] - box[1])), Image.BILINEAR)
                    return overlay.frame_scene((small, round(box[0]), round(box[1])), hhmm, "GŁOSOWANIE")
                return overlay.frame_scene(vote_result(v, t, RESULT_SECONDS), hhmm, "GŁOSOWANIE")
        if nxt and hall and decisive(nxt):
            # the next vote on an amendment: its pages full screen, ending as the vote is taken
            to_go = (warsaw(nxt["date"]) - clock).total_seconds()
            head, pages, src = diff_panel(nxt, FULL_WIDTH, FULL_LINES) if to_go < PAGE_CYCLE + RESULT_SECONDS else ("", [], None)
            if pages:
                num = nxt["votingNumber"]
                # the time it has: from the latest result's end (or when the vote is first known) to the vote
                prev_end = 0
                if shown and decisive(shown[-1]) and shown[-1]["votingNumber"] in result_from:
                    prev_end = RESULT_SECONDS + result_from[shown[-1]["votingNumber"]] - since_vote   # seconds from now
                    if whole(shown[-1]):   # the hall reacting to a bill passed or not: a moment on the picture
                        prev_end += REACTION
                window = diff_from.setdefault(num, min(PAGE_CYCLE, to_go - max(0, prev_end)))
                begun = window - to_go
                if window >= PAGE_MIN - 1 and 0 <= begun < window:
                    each = window / min(len(pages), max(1, int(window // PAGE_MIN)))
                    shown_pages = pages[:max(1, int(window // each))]
                    page = min(int(begun // each), len(shown_pages) - 1)
                    # which bill, where to read it all, then the vote: the bill's name cut to leave the rest whole
                    rest = (f" · całość: sejmomat.pl/{src}" if src else "") + f" · głosowanie nr {num} za chwilę" \
                        + (f" · strona {page + 1}/{len(pages)}" if len(pages) > 1 else "")
                    sub = shorten(live_chat.item(nxt), SUB_CHARS - len(rest)) + rest
                    return overlay.frame_scene(overlay.text_scene(("diff", num, page), head, sub, shown_pages[page],
                                                                  begun - page * each, each,
                                                                  fade=(page == 0, False)), hhmm, "GŁOSOWANIE")
        item, topic, vote = captions(shown, tags, title)
        recent = shown and (clock - warsaw(shown[-1]["date"])).total_seconds() < QUIET
        chip = note = None
        if shown and not recent:
            # a debate or a break: the vote below is an earlier one
            vote = textwrap.shorten(f"Ostatnie głosowanie ({shown[-1]['date'][11:16]}): {vote.replace('Głosowanie ', '')}", 112, placeholder="…")
        sp = speaker["card"]
        speaking = bool(sp) and 0 <= (clock - speaker["at"]).total_seconds() < SPEAKER_BAR and not (speaker["until"] and clock > speaker["until"])
        # in a block of votes, someone named after the latest one has the floor (a formal motion,
        # a question before the vote): they are shown, until the next vote
        floor = bool(recent) and speaking and speaker["at"] > warsaw(shown[-1]["date"])
        if not recent or floor:
            # no votes going on, or a speaker between them: the bar names who is speaking
            if speaking:
                stats = dict(sp["stats"])
                item, chip, note = sp["name"], sp["club"], sp.get("now")
                topic = (f"Na mównicy od {speaker['at']:%H:%M} · {sp['value']} wystąpień w kadencji · "
                         f"frekwencja {stats.get('frekwencja')} · wyłamania z linii klubu: {stats.get('wyłamania')}")
            else:
                item, topic = title, "Mówca pojawi się tu, gdy transmisja go przedstawi"
        panel = card = mini = None
        if recent and not floor and hall and shown[-1]["votingNumber"] in ballot_clubs and decisive(shown[-1]):
            # the picture back after the vote's full screen: its result in a small window, bottom right
            v = shown[-1]
            num = v["votingNumber"]
            img = vote_mini(v)
            x, y = live_overlay.MINI_BOX[:2]
            mini = (img, x, y)
        elif recent and not floor:
            # votes going on: no cards; with the chamber, amendments are full screen before their vote
            head, pages, _ = diff_panel(shown[-1]) if not hall else ("", [], None)
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
            elif facts and not floor:
                # a debate, a break: a fun-fact card, one every FACT_EVERY seconds for FACT_SECONDS;
                # one whose turn comes while the speaker's card is up is left out, not cut short
                slot, into = int((ts - first) // every), (ts - first) % every
                begun = ts - into
                if not (showing["speaker"] and showing["start"] <= begun < showing["start"] + SPEAKER_SECONDS):
                    c = pick(slot, clock)
                    if c.get("kind") == "region":   # five MPs a page, five seconds a page
                        length = min(max(10, 5 * -(-len(c["rows"]) // 5)), 30, every - 1)
                    else:
                        length = min(TOP_SECONDS if c.get("kind") == "top5" else FACT_SECONDS, every - 1)
                    if into < length:
                        card = overlay.card(c, into, length)
                        showing["until"] = begun + length
        return overlay.frame(item, topic, vote, panel, card, chip, note, clock=f"{clock:%H:%M}", chair=chair_now["text"], mini=mini)

    if args.fast and args.out in ("preview", "rtmp"):
        sys.exit("--fast is for a file.")
    cmd, preview = ffmpeg_command(src, args.out, snapshot if recogniser and not ahead else None, args.fast)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE if preview else None)
    reader = subprocess.Popen(snapshot_command(ahead, snapshot), stdin=subprocess.DEVNULL) if ahead else None
    # on air: the site hears of it every LIVE_EVERY seconds (a live sitting always; a replay with --announce)
    stopped = threading.Event()
    on_air = args.out == "rtmp" and bool(LIVE_KEY) and (not args.at or args.announce)
    shown_title = f"Retransmisja: {title}" if args.at else title

    def keep_announcing():
        told = False
        while not stopped.wait(0 if not told else LIVE_EVERY):
            try:
                ok = announce(True, shown_title)
                if not told:
                    print(f"strona: transmisja zgłoszona ({'przyjęta' if ok else 'odrzucona'})", flush=True)
                told = True
            except Exception as e:
                if not told:
                    print(f"strona: nie udało się zgłosić transmisji: {e}", file=sys.stderr, flush=True)
                told = True
    if on_air:
        threading.Thread(target=keep_announcing, daemon=True).start()
    # the votes into the stream's chat as the picture reaches them (live_chat.py), when on air
    # with the channel's YouTube login set
    if args.out == "rtmp" and (not args.at or args.announce or args.chat) and live_chat.configured() and not args.no_chat:
        def votes_now():
            with lock:
                return list(votes)
        live_chat.VoteChat(lambda: now["clock"], votes_now, start, short_topic).start()
        print("czat: linki do głosowań włączone", flush=True)
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
        stopped.set()
        if on_air:
            try:   # off air: at once, not when the last report runs out
                announce(False, shown_title)
            except Exception:
                pass
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
        for p in (viewer, proc, reader):
            if p and p.poll() is None:
                p.terminate()
        for p in (viewer, proc, reader):
            if p:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    main()
