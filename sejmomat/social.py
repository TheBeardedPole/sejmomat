"""Social media posts from the voting data: a summary of each voting day.

    python -m sejmomat.social              # print the latest day's posts (reads data/)
    python -m sejmomat.social 2026-10-08   # a given day
    python -m sejmomat.social post         # publish the newest summaries not posted yet
    python -m sejmomat.social post --dry-run

The posts are filled-in templates: every number and name comes straight from
the data, nothing is paraphrased or written by a language model. The build
puts them in api/v1/summaries.json and on the page podsumowania.html, and
draws each day as an image (card.py) with the site's address in its footer.

"post" reads that published file, so it needs neither data/ nor anything
outside the standard library. It publishes one post per day (the image with
a short caption and a link) to the services whose credentials are in the
environment (see PLATFORMS) and records what went out in data/social.json,
so a day is never posted twice.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .analysis import MIN_CLUB_VOTERS, NO_CLUB
from .config import DATA, SITE_URL
from .i18n import MONTHS

LIMIT = 280        # the tighter of the services' limits (X), counted as in weight()
RECENT_DAYS = 10   # voting days kept in summaries.json and on the page
# A day is ready to post once it is over, or once this long has passed since
# its last vote (a voting block has no gaps like that).
SETTLED_AFTER = timedelta(hours=2)
POST_MAX_AGE = 3   # days; older summaries are never posted (e.g. on the first run)
STATE = DATA / "social.json"
CARD_DIR = "dane/podsumowania"   # the images, within the site
ALT_LIMIT = 1000                 # the tighter of the services' limits on an image's description (X)
WARSAW = ZoneInfo("Europe/Warsaw")

# Club names short enough for a post (the games have their own, longer list:
# CLUB_SHORT in games/sejmdle/sejmdle.js).
CLUB_SHORT = {"Polska2050": "Polska 2050", "Polska2050-TD": "Polska 2050", "PSL-TD": "PSL", "RozwojPlus": "Rozwój Plus",
              "Konfederacja_KP": "Konfederacja KP", "niez.": "niezrzeszeni", "(nieustalony)": "autor nieustalony"}
LAW_RE = re.compile(r"projek\w*\s+ustawy", re.I)
RESOLUTION_RE = re.compile(r"projek\w*\s+uchwały", re.I)
# A law is "contested" when at least this share of the votes cast was not for it.
CONTESTED_SHARE = 0.2
PROPOSER_ROWS = 7
# how clubs lined up in a vote: key in "lines", label
LINE_LABELS = (("Y", "Za"), ("N", "Przeciw"), ("A", "Wstrzymali się"), ("split", "Podzieleni"))


def club_short(club):
    return CLUB_SHORT.get(club, club)


def weight(text):
    """Length of a post as X counts it: a link is 23, most letters 1, emoji
    and other symbols 2. Every code point of an emoji is counted, so this is
    never below the real figure."""
    n = 0
    for i, part in enumerate(re.split(r"(https?://\S+)", text)):
        if i % 2:
            n += 23
            continue
        for ch in part:
            o = ord(ch)
            n += 1 if o <= 0x10FF or 0x2000 <= o <= 0x200D or 0x2010 <= o <= 0x201F or 0x2032 <= o <= 0x2037 else 2
    return n


def shorten(text, room):
    """Cut at a word boundary so that the text weighs at most `room`."""
    if weight(text) <= room:
        return text
    words = text.split()
    while len(words) > 1 and weight(" ".join(words) + "…") > room:
        words.pop()
    return " ".join(words).rstrip(",;:-–") + "…"


def short_title(title):
    """"Rządowy projekt ustawy o zmianie ustawy o X oraz niektórych innych
    ustaw." -> "zmiana ustawy o X"; a new law -> "ustawa o X"."""
    t = (title or "").strip().rstrip(".")
    t = re.sub(r"\s+oraz niektórych innych ustaw$", "", t)
    m = re.search(r"projek\w*\s+(ustawy|uchwały)\s+(.*)", t, re.I | re.S)
    if not m:
        return t
    kind, rest = m[1].lower(), m[2]
    if kind == "ustawy" and rest.startswith("o zmianie "):
        return "zmiana " + rest[len("o zmianie "):]
    if kind == "ustawy" and rest.startswith("budżetowej "):
        return "ustawa budżetowa " + rest[len("budżetowej "):]
    # the nominative is safe only before "o ...", "w sprawie ..." or "- Kodeks ..."
    if re.match(r"(o|w sprawie)\s|[-–]\s", rest):
        return ("ustawa " if kind == "ustawy" else "uchwała ") + rest
    return f"projekt {kind} {rest}"


