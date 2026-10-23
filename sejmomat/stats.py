"""Voting statistics for the stats page (statystyki.html, static/stats.js):
maps of MPs placed by how alike they vote, per half-year and for the term,
club cohesion over time, how often clubs vote alike, and the closest votes.

The maps: for every pair of MPs, the share of the votes both cast (for,
against or abstaining) in which they cast the same; classical
multidimensional scaling turns (1 - that share) ** SPREAD into positions on
a plane, so MPs who vote alike sit close together; that start is then laid out as a
network (_force): each MP is linked to the EDGES MPs they agree with most and
pulled towards them, as in the familiar maps of the US Congress. Each
half-year's map is rotated (or mirrored) to fit the whole term's on the MPs
they share, so blocs keep their place from one map to the next.
"""
from collections import Counter, defaultdict

import numpy as np

MIN_SHARE = 0.25     # an MP on a period's map voted in at least this share of its votes
EDGES = 5            # links drawn from each MP to those they agree with most
CLOSE = 15           # closest votes listed
# Clubs of the governing coalition (as in games/sejmdle/sejmdle.js), for the
# agreement between coalition and opposition.
COALITION = {"KO", "Lewica", "Polska2050", "Polska2050-TD", "Centrum", "PSL-TD"}
CODES = ("Y", "N", "A")


def _period(day):
    """Half-year of a vote; the term's first weeks (2023) go with the first half of 2024."""
    year, month = int(day[:4]), int(day[5:7])
    if year == 2023:
        return "2024-1"
    return f"{year}-{1 if month <= 6 else 2}"


def _matrix(votes):
    """(MP ids, one-hot choices [3, votes, mps], each MP's most common club)."""
    ids = sorted({mp for v in votes for b in v["ballots"].values() for k in "YNAX" for mp in b.get(k, [])})
    col = {mp: i for i, mp in enumerate(ids)}
    choice = np.zeros((3, len(votes), len(ids)), dtype=np.float32)
    clubs = defaultdict(Counter)
    for r, v in enumerate(votes):
        for club, b in v["ballots"].items():
            for k in "YNAX":
                for mp in b.get(k, []):
                    clubs[mp][club] += 1
            for c, k in enumerate(CODES):
                for mp in b.get(k, []):
                    choice[c, r, col[mp]] = 1
    return ids, choice, {mp: clubs[mp].most_common(1)[0][0] for mp in ids}


