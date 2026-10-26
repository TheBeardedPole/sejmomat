"""How long after an MP starts speaking does the broadcast name them? Measured
on a past day: the archived stream read as fast as the computer can, the
caption band (live_speaker.BAND) saved once a second and read as
tools/livestream.py reads it, and each spoken speech in the transcript
(data/speeches) matched to the first second its speaker's caption is read.

    python tools/caption_lag.py 2026-10-22 --from 09:00 --minutes 90

The clock is the one livestream.py uses (the picture shows start + time
elapsed), so the lag found is what the stream would have to make up for.
Run on a Polish address, as livestream.py (the video CDN answers only those).
"""
import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from livestream import ROOT, VIDEO_PROXY, WARSAW, load_transcript, plenary, source  # noqa: E402
from live_speaker import BAND, Recogniser, load_mps, read  # noqa: E402

SEARCH_BEFORE = 20   # a caption this many seconds before the transcript's start still counts (clocks differ)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("day", help="a past sitting day, YYYY-MM-DD")
    ap.add_argument("--from", dest="start", default="09:00", help="Warsaw time to start at (default 09:00)")
    ap.add_argument("--minutes", type=int, default=90, help="how much of the day to read (default 90)")
    ap.add_argument("--jobs", type=int, default=8, help="Tesseract processes at a time (default 8)")
    ap.add_argument("--keep", help="keep the band images in this folder")
    args = ap.parse_args()

    start = datetime.fromisoformat(f"{args.day} {args.start}").replace(tzinfo=WARSAW)
    stop = start + timedelta(minutes=args.minutes)
    _, base, _, end = plenary(args.day)
    src = source(base, start, end, 720)
    work = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="sejmomat-lag-"))
    work.mkdir(parents=True, exist_ok=True)

    # the band once a second: frame n is start + n seconds, as livestream.py counts
    bx, by, bw, bh = BAND
    proxy = ["-http_proxy", VIDEO_PROXY] if VIDEO_PROXY else []
    print(f"reading {args.minutes} min from {start:%H:%M} …", flush=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *proxy, "-i", src, "-t", str(args.minutes * 60), "-an",
                    "-vf", f"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                           f"fps=1,crop={bw}:{bh}:{bx}:{by}",
                    "-start_number", "0", "-y", str(work / "%05d.png")], check=True)
    frames = sorted(work.glob("[0-9]*.png"))
    print(f"{len(frames)} frames; reading captions …", flush=True)

    recogniser = Recogniser(load_mps(ROOT))
    with ThreadPoolExecutor(args.jobs) as pool:
        texts = list(pool.map(read, frames))
    seen = {}   # MP id -> [seconds]
    for f, text in zip(frames, texts):
        if m := recogniser.match(text):
            seen.setdefault(m["id"], []).append(int(f.stem))

    lags, missed = [], []
    for sp in load_transcript(args.day):
        if not (start <= sp["start"] < stop):
            continue
        a = (sp["start"] - start).total_seconds()
        b = (sp["end"] - start).total_seconds()
        first = next((t for t in seen.get(sp["mp"], []) if a - SEARCH_BEFORE <= t <= b), None)
        if first is None:
            missed.append(sp)
        else:
            lags.append({"mp": sp["mp"], "start": f"{sp['start']:%H:%M:%S}", "lag": first - a, "length": b - a})

    print(f"\nspeeches in the window: {len(lags) + len(missed)}; caption read: {len(lags)}; never read: {len(missed)}")
    if lags:
        xs = sorted(x["lag"] for x in lags)
        q = statistics.quantiles(xs, n=10) if len(xs) >= 10 else xs
        print(f"lag (s): median {statistics.median(xs):.0f}, mean {statistics.mean(xs):.1f}, "
              f"min {xs[0]:.0f}, max {xs[-1]:.0f}, 10th–90th percentile {q[0]:.0f}–{q[-1]:.0f}")
        print("histogram (5 s bins):")
        for lo in range(int(min(xs) // 5 * 5), int(max(xs)) + 1, 5):
            n = sum(1 for x in xs if lo <= x < lo + 5)
            print(f"  {lo:>4}–{lo + 5:<4} {'#' * n} {n}")
    (work / "lags.json").write_text(json.dumps({"lags": lags, "missed": [
        {"mp": m["mp"], "start": f"{m['start']:%H:%M:%S}"} for m in missed]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\ndetails: {work / 'lags.json'}")


if __name__ == "__main__":
    main()