def day_label(day):
    d = datetime.fromisoformat(day)
    return f"{d.day} {MONTHS['pl'][d.month - 1]}"


def club_lines(v):
    """Clubs by how they voted, largest first: {"Y": [...], "N": [...], "A":
    [...], None: [clubs with no majority choice]}."""
    out = {"Y": [], "N": [], "A": [], None: []}
    cast = lambda c: c["Y"] + c["N"] + c["A"]
    for club, c in sorted(v["clubs"].items(), key=lambda kv: (-cast(kv[1]), kv[0])):
        if club not in NO_CLUB and cast(c) >= MIN_CLUB_VOTERS:
            out[c["line"]].append(club_short(club))
    return out


def summarize(ctx, day, votes):
    """Facts and posts for one day's votes (in voting order), or None when
    nothing but procedural votes took place."""
    def title(v):
        bill = ctx["bill_by_root"].get(v["bill"])
        return bill["title"] if bill else v["agenda"]

    whole = {}
    for v in votes:  # the last vote on the whole bill is the one that settled it
        if v["motion"] and v["motion"][0] == "final":
            whole[v["bill"] or v["agenda"]] = v
    laws = [v for v in whole.values() if LAW_RE.search(title(v))]
    resolutions = [v for v in whole.values() if RESOLUTION_RE.search(title(v)) and v not in laws]
    rejected = [v for v in laws if not v["passed"]] + [
        v for v in votes if v["motion"] and v["motion"][0] == "reject_bill" and v["passed"]]
    amend = [v for v in votes if v["amendments"]]
    adopted = [v for v in amend if v["outcome_class"] == "adopted"]
    if not (laws or resolutions or rejected or amend):
        return None

    # each club among a voting's proposers is credited once for that voting
    proposers = defaultdict(Counter)
    for v in amend:
        for club in v["proposer"]["clubs"]:
            proposers[club]["voted"] += 1
            proposers[club]["adopted"] += v["outcome_class"] == "adopted"
    cast = lambda v: v["yes"] + v["no"] + v["abstain"]
    contested = min((v for v in laws if cast(v) and v["no"] + v["abstain"] >= CONTESTED_SHARE * cast(v)),
                    key=lambda v: (abs(v["yes"] - v["no"]), v["votingNumber"]), default=None)
    sitting = votes[-1]["sitting"]
    out = {
        "day": day, "sitting": sitting, "url": f"{SITE_URL}posiedzenie/{sitting}.html",
        "lastVote": max(v["date"] for v in votes),
        "votes": len(votes), "lawsPassed": sum(1 for v in laws if v["passed"]),
        "resolutionsPassed": sum(1 for v in resolutions if v["passed"]), "billsRejected": len(rejected),
        "amendmentVotes": len(amend), "amendmentVotesAdopted": len(adopted),
        "againstCommitteeRecommendation": sum(1 for v in votes if v["against_rec"]),
        "mostContestedLaw": contested and {
            "sitting": contested["sitting"], "votingNumber": contested["votingNumber"], "title": title(contested),
            "passed": contested["passed"], "yes": contested["yes"], "no": contested["no"],
            "abstain": contested["abstain"], "lines": {k or "split": c for k, c in club_lines(contested).items() if c}},
        "amendmentProposers": [
            {"proposer": club, "adopted": c["adopted"], "voted": c["voted"]}
            for club, c in sorted(proposers.items(), key=lambda kv: (
                kv[0] == "(nieustalony)", -kv[1]["adopted"], -kv[1]["voted"], kv[0]))],
    }
    out["posts"] = thread(out)
    # no link in any post (links cut a post's reach); the image names sejmomat.pl in its footer
    out["single"] = summary_post(out)
    # for the post that carries the image (card.py): what to write next to
    # it, and the image's description for people who cannot see it
    out["caption"] = headline(out)
    out["alt"] = alt_text(out)
    return out


