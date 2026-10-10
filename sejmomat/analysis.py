"""Club discipline computed from individual ballots.

Definitions (also explained on the site's methodology page):

* Club line: the most common choice (for / against / abstain) among the club
  members who voted, if it is a strict majority of them and at least
  MIN_CLUB_VOTERS voted. Otherwise the club is "split" and nobody counts as
  breaking the line.
* Breaking the line: a club member who voted, but not the club line.
"""
from collections import defaultdict

MIN_CLUB_VOTERS = 3
NO_CLUB = {"niez.", "?"}  # independents have no line to break

CAST = ("Y", "N", "A")


def passed(v):
    if v.get("majorityType") == "SIMPLE_MAJORITY":
        return v["yes"] > v["no"]
    return v["yes"] >= (v.get("majorityVotes") or 0)


def club_breakdown(v):
    """{club: {"Y": n, "N": n, "A": n, "X": n, "line": code|None, "share": float, "rebels": [mp]}}"""
    out = {}
    for club, groups in v["ballots"].items():
        counts = {c: len(groups.get(c, [])) for c in ("Y", "N", "A", "X")}
        voted = sum(counts[c] for c in CAST)
        line, share = None, 0.0
        if voted:
            top = max(CAST, key=lambda c: counts[c])
            share = counts[top] / voted
            if club not in NO_CLUB and voted >= MIN_CLUB_VOTERS and counts[top] * 2 > voted:
                line = top
        rebels = []
        if line:
            rebels = [(mp, c) for c in CAST if c != line for mp in groups.get(c, [])]
        out[club] = {**counts, "line": line, "share": share, "rebels": rebels}
    return out


def mp_stats(sittings):
    """Per-MP aggregates over all votings.

    sittings: {sitting: [voting, ...]} with "clubs" (club_breakdown) set.
    """
    stats = defaultdict(lambda: {"eligible": 0, "cast": 0, "with_line": 0,
                                 "rebellions": [], "clubs": set()})
    for s, votings in sittings.items():
        for v in votings:
            for club, groups in v["ballots"].items():
                line = v["clubs"][club]["line"]
                for code, mps in groups.items():
                    for mp in mps:
                        st = stats[mp]
                        st["eligible"] += 1
                        st["clubs"].add(club)
                        if code in CAST:
                            st["cast"] += 1
                            if line:
                                st["with_line"] += 1
                                if code != line:
                                    st["rebellions"].append((s, v["votingNumber"], code, line, club))
    return stats
