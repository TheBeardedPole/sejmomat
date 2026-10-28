"""Sejmowa liga: a fantasy game on the Sejm's record. Each sitting is a gameweek
("kolejka"): players pick ten MPs in six positions within a budget, the squad locks
at 00:00 Warsaw time on the sitting's first day, and every MP scores from what they
did in that sitting. The server side (squads, transfers, accounts) is server/fantasy.php;
this module makes the data it reads:

    api/v1/fantasy/game.json         the kolejka open for transfers (or under way), its
                                     lock, prices, MPs and the rules
    api/v1/fantasy/points/<id>.json  every MP's points in a kolejka, per position, with
                                     what they scored for; "final" once the sitting's
                                     transcripts are in

A kolejka is identified by its first day (the Sejm's calendar has a sitting's dates
before its number), and counts the votes and speeches on its days. Prices come from
form: an MP's rank in a position over the last PRICE_WINDOW sittings, moving at most
PRICE_STEP a sitting (tools/fantasy/simulate.py replays the term with the same rules).
"""
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .analysis import CAST, NO_CLUB
from .config import DATA

WARSAW = ZoneInfo("Europe/Warsaw")
SEASON_START = "2026-11-05"   # the first kolejka: sitting 68

RULES = {
    "base": {"played": 2, "missed_day": -2, "missed_per_10": -1},   # every position
    # 2 for each of the first 3 speeches, then 1 up to 10; +1 for a speech of 5 minutes or more (up to 3)
    "Mówca": {"first": 2, "first_n": 3, "more": 1, "max_n": 10, "long": 1, "long_max": 3},
    # 3 per break of the club line, +3 when the vote was close; at most 24 a sitting
    "Buntownik": {"rebel": 3, "rebel_close": 3, "cap": 24},
    # 1 per vote with the line while the club was split (up to 15), -3 per break (at most -12),
    # +4 for a clean sheet: no break and at least 90% of votes cast
    "Lojalista": {"loyal_split": 1, "loyal_max": 15, "rebel": -3, "rebel_floor": -12, "clean": 4},
    "Klikacz": {"every_vote": 4, "full_day": 1, "missed_vote": -1, "missed_floor": -10},
    "Zwycięzca": {"won_close": 2},
    "Opozycjonista": {"lost_close": 2},
}
POSITIONS = ["Mówca", "Buntownik", "Lojalista", "Klikacz", "Zwycięzca", "Opozycjonista"]
SQUAD = {"Mówca": 2, "Buntownik": 2, "Lojalista": 2, "Klikacz": 2, "Zwycięzca": 1, "Opozycjonista": 1}
BUDGET = 80.5
CLUB_CAP = 2
CLOSE = 15            # a vote is close when the result is this many votes or fewer from the threshold
SPLIT = 0.9           # a club is split when under this share followed its line
PRICE_MIN, PRICE_MAX = 4.0, 13.0
PRICE_WINDOW = 5
PRICE_STEP = 0.5
WARMUP = 6            # sittings of the term before prices start
TRANSFERS = {"free": 1, "bank_max": 2, "hit": 4}   # free transfers a kolejka, how many can be saved, points per extra
FINAL_AFTER = 2       # days after a sitting's last day when its points are final (transcripts are in)


def margin(v):
    """Votes between the result and the threshold (positive: passed)."""
    if v.get("majorityType") == "SIMPLE_MAJORITY":
        return v["yes"] - v["no"]
    return v["yes"] - (v.get("majorityVotes") or 0)