def figures(s):
    """The day's figures that are not zero: (emoji, text)."""
    rows = [("🗳️", f"Głosowania: {s['votes']}"),
            ("✅", s["lawsPassed"] and f"Uchwalone ustawy: {s['lawsPassed']}"),
            ("📜", s["resolutionsPassed"] and f"Podjęte uchwały: {s['resolutionsPassed']}"),
            ("❌", s["billsRejected"] and f"Odrzucone projekty ustaw: {s['billsRejected']}"),
            ("✏️", s["amendmentVotes"] and
             f"Głosowania nad poprawkami: {s['amendmentVotes']}, w tym przyjęte: {s['amendmentVotesAdopted']}"),
            ("⚖️", s["againstCommitteeRecommendation"] and
             f"Rozstrzygnięcia wbrew rekomendacji komisji: {s['againstCommitteeRecommendation']}")]
    return [r for r in rows if r[1]]


def headline(s):
    return f"🏛️ #Sejm, {day_label(s['day'])}: podsumowanie dnia"


def summary_post(s):
    return f"{headline(s)}\n\n" + "\n".join(f"{emoji} {text}" for emoji, text in figures(s))


def alt_text(s):
    """What the image shows, in plain sentences."""
    parts = [f"Podsumowanie dnia w Sejmie, {day_label(s['day'])} {s['day'][:4]} ({s['sitting']}. posiedzenie)",
             *(text for _, text in figures(s))]
    law = s["mostContestedLaw"]
    if law:
        parts.append(f"Najbardziej sporne głosowanie nad ustawą: {short_title(law['title'])}: {law['yes']} za, "
                     f"{law['no']} przeciw, {law['abstain']} wstrzymujących się"
                     + ("" if law["passed"] else ", projekt odrzucony"))
        parts += [f"{label}: {', '.join(law['lines'][k])}" for k, label in LINE_LABELS if law["lines"].get(k)]
    rows = s["amendmentProposers"]
    if any(r["proposer"] != "(nieustalony)" for r in rows):
        parts.append("Czyje poprawki przeszły (przyjęte/głosowane): " + ", ".join(
            f"{club_short(r['proposer'])} {r['adopted']}/{r['voted']}" for r in rows[:PROPOSER_ROWS]))
    text = ". ".join(parts) + ". sejmomat.pl"
    return text if len(text) <= ALT_LIMIT else text[:ALT_LIMIT - 1].rsplit(" ", 1)[0] + "…"


def contested_post(law):
    abstained = "wstrzymał się" if law["abstain"] == 1 else "wstrzymało się"
    tail = (f"\n\n{law['yes']} za, {law['no']} przeciw, {law['abstain']} {abstained}."
            f"{'' if law['passed'] else ' Projekt odrzucony.'}\n"
            + "\n".join(f"{label}: {', '.join(law['lines'][k])}" for k, label in LINE_LABELS if law["lines"].get(k)))
    head = "Najbardziej sporne głosowanie nad ustawą:\n"
    return head + shorten(short_title(law["title"]), LIMIT - weight(head) - weight(tail)) + tail


def proposers_post(rows):
    head = "✏️ Czyje poprawki przeszły? (przyjęte / głosowane)\n\n"
    shown = rows[:PROPOSER_ROWS]
    lines = [f"{shorten(club_short(r['proposer']), 60)}: {r['adopted']}/{r['voted']}" for r in shown]
    rest = rows[PROPOSER_ROWS:]
    if rest:
        lines.append(f"pozostali: {sum(r['adopted'] for r in rest)}/{sum(r['voted'] for r in rest)}")
    while weight(head + "\n".join(lines)) > LIMIT:
        lines.pop()
    return head + "\n".join(lines)


