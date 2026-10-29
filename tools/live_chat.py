"""Votes in the chat of Sejmomat's own YouTube stream: a message with the result and
a link to the vote's page when the picture reaches it (the vote's moment plus
POST_AFTER), so the chat goes with what the stream shows. livestream.py starts it
by itself when it streams to the platform and the YouTube login is set:

    python tools/live_chat.py auth             # once, on a computer with a browser: the login
    python tools/live_chat.py preview 67       # what a sitting's votes would put in the chat, nothing sent
    python tools/live_chat.py test "Dzień dobry"   # one message to the stream live now
    python tools/live_chat.py broadcast "Test"     # a new unlisted broadcast with its own stream key
    python tools/live_chat.py title "Nowy tytuł"   # the title of the broadcast live now

A live sitting's broadcast is also titled by itself once on air: TITLE, "67. Posiedzenie
Sejmu | Lepsza Transmisja" (SEJMOMAT_YT_TITLE to change it; replays and tests are left alone).

Which votes: every vote but a quorum check, its result worded as on the vote's
page (sejmomat/build.py: a motion to reject passed is a bill rejected, a Senate
amendment stands unless the Sejm rejects it). Amendments and minority motions
go into one line of the bill's final vote ("poprawki: 4 z 19 przyjęte"); a run
of them with no final vote after it (the Senate's amendments) gets one message
once it ends, and so does a run of motions to cut the time between readings
(a dozen or more at a day's start).

The login: a Google Cloud project with the YouTube Data API v3 on, an OAuth
client of the "Desktop app" kind, and its consent screen published ("In
production"; while it is "Testing" the login lapses after 7 days). `auth`
signs in as the channel (@Sejmomat) and prints three lines for
/etc/sejmomat-live.env: SEJMOMAT_YT_CLIENT_ID, SEJMOMAT_YT_CLIENT_SECRET and
SEJMOMAT_YT_REFRESH_TOKEN. Messages come from the channel itself, so its links
are not held back.

Quota: a message costs 20 units, finding the stream's chat 1, of 10,000 a day; a new
broadcast with its stream some 150, a new title 50.

`broadcast` is for a test: an unlisted broadcast that starts when video comes to its
own key and ends when it stops; tools/vps/test-stream.sh sends a replay there with
the key it prints (TEST_RTMP=...). The sittings themselves go to the channel's
default key (SEJMOMAT_RTMP), whose title is set in YouTube Studio or with `title`.
"""
import getpass
import http.server
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sejmomat.build import motion, outcome  # noqa: E402  (a vote's result worded as on its page)
from sejmomat.model import SENATE_RE, agenda_label  # noqa: E402
from sejmomat.social import shorten, short_title  # noqa: E402

WARSAW = ZoneInfo("Europe/Warsaw")
SITE = "https://sejmomat.pl"
SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
YT = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

MAX_LEN = 200            # YouTube's chat box takes 200 characters
POST_AFTER = 6           # seconds after the vote's moment: its result is on screen by then
# and this much more on a stream (SEJMOMAT_CHAT_LAG): a frame drawn here reaches viewers after
# ffmpeg's buffer, the encoder and YouTube's own delay, while a message shows at once
CHAT_LAG = float(os.environ.get("SEJMOMAT_CHAT_LAG", "") or 12)
AMEND_RUN_END = 180      # a run of votes (amendments, motions) this long after its last: posted, the run over
GAP = 4                  # seconds between two messages at least
FIND_EVERY = 15          # seconds between looks for the stream's chat while there is none
KEEP_FOR = 300           # a message waits this long for the chat (a broadcast takes a while to go live)

# a sitting's broadcast is given this title once it is live (SEJMOMAT_YT_TITLE, {n}: the sitting)
TITLE = os.environ.get("SEJMOMAT_YT_TITLE", "").strip() or "{n}. Posiedzenie Sejmu | Lepsza Transmisja"
TITLE_FOR = 900          # seconds the stream keeps looking for its broadcast to give it the title