def counters(votings, speeches):
    """{mp: Counter} of the facts behind the points, for one set of votes and speeches,
    and {mp: club} (the club the MP voted in last)."""
    out = defaultdict(Counter)
    club_of = {}
    days = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # mp -> day -> [eligible, cast]
    for v in votings:
        is_close = abs(margin(v)) <= CLOSE
        win = "Y" if v["passed"] else "N"
        for club, groups in v["ballots"].items():
            info = v["clubs"][club]
            line, split = info["line"], info["share"] < SPLIT
            for code, mps in groups.items():
                for mp in mps:
                    c = out[mp]
                    club_of[mp] = club
                    c["eligible"] += 1
                    d = days[mp][v["date"][:10]]
                    d[0] += 1
                    if code not in CAST:
                        c["missed"] += 1
                        continue
                    c["cast"] += 1
                    d[1] += 1
                    if line and club not in NO_CLUB:
                        if code != line:
                            c["rebel"] += 1
                            if is_close:
                                c["rebel_close"] += 1
                        elif split:
                            c["loyal_split"] += 1
                    if is_close and code in ("Y", "N"):
                        c["won_close" if code == win else "lost_close"] += 1
    for mp, per_day in days.items():
        c = out[mp]
        c["missed_day"] = sum(1 for e, k in per_day.values() if k == 0)
        c["full_day"] = sum(1 for e, k in per_day.values() if k == e)
    for st in speeches:
        if st.get("mp") is not None and not st.get("unspoken") and st.get("function") == "Poseł" and st["mp"] in out:
            c = out[st["mp"]]
            c["speech"] += 1
            if st.get("start") and st.get("end") and st["end"] > st["start"]:
                mins = (datetime.fromisoformat(st["end"]) - datetime.fromisoformat(st["start"])).total_seconds() / 60
                if mins >= 5:
                    c["long_speech"] += 1
    return out, club_of


