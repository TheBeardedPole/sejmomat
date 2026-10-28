"""Interpret caption, transcript and wide-shot observations by the picture's clock."""
import threading
from dataclasses import dataclass
from datetime import timedelta

QUIET = 300
SPEAKER_BAR = 600
CAPTION_LAG = 8  # measured caption delay; tools/caption_lag.py
SNAP_EVERY = 1
BREAK_MATCH = 18
BREAK_AFTER = 60
BREAK_ENDS = 2
BREAK_NO_VOTE = 120
BREAK_NO_SPEAKER = 180


@dataclass(frozen=True)
class PictureState:
    speaker: dict
    chair: str | None
    on_break: tuple | None
    speaking: bool
    recent_vote: bool
    floor: bool


class PictureTime:
    def __init__(self, start, lead=0, transcript=()):
        self.start, self.lead = start, lead
        self.transcript = transcript
        self._speaker = {"card": None, "at": None, "mp": None, "until": None}
        self._last = {"mp": None, "seen": None}
        self._pending = []
        self._pending_chair = []
        self._chair_mp = self._chair = None
        self._breaks = []
        self._run = self._first_miss = self._quiet_from = None
        self._misses = 0
        self._on_break = False
        self._lock = threading.Lock()

    def observe_chair(self, seen, mp, text):
        with self._lock:
            if self._chair_mp == mp:
                return False
            self._pending_chair.append((seen, text))
            self._pending_chair.sort(key=lambda x: x[0])
            self._chair_mp = mp
            return True

    def observe_speaker(self, seen, card, clock):
        with self._lock:
            if self._last["mp"] == card["mp"] and (seen - self._last["seen"]).total_seconds() < 60:
                return None
            self._last.update(mp=card["mp"], seen=seen)
            began = max(seen - timedelta(seconds=CAPTION_LAG if self.lead else 0), clock)
            self._pending.append((began, {"mp": card["mp"], "at": began, "until": None, "card": card}))
            self._pending.sort(key=lambda x: x[0])
            if self._on_break and self._breaks and self._breaks[-1][1] is None:
                self._breaks[-1][1] = max(began, self._breaks[-1][0])
                print(f"{self._breaks[-1][1]:%H:%M:%S} koniec przerwy (mówca)", flush=True)
            self._on_break, self._run, self._misses = False, None, 0
            self._quiet_from = seen + timedelta(seconds=BREAK_NO_SPEAKER)
            return began

    def observe_shot(self, seen, score):
        if score is None:
            return
        with self._lock:
            if score <= BREAK_MATCH:
                self._misses, self._first_miss = 0, None
                self._run = self._run or seen
                opening = (self._run - self.start).total_seconds() <= self.lead + 2 * SNAP_EVERY
                spoken = self._quiet_from and seen < self._quiet_from
                quiet = max(self._run, self._quiet_from or self._run)
                if not self._on_break and not spoken and (opening or (seen - quiet).total_seconds() >= BREAK_AFTER):
                    self._on_break = True
                    began = self._run if opening else quiet + timedelta(seconds=BREAK_AFTER)
                    self._breaks.append([began, None])
                    print(f"{began:%H:%M:%S} przerwa: porównania na ekranie", flush=True)
            else:
                self._misses += 1
                self._first_miss = self._first_miss or seen
                if self._misses >= BREAK_ENDS:
                    if self._on_break:
                        self._breaks[-1][1] = self._first_miss
                        print(f"{self._first_miss:%H:%M:%S} koniec przerwy", flush=True)
                    self._run, self._on_break = None, False

    def frame(self, clock, last_vote=None):
        with self._lock:
            if self.transcript:
                on = next((x for x in self.transcript if x["start"] <= clock < x["end"]), None)
                if on and (self._speaker["mp"], self._speaker["at"]) != (on["mp"], on["start"]):
                    self._speaker.update(mp=on["mp"], at=on["start"], until=on["end"], card=on["card"])
            while self._pending and self._pending[0][0] <= clock:
                self._speaker.update(self._pending.pop(0)[1])
            while self._pending_chair and self._pending_chair[0][0] <= clock:
                self._chair = self._pending_chair.pop(0)[1]
            on_break = next((tuple(b) for b in self._breaks if b[0] <= clock and (b[1] is None or clock < b[1])), None)
            since_vote = (clock - last_vote).total_seconds() if last_vote is not None else float("inf")
            if since_vote <= BREAK_NO_VOTE:
                on_break = None
            speaker = self._speaker.copy()
            speaking = bool(speaker["card"]) and 0 <= (clock - speaker["at"]).total_seconds() < SPEAKER_BAR and (speaker["until"] is None or clock < speaker["until"])
            recent = since_vote < QUIET
            floor = recent and speaking and speaker["at"] > last_vote
            return PictureState(speaker, self._chair, on_break, speaking, recent, floor)
