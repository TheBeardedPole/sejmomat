"""Videos of past sittings with the stream's captions (tools/livestream.py), to
upload: the debate on a bill and the votes on it, or a day's votes.

    python tools/clips.py list                  # the most contested bills of the term
    python tools/clips.py bill 67:44            # the bill decided in vote 44 of sitting 67:
                                                #   its main debate, then its votes
    python tools/clips.py votes 2026-10-22      # that day's votes (each block of them)

Videos go to clips/<name>/ (not in git) with a text file holding a title and a
description to paste into YouTube. Who speaks comes from the transcript (data/
speeches), so the speaker card shows the moment each MP begins. Rendering runs
as fast as the computer can (--fast), but reads the Sejm's archive, so it needs a
Polish address (or SEJMOMAT_VIDEO_PROXY), like the stream. Needs `git pull` for
the votes and transcripts.

"Contested": final votes on a bill (the whole bill, or rejecting it) where both
"for" and "against" got at least 60 votes, closest first, with how far the
coalition and the opposition voted apart.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sejmomat.stats import COALITION  # noqa: E402

WARSAW = ZoneInfo("Europe/Warsaw")
OUT = ROOT / "clips"
FINAL = re.compile(r"całością projektu|odrzucenie (w pierwszym czytaniu )?projektu|odrzuceni[ea] .*projektu", re.I)
PAD = timedelta(seconds=30)            # before the first speech, after the last
VOTES_BEFORE = timedelta(seconds=90)   # before the first vote of a block: the Marshal announcing it
VOTES_AFTER = timedelta(seconds=45)
BLOCK_GAP = timedelta(minutes=20)      # votes further apart than this are separate blocks
MIN_SPEECHES = 8                       # a day with fewer speeches on a bill is not its debate


def when(s):
    return datetime.fromisoformat(s).replace(tzinfo=WARSAW)


def prints_of(text):
    """Print numbers named in a vote title or agenda line ("druk nr 3227", "druki nr 3146 i 3196")."""
    out = []
    for m in re.finditer(r"druk(?:i|ów)?\s+nr\s+([\d\-A-Za-z ,i]+)", text or ""):
        out += re.findall(r"\d+(?:-[A-Za-z0-9]+)?", m[1])
    return set(out)


def load_votes():
    votes = []
    for f in sorted((ROOT / "data" / "votings").glob("*.json"), key=lambda f: int(f.stem)):
        d = json.loads(f.read_text(encoding="utf-8"))
        for v in d["votings"]:
            votes.append({**v, "sitting": d["sitting"]})
    return votes


def sides(v):
    """(coalition yes share, opposition yes share) among those who voted for or against."""
    out = []
    for coalition in (True, False):
        yes = no = 0
        for club, b in (v.get("ballots") or {}).items():
            if (club in COALITION) == coalition:
                yes, no = yes + len(b.get("Y") or []), no + len(b.get("N") or [])
        out.append(yes / (yes + no) if yes + no else None)
    return out


def contested(votes, n):
    """The closest decisive votes, one per bill (the same prints): the vote on the whole bill
    rather than a motion to reject it, when both are among them."""
    finals = [v for v in votes if FINAL.search(v.get("topic") or "") and min(v["yes"], v["no"]) >= 60]
    out, seen = [], []
    for v in sorted(finals, key=lambda v: (abs(v["yes"] - v["no"]), "całością" not in v["topic"])):
        prints = prints_of(v["title"])
        if any(prints & other for other in seen):
            continue
        seen.append(prints)
        out.append(v)
    return out[:n]


def transcripts():
    for f in sorted((ROOT / "data" / "speeches").glob("*.json")):
        yield json.loads(f.read_text(encoding="utf-8"))


def debate(prints, before):
    """(start, end, number of speeches) of the debate that led to a vote: the latest day up to
    the vote with at least MIN_SPEECHES spoken speeches on the bill's prints (the reading the
    vote closes, not one months before), from the first of them to the last; or None."""
    best = None
    for day in transcripts():
        if day["date"] > before:
            continue
        st = [x for x in day["statements"] if set(x.get("prints") or []) & prints
              and not x.get("unspoken") and x.get("start") and x.get("end")]
        if len(st) >= MIN_SPEECHES and (not best or day["date"] > best[0]):
            best = (day["date"], min(when(x["start"]) for x in st), max(when(x["end"]) for x in st), len(st))
    return best and best[1:]


def bill_votes(votes, final):
    """The run of votes on the same bill around the chosen one, that day: back to the first
    and on to the last with no more than BLOCK_GAP between them (a motion to reject comes
    before the vote on the whole bill, amendments before both)."""
    prints = prints_of(final["title"])
    same = sorted((v for v in votes if v["sitting"] == final["sitting"] and v["date"][:10] == final["date"][:10]
                   and prints_of(v["title"]) & prints), key=lambda v: v["votingNumber"])
    i = next(k for k, v in enumerate(same) if v is final)
    lo = hi = i
    while lo > 0 and when(same[lo]["date"]) - when(same[lo - 1]["date"]) <= BLOCK_GAP:
        lo -= 1
    while hi < len(same) - 1 and when(same[hi + 1]["date"]) - when(same[hi]["date"]) <= BLOCK_GAP:
        hi += 1
    return same[lo:hi + 1]


def describe(v):
    c, o = sides(v)
    pct = lambda x: "–" if x is None else f"{x * 100:.0f}%"
    return (f"{v['yes']} za, {v['no']} przeciw, {v['abstain']} wstrz. · koalicja za: {pct(c)}, opozycja za: {pct(o)}")


def render(at, seconds, out):
    """The stream tool over a stretch of the archive, to a file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT / "tools" / "livestream.py"), "--at", at.strftime("%Y-%m-%d %H:%M:%S"),
           "--seconds", str(int(seconds)), "--out", str(out), "--fast", "--transcript"]
    print(f"→ {out.name}: {at:%Y-%m-%d %H:%M:%S}, {seconds / 60:.0f} min", flush=True)
    subprocess.run(cmd, check=True)


