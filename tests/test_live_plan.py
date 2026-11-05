"""tools/live_plan.py on a hand-made timetable (as sitting 68's). Run: python -m unittest discover tests"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import live_plan as lp  # noqa: E402

D = "2026-11-05"


def slot(a, b, points=(), vote=False, text="", day=D):
    return {"start": f"{day}T{a}", "end": f"{day}T{b}", "points": list(points), "vote": vote, "text": text}


SLOTS = lp.slots_of([
    slot("09:00", "09:30", vote=True, text="Głosowania proceduralne"),
    slot("09:30", "10:45", [1], text="Pierwsze czytanie projektu ustawy o podatku"),
    slot("10:45", "11:00", vote=True, text="Głosowanie"),
    slot("11:00", "12:30", [2], text="Sprawozdanie Komisji o projekcie ustawy o Karcie Rodziny Mundurowej"),
    slot("14:30", "15:45", [5], text="Sprawozdanie o systemie oświaty"),
    slot("15:45", "16:30", [6], text="Wniosek Rady Ministrów"),
    slot("16:30", "17:00", [7, 8], vote=True, text="Głosowania"),
    slot("17:00", "18:00", [11], text="Sprawozdanie o podatku dochodowym"),
    slot("10:00", "10:05", vote=True, text="Głosowania proceduralne", day="2026-11-06"),
    slot("10:30", "11:30", [18], text="Sprawozdanie o szkolnictwie", day="2026-11-06"),
])


def vote(hhmm, point=None, day=D):
    return {"date": f"{day}T{hhmm}:00", "title": f"Pkt. {point} Coś" if point else "Wniosek o przerwę"}


def at(hhmm, day=D):
    return datetime.fromisoformat(f"{day}T{hhmm}")


class Delay(unittest.TestCase):
    def test_on_time(self):
        votes = [vote("09:08"), vote("09:26"), vote("10:51", 1), vote("10:52", 1)]
        late, why = lp.delay(SLOTS, votes, at("15:00"))
        self.assertEqual(late, timedelta(0))
        self.assertEqual(why, "głosowania")
        self.assertEqual(lp.current(SLOTS, at("15:00"), late)["points"], [5])

    def test_block_late(self):
        votes = [vote("09:08"), vote("10:51", 1), vote("17:10", 7), vote("17:12", 8)]
        late, why = lp.delay(SLOTS, votes, at("17:30"))
        self.assertEqual(late, timedelta(minutes=40))
        # 17:30 is 16:50 by the plan: still the votes, not item 11
        self.assertTrue(lp.current(SLOTS, at("17:30"), late)["vote"])
        self.assertEqual(lp.current(SLOTS, at("17:45"), late)["points"], [11])

    def test_block_not_begun(self):
        votes = [vote("09:08"), vote("10:51", 1)]
        self.assertEqual(lp.delay(SLOTS, votes, at("16:35")), (timedelta(0), "głosowania"))   # within the grace
        late, why = lp.delay(SLOTS, votes, at("16:50"))
        self.assertEqual((late, why), (timedelta(minutes=20), "czeka"))

    def test_matched_by_items_not_time(self):
        # item 7's vote, three hours late, goes with the 16:30 block, not the nearer 17:00 slot or another
        late, _ = lp.delay(SLOTS, [vote("19:30", 7)], at("19:40"))
        self.assertEqual(late, timedelta(hours=3))

    def test_split_block_counts_once(self):
        votes = [vote("16:32", 7), vote("17:40", 8)]   # a pause inside the block
        late, _ = lp.delay(SLOTS, votes, at("17:45"))
        self.assertEqual(late, timedelta(0))

    def test_next_morning_fresh(self):
        votes = [vote("17:10", 7)]
        late, why = lp.delay(SLOTS, votes, at("10:40", "2026-11-06"))
        self.assertEqual(late, timedelta(minutes=40))   # 10:00 block not begun at 10:40: the morning's own
        self.assertEqual(why, "czeka")
        late, _ = lp.delay(SLOTS, votes + [vote("10:02", day="2026-11-06")], at("10:40", "2026-11-06"))
        self.assertEqual(late, timedelta(0))


class ByHand(unittest.TestCase):
    """!nowypunkt / !poprzednipunkt from the chat."""

    def test_next_starts_now(self):
        late, slot = lp.step(SLOTS, at("15:30"), timedelta(0), forward=True)   # plan: item 5 until 15:45
        self.assertEqual(slot["points"], [6])
        self.assertEqual(late, timedelta(minutes=-15))
        self.assertEqual(lp.current(SLOTS, at("15:30"), late)["points"], [6])

    def test_previous_means_late(self):
        late, slot = lp.step(SLOTS, at("16:00"), timedelta(0), forward=False)  # plan: item 6; still on item 5
        self.assertEqual(slot["points"], [5])
        self.assertEqual(lp.current(SLOTS, at("16:00"), late)["points"], [5])
        self.assertGreater(late, timedelta(0))

    def test_manual_holds_until_votes_after_it(self):
        votes = [vote("09:08"), vote("10:51", 1)]
        manual = (at("15:30"), timedelta(minutes=50))
        self.assertEqual(lp.delay(SLOTS, votes, at("15:40"), manual), (timedelta(minutes=50), "ręcznie"))
        # votes measured after it take over: the 16:30 block run at 17:00 is 30 min late
        late, why = lp.delay(SLOTS, votes + [vote("17:00", 7)], at("17:05"), manual)
        self.assertEqual((late, why), (timedelta(minutes=30), "głosowania"))


class Words(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(lp.minutes(timedelta(minutes=41)), "ok. 40 min")
        self.assertEqual(lp.minutes(timedelta(minutes=70)), "ok. 1 godz. 10 min")
        self.assertEqual(lp.minutes(timedelta(minutes=118)), "ok. 2 godz.")

    def test_subject(self):
        self.assertEqual(lp.subject("projekt ustawy zmieniającej ustawę o zmianie ustawy o systemie oświaty oraz niektórych innych ustaw oraz ustawę o rynku pracy"),
                         "o systemie oświaty")
        self.assertEqual(lp.subject("zmiana ustawy o podatku dochodowym od osób fizycznych, ustawy o podatku dochodowym od osób prawnych"),
                         "o podatku dochodowym od osób fizycznych")
        self.assertEqual(lp.subject("zmiana ustawy – Karta Nauczyciela"), "Karta Nauczyciela")
        self.assertEqual(lp.subject("ustawa o Karcie Rodziny Mundurowej"), "o Karcie Rodziny Mundurowej")
        self.assertEqual(lp.subject("Wniosek o wyrażenie wotum nieufności wobec Ministra Spraw Wewnętrznych"), "Wotum nieufności wobec Ministra Spraw Wewnętrznych")
        self.assertEqual(lp.subject("Rozpatrzenie wniosku Rady Ministrów o wyrażenie przez Sejm Rzeczypospolitej Polskiej zgody na przedłużenie ograniczenia"),
                         "Zgoda na przedłużenie ograniczenia")
        self.assertEqual(lp.subject("Informacja bieżąca"), "Informacja bieżąca")

    def test_label(self):
        self.assertEqual(lp.label(SLOTS[1]), "Punkt 1 · Pierwsze czytanie projektu ustawy o podatku")
        self.assertEqual(lp.label(SLOTS[0]), "Głosowania")
        self.assertEqual(lp.label({**SLOTS[1], "points": [12, 13]}), "Punkty 12–13 · Pierwsze czytanie projektu ustawy o podatku")
        self.assertEqual(lp.label({**SLOTS[1], "text": "cd. pkt 1"}), "Punkt 1 (cd.)")


if __name__ == "__main__":
    unittest.main()
