import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import live_ai  # noqa: E402


def make(tmp):
    (tmp / "data" / "ai").mkdir(parents=True)
    (tmp / "data" / "prints").mkdir()
    (tmp / "data" / "ai" / "bills.json").write_text(json.dumps({
        "100": {"summary": "Projekt zmienia coś.", "points": ["a" * 200, "b" * 200, "c"], "who": "Wszystkich."},
        "300": {"summary": "Za mało tekstu.", "points": [], "insufficient": True}}))
    # 120 considered jointly with 100; 150 a committee report on 120
    (tmp / "data" / "processes.json").write_text(json.dumps({"120": {"prints": ["100"]}, "100": {"prints": []}}))
    (tmp / "data" / "prints" / "150.json").write_text(json.dumps({"processPrint": ["120"]}))
    return live_ai.Summaries(tmp)


def test_root_of(tmp_path):
    s = make(tmp_path)
    assert s.root_of(["100"]) == "100"
    assert s.root_of(["120"]) == "100"     # a joint bill
    assert s.root_of(["150"]) == "100"     # a committee report's process print
    assert s.root_of(["300"]) is None      # marked insufficient
    assert s.root_of(["999", "150"]) == "100"


def test_cards_and_pages(tmp_path):
    s = make(tmp_path)
    cards = live_ai.cards("100", s.by_root["100"], "Punkt 1")
    assert cards[0]["text"] == "Projekt zmienia coś." and cards[0]["url"] == "sejmomat.pl/100"
    assert [len(c["points"]) for c in cards[1:]] == [1, 2]   # long points one to a card, never split
    pages = live_ai.pages(s.by_root["100"], width=40, lines=6)
    assert all(len(p) <= 6 for p in pages)
    assert pages[0][0] == ("w", "Projekt zmienia coś.")
    flat = [line for p in pages for _, line in p]
    assert sum(line.startswith("• ") for line in flat) == 3
