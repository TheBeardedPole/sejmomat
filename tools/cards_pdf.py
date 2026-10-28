"""Every card the stream can show, one a page, as tools/livestream.py draws it
(tools/live_overlay.py), on a still of the Sejm's broadcast, with what it is and
when it comes up; for looking them over and seeing what is missing.

    python tools/cards_pdf.py                 # cards.pdf, from the data as the build has it
    python tools/cards_pdf.py --out x.pdf --frame "2026-10-22 14:02"

The cards are made from the data here (sejmomat/facts.py on the build's context,
about a minute), so a change to facts.py shows at once, before any build. Needs the
Sejm's video CDN for the still (a Polish address); without it the background is plain.
"""
import argparse
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live_overlay  # noqa: E402
from live_overlay import H, W, Overlay  # noqa: E402
from livestream import (CLUB_AFTER, CMP_SECONDS, FACT_EVERY, FACT_SECONDS, PROMO_EVERY, PROMOS, ROOT, SPEAKER_SECONDS,  # noqa: E402
                        TOP_SECONDS, WARSAW, font, load_mps, plenary, source)

from sejmomat.build import build_context  # noqa: E402
from sejmomat.facts import facts  # noqa: E402

PAGE_W, CAPTION = W, 170


def still(at):
    """A frame of the broadcast at that Warsaw time, as an RGBA image, or None."""
    try:
        when = datetime.fromisoformat(at).replace(tzinfo=WARSAW)
        _, base, _, end = plenary(when.date().isoformat())
        out = Path(tempfile.mkdtemp()) / "still.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source(base, when, end, 720), "-frames:v", "1",
                        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
                        str(out)], check=True, timeout=120)
        return Image.open(out).convert("RGBA")
    except Exception as e:
        print(f"no still from the broadcast ({e}); plain background", file=sys.stderr)
        return None