def _agreement(choice):
    """Share of the votes both MPs cast in which they cast the same, and how many both cast."""
    cast = choice.sum(axis=0)
    both = cast.T @ cast
    same = sum(choice[c].T @ choice[c] for c in range(3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(both > 0, same / both, 0), both


SPREAD = 0.35   # distance = (1 - agreement) ** SPREAD: blocs agree 98-99% inside and ~35% across, so plain
                # distances shrink each bloc to a point; the power keeps the order and opens them up


def _mds(agree):
    d2 = ((1 - agree) ** SPREAD) ** 2
    n = len(d2)
    j = np.eye(n) - np.ones((n, n)) / n
    b = -0.5 * j @ d2 @ j
    vals, vecs = np.linalg.eigh(b)
    top = np.argsort(vals)[::-1][:2]
    return vecs[:, top] * np.sqrt(np.maximum(vals[top], 0))


def _force(xy, edges, weights, steps=300):
    """Fruchterman-Reingold layout from a start (xy): MPs pull towards those they
    are linked to (by agreement), all push each other apart, and a light pull
    keeps the whole near the centre (blocs with no links between them would
    drift apart otherwise)."""
    n = len(xy)
    pos = (xy - xy.mean(axis=0)) / (xy.std() or 1)
    pos += np.random.default_rng(0).normal(0, 0.01, pos.shape)
    k = 2.0 / np.sqrt(n)
    i, j = np.array([e[0] for e in edges]), np.array([e[1] for e in edges])
    w = np.asarray(weights)
    for step in range(steps):
        temp = 0.1 * (1 - step / steps) + 0.002
        delta = pos[:, None, :] - pos[None, :, :]
        d2 = (delta ** 2).sum(axis=2) + 1e-6
        disp = (delta * (k * k / d2)[:, :, None]).sum(axis=1)
        pull = pos[i] - pos[j]
        dist = np.sqrt((pull ** 2).sum(axis=1))[:, None]
        f = pull * (dist / k) * w[:, None]
        np.add.at(disp, i, -f)
        np.add.at(disp, j, f)
        disp -= pos * 0.6
        length = np.sqrt((disp ** 2).sum(axis=1))[:, None] + 1e-9
        pos += disp / length * np.minimum(length, temp)
    return pos


def _rotation(a, b):
    """Rotation or mirror that best fits a onto b, rows matched (orthogonal Procrustes)."""
    a, b = a - a.mean(axis=0), b - b.mean(axis=0)
    u, _, vt = np.linalg.svd(a.T @ b)
    return u @ vt


def _map(votes, names):
    ids, choice, club = _matrix(votes)
    cast = choice.sum(axis=(0, 1))
    keep = [i for i, n in enumerate(cast) if n >= MIN_SHARE * len(votes)]
    ids = [ids[i] for i in keep]
    agree, _ = _agreement(choice[:, :, keep])
    np.fill_diagonal(agree, 1)
    # each MP's closest (by agreement), each pair once
    order = np.argsort(-agree, axis=1)
    edges = sorted({tuple(sorted((i, int(j)))) for i in range(len(ids)) for j in order[i, 1:EDGES + 1]})
    xy = _force(_mds(agree), edges, [agree[i, j] for i, j in edges])
    side = np.array([club[mp] in COALITION for mp in ids])
    between = agree[np.ix_(side, ~side)].mean() if side.any() and (~side).any() else None
    return {"ids": ids, "xy": xy, "club": [club[mp] for mp in ids], "edges": edges,
            "names": [names.get(mp, f"#{mp}") for mp in ids], "votes": len(votes),
            "between": float(between) if between is not None else None}


def _cohesion(votes):
    """{club: average share of the club's MPs who voted with its majority}, clubs of 3+ voters."""
    shares = defaultdict(list)
    for v in votes:
        for club, b in v["ballots"].items():
            n = [len(b.get(k, [])) for k in CODES]
            if club != "niez." and sum(n) >= 3:
                shares[club].append(max(n) / sum(n))
    return {c: sum(s) / len(s) for c, s in shares.items() if len(s) >= 20}


def _label(key):
    year, half = key.split("-")
    return [f"{'I' if half == '1' else 'II'} poł. {year}", f"{'H1' if half == '1' else 'H2'} {year}"]


def compute(sittings, mps, club_rows):
    names = {mp_id: m.get("firstLastName") or f"#{mp_id}" for mp_id, m in mps.items()}
    votes = sorted((v for vs in sittings.values() for v in vs), key=lambda v: (v["date"], v["votingNumber"]))
    by_period = defaultdict(list)
    for v in votes:
        by_period[_period(v["date"])].append(v)

    term = _map(votes, names)
    # on the term's map an MP sitting now wears their present club
    term["club"] = [mps[mp]["club"] if mps.get(mp, {}).get("active") and mps[mp].get("club") else c
                    for mp, c in zip(term["ids"], term["club"])]
    panels = []
    for key in sorted(by_period, key=lambda k: tuple(map(int, k.split("-")))):
        p = _map(by_period[key], names)
        common = [i for i, mp in enumerate(p["ids"]) if mp in term["ids"]]
        ref = np.array([term["xy"][term["ids"].index(p["ids"][i])] for i in common])
        if len(common) >= 3:
            p["xy"] = (p["xy"] - p["xy"][common].mean(axis=0)) @ _rotation(p["xy"][common], ref)
        p["key"], p["label"] = key, _label(key)
        p["from"], p["to"] = by_period[key][0]["date"][:10], by_period[key][-1]["date"][:10]
        p["cohesion"] = _cohesion(by_period[key])
        panels.append(p)
    term["xy"] = term["xy"] - term["xy"].mean(axis=0)
    # one scale for all maps
    scale = max(float(np.abs(m["xy"]).max()) for m in [term, *panels]) or 1

    def out(m):
        return {"votes": m["votes"], "between": m["between"],
                "mps": [[mp, round(float(x) / scale, 4), round(float(y) / scale, 4), c, n]
                        for mp, (x, y), c, n in zip(m["ids"], m["xy"], m["club"], m["names"])],
                "edges": m["edges"]}

    # the closest votes: margin over what was needed
    def margin(v):
        need = v["no"] + 1 if v.get("majorityType") == "SIMPLE_MAJORITY" else (v.get("majorityVotes") or 0)
        return v["yes"] - need
    # votes most MPs took part in (not quorum checks or votes nobody cast)
    real = [v for v in votes if v["yes"] + v["no"] >= 100]
    close = sorted(real, key=lambda v: (abs(margin(v) + 0.5), v["date"]))[:CLOSE]
    margins = Counter(margin(v) for v in real)

    clubs_now = [c for c in club_rows if c["current"] and len(c["members"]) >= 3]
    agreement = {c["id"]: {o["club"]: o["rate"] for o in c["agreement"]} for c in clubs_now}
    return {
        "json": {"term": {**out(term), "from": votes[0]["date"][:10], "to": votes[-1]["date"][:10]},
                 "panels": [{**out(p), "key": p["key"], "label": p["label"], "from": p["from"], "to": p["to"]} for p in panels]},
        "panels": [{"key": p["key"], "label": p["label"], "votes": p["votes"], "between": p["between"],
                    "cohesion": p["cohesion"], "mps": len(p["ids"])} for p in panels],
        "term_between": term["between"],
        "clubs": [c["id"] for c in clubs_now],
        "agreement": agreement,
        "close": close,
        "margins": sorted(margins.items()),
    }

