import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from live_photos import Photos
from live_overlay import Overlay


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (8, 10), "navy").save(out, format="JPEG")
    return out.getvalue()


class PhotoReadiness(unittest.TestCase):
    def test_drawing_never_fetches_a_missing_photo(self):
        with tempfile.TemporaryDirectory() as cache:
            def fetch(mp):
                self.fail("drawing must not fetch")
            photos = Photos(cache, fetch)
            overlay = Overlay("", "", None, "test", photos=photos)
            overlay.font = lambda size, bold=False: ImageFont.load_default(size=size)
            card = {"kind": "mp", "mp": 7, "name": "Test MP", "club": "Test", "title": "Speaker",
                    "value": 4, "unit": "speeches", "stats": []}
            self.assertIsNone(photos.get(7))
            self.assertIsNotNone(overlay.card(card, 2, 20))
            self.assertEqual(list(Path(cache).iterdir()), [])

    def test_retry_and_disk_reuse(self):
        with tempfile.TemporaryDirectory() as cache:
            calls = []
            def fetch(mp):
                calls.append(mp)
                if len(calls) == 1:
                    raise TimeoutError("transient")
                return jpeg()
            photos = Photos(cache, fetch)
            self.assertEqual(photos.prepare([7, 7]), 1)
            self.assertEqual(calls, [7, 7])
            self.assertEqual(photos.get(7).mode, "RGB")
            reused = Photos(cache, lambda mp: self.fail("cached image fetched again"))
            self.assertEqual(reused.prepare([7]), 1)

    def test_all_card_shapes_prepare_photos_without_treating_metric_rows_as_mps(self):
        with tempfile.TemporaryDirectory() as cache:
            calls = []
            def fetch(mp):
                calls.append(mp)
                return jpeg()
            photos = Photos(cache, fetch)
            cards = [{"kind": "mp", "mp": 1}, {"kind": "top5", "rows": [{"mp": 2}]},
                     {"kind": "region", "rows": [{"mp": 3}, {"mp": 1}]},
                     {"kind": "compare", "sides": [{"mp": 4}, {"mp": 5}],
                      "rows": [{"label": "speeches", "a": 3, "b": 2}]}]
            self.assertEqual(photos.prepare_cards(cards), 5)
            self.assertEqual(sorted(calls), [1, 2, 3, 4, 5])
            self.assertTrue(all(photos.get(mp) is not None for mp in calls))

    def test_permanent_failure_is_not_retried_for_every_caption(self):
        with tempfile.TemporaryDirectory() as cache:
            calls = []
            def fetch(mp):
                calls.append(mp)
                raise TimeoutError("unavailable")
            photos = Photos(cache, fetch)
            self.assertEqual(photos.prepare([7]), 0)
            self.assertEqual(photos.prepare([7]), 0)
            self.assertIsNone(photos.prefetch([7]))
            self.assertEqual(calls, [7, 7])

    def test_unwritable_cache_keeps_image_and_corrupt_cache_is_refetched(self):
        with tempfile.TemporaryDirectory() as cache:
            path = Path(cache)
            (path / "7.jpg").write_bytes(b"broken")
            photos = Photos(cache, lambda mp: jpeg())
            with patch.object(Path, "write_bytes", side_effect=PermissionError):
                self.assertEqual(photos.prepare([7]), 1)
            self.assertIsNotNone(photos.get(7))

    def test_prefetch_and_prepare_share_in_flight_work_without_blocking_get(self):
        with tempfile.TemporaryDirectory() as cache:
            started, release = threading.Event(), threading.Event()
            calls = []
            def fetch(mp):
                calls.append(mp)
                started.set()
                if not release.wait(3):
                    raise TimeoutError("test did not release fetch")
                return jpeg()
            photos = Photos(cache, fetch)
            worker = photos.prefetch([7])
            self.assertTrue(started.wait(2))
            try:
                self.assertIsNone(photos.get(7))
                self.assertIsNone(photos.prefetch([7]))
                other = threading.Thread(target=photos.prepare, args=([7],))
                other.start()
            finally:
                release.set()
            worker.join(3)
            other.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(other.is_alive())
            self.assertEqual(calls, [7])
            self.assertIsNotNone(photos.get(7))
