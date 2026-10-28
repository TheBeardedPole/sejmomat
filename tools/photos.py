"""MPs' photos kept with the site (static/foto/<id>.jpg), for the seating plan's cards on the
home page (static/home.js), so they load from our own server, quickly, rather than one by one
from the Sejm's API. Run once, and again when new MPs take their seats; photos already there
are kept (--all fetches every one again).

    python tools/photos.py           # the MPs in office without a photo here
    python tools/photos.py --all

The Sejm's API serves the photos and allows their use (as on the MP pages). Each is re-saved
as a small JPEG (about 8 KB); 460 MPs come to about 4 MB. A push publishes them in a minute
(static/** goes out without a rebuild).
"""
import argparse
import io
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "foto"
TERM = 10
URL = "https://api.sejm.gov.pl/sejm/term{term}/MP/{id}/photo"
SIZE = (110, 137)   # the API's own size: kept, not enlarged


def fetch(mp_id):
    req = urllib.request.Request(URL.format(term=TERM, id=mp_id), headers={"User-Agent": "sejmomat.pl photos"})
    with urllib.request.urlopen(req, timeout=30) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    im.thumbnail(SIZE, Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78, optimize=True, progressive=True)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="fetch every photo again")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mps = [m for m in json.loads((ROOT / "data" / "mps.json").read_text()) if m.get("active")]
    todo = [m["id"] for m in mps if args.all or not (OUT / f"{m['id']}.jpg").exists()]
    print(f"{len(mps)} MPs in office, {len(todo)} photos to fetch")
    failed = []

    def one(mp_id):
        try:
            (OUT / f"{mp_id}.jpg").write_bytes(fetch(mp_id))
        except Exception as e:   # noqa: BLE001 - one missing photo should not stop the rest
            failed.append((mp_id, str(e)))

    with ThreadPoolExecutor(6) as pool:
        list(pool.map(one, todo))
    size = sum(f.stat().st_size for f in OUT.glob("*.jpg"))
    print(f"{OUT.relative_to(ROOT)}: {len(list(OUT.glob('*.jpg')))} photos, {size / 1e6:.1f} MB")
    if failed:
        print("failed:", failed, file=sys.stderr)


if __name__ == "__main__":
    main()
