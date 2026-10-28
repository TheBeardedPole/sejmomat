import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from live_timeline import PictureTime

START = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)


def at(seconds):
    return START + timedelta(seconds=seconds)


def card(mp=1):
    return {"mp": mp, "name": f"MP {mp}"}


class PictureClock(unittest.TestCase):
    def test_lookahead_queues_speaker_and_chair_until_picture_reaches_them(self):
        time = PictureTime(START, lead=25)
        self.assertEqual(time.observe_speaker(at(40), card(), at(10)), at(32))
        self.assertTrue(time.observe_chair(at(35), 2, "Chair 2"))
        self.assertFalse(time.frame(at(31)).speaking)
        self.assertTrue(time.frame(at(32)).speaking)
        self.assertIsNone(time.frame(at(34)).chair)
        state = time.frame(at(35))
        self.assertEqual(state.chair, "Chair 2")
        self.assertEqual(state.speaker["mp"], 1)
        self.assertFalse(time.observe_chair(at(36), 2, "Chair 2"))

    def test_caption_is_deduplicated_and_late_observation_cannot_start_in_past(self):
        time = PictureTime(START, lead=25)
        self.assertEqual(time.observe_speaker(at(15), card(), at(20)), at(20))
        self.assertIsNone(time.observe_speaker(at(16), card(), at(21)))
        self.assertEqual(time.frame(at(21)).speaker["at"], at(20))
        live = PictureTime(START)
        self.assertEqual(live.observe_speaker(at(40), card(), at(39)), at(40))

    def test_speaker_after_vote_has_floor_until_next_vote(self):
        time = PictureTime(START)
        time.observe_speaker(at(40), card(), at(40))
        state = time.frame(at(45), last_vote=at(30))
        self.assertTrue(state.recent_vote)
        self.assertTrue(state.floor)
        self.assertFalse(time.frame(at(46), last_vote=at(46)).floor)
        self.assertFalse(time.frame(at(641)).speaking)

    def test_opening_wide_shot_and_two_misses_close_at_first_miss(self):
        time = PictureTime(START, lead=25)
        time.observe_shot(at(25), 0)
        self.assertIsNone(time.frame(at(24)).on_break)
        self.assertEqual(time.frame(at(25)).on_break, (at(25), None))
        self.assertIsNone(time.frame(at(26), last_vote=at(20)).on_break)
        time.observe_shot(at(40), 50)
        self.assertIsNotNone(time.frame(at(40)).on_break)
        time.observe_shot(at(41), 50)
        self.assertIsNone(time.frame(at(40)).on_break)
        self.assertEqual(time.frame(at(39)).on_break, (at(25), at(40)))

    def test_speaker_ends_break_and_holds_off_another_wide_shot(self):
        time = PictureTime(START, lead=25)
        time.observe_shot(at(25), 0)
        time.observe_speaker(at(40), card(), at(10))
        self.assertEqual(time.frame(at(31)).on_break, (at(25), at(32)))
        self.assertIsNone(time.frame(at(32)).on_break)
        time.observe_shot(at(100), 0)
        time.observe_shot(at(220), 0)
        self.assertIsNone(time.frame(at(220)).on_break)
        time.observe_shot(at(280), 0)
        self.assertEqual(time.frame(at(280)).on_break, (at(280), None))

    def test_mid_sitting_wide_shot_needs_full_quiet_interval(self):
        time = PictureTime(START, lead=25)
        time.observe_shot(at(100), 0)
        time.observe_shot(at(159), 0)
        self.assertIsNone(time.frame(at(159)).on_break)
        time.observe_shot(at(160), 0)
        self.assertIsNotNone(time.frame(at(160)).on_break)

    def test_transcript_intervals_expire_and_same_mp_can_begin_again(self):
        entries = [{"mp": 1, "start": at(10), "end": at(30), "card": card()},
                   {"mp": 1, "start": at(40), "end": at(60), "card": card()}]
        time = PictureTime(START, transcript=entries)
        self.assertFalse(time.frame(at(9)).speaking)
        self.assertTrue(time.frame(at(10)).speaking)
        self.assertFalse(time.frame(at(30)).speaking)
        state = time.frame(at(45))
        self.assertTrue(state.speaking)
        self.assertEqual(state.speaker["at"], at(40))
        self.assertFalse(time.frame(at(60)).speaking)
