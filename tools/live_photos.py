"""Prepare MP photos away from drawing; get() never touches disk or network."""
import io
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image


PHOTO = "https://api.sejm.gov.pl/sejm/term10/MP/{}/photo"


def fetch_photo(mp):
    req = urllib.request.Request(PHOTO.format(mp), headers={"User-Agent": "sejmomat-live"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read()


class Photos:
    def __init__(self, cache=None, fetch=fetch_photo):
        self.cache = Path(cache) if cache is not None else Path.home() / ".cache" / "sejmomat-live" / "photos"
        self.fetch = fetch
        self._images = {}
        self._attempts = {}
        self._pending = {}
        self._lock = threading.Lock()

    def get(self, mp):
        with self._lock:
            return self._images.get(mp)

    def _load(self, mp):
        with self._lock:
            if self._images.get(mp) is not None:
                return self._images[mp]
            if self._attempts.get(mp, 0) >= 2 and mp not in self._pending:
                return None
            owner = mp not in self._pending
            done = self._pending.setdefault(mp, threading.Event())
            if owner:
                self._attempts[mp] = self._attempts.get(mp, 0) + 1
        if not owner:
            done.wait()
            return self.get(mp)
        image = None
        try:
            path = self.cache / f"{mp}.jpg"
            data = path.read_bytes() if path.exists() else None
            if data is not None:
                try:
                    with Image.open(io.BytesIO(data)) as source:
                        image = source.convert("RGB")
                except OSError:
                    data = None
            if data is None:
                data = self.fetch(mp)
                with Image.open(io.BytesIO(data)) as source:
                    image = source.convert("RGB")
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                except OSError:
                    pass  # a read-only cache must not discard an already decoded photo
        except Exception as error:
            print(f"no photo for MP {mp}: {error}", file=sys.stderr)
        finally:
            with self._lock:
                self._images[mp] = image
                self._pending.pop(mp)
                done.set()
        return image

    def prepare(self, ids, workers=8, progress=None):
        ids = sorted(set(ids))
        if not ids:
            return 0
        with ThreadPoolExecutor(workers) as pool:
            for i, _ in enumerate(pool.map(self._load, ids), 1):
                if progress:
                    progress(i, len(ids))
            failed = [mp for mp in ids if self.get(mp) is None]
            list(pool.map(self._load, failed))  # transient fetch failures get one retry
        return sum(self.get(mp) is not None for mp in ids)

    def prepare_cards(self, cards, progress=None):
        ids = set()
        for card in cards:
            for item in [card, *(card.get("rows") or []), *(card.get("sides") or [])]:
                if item.get("mp"):
                    ids.add(item["mp"])
        return self.prepare(ids, progress=progress)

    def prefetch(self, ids):
        with self._lock:
            missing = [mp for mp in set(ids) if self._images.get(mp) is None
                       and mp not in self._pending and self._attempts.get(mp, 0) < 2]
        if not missing:
            return None
        worker = threading.Thread(target=self.prepare, args=(missing, 4), daemon=True)
        worker.start()
        return worker
