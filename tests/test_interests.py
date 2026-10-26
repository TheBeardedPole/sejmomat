"""sejmomat/interests.py on small hand-made data. Run: python -m unittest discover tests"""
import unittest
from datetime import date

from sejmomat import interests

SPEC = [
    {"id": "zdrowie", "pl": "Zdrowie", "en": "Health", "committees": ["ZDR"], "ministers": ["minister zdrowia"],
     "tags": ["Szpitale", "Leki"]},
    {"id": "rolnictwo", "pl": "Rolnictwo", "en": "Agriculture", "committees": ["RRW"],
     "ministers": ["minister rolnictwa i rozwoju wsi"], "tags": ["Rolnictwo"]},
]
TODAY = date(2026, 10, 24)


def proc(title, stages):
    return {"title": title, "stages": [{"date": d, "name": n, "committee": c, "depth": 0} for d, n, c in stages]}


class Matching(unittest.TestCase):
    def test_tags_and_committees_are_the_reasons(self):
        m = interests.bill_matches(["Szpitale", "Upamiętnienie"], ["ZDR", "FPB"], SPEC)
        self.assertEqual(m, {"zdrowie": [("tag", "Szpitale"), ("committee", "ZDR")]})
        self.assertEqual(interests.bill_matches(["Upamiętnienie"], ["FPB"], SPEC), {})

    def test_events(self):
        bills = {"10": {"title": "Ustawa o szpitalach", "tags": ["Szpitale"]},
                 "20": {"title": "Uchwała", "tags": ["Upamiętnienie"]}}
        by_id = {
            1: {"date": "2026-10-20T10:00:00", "sitting": 67, "votingNumber": 5, "bill": "10",
                "motion": ("final",), "outcome": "Ustawa przyjęta", "outcome_class": "adopted"},
            # an amendment vote: never matched, its description says too little
            2: {"date": "2026-10-20T10:00:00", "sitting": 67, "votingNumber": 4, "bill": "10",
                "motion": None, "outcome": "Poprawka odrzucona", "outcome_class": "rejected"},
            # too old
            3: {"date": "2026-09-01T10:00:00", "sitting": 60, "votingNumber": 1, "bill": "10",
                "motion": ("final",), "outcome": "Ustawa przyjęta", "outcome_class": "adopted"},
            # no topic of interest
            4: {"date": "2026-10-21T10:00:00", "sitting": 67, "votingNumber": 9, "bill": "20",
                "motion": ("final",), "outcome": "Uchwała przyjęta", "outcome_class": "adopted"},
        }
        procs = {
            "10": proc("Ustawa o szpitalach", [("2026-10-01", "Projekt wpłynął do Sejmu", ""),
                                                ("2026-10-05", "Skierowano do I czytania w komisjach", "ZDR"),
                                                ("2026-10-20", "Uchwalono", "")]),
            # no page here yet: matched through its committee, linked to the Sejm
            "30": proc("Projekt o rolnictwie", [("2026-10-15", "I czytanie w komisjach", "RRW")]),
        }
        upcoming = {"dates": ["2026-11-05"], "groups": [{"items": [
            {"n": "3", "kind": "Sprawozdanie", "rest": "o szpitalach", "prints": ["10"], "bill": "10"},
            {"n": "4", "kind": "Pierwsze czytanie", "rest": "o czymś", "prints": ["40"], "bill": None},
        ]}]}
        ev = interests.events(SPEC, bills, by_id, procs, upcoming, TODAY)
        kinds = [(e["k"], e["root"], e["d"]) for e in ev]
        self.assertEqual(kinds[0], ("agenda", "10", "2026-11-05"))
        self.assertIn(("vote", "10", "2026-10-20"), kinds)
        self.assertIn(("stage", "10", "2026-10-20"), kinds)
        self.assertIn(("stage", "30", "2026-10-15"), kinds)
        self.assertNotIn("20", {e["root"] for e in ev})
        self.assertEqual(sum(1 for e in ev if e["k"] == "vote"), 1)
        # "Skierowano do I czytania" is a step not shown on its own
        self.assertNotIn("Skierowano do I czytania w komisjach", {e["s"] for e in ev})
        off_site = next(e for e in ev if e["root"] == "30")
        self.assertTrue(off_site["url"].startswith("https://www.sejm.gov.pl/"))
        self.assertEqual(off_site["m"], {"rolnictwo": [("committee", "RRW")]})
        self.assertEqual([e["d"] for e in ev], sorted((e["d"] for e in ev), reverse=True))

    def test_amendments_counted_together_and_sittings_named(self):
        bills = {"10": {"title": "Ustawa o szpitalach", "tags": ["Szpitale"]}}
        vote = {"sitting": 67, "bill": "10", "yes": 0, "no": 0, "abstain": 0}
        by_id = {
            1: {**vote, "date": "2026-10-21T10:00:00", "votingNumber": 1, "amendments": [{}], "motion": None,
                "outcome_class": "adopted"},
            2: {**vote, "date": "2026-10-22T10:00:00", "votingNumber": 2, "amendments": [{}], "motion": None,
                "outcome_class": "rejected"},
            3: {**vote, "date": "2026-10-22T11:00:00", "votingNumber": 3, "motion": ("final",), "yes": 300, "no": 100,
                "abstain": 5, "outcome": "Projekt przyjęty", "outcome_class": "adopted"},
        }
        procs = {"10": proc("Ustawa o szpitalach", [("2026-10-22", "Uchwalono", ""), ("2026-10-24", "Stanowisko Senatu", "")])}
        ev = interests.events(SPEC, bills, by_id, procs, None, TODAY)
        amend = [e for e in ev if e["k"] == "amend"]
        self.assertEqual(len(amend), 1)
        self.assertEqual((amend[0]["a"], amend[0]["d"], amend[0]["p"]), ([2, 1], "2026-10-22", 67))
        self.assertEqual(amend[0]["url"], "ustawa/10.html#poprawki")
        v = next(e for e in ev if e["k"] == "vote")
        self.assertEqual((v["c"], v["a"], v["p"], v["n"], v["mo"]), ([300, 100, 5], [2, 1], 67, 3, "final"))
        stages = {e["d"]: e.get("p") for e in ev if e["k"] == "stage"}
        self.assertEqual(stages, {"2026-10-22": 67, "2026-10-24": None})   # a stage off a sitting day names none


