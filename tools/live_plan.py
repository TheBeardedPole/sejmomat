"""Where the sitting is against its planned timetable (sejmomat/agenda.py, timetable()), for
the stream (tools/livestream.py): nothing in the Sejm's data says which item is on, so the plan
is the guess, moved by how late the sitting runs.

How late it runs comes from the votes, the one thing timed exactly: each run of votes (a voting
block) is matched to its planned block, by the items it votes on, else by time, and its first
vote against the block's start gives the delay. A planned block that should have begun but has
not shows a delay too, before any vote: at least the time since its planned start. A run of
votes starts a few minutes into its block (the chair opens it), so up to GRACE late counts as on
time. The delay then moves the rest of the plan: an item planned at 15:00 is expected at 15:40
when the sitting runs 40 minutes late.
"""
import re
from datetime import datetime, timedelta

RUN_GAP = timedelta(minutes=20)     # votes this close together are one run (a voting block)
GRACE = timedelta(minutes=10)       # a block whose first vote comes this late or less is on time
MATCH_WITHIN = timedelta(hours=4)   # a run is matched by time only to a block this near
OVERRUN = timedelta(minutes=15)     # a delay this long or more is shown ("opóźnienie ok. 40 min")
MAX_AHEAD = timedelta(minutes=30)   # a run earlier than planned moves the plan back at most this much


def _at(s):
    return datetime.fromisoformat(s) if isinstance(s, str) else s


def slots_of(timetable):
    """The timetable's slots with their times as datetimes (naive, Warsaw time)."""
    return [{**s, "start": _at(s["start"]), "end": _at(s["end"])} for s in timetable]


def vote_point(v):
    """The item a vote is on, from its title ("Pkt. 7 Sprawozdanie …"), or None."""
    m = re.match(r"\s*Pkt\.?\s*(\d+)", v.get("title") or "")
    return int(m[1]) if m else None


def runs(votes):
    """Votes in runs (voting blocks): [(first vote's time, {items voted on})] in order."""
    out = []
    for v in sorted(votes, key=lambda v: v["date"]):
        at = _at(v["date"][:19])
        p = vote_point(v)
        if out and at - out[-1][2] <= RUN_GAP:
            first, points, _ = out[-1]
            out[-1] = (first, points | ({p} if p else set()), at)
        else:
            out.append((at, {p} if p else set(), at))
    return [(first, points) for first, points, _ in out]


def sitting_day(t):
    """The sitting day a moment belongs to: a day's sitting runs past midnight, the next one
    starts in the morning, so the hours before 6:00 count with the day before."""
    return (t - timedelta(hours=6)).date()


def delay(slots, votes, clock):
    """(delay, why): how late the sitting runs at `clock` (a timedelta, negative when ahead), and
    "głosowania" (measured on a run of votes), "czeka" (a planned block not begun yet) or None.
    Each sitting day on its own: the morning does not inherit the night before's delay."""
    day = sitting_day(clock)
    blocks = [s for s in slots if s["vote"] and sitting_day(s["start"]) == day]
    if not blocks:
        return timedelta(0), None
    found, used = None, set()
    today = [v for v in votes if _at(v["date"][:19]) <= clock and sitting_day(_at(v["date"][:19])) == day]
    for first, points in runs(today):
        # the block that plans these items, else the nearest one by time; a block counts its
        # first run only (a second run after a pause would overstate the delay)
        by_items = [b for b in blocks if points & set(b["points"])]
        if by_items and all(id(b) in used for b in by_items):
            continue
        near = [b for b in blocks if id(b) not in used and abs(first - b["start"]) <= MATCH_WITHIN]
        pick = [b for b in by_items if id(b) not in used] or sorted(near, key=lambda b: abs(first - b["start"]))
        if not pick:
            continue
        b = pick[0]
        used.add(id(b))
        late = first - b["start"]
        found = (b, timedelta(0) if timedelta(0) <= late <= GRACE else max(late, -MAX_AHEAD))
    late, why = (found[1], "głosowania") if found else (timedelta(0), None)
    # the next block after the last one matched: should it have begun by now?
    after = found[0]["start"] if found else datetime.min
    nxt = next((b for b in blocks if b["start"] > after and id(b) not in used), None)
    if nxt and clock > nxt["start"] + max(late, timedelta(0)) + GRACE:
        late, why = clock - nxt["start"], "czeka"
    return late, why


def current(slots, clock, late):
    """The slot the sitting is in by the plan moved by `late`, or None (before it, after it)."""
    t = clock - late
    return next((s for s in slots if s["start"] <= t < s["end"]), None)


def minutes(late):
    """A delay in words: "ok. 40 min", "ok. 1 godz. 10 min"."""
    m = int(round(late.total_seconds() / 60 / 5) * 5) or int(late.total_seconds() // 60)
    return f"ok. {m // 60} godz. {m % 60} min" if m >= 60 and m % 60 else f"ok. {m // 60} godz." if m >= 60 else f"ok. {m} min"


def label(slot, short=lambda t: t):
    """What a slot is, for the caption: "Punkt 3 · Karta Nauczyciela", "Głosowania", "Przerwa"."""
    if slot["vote"]:
        return "Głosowania"
    pts = slot["points"]
    text = short(slot["text"])
    if not pts:
        return text
    head = f"Punkt {pts[0]}" if len(pts) == 1 else f"Punkty {pts[0]}–{pts[-1]}"
    return f"{head} (cd.)" if text.lower().startswith("cd. pkt") else f"{head} · {text}"