def points(c, position):
    """An MP's points in one kolejka, in one position."""
    b = RULES["base"]
    p = (b["played"] if c["cast"] else 0) + b["missed_day"] * c["missed_day"] + b["missed_per_10"] * (c["missed"] // 10)
    r = RULES[position]
    if position == "Klikacz":
        if c["eligible"] and c["missed"] == 0:
            p += r["every_vote"]
        p += r["full_day"] * c["full_day"] + max(r["missed_floor"], r["missed_vote"] * c["missed"])
    elif position == "Mówca":
        n = c["speech"]
        p += r["first"] * min(n, r["first_n"]) + r["more"] * max(0, min(n, r["max_n"]) - r["first_n"])
        p += r["long"] * min(c["long_speech"], r["long_max"])
    elif position == "Buntownik":
        p += min(r["cap"], r["rebel"] * c["rebel"] + r["rebel_close"] * c["rebel_close"])
    elif position == "Lojalista":
        p += r["loyal_split"] * min(c["loyal_split"], r["loyal_max"]) + max(r["rebel_floor"], r["rebel"] * c["rebel"])
        if c["eligible"] and not c["rebel"] and c["cast"] >= 0.9 * c["eligible"]:
            p += r["clean"]
    else:
        p += sum(r[k] * c[k] for k in r)
    return p


def facts(c):
    """What an MP did in a kolejka, short, for the player's breakdown."""
    keys = ("cast", "eligible", "missed", "missed_day", "speech", "long_speech", "rebel", "rebel_close",
            "loyal_split", "won_close", "lost_close")
    return {k: c[k] for k in keys if c[k]}


def speeches_by_day():
    out = {}
    for f in (DATA / "speeches").glob("*.json"):
        d = json.loads(f.read_text())
        out[d["date"]] = d["statements"]
    return out


def price_chain(sittings, speech_days):
    """{sitting: {mp: {position: price}}}: the price an MP has going into each sitting
    after the warm-up, from rank in form over the sittings before it."""
    order = sorted(sittings)
    pts = {}
    for s in order:
        days = sorted({v["date"][:10] for v in sittings[s]})
        raw, _ = counters(sittings[s], [st for d in days for st in speech_days.get(d, [])])
        pts[s] = {mp: {pos: points(c, pos) for pos in POSITIONS} for mp, c in raw.items()}
    chain, prev = {}, {}
    for i, s in enumerate(order):
        if i < WARMUP:
            continue
        chain[s] = _prices(pts, order[:i], prev, pts[order[i - 1]].keys() | pts[s].keys())
    return chain, pts, prev


def _prices(pts, before, prev, mps):
    """Prices from form over the sittings in `before` (PRICE_WINDOW latest), moved from `prev`."""
    out = {}
    recent = before[-PRICE_WINDOW:]
    for pos in POSITIONS:
        form = {}
        for mp in mps:
            got = [pts[s][mp][pos] for s in recent if mp in pts[s]]
            form[mp] = sum(got) / len(got) if got else 0.0
        ranked = sorted(form, key=lambda mp: form[mp])
        n = len(ranked) - 1 or 1
        first_rank = {}
        for i, mp in enumerate(ranked):
            first_rank.setdefault(form[mp], i)
        for mp in ranked:
            target = PRICE_MIN + (first_rank[form[mp]] / n) ** 2 * (PRICE_MAX - PRICE_MIN)
            was = prev.get((mp, pos))
            new = target if was is None else max(was - PRICE_STEP, min(was + PRICE_STEP, target))
            prev[(mp, pos)] = new
            out.setdefault(mp, {})[pos] = round(new, 1)
    return out


def kolejki(today=None):
    """The game's gameweeks from the Sejm's calendar: [{"id": first day, "dates", "number"}],
    from SEASON_START on, in order (data/proceedings.json; a sitting's number is 0 until its
    agenda is out)."""
    today = today or date.today()
    rows = json.loads((DATA / "proceedings.json").read_text())
    rows = rows if isinstance(rows, list) else rows.get("sittings", [])
    out = []
    for p in rows:
        ds = sorted(p.get("dates") or [])
        if ds and ds[0] >= SEASON_START:
            out.append({"id": ds[0], "dates": ds, "number": p.get("number") or 0})
    out.sort(key=lambda k: k["id"])
    return out


def lock_of(k):
    """00:00 Warsaw time on the kolejka's first day, as ISO with the offset."""
    d = date.fromisoformat(k["id"])
    return datetime(d.year, d.month, d.day, tzinfo=WARSAW).isoformat()


def write(ctx, site, now=None):
    """Writes api/v1/fantasy/ into the built site (now: for trying other moments)."""
    out = site / "api" / "v1" / "fantasy"
    (out / "points").mkdir(parents=True, exist_ok=True)
    sittings = ctx["sittings"]
    speech_days = speeches_by_day()
    chain, past_pts, prev = price_chain(sittings, speech_days)
    mps = ctx["mps"]
    now = now or datetime.now(WARSAW)
    today = now.date()
    by_day = defaultdict(list)
    for s, votings in sittings.items():
        for v in votings:
            by_day[v["date"][:10]].append(v)

    ks = kolejki(today)
    played = []
    for k in ks:
        if datetime.fromisoformat(lock_of(k)) > now:
            continue
        votings = [v for d in k["dates"] for v in by_day.get(d, [])]
        raw, club_of = counters(votings, [st for d in k["dates"] for st in speech_days.get(d, [])])
        final = today >= date.fromisoformat(k["dates"][-1]) + timedelta(days=FINAL_AFTER)
        number = k["number"] or next((v["sitting"] for v in votings), 0)
        data = {"id": k["id"], "number": number, "dates": k["dates"], "final": final, "updated": now.isoformat(timespec="minutes"),
                "positions": POSITIONS,
                "mps": {str(mp): {"p": [points(c, pos) for pos in POSITIONS], "f": facts(c)} for mp, c in raw.items()}}
        (out / "points" / f"{k['id']}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        played.append({"id": k["id"], "number": number, "dates": k["dates"], "final": final})

    # the kolejka players pick for: the first not yet locked
    upcoming = next((k for k in ks if datetime.fromisoformat(lock_of(k)) > now), None)
    live = played[-1] if played and not played[-1]["final"] else None
    state = "live" if live else ("open" if upcoming else "off")
    # prices: while a kolejka is under way, the ones it started with (transfers are shut);
    # otherwise one more step of the chain, over every sitting played
    active = {m["id"] for m in mps.values() if m.get("active")}
    live_number = live and live["number"]
    if live_number and live_number in chain:
        prices = chain[live_number]
    else:
        order = sorted(past_pts)
        prices = _prices(past_pts, order, prev, set().union(*(past_pts[x].keys() for x in order[-PRICE_WINDOW:])) | active)
    game = {
        "season": SEASON_START[:4], "state": state, "updated": now.isoformat(timespec="minutes"),
        "kolejka": ({**upcoming, "lock": lock_of(upcoming)} if upcoming else None),
        "live": live, "played": played,
        "rules": RULES, "positions": POSITIONS, "squad": SQUAD, "budget": BUDGET, "clubCap": CLUB_CAP,
        "transfers": TRANSFERS, "close": CLOSE,
        "mps": {str(m["id"]): [m["firstLastName"], m.get("club") or "niez."] for m in mps.values() if m.get("active")},
        "prices": {str(mp): [p[pos] for pos in POSITIONS] for mp, p in prices.items() if mp in active},
    }
    (out / "game.json").write_text(json.dumps(game, ensure_ascii=False, separators=(",", ":")))
    return game
