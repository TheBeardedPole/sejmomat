"""A fantasy game on Sejm data, replayed over the term so far: every MP scored in every
sitting (a sitting is a gameweek) for each position, prices set from past points, and a
few strategies played against each other, to see whether the rules make for real choices.

    python tools/fantasy/simulate.py              # writes tools/fantasy/out/sim.json and prints a summary
    python tools/fantasy/simulate.py --close 10   # a different margin for a "close" vote

Positions (RULES below): Mówca (speeches), Buntownik (breaking the club line), Lojalista
(voting with the line when the club is split), Klikacz (taking part in every vote),
Zwycięzca and Opozycjonista (on the winning or losing side of a close vote). Everyone also
gets points for turning up and loses them for missed votes and days. Only data from the
term's record: ballots (data/votings), spoken speeches as an MP (data/speeches).
"""
import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sejmomat.model import load  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"

# the rules, positions, squad, prices: the game's own (sejmomat/fantasy.py)
from sejmomat import fantasy  # noqa: E402
from sejmomat.fantasy import (BUDGET, CLUB_CAP, POSITIONS, PRICE_MAX, PRICE_MIN, PRICE_STEP, PRICE_WINDOW,  # noqa: E402
                              RULES, SQUAD, WARMUP, points)


def counters(sittings, close):
    """{sitting: {mp: Counter}} and {sitting: {mp: club}}, as the game counts them."""
    fantasy.CLOSE = close
    speech_days = fantasy.speeches_by_day()
    out, club_of = {}, {}
    for s, votings in sittings.items():
        days = sorted({v["date"][:10] for v in votings})
        out[s], club_of[s] = fantasy.counters(votings, [st for d in days for st in speech_days.get(d, [])])
    return out, club_of


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--close", type=int, default=fantasy.CLOSE, help="a vote is close when the result is this many votes or fewer from the threshold")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.seed)

    mps, clubs, sittings = load()
    names = {m["id"]: m["firstLastName"] for m in mps.values()}
    order = sorted(sittings)
    raw, club_of = counters(sittings, args.close)

    # points[s][mp][position]
    pts = {s: {mp: {pos: points(c, pos) for pos in POSITIONS} for mp, c in raw[s].items()} for s in order}

    # ---- prices: per MP and position, from the mean of the last PRICE_WINDOW sittings,
    # mapped linearly onto PRICE_MIN..PRICE_MAX by that position's spread (5th to 99th percentile)
    def form(mp, pos, upto):
        past = [pts[s][mp][pos] for s in order if s < upto and mp in pts[s]][-PRICE_WINDOW:]
        return statistics.mean(past) if past else 0.0

    # ---- prices: per MP and position, from the MP's rank in recent form among all MPs
    # in that position (mean of the last PRICE_WINDOW sittings), PRICE_MIN for the
    # weakest to PRICE_MAX for the best; after the first, a price moves at most PRICE_STEP
    prices = {}
    prev = {}
    for s in order[WARMUP:]:
        prices[s] = {}
        for pos in POSITIONS:
            f = {mp: form(mp, pos, s) for mp in pts[s]}
            ranked = sorted(f, key=lambda mp: f[mp])
            n = len(ranked) - 1 or 1
            # equal form, equal price: the rank of the first with that form
            first_rank = {}
            for i, mp in enumerate(ranked):
                first_rank.setdefault(f[mp], i)
            for mp in ranked:
                target = PRICE_MIN + (first_rank[f[mp]] / n) ** 2 * (PRICE_MAX - PRICE_MIN)   # most MPs cheap, stars dear
                was = prev.get((mp, pos))
                new = target if was is None else max(was - PRICE_STEP, min(was + PRICE_STEP, target))
                prices[s].setdefault(mp, {})[pos] = round(new, 1)
                prev[(mp, pos)] = new

    # ---- squads under a budget, with the club cap and no MP twice
    slots = [pos for pos, n in SQUAD.items() for _ in range(n)]

    def pick(s, value, budget=BUDGET):
        """Greedy by value per price, then swaps that add value within the budget."""
        pr = prices[s]
        team, spent, per_club = [], 0.0, Counter()
        cand = [(mp, pos) for mp in pr for pos in POSITIONS]
        need = Counter(slots)
        for mp, pos in sorted(cand, key=lambda x: -value(*x) / pr[x[0]][x[1]]):
            if not need[pos] or any(m == mp for m, _ in team) or per_club[club_of[s].get(mp)] >= CLUB_CAP:
                continue
            left = len(slots) - len(team) - 1
            if spent + pr[mp][pos] + left * PRICE_MIN > budget:
                continue
            team.append((mp, pos)); spent += pr[mp][pos]; need[pos] -= 1; per_club[club_of[s].get(mp)] += 1
        improved = True
        while improved:
            improved = False
            for i, (mp, pos) in enumerate(team):
                for alt in sorted(pr, key=lambda m: -value(m, pos))[:60]:
                    if any(m == alt for m, _ in team):
                        continue
                    clubs_now = Counter(club_of[s].get(m) for j, (m, _) in enumerate(team) if j != i)
                    if clubs_now[club_of[s].get(alt)] >= CLUB_CAP:
                        continue
                    cost = spent - pr[mp][pos] + pr[alt][pos]
                    if cost <= budget and value(alt, pos) > value(mp, pos) + 1e-9:
                        team[i] = (alt, pos); spent = cost; improved = True
                        break
        return team, round(spent, 1)

    def score(s, team):
        """The squad's points in sitting s, the captain (best expected) doubled."""
        got = [pts[s].get(mp, {}).get(pos, 0) for mp, pos in team]
        return sum(got)

    strategies = defaultdict(list)
    dream = []
    for s in order[WARMUP:]:
        exp = lambda mp, pos, s=s: form(mp, pos, s)   # noqa: E731
        smart, _ = pick(s, exp)
        cap = max(smart, key=lambda t: exp(*t))
        strategies["Menedżer (forma, budżet)"].append(score(s, smart) + pts[s].get(cap[0], {}).get(cap[1], 0))
        stars, _ = pick(s, exp, budget=10 ** 6)
        strategies["Same gwiazdy (bez budżetu)"].append(score(s, stars) + max(pts[s].get(m, {}).get(p, 0) for m, p in stars))
        rnd = []
        for _ in range(200):
            team, spent, per_club = [], 0.0, Counter()
            for pos in slots:
                opts = [mp for mp in prices[s] if all(m != mp for m, _ in team) and per_club[club_of[s].get(mp)] < CLUB_CAP]
                random.shuffle(opts)
                for mp in opts:
                    left = len(slots) - len(team) - 1
                    if spent + prices[s][mp][pos] + left * PRICE_MIN <= BUDGET:
                        team.append((mp, pos)); spent += prices[s][mp][pos]; per_club[club_of[s].get(mp)] += 1
                        break
            rnd.append(score(s, team) + max(pts[s].get(m, {}).get(p, 0) for m, p in team))
        strategies["Losowy skład (w budżecie)"].append(statistics.mean(rnd))
        best, _ = pick(s, lambda mp, pos, s=s: pts[s].get(mp, {}).get(pos, 0))
        dream.append({"sitting": s, "points": score(s, best) + max(pts[s].get(m, {}).get(p, 0) for m, p in best),
                      "team": [(names.get(mp, mp), pos, club_of[s].get(mp), pts[s][mp][pos], prices[s][mp][pos]) for mp, pos in best]})

    # ---- stats per position
    per_pos = {}
    for pos in POSITIONS:
        season = Counter()
        hauls = []
        for s in order[WARMUP:]:
            for mp, p in pts[s].items():
                season[mp] += p[pos]
                hauls.append((p[pos], mp, s))
        tops = season.most_common(10)
        total = sum(v for v in season.values() if v > 0) or 1
        # how predictable: points in one sitting against the mean of the previous PRICE_WINDOW
        xs, ys = [], []
        for s in order[WARMUP:]:
            for mp in pts[s]:
                xs.append(form(mp, pos, s)); ys.append(pts[s][mp][pos])
        corr = statistics.correlation(xs, ys) if len(set(xs)) > 1 else 0
        per_sitting = [pts[s][mp][pos] for s in order[WARMUP:] for mp in pts[s]]
        by_club = defaultdict(list)
        for s in order[WARMUP:]:
            for mp, p in pts[s].items():
                by_club[club_of[s].get(mp)].append(p[pos])
        per_pos[pos] = {
            "top10": [(names.get(mp, mp), club_of[order[-1]].get(mp) or "", v) for mp, v in tops],
            "top5_share": round(sum(v for _, v in tops[:5]) / total, 3),
            "predictability": round(corr, 3),
            "per_sitting": {"mean": round(statistics.mean(per_sitting), 2), "median": statistics.median(per_sitting),
                            "p90": sorted(per_sitting)[int(len(per_sitting) * 0.9)], "max": max(per_sitting),
                            "zero_or_less": round(sum(1 for x in per_sitting if x <= 2) / len(per_sitting), 3)},
            "best_hauls": [(p, names.get(mp, mp), s) for p, mp, s in sorted(hauls, reverse=True)[:5]],
            "by_club": {c: round(statistics.mean(v), 2) for c, v in sorted(by_club.items(), key=lambda kv: -statistics.mean(kv[1])) if len(v) >= 50},
        }

    # ---- value: points per price over the game (a differential is cheap and scores)
    value = []
    for pos in POSITIONS:
        for mp in {mp for s in order[WARMUP:] for mp in pts[s]}:
            got = [(pts[s][mp][pos], prices[s][mp][pos]) for s in order[WARMUP:] if mp in pts[s]]
            if len(got) >= 20:
                value.append((round(sum(p for p, _ in got) / sum(c for _, c in got), 2), names.get(mp, mp), pos,
                              round(statistics.mean(c for _, c in got), 1), sum(p for p, _ in got)))
    value.sort(reverse=True)

    # price moves: biggest rises and falls over the game
    first, last = order[WARMUP], order[-1]
    moves = sorted(((prices[last][mp][pos] - prices[first][mp][pos], names.get(mp, mp), pos, prices[first][mp][pos], prices[last][mp][pos])
                    for mp in prices[last] if mp in prices[first] for pos in POSITIONS), reverse=True)

    out = {
        "rules": RULES, "squad": SQUAD, "budget": BUDGET, "club_cap": CLUB_CAP, "close": args.close,
        "sittings": [order[WARMUP], order[-1]], "gameweeks": len(order) - WARMUP,
        "strategies": {k: {"total": round(sum(v)), "per_sitting": round(statistics.mean(v), 1), "series": [round(x, 1) for x in v]}
                       for k, v in strategies.items()},
        "dream": dream, "positions": per_pos,
        "value": value[:15], "rises": moves[:8], "falls": moves[-8:][::-1],
        "price_examples": {pos: sorted(((prices[last][mp][pos], names.get(mp, mp)) for mp in prices[last]), reverse=True)[:5] for pos in POSITIONS},
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "sim.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"{out['gameweeks']} gameweeks (sittings {order[WARMUP]}–{order[-1]}), budget {BUDGET}, close = ±{args.close}")
    for k, v in out["strategies"].items():
        print(f"  {k:32} {v['total']:6} pts, {v['per_sitting']}/sitting")
    for pos, d in per_pos.items():
        print(f"\n{pos}: mean {d['per_sitting']['mean']}, p90 {d['per_sitting']['p90']}, max {d['per_sitting']['max']}, "
              f"top-5 share {d['top5_share']}, predictability r={d['predictability']}")
        print("   top:", ", ".join(f"{n} ({c}) {v}" for n, c, v in d["top10"][:5]))
        print("   by club:", ", ".join(f"{c} {v}" for c, v in list(d["by_club"].items())))


if __name__ == "__main__":
    main()