class Mps(unittest.TestCase):
    def rows(self):
        def mp(i, active=True, questions=()):
            return {"mp": {"id": i, "firstLastName": f"Poseł {i}", "club": "X", "active": active},
                    "questions": [{"date": d, "to": to} for d, to in questions]}
        return [
            mp(1),                                               # committee chair only
            mp(2, questions=[("2026-10-01", ["minister zdrowia"])] * 5),   # five recent questions: the top tier
            mp(3, questions=[("2025-01-01", ["minister zdrowia"])] * 40),  # many old ones: 1 point, not enough alone
            mp(4, active=False),                                 # no longer an MP
            mp(5, questions=[("2026-10-01", ["minister finansów"])] * 9),  # other ministry
        ]

    def test_scores_and_reasons(self):
        committees = [{"code": "ZDR", "members": [{"id": 1, "function": "przewodniczący"}, {"id": 4, "function": None},
                                                  {"id": 6, "function": None}]}]
        bills = {"10": {"tags": ["Szpitale"], "date": "2026-10-20", "mps": [6, 6]}}
        rows = self.rows() + [{"mp": {"id": 6, "firstLastName": "Poseł 6", "club": "Y", "active": True}, "questions": []}]
        out = interests.suggested_mps(SPEC, rows, committees, bills, TODAY)
        zdrowie = {r["id"]: r for r in out["zdrowie"]}
        self.assertEqual(zdrowie[1]["score"], 4)
        self.assertEqual(zdrowie[1]["why"], [{"k": "committee", "code": "ZDR", "fn": "przewodniczący"}])
        self.assertEqual(zdrowie[2]["score"], 3)
        self.assertNotIn(3, zdrowie)   # old questions alone are not enough
        self.assertEqual(zdrowie[6]["why"][-1]["k"], "bills")
        self.assertEqual(zdrowie[6]["score"], 4)   # a member (2) with two bills (2)
        self.assertNotIn(4, zdrowie)   # not active
        self.assertNotIn(5, zdrowie)   # nothing on health
        self.assertEqual(out["rolnictwo"], [])   # too little to suggest anyone
        self.assertEqual([r["id"] for r in out["zdrowie"]], sorted(zdrowie, key=lambda i: (-zdrowie[i]["score"], i)))

    def test_below_threshold_is_left_out(self):
        committees = [{"code": "ZDR", "members": [{"id": 1, "function": None}]}]   # a member: 2 points
        out = interests.suggested_mps(SPEC, self.rows()[:1], committees, {}, TODAY)
        self.assertEqual(out["zdrowie"], [])


class QuestionTiers(unittest.TestCase):
    def test_tiers(self):
        q = interests.question_points
        self.assertEqual([q(5, 0), q(40, 0), q(1, 0), q(4, 99), q(0, 5), q(0, 4)], [3, 3, 2, 2, 1, 0])


class Spec(unittest.TestCase):
    def test_the_real_file(self):
        spec = interests.load()
        self.assertGreaterEqual(len(spec), 10)
        self.assertEqual(len({i["id"] for i in spec}), len(spec))
        for i in spec:
            self.assertTrue(i["pl"] and i["en"] and i["tags"])


if __name__ == "__main__":
    unittest.main()