def join(parts, out):
    """The parts one after another as an MP4 for upload. They come from the same encoder
    with the same settings, so they are joined as they are (a cut, not a crossfade:
    blending would mean encoding hours of video again for one second)."""
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    listing.unlink()
    for p in parts:   # the joined file has them all
        p.unlink()


def agenda_title(final):
    """The bill's name, from the vote title: "Pkt. 17 Sprawozdanie Komisji o … (druk nr 3227)"."""
    t = re.sub(r"^(Pkt\.?\s*)?[\d.,\si]+(?=[A-ZŁŚŻŹĆ])", "", final["title"])
    return re.sub(r"\s*\((druk|druki).*$", "", t).strip()


def subject(final):
    """What the bill is, briefly: "projekt ustawy o zmianie ustawy - Kodeks karny"."""
    t = agenda_title(final)
    m = re.search(r"(projek\w*\s+(ustawy|uchwały).*)$", t, re.I)
    t = m[1] if m else t
    t = re.sub(r"^projek\w*", "Projekt", t)
    # "Projekt ustawy o zmianie ustawy o X" says no more than "Zmiana ustawy o X"
    t = re.sub(r"^Projekt ustawy o zmianie ustaw(y|)\s*", lambda m: "Zmiana ustawy " if m[1] else "Zmiana ustaw ", t)
    return t.replace(" - ", " – ")