def when_shown(c):
    """What the card is and when the stream shows it, in a line or two (Polish, like the cards)."""
    if c.get("kind") == "region":
        return ("Posłowie z regionu",
                f"Gdy mówi poseł z tego okręgu, raz na wystąpienie, od {CLUB_AFTER}. sekundy; po pięciu posłów, 5 s na stronę.")
    if c.get("kind") == "compare":
        return ("Porównanie (przerwa)",
                f"W przerwie obrad, na zmianę z porządkiem obrad i głosowaniami dnia: {CMP_SECONDS} s każde.")
    if c.get("kind") == "speaker":
        return "Na mównicy", f"Gdy poseł staje na mównicy: przez {SPEAKER_SECONDS} s od początku wystąpienia."
    if c.get("kind") == "promo":
        return "O Sejmomacie", f"Co {PROMO_EVERY}. karta kolejki ogólnej (pomijana z --demo)."
    if c.get("for_club"):
        return (f"Ranking klubu {c['for_club']}",
                f"Tylko gdy mówi poseł klubu {c['for_club']}, od {CLUB_AFTER}. sekundy wystąpienia; {TOP_SECONDS} s na ekranie.")
    if c.get("kind") == "top5":
        return "Ranking (cały Sejm)", f"Kolejka ogólna: jedna karta co {FACT_EVERY} s, gdy nie trwają głosowania; {TOP_SECONDS} s na ekranie."
    if c.get("kind") == "fact" and c.get("stats") and c.get("club"):
        return (f"Klub w liczbach: {c['club']}",
                f"Kolejka ogólna (co {FACT_EVERY} s) oraz gdy mówi poseł klubu {c['club']}, od {CLUB_AFTER}. sekundy; {FACT_SECONDS} s.")
    if c.get("kind") == "mp":
        return "Rekord posła", f"Kolejka ogólna: jedna karta co {FACT_EVERY} s, gdy nie trwają głosowania; {FACT_SECONDS} s na ekranie."
    return "Ciekawostka", f"Kolejka ogólna: jedna karta co {FACT_EVERY} s, gdy nie trwają głosowania; {FACT_SECONDS} s na ekranie."


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="cards.pdf")
    ap.add_argument("--frame", default="2026-10-22 14:02", help="Warsaw time of the broadcast still behind the cards")
    args = ap.parse_args()

    print("data …", flush=True)
    ctx = build_context()
    cards = facts(ctx)
    # the speaker's card as the stream makes it (livestream.speaker_card), for one MP
    mps = {m["id"]: m for m in load_mps(ROOT)}
    m = next((m for m in mps.values() if m["name"].startswith("Witold Tumanowicz")), next(iter(mps.values())))
    speaker = {"kind": "mp", "mp": m["id"], "name": m["name"], "club": m.get("club") or "niez.", "title": "Na mównicy",
               "value": m.get("speeches") or 0, "unit": "wystąpień w kadencji",
               "stats": [["frekwencja", f"{m.get('turnout', 0) * 100:.1f}%".replace(".", ",")],
                         ["wyłamania", str(m.get("brokeLine", 0))], ["interpelacje", str(m.get("questions", 0))],
                         ["zmiany klubu", str(m.get("clubSwitches", 0))]]}
    # the pool of MPs is not a card: three pairs drawn from it, as the stream draws them
    import random
    from sejmomat.facts import mp_compare
    pool = next((c["mps"] for c in cards if c.get("kind") == "mp_pool"), [])
    spoke = [m for m in pool if m["speeches"]]
    for num in random.sample(sorted({m["num"] for m in spoke}), min(3, len({m["num"] for m in spoke}))):
        k = [m for m in spoke if m["num"] == num and m["tag"] == "Koalicja"]
        o = [m for m in spoke if m["num"] == num and m["tag"] == "Opozycja"]
        if k and o:
            cards.append(mp_compare(random.choice(k), random.choice(o)))
    cards = [c for c in cards if c.get("kind") != "mp_pool"]
    pages = [({**speaker, "_as": "speaker"}, "speaker")] + [(p, "promo") for p in PROMOS] + [(c, None) for c in cards]

    live_overlay.CARD_SCALE = 1.0   # drawn at full size, to be read on paper
    overlay = Overlay(font(True), font(False), ROOT / "static" / "logo-white.png", "SEJMOMAT · karty transmisji")
    print("photos …", flush=True)
    overlay.photos.prepare_cards(c for c, _ in pages)

    back = still(args.frame) or Image.new("RGBA", (W, H), (40, 44, 52, 255))
    back = Image.alpha_composite(back, Image.new("RGBA", (W, H), (0, 0, 0, 90)))   # darker, so the card stands out
    bold, regular = overlay.font(30, True), overlay.font(22, False)
    out = []
    for i, (c, special) in enumerate(pages, 1):
        page = Image.new("RGB", (PAGE_W, H + CAPTION), (250, 250, 248))
        frame = back.copy()
        if c.get("kind") == "compare":
            # a break's comparison: over the whole hall, as the stream shows it
            scene = Image.frombytes("RGBA", (W, H), overlay.frame_scene(overlay.compare(c, 10.0, 20.0)))
            frame.alpha_composite(scene)
        else:
            drawn = overlay.card(c, 10.0, 20.0)   # the still part of its turn: counted in, rows in
            if drawn:
                img, _, _ = drawn
                frame.alpha_composite(img, ((W - img.width) // 2, (H - img.height) // 2))
        page.paste(frame.convert("RGB"), (0, 0))
        d = ImageDraw.Draw(page)
        kind, rule = when_shown({**c, "kind": special} if special else c)
        d.text((28, H + 22), f"{i}/{len(pages)} · {kind}", font=bold, fill=(29, 29, 31))
        d.text((28, H + 66), (c.get("title") or "").replace("\n", " ")[:110], font=regular, fill=(29, 29, 31))
        d.text((28, H + 104), rule, font=regular, fill=(107, 107, 112))
        out.append(page)
        if i % 20 == 0:
            print(f"  {i}/{len(pages)}", flush=True)
    out[0].save(args.out, save_all=True, append_images=out[1:], resolution=150)
    print(f"{args.out}: {len(out)} pages")


if __name__ == "__main__":
    main()