CLIENT_ID = os.environ.get("SEJMOMAT_YT_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("SEJMOMAT_YT_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("SEJMOMAT_YT_REFRESH_TOKEN", "").strip()


def configured():
    return bool(CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN)


# ---- the messages

def passed(v):
    return v["yes"] > v["no"] if v.get("majorityType") == "SIMPLE_MAJORITY" else v["yes"] >= (v.get("majorityVotes") or 0)


def decisive(v):
    return bool(v.get("yes") or v.get("no"))   # not a quorum check


def whole(v):
    return "nad całością" in (v.get("topic") or "").lower()


def amendment(v):
    return bool(re.match(r"\s*(poprawk|wnios\w* mniejszości)", v.get("topic") or "", re.I))


def senate(v):
    return bool(SENATE_RE.search(v.get("title") or ""))


def pace(v):
    return "skrócenie terminu" in (v.get("topic") or "").lower()   # one after another at a day's start


def for_site(v):
    """The fields the site's own outcome wording (build.motion, build.outcome) reads."""
    return {**v, "senate": senate(v), "amendments": [{"kind": "amendment"}] if amendment(v) else [], "passed": passed(v)}


def link(v):
    # the page for a vote since the last rebuild; it goes on to the regular one once the site has it
    return f"{SITE}/glosowanie-na-zywo.html?posiedzenie={v['sitting']}&nr={v['votingNumber']}"


def item(v):
    """The agenda item, short: "ustawa o X", "zmiana ustawy o Y"."""
    t = agenda_label(v.get("title") or "")
    t = re.sub(r"^Sprawozdanie Komisji o uchwale Senatu w sprawie ", "projekt ", t)   # "projekt ustawy o …" for short_title
    return short_title(t) or (v.get("topic") or "").rstrip(".")


def counts(v):
    return f"{v['yes']} za, {v['no']} przeciw, {v.get('abstain') or 0} wstrz."


def numbers(run):
    a, b = run[0]["votingNumber"], run[-1]["votingNumber"]
    return f"głosowanie {a}" if a == b else f"głosowania {a}–{b}"


def compose(head, what, tail, url):
    """head · what · tail → url in MAX_LEN, the item cut to fit (left out if it would be a word or two)."""
    fixed = f"{head} ·  · {tail} → {url}"
    room = MAX_LEN - len(fixed)
    if room < 25:
        return f"{shorten(head, MAX_LEN - len(f' · {tail} → {url}'))} · {tail} → {url}"
    return f"{head} · {shorten(what, room)} · {tail} → {url}"


def first_upper(t):
    return t[:1].upper() + t[1:]


def message(v, amends=(), name=lambda t: t):
    """The chat line for vote `v`, worded as on its page; `amends`: the bill's amendment
    votes before its final vote, `name`: a procedural motion's plain name (livestream.short_topic)."""
    tail = counts(v)
    m = motion(for_site(v))
    if m and m[0] == "final":
        ok = passed(v)
        head = f"{'✅' if ok else '❌'} {m[2][0] if ok else m[2][1]}"
        if amends:
            kept = sum(outcome(for_site(a))[1] == "adopted" for a in amends)
            tail += f" · poprawki: {kept} z {len(amends)} przyjęte"
    elif m and m[0] in ("adjourn", "skip_committee"):   # "Wniosek odrzucony" alone does not say which
        said = outcome(for_site(v))[0]
        head = f"🗳️ {first_upper(name(v.get('topic') or '').rstrip('.'))}: {said[0].lower()}{said[1:]}"
    elif m:
        head = f"🗳️ {outcome(for_site(v))[0]}"
    else:
        head = f"🗳️ {first_upper(name(v.get('topic') or '').rstrip('.'))}: {'przyjęto' if passed(v) else 'odrzucono'}"
    return compose(head, item(v), tail, link(v))


def run_message(run):
    """A run of votes in one message: a bill's amendments with no final vote after them
    (the Senate's), or the motions to cut the waiting time between readings."""
    last = run[-1]
    if pace(last):
        prints = [p for v in run for p in re.findall(r"druk\w*\s+(?:nr\s+)?(\d+)", v.get("title") or "")]
        k = sum(passed(v) for v in run)
        what = f"druki {', '.join(prints)}" if prints else ""
        return compose(f"⏩ Przyśpieszenie prac: {k} z {len(run)} wniosków przyjęte", what, numbers(run), link(last))
    kept = sum(outcome(for_site(a))[1] == "adopted" for a in run)
    noun = "Poprawki Senatu" if senate(last) else "Poprawki"
    return compose(f"📝 {noun}: {kept} z {len(run)} przyjęte", item(last), numbers(run), link(last))


def run_key(v):
    if amendment(v):
        return ("amend", v.get("title"))
    if pace(v):
        return ("pace",)
    return None


class Planner:
    """Which votes to post, and when: `due(votes, clock)` gives the messages the picture
    at `clock` has reached and that were not given before. Votes before `start` are
    left out (the stream began after them)."""

    def __init__(self, start, name=lambda t: t, lag=0):
        self.start, self.name, self.lag = start, name, lag
        self.done = set()   # vote numbers handled
        self.run = []       # votes going into one message: amendments waiting for their bill's final vote, or a run of motions

    def due(self, votes, clock):
        out = []
        for v in sorted(votes, key=lambda v: v["votingNumber"]):
            num, at = v["votingNumber"], datetime.fromisoformat(v["date"]).replace(tzinfo=WARSAW)
            if num in self.done or at + timedelta(seconds=POST_AFTER + self.lag) > clock:
                continue
            self.done.add(num)
            if at < self.start or not decisive(v):
                continue
            key = run_key(v)
            ends_run = self.run and key != run_key(self.run[-1])
            # a bill's final vote takes its amendments along
            if ends_run and whole(v) and run_key(self.run[-1]) == ("amend", v.get("title")):
                out.append(message(v, self.run, self.name))
                self.run = []
                continue
            if ends_run:
                out.append(run_message(self.run))
                self.run = []
            if key:
                self.run.append(v)
            else:
                out.append(message(v, (), self.name))
        if self.run:
            last = datetime.fromisoformat(self.run[-1]["date"]).replace(tzinfo=WARSAW)
            if (clock - last).total_seconds() > AMEND_RUN_END + self.lag:
                out.append(run_message(self.run))
                self.run = []
        return out


# ---- YouTube

class Chat:
    """Messages to the live chat of the channel's broadcast live now."""

    def __init__(self):
        self.token, self.token_until, self.chat_id = None, 0, None

    def _access(self):
        if not self.token or time.time() > self.token_until - 60:
            got = _post_form(TOKEN_URL, {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                                         "refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token"})
            self.token, self.token_until = got["access_token"], time.time() + got.get("expires_in", 3600)
        return self.token

    def _call(self, method, path, params, body=None):
        url = f"{YT}/{path}?{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None)
        req = urllib.request.Request(url, method=method, data=data,
                                     headers={"Authorization": f"Bearer {self._access()}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    def find(self):
        """The chat of the broadcast live now, or None."""
        # only one on air: the channel's default broadcast can be listed while idle, and its chat is not the stream's
        b = on_air(self)
        self.chat_id = (b or {}).get("snippet", {}).get("liveChatId")
        return self.chat_id

    def send(self, text):
        self._call("POST", "liveChat/messages", {"part": "snippet"},
                   {"snippet": {"liveChatId": self.chat_id, "type": "textMessageEvent",
                                "textMessageDetails": {"messageText": text[:MAX_LEN]}}})


def _post_form(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _reason(e):
    try:
        return json.load(e)["error"]["errors"][0]["reason"]
    except Exception:
        return str(e)


class VoteChat:
    """In the background, for livestream.py: every second, the votes the picture has
    reached (`clock()`, `votes()`) into the chat, GAP seconds apart. A message that
    cannot be sent (no chat yet, the API refusing) is dropped, never the stream."""

    def __init__(self, clock, votes, start, name=lambda t: t):
        self.clock, self.votes = clock, votes
        self.planner, self.chat, self.out = Planner(start, name, CHAT_LAG), Chat(), queue.Queue()
        self.looked = 0

    def start(self):
        threading.Thread(target=self._plan, daemon=True).start()
        threading.Thread(target=self._send, daemon=True).start()

    def _plan(self):
        while True:
            try:
                for text in self.planner.due(self.votes(), self.clock()):
                    self.out.put(text)
            except Exception as e:
                print(f"czat: {e}", file=sys.stderr, flush=True)
            time.sleep(1)

    def _send(self):
        waiting = []   # (since, text): messages kept while the broadcast is not live yet
        while True:
            if not waiting:
                waiting.append((time.time(), self.out.get()))
            while not self.out.empty():
                waiting.append((time.time(), self.out.get()))
            since, text = waiting[0]
            try:
                if not self.chat.chat_id and time.time() - self.looked >= FIND_EVERY:
                    self.looked = time.time()
                    if self.chat.find():
                        print("czat: transmisja znaleziona", flush=True)
                if not self.chat.chat_id:
                    if time.time() - since > KEEP_FOR:
                        waiting.pop(0)
                        print(f"czat: brak transmisji na żywo, pominięte: {text}", file=sys.stderr, flush=True)
                    else:
                        time.sleep(1)
                    continue
                waiting.pop(0)
                self.chat.send(text)
                print(f"czat: {text}", flush=True)
            except urllib.error.HTTPError as e:
                why = _reason(e)
                print(f"czat: nie wysłano ({e.code} {why}): {text}", file=sys.stderr, flush=True)
                if why in ("liveChatEnded", "liveChatNotFound", "liveChatDisabled", "forbidden"):
                    # the broadcast changed (the stream restarted): its new chat, and the message once more
                    self.chat.chat_id = None
                    try:
                        if self.chat.find():
                            self.chat.send(text)
                            print(f"czat: {text}", flush=True)
                    except Exception as e2:
                        print(f"czat: nie wysłano ponownie ({e2})", file=sys.stderr, flush=True)
                elif why == "rateLimitExceeded":
                    time.sleep(30)
            except Exception as e:
                print(f"czat: nie wysłano ({e}): {text}", file=sys.stderr, flush=True)
            time.sleep(GAP)


# ---- the commands

def auth():
    """Sign in as the channel in the browser; prints the lines for /etc/sejmomat-live.env."""
    global CLIENT_ID, CLIENT_SECRET
    if not (CLIENT_ID and CLIENT_SECRET):
        # asked for here when not in the environment (the secret not echoed, nor kept in the shell's history)
        print("The OAuth client (Google Cloud > APIs & Services > Credentials, the Desktop app one):")
        CLIENT_ID = CLIENT_ID or input("Client ID: ").strip()
        CLIENT_SECRET = CLIENT_SECRET or getpass.getpass("Client secret (not shown as you type): ").strip()
        if not (CLIENT_ID and CLIENT_SECRET):
            sys.exit("Both are needed.")
    got = {}

    class Back(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Gotowe, można zamknąć tę kartę.".encode() if "code" in q else "Nie udało się.".encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Back)
    back = f"http://127.0.0.1:{server.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "redirect_uri": back, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent"})
    print(f"Sign in as the channel (@Sejmomat):\n{url}\n", flush=True)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        server.handle_request()
    if "error" in got:
        sys.exit(f"Sign-in refused: {got['error']}")
    tokens = _post_form(TOKEN_URL, {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": got["code"],
                                    "redirect_uri": back, "grant_type": "authorization_code"})
    print("For /etc/sejmomat-live.env:\n")
    print(f"SEJMOMAT_YT_CLIENT_ID={CLIENT_ID}\nSEJMOMAT_YT_CLIENT_SECRET={CLIENT_SECRET}\n"
          f"SEJMOMAT_YT_REFRESH_TOKEN={tokens['refresh_token']}")


def preview(sitting):
    from livestream import get, short_topic   # (it imports this file: here, not at the top)
    votes = get(f"votings/{sitting}")
    first = min(datetime.fromisoformat(v["date"]) for v in votes).replace(tzinfo=WARSAW)
    planner = Planner(first, short_topic)
    end = datetime.now(WARSAW)
    msgs = planner.due(votes, end)
    for text in msgs:
        print(f"{len(text):3}  {text}")
    print(f"\n{len(msgs)} messages for {len(votes)} votes; {20 * len(msgs)} quota units", file=sys.stderr)


def broadcast(title, privacy="unlisted"):
    """A new broadcast (unlisted) bound to a new stream key: prints where to send the video."""
    if not configured():
        sys.exit("The YouTube login is not set (python tools/live_chat.py auth).")
    yt = Chat()
    now = datetime.now(WARSAW).isoformat(timespec="seconds")
    b = yt._call("POST", "liveBroadcasts", {"part": "snippet,status,contentDetails"}, {
        "snippet": {"title": title[:100], "scheduledStartTime": now},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        "contentDetails": {"enableAutoStart": True, "enableAutoStop": True,
                           "monitorStream": {"enableMonitorStream": False}}})
    st = yt._call("POST", "liveStreams", {"part": "snippet,cdn,contentDetails"}, {
        "snippet": {"title": f"Sejmomat: {title}"[:128]},
        "cdn": {"ingestionType": "rtmp", "resolution": "variable", "frameRate": "variable"},
        "contentDetails": {"isReusable": False}})
    yt._call("POST", "liveBroadcasts/bind", {"id": b["id"], "part": "id,contentDetails", "streamId": st["id"]})
    ing = st["cdn"]["ingestionInfo"]
    print(f"broadcast ({privacy}): https://youtu.be/{b['id']}")
    print(f"studio: https://studio.youtube.com/video/{b['id']}/livestreaming")
    print(f"\nTEST_RTMP={ing['ingestionAddress']}/{ing['streamName']}")


def on_air(yt):
    """The channel's broadcast on air now (live, or testing before it goes public), or None."""
    got = yt._call("GET", "liveBroadcasts", {"part": "snippet,status", "broadcastStatus": "active", "broadcastType": "all"})
    items = sorted((b for b in got.get("items", []) if b.get("status", {}).get("lifeCycleStatus") in ("live", "testing")),
                   key=lambda b: b["status"]["lifeCycleStatus"] != "live")
    return items[0] if items else None


def retitle(yt, b, title):
    """Broadcast `b` under `title` (its description and start kept); the old title, or None if it had it."""
    sn = b["snippet"]
    if sn.get("title") == title[:100]:
        return None
    yt._call("PUT", "liveBroadcasts", {"part": "snippet"}, {"id": b["id"], "snippet": {
        "title": title[:100], "description": sn.get("description", ""), "scheduledStartTime": sn["scheduledStartTime"]}})
    return sn.get("title")


def set_title(title):
    """The title of the broadcast live now."""
    if not configured():
        sys.exit("The YouTube login is not set (python tools/live_chat.py auth).")
    yt = Chat()
    b = on_air(yt)
    if not b:
        sys.exit("No broadcast live on the channel now.")
    old = retitle(yt, b, title)
    print(f"{old!r} -> {title[:100]!r}" if old is not None else f"already {title[:100]!r}")


def keep_title(sitting):
    """In the background, for livestream.py: once the sitting's broadcast is on air (the channel's
    default key starts a new one under Studio's default title), the title TITLE, once. Looked for
    every FIND_EVERY seconds for TITLE_FOR seconds; a failure costs the title, not the stream."""
    title = TITLE.format(n=sitting)

    def run():
        yt, until = Chat(), time.time() + TITLE_FOR
        while time.time() < until:
            try:
                b = on_air(yt)
                if b:
                    old = retitle(yt, b, title)
                    print(f"tytuł: {title}" + (f" (był: {old})" if old else ""), flush=True)
                    return
            except Exception as e:
                print(f"tytuł: nie ustawiono ({e})", file=sys.stderr, flush=True)
            time.sleep(FIND_EVERY)
        print("tytuł: transmisja się nie pojawiła, tytuł bez zmian", file=sys.stderr, flush=True)
    threading.Thread(target=run, daemon=True).start()


def test(text):
    if not configured():
        sys.exit("The YouTube login is not set (python tools/live_chat.py auth).")
    chat = Chat()
    if not chat.find():
        sys.exit("No broadcast live on the channel now.")
    chat.send(text)
    print("sent")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "auth":
        auth()
    elif cmd == "preview" and len(sys.argv) > 2:
        preview(int(sys.argv[2]))
    elif cmd == "test" and len(sys.argv) > 2:
        test(" ".join(sys.argv[2:]))
    elif cmd == "broadcast" and len(sys.argv) > 2:
        broadcast(" ".join(sys.argv[2:]))
    elif cmd == "title" and len(sys.argv) > 2:
        set_title(" ".join(sys.argv[2:]))
    else:
        sys.exit(__doc__)