def thread(s):
    """The day as a thread: summary, the most contested law, whose amendments
    passed. No links (the image carries the address)."""
    posts = [summary_post(s)]
    if s["mostContestedLaw"]:
        posts.append(contested_post(s["mostContestedLaw"]))
    # worth a post only if at least one proposer is known
    if any(r["proposer"] != "(nieustalony)" for r in s["amendmentProposers"]):
        posts.append(proposers_post(s["amendmentProposers"]))
    return posts


def summaries(ctx, limit=RECENT_DAYS):
    """Summaries of the latest voting days, newest first."""
    days = defaultdict(list)
    for v in ctx["by_id"].values():
        days[v["date"][:10]].append(v)
    out = []
    for day in sorted(days, reverse=True):
        s = summarize(ctx, day, sorted(days[day], key=lambda v: (v["date"], v["votingNumber"])))
        if s:
            out.append(s)
        if len(out) == limit:
            break
    return out


# ------------------------------------------------------------- publishing

def _request(url, body, headers):
    """POST JSON (or raw bytes, with their own Content-Type); the JSON answer."""
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            answer = r.read()
            return json.loads(answer) if answer.strip() else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url}: HTTP {e.code} {e.read().decode(errors='replace')[:500]}") from None


def oauth1_header(method, url, key, key_secret, token, token_secret, nonce=None, timestamp=None):
    """Authorization header of an OAuth 1.0a request (HMAC-SHA1) whose body is
    JSON, i.e. takes no part in the signature."""
    quote = lambda s: urllib.parse.quote(str(s), safe="")
    params = {
        "oauth_consumer_key": key, "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_token": token, "oauth_version": "1.0",
    }
    base_url, _, query = url.partition("?")
    signed = sorted((quote(k), quote(v)) for k, v in [*params.items(), *urllib.parse.parse_qsl(query)])
    base = "&".join([method.upper(), quote(base_url), quote("&".join(f"{k}={v}" for k, v in signed))])
    digest = hmac.new(f"{quote(key_secret)}&{quote(token_secret)}".encode(), base.encode(), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(f'{quote(k)}="{quote(v)}"' for k, v in sorted(params.items()))


X_KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


def post_x(text, image, alt, size, env):
    """Publish a post on X, with the image (PNG bytes) if there is one;
    returns the post's id."""
    base = (env.get("X_API_URL") or "https://api.x.com").rstrip("/")
    call = lambda path, body: _request(f"{base}{path}", body, {
        "Authorization": oauth1_header("POST", f"{base}{path}", *(env[k] for k in X_KEYS))})
    body = {"text": text}
    if image:
        media = call("/2/media/upload", {"media": base64.b64encode(image).decode(), "media_category": "tweet_image"})["data"]["id"]
        try:
            call("/2/media/metadata", {"id": media, "metadata": {"alt_text": {"text": alt}}})
        except Exception as e:  # a missing description is no reason to hold the post back
            print(f"x: image description not set: {e}", file=sys.stderr)
        body["media"] = {"media_ids": [media]}
    return call("/2/tweets", body)["data"]["id"]


BLUESKY_KEYS = ("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD")


def bluesky_facets(text):
    """Links and #tags are plain text on Bluesky unless marked, by position
    in the UTF-8 bytes of the post."""
    facets = []
    for m in re.finditer(r"https?://\S+|#\w+", text):
        start = len(text[:m.start()].encode())
        feature = ({"$type": "app.bsky.richtext.facet#tag", "tag": m[0][1:]} if m[0].startswith("#")
                   else {"$type": "app.bsky.richtext.facet#link", "uri": m[0]})
        facets.append({"index": {"byteStart": start, "byteEnd": start + len(m[0].encode())}, "features": [feature]})
    return facets


def post_bluesky(text, image, alt, size, env):
    """Publish a post on Bluesky, with the image (PNG bytes) if there is one;
    returns the post's address (an at:// URI)."""
    host = (env.get("BLUESKY_HOST") or "https://bsky.social").rstrip("/")
    session = _request(f"{host}/xrpc/com.atproto.server.createSession",
                       {"identifier": env["BLUESKY_HANDLE"], "password": env["BLUESKY_APP_PASSWORD"]}, {})
    auth = {"Authorization": f"Bearer {session['accessJwt']}"}
    record = {"$type": "app.bsky.feed.post", "text": text, "langs": ["pl"],
              "createdAt": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
              "facets": bluesky_facets(text)}
    if image:
        blob = _request(f"{host}/xrpc/com.atproto.repo.uploadBlob", image, {**auth, "Content-Type": "image/png"})["blob"]
        shot = {"alt": alt, "image": blob}
        if size:
            shot["aspectRatio"] = {"width": size[0], "height": size[1]}
        record["embed"] = {"$type": "app.bsky.embed.images", "images": [shot]}
    return _request(f"{host}/xrpc/com.atproto.repo.createRecord",
                    {"repo": session["did"], "collection": "app.bsky.feed.post", "record": record}, auth)["uri"]


# name -> (environment variables that switch it on, function)
PLATFORMS = {"x": (X_KEYS, post_x), "bluesky": (BLUESKY_KEYS, post_bluesky)}


def settled(s, now):
    """Whether a day's summary can go out: the day is over in Warsaw, or its
    last vote is old enough for the voting block to be finished."""
    last = datetime.fromisoformat(s["lastVote"]).replace(tzinfo=WARSAW)
    return s["day"] < now.date().isoformat() or now - last >= SETTLED_AFTER


def due(items, posted, now):
    """Summaries to post now, oldest first: settled, recent, not posted yet."""
    oldest = (now.date() - timedelta(days=POST_MAX_AGE)).isoformat()
    return sorted((s for s in items if s["day"] >= oldest and s["day"] not in posted and settled(s, now)),
                  key=lambda s: s["day"])


def _image(s):
    """The day's image as PNG bytes, or None (the post then goes out as text)."""
    if not s.get("image"):
        return None
    try:
        with urllib.request.urlopen(s["image"], timeout=60) as r:
            return r.read()
    except (urllib.error.URLError, ValueError) as e:
        print(f"{s['day']}: no image ({s['image']}: {e}); posting text only", file=sys.stderr)
        return None


def publish(items, env=os.environ, dry_run=False, now=None, state_path=STATE):
    """Post what is due on every service with credentials. Returns False if
    a post failed (what did go out is recorded all the same)."""
    now = now or datetime.now(WARSAW)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    active = {name: fn for name, (keys, fn) in PLATFORMS.items() if all(env.get(k) for k in keys)}
    if not active:
        print("no credentials set: nothing to post to (showing what is due)")
        dry_run, active = True, {"(none)": None}
    ok, images = True, {}
    for name, fn in active.items():
        todo = due(items, state.get(name, {}), now)
        if not todo:
            print(f"{name}: nothing due")
        for s in todo:
            if dry_run:
                print(f"--- {name}: would post {s['day']}\n{s['caption']}\n[image: {s.get('image') or 'none'}]\n[alt: {s['alt']}]")
                continue
            if s["day"] not in images:
                images[s["day"]] = _image(s)
            image = images[s["day"]]
            try:  # without the image, the one-post text summary says the same
                made = fn(s["caption"] if image else s["single"], image, s["alt"], s.get("imageSize"), env)
            except Exception as e:
                ok = False
                print(f"{name}: {s['day']} failed: {e}", file=sys.stderr)
                continue
            state.setdefault(name, {})[s["day"]] = made
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            print(f"{name}: posted {s['day']} ({made})")
    return ok


def _published():
    url = (SITE_URL or "https://sejmomat.pl/") + "api/v1/summaries.json"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.load(r)
    except (urllib.error.URLError, ValueError) as e:
        sys.exit(f"cannot read {url}: {e}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["post"]:
        sys.exit(0 if publish(_published(), dry_run="--dry-run" in args or os.environ.get("SOCIAL_DRY_RUN") == "true") else 1)
    from .build import build_context  # needs data/ and the build's dependencies
    found = summaries(build_context(), limit=10 ** 6 if args else 1)
    chosen = next((s for s in found if not args or s["day"] == args[0]), None)
    if not chosen:
        sys.exit(f"no summary for {args[0] if args else 'the latest day'} (no votes on bills or amendments that day)")
    print("\n\n".join(f"[{weight(p)}/{LIMIT}]\n{p}" for p in chosen["posts"]))
