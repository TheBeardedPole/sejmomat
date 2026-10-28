import unittest

from PIL import Image, ImageDraw
from sejmomat import card


class ShareGraphics(unittest.TestCase):
    def test_summary_uses_publication_masthead_and_complete_output(self):
        summary = {"day": "2026-10-22", "sitting": 67, "votes": 237, "lawsPassed": 26,
                   "resolutionsPassed": 3, "billsRejected": 1, "amendmentVotes": 189,
                   "amendmentVotesAdopted": 89, "againstCommitteeRecommendation": 3,
                   "mostContestedLaw": None, "amendmentProposers": []}
        image = card.render(summary)
        self.assertEqual(image.width, 1200)
        self.assertGreaterEqual(image.height, 675)
        self.assertLess(image.height, 3000)
        self.assertEqual(image.getpixel((0, 20)), (11, 12, 12))
        self.assertEqual(image.getpixel((0, 84)), (29, 112, 184))
        self.assertEqual(image.getpixel((0, image.height - 20)), (255, 255, 255))

    def test_reading_fonts_load_from_bundled_files_with_distinct_weights(self):
        regular, bold = card.font("regular", 32), card.font("bold", 32)
        self.assertIn("Source Sans", regular.getname()[0])
        self.assertIn("Source Serif", card.font("heading", 64).getname()[0])
        self.assertNotEqual(regular.getlength("Zażółć gęślą jaźń"), bold.getlength("Zażółć gęślą jaźń"))

    def test_summary_rows_scale_with_content_and_preserve_all_figures(self):
        image = Image.new("RGB", (1200, 1600), card.BG)
        end = card.summary_rows(ImageDraw.Draw(image), 300,
            [("100,0%", "udział w głosowaniach (10000 z 10000)", card.TEXT, 1),
             ("1987 z 2001", "podpisanych poprawek i wniosków przeszło", card.TEXT)])
        self.assertEqual(end, 300 + 2 * 104 + 32)
        self.assertEqual(image.getpixel((card.PAD, 310)), (243, 243, 243))
        self.assertEqual(image.getpixel((card.PAD, 414)), (255, 255, 255))

    def test_mp_club_and_minister_variants_render_with_missing_photo_and_long_names(self):
        row = {"mp": {"firstLastName": "Aleksandra Karolina Uznańska-Wiśniewska", "club": "KO", "districtName": "Łódź"},
               "terms": [10], "eligible": 100, "cast": 92, "turnout": .92, "rebel_count": 3,
               "rebel_rate": .03, "signed": [1], "signed_adopted": 0, "standing": {"turnout": 5},
               "speeches": {"spoken": 20, "cloud": [("mieszkalnictwo", 3, 2)]}}
        c = {"id": "KO", "name": "Testowy klub", "first": "2023-11-13", "last": "2026-10-22", "members": [1],
             "current": True, "cohesion": .99, "effectiveness": .5, "split": [], "agreement": [],
             "sittings": [{"sitting": 67, "votes": 100, "cast": 90, "Y": 60, "N": 30, "A": 0, "X": 10, "split": 10, "rebels": 3}]}
        minister = {"name": "minister testowy", "received": 20, "answered": 10, "median": 14, "late": 2,
                    "prolonged": 3, "overdue": 1}
        for image in [card.mp_term(row, tag=card.SERIES_TAG), card.club_term(c, [], str),
                      card.club_sitting(c, [{"date": "2026-10-22T10:00:00"}], str), card.minister(minister, 21)]:
            self.assertEqual(image.width, 1200)
            self.assertLess(image.height, 3000)