def youtube_title(text, tail):
    """At most 100 characters (YouTube's limit), cut on a word."""
    room = 100 - len(tail)
    if len(text) > room:
        text = text[:room - 1].rsplit(" ", 1)[0].rstrip(" ,-–") + "…"
    return text + tail


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("-n", type=int, default=15)
    b = sub.add_parser("bill")
    b.add_argument("vote", help="sitting:vote number of the final vote, as `list` shows it")
    b.add_argument("--no-debate", action="store_true", help="only the votes")
    d = sub.add_parser("votes")
    d.add_argument("day", help="YYYY-MM-DD")
    args = ap.parse_args()
    votes = load_votes()

    if args.cmd == "list":
        for v in contested(votes, args.n):
            deb = debate(prints_of(v["title"]), v["date"][:10])
            span = f"debata {deb[0]:%d.%m.%Y %H:%M}–{deb[1]:%H:%M} ({deb[2]} wystąpień)" if deb else "debata: brak w stenogramach"
            print(f"{v['sitting']}:{v['votingNumber']}  {v['date'][:10]}  {describe(v)}\n    {agenda_title(v)[:150]}\n    {span}")
        return

    if args.cmd == "bill":
        sitting, number = (int(x) for x in args.vote.split(":"))
        final = next((v for v in votes if v["sitting"] == sitting and v["votingNumber"] == number), None)
        if not final:
            sys.exit("No such vote.")
        run = bill_votes(votes, final)
        name = f"{final['date'][:10]}-projekt-{'-'.join(sorted(prints_of(final['title'])))}"
        folder = OUT / name
        parts = []
        deb = None if args.no_debate else debate(prints_of(final["title"]), final["date"][:10])
        if deb:
            parts.append(folder / "1-debata.mkv")
            render(deb[0] - PAD, (deb[1] - deb[0] + 2 * PAD).total_seconds(), parts[-1])
        start, end = when(run[0]["date"]) - VOTES_BEFORE, when(run[-1]["date"]) + VOTES_AFTER
        parts.append(folder / "2-glosowania.mkv")
        render(start, (end - start).total_seconds(), parts[-1])
        join(parts, folder / f"{name}.mp4")
        title = youtube_title(subject(final), f" – {'debata i głosowanie' if deb else 'głosowanie'} ({when(final['date']):%d.%m.%Y})")
        text = [title, "", agenda_title(final), "",
                *[f"{v['topic'][:1].upper() + v['topic'][1:].rstrip('.')}: {'przyjęto' if v['yes'] > v['no'] else 'odrzucono'} – {describe(v)}."
                  for v in run if FINAL.search(v.get("topic") or "")],
                f"Głosowań nad projektem tego dnia: {len(run)}.",
                *([f"Debata: {deb[0]:%d.%m.%Y, %H:%M}–{deb[1]:%H:%M}, {deb[2]} wystąpień."] if deb else []),
                "", "Transmisja Sejmu RP z napisami Sejmomatu: wyniki głosowań, co zmieniają poprawki, kto mówi.",
                "Nagranie: Kancelaria Sejmu."]
        (folder / "opis.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
        print(f"\n{folder / (name + '.mp4')}\n{folder / 'opis.txt'}")
        return

    if args.cmd == "votes":
        day = [v for v in votes if v["date"][:10] == args.day]
        if not day:
            sys.exit("No votes that day.")
        day.sort(key=lambda v: v["date"])
        blocks = [[day[0]]]
        for v in day[1:]:
            if when(v["date"]) - when(blocks[-1][-1]["date"]) > BLOCK_GAP:
                blocks.append([])
            blocks[-1].append(v)
        folder = OUT / f"{args.day}-glosowania"
        for i, block in enumerate(blocks, 1):
            start, end = when(block[0]["date"]) - VOTES_BEFORE, when(block[-1]["date"]) + VOTES_AFTER
            part = folder / f"blok-{i}.mkv"
            render(start, (end - start).total_seconds(), part)
            join([part], folder / f"{args.day}-glosowania-{i}.mp4")
            finals = [v for v in block if FINAL.search(v.get("topic") or "")]
            text = [f"Głosowania w Sejmie {when(block[0]['date']):%d.%m.%Y}"
                    + (f", część {i}" if len(blocks) > 1 else "") + f" ({when(block[0]['date']):%H:%M}–{when(block[-1]['date']):%H:%M})",
                    "", f"{len(block)} głosowań. Projekty głosowane w całości:", ""]
            text += [f"• {agenda_title(v)} – {'przyjęto' if v['yes'] > v['no'] else 'odrzucono'} ({v['yes']}:{v['no']})" for v in finals] or ["(brak)"]
            text += ["", "Transmisja Sejmu RP z napisami Sejmomatu: wyniki głosowań, co zmieniają poprawki.", "Nagranie: Kancelaria Sejmu."]
            (folder / f"opis-{i}.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
        print(f"\n{folder}")


if __name__ == "__main__":
    main()
