"""tools/live_chat.py on small hand-made votes. Run: python -m unittest discover tests"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import live_chat  # noqa: E402

BILL = "Pkt. 5 Sprawozdanie Komisji o rządowym projekcie ustawy o zmianie ustawy o zdrowiu publicznym (druki nr 3247 i 3250)"
SENATE = "Pkt. 9 Sprawozdanie Komisji o uchwale Senatu w sprawie ustawy o asystencji osobistej (druki nr 3100 i 3120)"
START = datetime(2026, 10, 22, 9, 0, tzinfo=live_chat.WARSAW)


def vote(num, minute, topic, title=BILL, yes=230, no=200, abstain=5, majority="SIMPLE_MAJORITY"):
    at = START + timedelta(minutes=minute)
    return {"sitting": 67, "votingNumber": num, "date": at.strftime("%Y-%m-%dT%H:%M:%S"), "topic": topic,
            "title": title, "yes": yes, "no": no, "abstain": abstain, "majorityType": majority, "majorityVotes": 231}


def after(minute, seconds=live_chat.POST_AFTER + 1):
    return START + timedelta(minutes=minute, seconds=seconds)


class Messages(unittest.TestCase):
    def test_final_vote_takes_its_amendments(self):
        votes = [vote(1, 1, "poprawka 1", yes=240, no=190), vote(2, 2, "poprawka 2", yes=100, no=330),
                 vote(3, 3, "wniosek mniejszości 1", yes=200, no=230), vote(4, 4, "głosowanie nad całością projektu.")]
        out = live_chat.Planner(START).due(votes, after(4))
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("✅ Projekt przyjęty · zmiana ustawy o zdrowiu publicznym"))
        self.assertIn("poprawki: 1 z 3 przyjęte", out[0])
        self.assertTrue(out[0].endswith("glosowanie-na-zywo.html?posiedzenie=67&nr=4"))

    def test_senate_amendment_stands_unless_rejected(self):
        # "za" is for rejecting the Senate's amendment (an absolute majority, 231)
        votes = [vote(1, 1, "poprawka 1", SENATE, yes=300, no=130, majority="ABSOLUTE_MAJORITY"),
                 vote(2, 2, "poprawka 2", SENATE, yes=200, no=230, majority="ABSOLUTE_MAJORITY")]
        planner = live_chat.Planner(START)
        self.assertEqual(planner.due(votes, after(2)), [])   # the run could go on
        out = planner.due(votes, after(2, live_chat.AMEND_RUN_END + 1))
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("📝 Poprawki Senatu: 1 z 2 przyjęte · ustawa o asystencji osobistej"))
        self.assertIn("głosowania 1–2", out[0])

    def test_motion_to_reject_reads_the_other_way(self):
        out = live_chat.Planner(START).due([vote(1, 1, "wniosek o odrzucenie w całości projektu.", yes=60, no=370)], after(1))
        self.assertTrue(out[0].startswith("🗳️ Wniosek odrzucony: projekt trafia do dalszych prac"))

    def test_motions_to_cut_the_wait_in_one_message(self):
        votes = [vote(i, i, "wniosek o skrócenie terminu, o którym mowa w art. 44 ust. 3 regulaminu Sejmu",
                      f"Głosowanie proceduralne dotyczące druku {3200 + i}") for i in range(1, 4)]
        votes.append(vote(4, 5, "głosowanie nad całością projektu."))
        out = live_chat.Planner(START).due(votes, after(5))
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0].startswith("⏩ Przyśpieszenie prac: 3 z 3 wniosków przyjęte · druki 3201, 3202, 3203"))
        self.assertTrue(out[1].startswith("✅ Projekt przyjęty"))

    def test_when_and_what_is_left_out(self):
        votes = [vote(1, -5, "głosowanie nad całością projektu."),               # before the stream began
                 vote(2, 1, "Głosowanie kworum", yes=0, no=0, abstain=0),      # a quorum check
                 vote(3, 2, "głosowanie nad całością projektu.")]
        planner = live_chat.Planner(START)
        self.assertEqual(planner.due(votes, after(2, live_chat.POST_AFTER - 1)), [])   # not on screen yet
        out = planner.due(votes, after(2))
        self.assertEqual([m.rsplit("nr=", 1)[1] for m in out], ["3"])
        self.assertEqual(planner.due(votes, after(10)), [])                    # each vote once

    def test_fits_the_chat_box(self):
        long = "Pkt. 2 " + "Sprawozdanie Komisji o rządowym projekcie ustawy o zmianie ustawy " * 6
        topic = "głosowanie nad przyjęciem wniosku o wyrażenie zgody na pociągnięcie do odpowiedzialności karnej posła " * 2
        out = live_chat.Planner(START).due([vote(1, 1, "głosowanie nad całością projektu.", long),
                                            vote(2, 2, topic, long)], after(2))
        self.assertEqual(len(out), 2)
        for m in out:
            self.assertLessEqual(len(m), live_chat.MAX_LEN)
            self.assertIn("https://sejmomat.pl/", m)


if __name__ == "__main__":
    unittest.main()
