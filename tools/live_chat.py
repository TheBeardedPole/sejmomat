"""Votes in the chat of Sejmomat's own YouTube stream: a message with the result and
a link to the vote's page when the picture reaches it (the vote's moment plus
POST_AFTER), so the chat goes with what the stream shows. livestream.py starts it
by itself when it streams to the platform and the YouTube login is set:

    python tools/live_chat.py auth             # once, on a computer with a browser: the login
    python tools/live_chat.py preview 67       # what a sitting's votes would put in the chat, nothing sent
    python tools/live_chat.py test "Dzień dobry"   # one message to the stream live now
    python tools/live_chat.py broadcast "Test"     # a new unlisted broadcast with its own stream key
    python tools/live_chat.py title "Nowy tytuł"   # the title of the broadcast live now
    python tools/live_chat.py autostop             # the broadcast live now kept on air if the video drops
    python tools/live_chat.py end                  # the broadcast live now ended (its video kept)
    python tools/live_chat.py prepare 68           # what the stream does before going on air: a broadcast waiting on SEJMOMAT_RTMP's key

A live sitting's broadcast is also titled by itself once on air: TITLE, "67. Posiedzenie
Sejmu | Lepsza Transmisja" (SEJMOMAT_YT_TITLE to change it; replays and tests are left alone),
and its Auto-stop turned off, so a dropped connection pauses the broadcast rather than ending it.

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

Viewers can ask: "!punkt" in the chat gets the item on by the plan with its print's page (livestream.py),
the chat read once a minute, one reply a minute however many ask; "!opoznienie" how late the sitting runs
against its planned timetable, with the agenda's page. The channel, its moderators and
ADMINS (SEJMOMAT_CHAT_ADMINS) can move the plan by hand: "!nowypunkt" (the next item has begun),
"!poprzednipunkt" (still on the previous one: the sitting runs late).

Quota: a message costs 20 units, finding the stream's chat 1, a read of the chat 5 (once a minute:
some 4,200 over a long day), of 10,000 a day; a new
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
COMMAND_EVERY = 60       # seconds between reads of the chat for commands ("!punkt"): 5 units a read
COMMAND_COOLDOWN = 60    # a command answered at most once in this long, however many ask
# who may give the stream's own commands ("!nowypunkt"): the channel itself, its moderators (YouTube
# vouches for both), and these names (a display name is not unique: making the account a moderator
# is the safe way)
ADMINS = {n.strip().lstrip("@").lower() for n in (os.environ.get("SEJMOMAT_CHAT_ADMINS") or "AdamKoscielakRZM").split(",") if n.strip()}
KEEP_FOR = 300           # a message waits this long for the chat (a broadcast takes a while to go live)

# a sitting's broadcast is given this title once it is live (SEJMOMAT_YT_TITLE, {n}: the sitting)
TITLE = os.environ.get("SEJMOMAT_YT_TITLE", "").strip() or "{n}. Posiedzenie Sejmu | Lepsza Transmisja"
PRIVACY = os.environ.get("SEJMOMAT_YT_PRIVACY", "").strip() or "public"   # of the broadcast the stream makes for a day
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
        self.commands, self.answered, self.token = {}, {}, None

    def start(self):
        threading.Thread(target=self._plan, daemon=True).start()
        threading.Thread(target=self._send, daemon=True).start()
        return self

    def post(self, text):
        """A message of the stream's own (the item on by the plan), sent in turn with the votes'."""
        self.out.put(text[:MAX_LEN])

    def command(self, word, answer, admin=False):
        """`word` ("!punkt") typed in the chat gets `answer(message)` in reply (None: no reply): the
        chat read every COMMAND_EVERY seconds. For viewers, one reply per COMMAND_COOLDOWN whoever
        asks; an `admin` command only from the channel, its moderators or ADMINS, each one done."""
        if not self.commands:
            threading.Thread(target=self._listen, daemon=True).start()
        self.commands[word.lower()] = (answer, admin)
        return self

    @staticmethod
    def is_admin(m):
        a = m.get("authorDetails") or {}
        return bool(a.get("isChatOwner") or a.get("isChatModerator") or (a.get("displayName") or "").lstrip("@").lower() in ADMINS)

    def _asked(self, items, now=None):
        """[(command, message)] asked in these chat messages, to be done now: a viewers' command
        once, not again within COMMAND_COOLDOWN, never from the channel's own messages (its replies);
        an admin command each time, from those allowed only."""
        now = time.time() if now is None else now
        out = []
        for m in items:
            words = ((m.get("snippet") or {}).get("displayMessage") or "").strip().lower().split()
            word = words[0] if words else ""
            if word not in self.commands:
                continue
            if len(words) > 1 and self.is_admin(m):
                # an admin's command with something after it ("!punkt 12"): every time, the channel too
                out.append((word, m))
                continue
            if self.commands[word][1]:
                if self.is_admin(m):
                    out.append((word, m))
            elif (not (m.get("authorDetails") or {}).get("isChatOwner") and all(w != word for w, _ in out)
                  and now - self.answered.get(word, 0) >= COMMAND_COOLDOWN):
                self.answered[word] = now
                out.append((word, m))
        return out

    def _listen(self):
        while True:
            try:
                if not self.chat.chat_id and time.time() - self.looked >= FIND_EVERY:
                    self.looked = time.time()
                    self.chat.find()
                if self.chat.chat_id:
                    params = {"liveChatId": self.chat.chat_id, "part": "snippet,authorDetails", "maxResults": 200}
                    if self.token:
                        params["pageToken"] = self.token
                    got = self.chat._call("GET", "liveChat/messages", params)
                    first, self.token = self.token is None, got.get("nextPageToken")
                    # the first read only marks where the chat is: what was asked before is left
                    for word, m in ([] if first else self._asked(got.get("items", []))):
                        reply = self.commands[word][0](m)
                        if reply:
                            self.post(reply)
                        print(f"czat: {word} od {(m.get('authorDetails') or {}).get('displayName')}", flush=True)
            except urllib.error.HTTPError as e:
                why = _reason(e)
                print(f"czat: nie odczytano ({e.code} {why})", file=sys.stderr, flush=True)
                if why in ("liveChatEnded", "liveChatNotFound", "liveChatDisabled", "forbidden"):
                    self.chat.chat_id, self.token = None, None
            except Exception as e:
                print(f"czat: nie odczytano ({e})", file=sys.stderr, flush=True)
            time.sleep(COMMAND_EVERY)

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


# the broadcast's settings sent back as they are when one changes (contentDetails is replaced whole)
KEEP_DETAILS = ("enableAutoStart", "enableAutoStop", "enableDvr", "enableEmbed", "recordFromStart",
                "closedCaptionsType", "latencyPreference", "projection")


def no_autostop(yt, b):
    """Broadcast `b` kept on air when the video stops (YouTube's "Auto-stop" off): a dropped
    connection then pauses it, and the encoder's reconnect carries on, instead of ending it and
    leaving the new video without a broadcast (5 November 2026). True if it was changed."""
    got = yt._call("GET", "liveBroadcasts", {"part": "contentDetails", "id": b["id"]})
    cd = got["items"][0]["contentDetails"]
    if cd.get("enableAutoStop") is False:
        return False
    body = {k: cd[k] for k in KEEP_DETAILS if k in cd}
    ms = cd.get("monitorStream") or {}
    body["monitorStream"] = {k: ms[k] for k in ("enableMonitorStream", "broadcastStreamDelayMs") if k in ms}
    body["enableAutoStop"] = False
    yt._call("PUT", "liveBroadcasts", {"part": "contentDetails"}, {"id": b["id"], "contentDetails": body})
    return True


def set_no_autostop():
    """Auto-stop off on the broadcast live now."""
    if not configured():
        sys.exit("The YouTube login is not set (python tools/live_chat.py auth).")
    yt = Chat()
    b = on_air(yt)
    if not b:
        sys.exit("No broadcast live on the channel now.")
    print("auto-stop off" if no_autostop(yt, b) else "auto-stop was already off")


def end_broadcast(yt, b):
    """Broadcast `b` ended ("complete"; its recording stays on the channel). With auto-stop off it
    would otherwise stay on air with no video, and the next day's stream would join it instead of
    starting a broadcast of its own (6 November 2026)."""
    yt._call("POST", "liveBroadcasts/transition", {"broadcastStatus": "complete", "id": b["id"], "part": "status"})


def close_before(when):
    """For livestream.py, before it goes on air: the channel's broadcast still on air ended if it
    began before `when` (the start of the day's sitting video): a previous day's, left on air.
    Its title if one was ended, else None."""
    yt = Chat()
    b = on_air(yt)
    began = (b or {}).get("snippet", {}).get("actualStartTime")
    if not b or not began or datetime.fromisoformat(began.replace("Z", "+00:00")) >= when:
        return None
    end_broadcast(yt, b)
    return b["snippet"].get("title")


def prepare(sitting, key, since):
    """For livestream.py, before it goes on air: a broadcast for the day waiting on the stream key
    `key` (the one in SEJMOMAT_RTMP), so the video has somewhere to go. YouTube does not always
    start one for the default key by itself (6 November 2026: the second day's video found none).
    One live on this key since `since` (the day's sitting video began: a restart) or one waiting on
    it is kept; else a new one, titled TITLE, PRIVACY, started by the video and not stopped when it
    drops. "kept: <id>", "new: <id>", or None when the key is not among the channel's streams."""
    yt = Chat()
    streams = yt._call("GET", "liveStreams", {"part": "id,cdn", "mine": "true", "maxResults": 50}).get("items", [])
    st = next((x for x in streams if (x.get("cdn", {}).get("ingestionInfo") or {}).get("streamName") == key), None)
    if not st:
        return None
    # waiting: a scheduled one only, not the channel's persistent default broadcast (the one that
    # found no video on 6 November)
    for status, kind in (("active", "all"), ("upcoming", "event")):
        got = yt._call("GET", "liveBroadcasts", {"part": "id,snippet,contentDetails,status", "broadcastStatus": status,
                                                 "broadcastType": kind, "maxResults": 50}).get("items", [])
        for b in got:
            if b.get("contentDetails", {}).get("boundStreamId") != st["id"]:
                continue
            began = b["snippet"].get("actualStartTime")
            if status == "upcoming" or (began and datetime.fromisoformat(began.replace("Z", "+00:00")) >= since):
                return f"kept: {b['id']}"
    now = datetime.now(WARSAW).isoformat(timespec="seconds")
    b = yt._call("POST", "liveBroadcasts", {"part": "snippet,status,contentDetails"}, {
        "snippet": {"title": (TITLE.format(n=sitting) if sitting else "Posiedzenie Sejmu | Lepsza Transmisja")[:100],
                    "scheduledStartTime": now},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
        "contentDetails": {"enableAutoStart": True, "enableAutoStop": False, "enableDvr": True, "recordFromStart": True,
                           "monitorStream": {"enableMonitorStream": False}}})
    yt._call("POST", "liveBroadcasts/bind", {"id": b["id"], "part": "id,contentDetails", "streamId": st["id"]})
    return f"new: {b['id']}"


def close_now():
    """For livestream.py, once the day's sitting has ended: the broadcast on air ended. Its title
    if one was ended, else None."""
    yt = Chat()
    b = on_air(yt)
    if not b:
        return None
    end_broadcast(yt, b)
    return b["snippet"].get("title")


def end_now():
    """The broadcast live now ended."""
    if not configured():
        sys.exit("The YouTube login is not set (python tools/live_chat.py auth).")
    title = close_now()
    print(f"ended: {title}" if title else "No broadcast live on the channel now.")


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
                    try:   # a drop then pauses the broadcast instead of ending it
                        if no_autostop(yt, b):
                            print("auto-stop: wyłączony", flush=True)
                    except Exception as e:
                        why = _reason(e) if isinstance(e, urllib.error.HTTPError) else e
                        print(f"auto-stop: nie wyłączono ({why})", file=sys.stderr, flush=True)
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
    elif cmd == "autostop":
        set_no_autostop()
    elif cmd == "end":
        end_now()
    elif cmd == "prepare" and len(sys.argv) > 2:
        if not configured():
            sys.exit("The YouTube login is not set (python tools/live_chat.py auth).")
        key = os.environ.get("SEJMOMAT_RTMP", "").rstrip("/").rsplit("/", 1)[-1]
        print(prepare(int(sys.argv[2]), key, datetime.now(WARSAW).replace(hour=0, minute=0, second=0)) or "the key is not among the channel's streams")
    else:
        sys.exit(__doc__)
