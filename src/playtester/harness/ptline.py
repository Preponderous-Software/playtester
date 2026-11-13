"""Probe lines: short, fixed-format records a game prints on screen, read back by OCR or from a log.

A game that cannot write ``state.json`` itself (Mount&Blade: Warband: its
scripts cannot write files, and ``rgl_log.txt`` is only written when the game
exits) can still print short lines. A mod's test build prints one line an
in-game hour, and one per event, in a colour nothing else uses; the Windows
driver reads them from screenshots (``windows_ocr``) and from the log
(``windows_log``), and this module turns them into the probe's
``state.json`` and ``events.jsonl`` (docs/PROBE_CONTRACT.md).

The format (docs/PROBE_LINES.md has the full description)::

    PT <kind> <seq> <field> ... <check>

``kind`` is one capital letter, every other word an integer (possibly
negative). ``seq`` counts the game's probe lines (1, 2, ...), so a line seen
in several screenshots is kept once. ``check`` is a checksum digit over the
kind's code and every number before it: with W = (1, 3, 7, 9) and
D(n) = the sum of the decimal digits of |n|, plus 1 when n < 0,

    check = sum(W[i % 4] * D(n_i) for i, n_i in enumerate([code, seq, field, ...])) % 10

so any one misread digit or a lost minus sign is caught, and a line with the
wrong number of words for its kind is dropped.

    kind  code  fields after seq                       what it is
    P     1     t day x y gold party free menu         the hourly state probe
    S     2     t day x y gold party                   a new game started (the automatic start)
    M     3     menu at t day x y                      a settlement menu opened
    E     4     with rel t day x y                     an encounter began
    B     5     with t day x y gold party              a battle the player was in ended

``t`` is game hours (the probe's tick), ``day`` = t // 24, ``x``/``y`` the
party's map position in hundredths (``player.x``/``player.z``), ``free`` 1
when the map runs with nothing open, ``menu`` 1 town / 2 castle / 3 village
(0 none), ``at``/``with`` party numbers, ``rel`` the relation.

Tools that build such test builds can reuse this file: its code is
standard-library Python with no imports from playtester, and
``tests/data/ptline_vectors.json`` holds test vectors (lines in; events and
state out) for any other implementation of the format to check itself
against, so that every reader writes the same files for the same lines.
"""

import itertools
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

FORMAT = "PT line v2"
WEIGHTS = (1, 3, 7, 9)
KINDS = {
    "P": (1, ("t", "day", "x", "y", "gold", "party", "free", "menu")),
    "S": (2, ("t", "day", "x", "y", "gold", "party")),
    "M": (3, ("menu", "at", "t", "day", "x", "y")),
    "E": (4, ("with", "rel", "t", "day", "x", "y")),
    "B": (5, ("with", "t", "day", "x", "y", "gold", "party")),
}
EVENT_TYPES = {"M": "menu", "E": "encounter", "B": "battle_end"}
MENU_NAMES = {0: None, 1: "town", 2: "castle", 3: "village"}
# what OCR tends to read for a digit or a kind letter
_DIGIT = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0", "I": "1", "l": "1", "|": "1", "i": "1", "!": "1",
                        "Z": "2", "z": "2", "S": "5", "s": "5", "G": "6", "b": "6", "B": "8", "g": "9", "q": "9",
                        "—": "-", "–": "-", "~": "-", "_": "-"})
_KIND = {"5": "S", "8": "B", "3": "B", "F": "E", "N": "M", "R": "P", "p": "P", "s": "S", "e": "E", "m": "M"}
_HEAD = re.compile(r"P\s*[T7]\s*([A-Za-z0-9])\s+(.*)$")
_NUMBER = re.compile(r"^-?\d+$")
RECENT = 256      # canonical lines remembered for de-duplication
LATE = 16         # a line this many seq numbers behind the last one, at no later hour, is a late read


def digit_value(n: int) -> int:
    """D(n): the digits of |n| summed, plus 1 for a minus sign."""
    return sum(int(c) for c in str(abs(int(n)))) + (1 if n < 0 else 0)


def checksum(code: int, numbers: List[int]) -> int:
    """The check digit for a line of kind ``code`` whose numbers (seq first) are ``numbers``."""
    values = [code] + list(numbers)
    return sum(WEIGHTS[i % 4] * digit_value(v) for i, v in enumerate(values)) % 10


def format_line(kind: str, seq: int, values: Dict[str, int]) -> str:
    """The line a game prints (and the canonical form of one read back)."""
    code, names = KINDS[kind]
    numbers = [int(seq)] + [int(values[n]) for n in names]
    return "PT %s %s %d" % (kind, " ".join(str(n) for n in numbers), checksum(code, numbers))


def parse_line(text: str) -> Optional[Dict[str, Any]]:
    """``{"kind", "seq", <field>: int, ...}`` for a probe line (OCR slips tolerated), or None.

    None for anything that is not a probe line, cannot be read as its kind's
    number of words, fails its check digit, or is not ``plausible``. OCR
    drops spaces between one-digit words, so a line with up to MAX_MERGED
    words too few is tried with the spaces put back in every possible place;
    it is taken only when exactly one reading passes.
    """
    m = _HEAD.search(text.strip())
    if not m:
        return None
    kind = m.group(1)
    kind = _KIND.get(kind, kind.upper())
    if kind not in KINDS:
        return None
    code, names = KINDS[kind]
    words = m.group(2).replace(",", " ").replace(".", " ").translate(_DIGIT).replace("-", " -").split()
    if not all(_NUMBER.match(w) for w in words):
        return None
    good = []  # type: List[List[int]]
    for numbers in _splits(words, len(names) + 2):
        *numbers, check = numbers
        if check == checksum(code, numbers) and plausible(kind, numbers) and numbers not in good:
            good.append(numbers)
    if len(good) != 1:
        return None
    out = {"kind": kind, "seq": good[0][0]}  # type: Dict[str, Any]
    out.update(zip(names, good[0][1:]))
    return out


def plausible(kind: str, numbers: List[int]) -> bool:
    """Whether a line's numbers (seq first) can be what a game wrote: seq >= 1, t >= 0, day = t // 24,
    free 0 or 1, menu 0 to 3, gold and party not negative."""
    r = dict(zip(("seq",) + KINDS[kind][1], numbers))
    return (r["seq"] >= 1 and r["t"] >= 0 and r["day"] == r["t"] // 24 and r.get("free", 0) in (0, 1)
            and 0 <= r.get("menu", 0) <= 3 and r.get("gold", 0) >= 0 and r.get("party", 0) >= 0)


MAX_MERGED = 4   # spaces OCR may have lost in one line (it drops them between one-digit words)


def _splits(words: List[str], want: int) -> Iterator[List[int]]:
    """Every way to read ``words`` as ``want`` numbers: as they are, or with up to MAX_MERGED spaces put
    back inside words (never making a number with a leading zero)."""
    missing = want - len(words)
    if missing < 0 or missing > MAX_MERGED:
        return
    spots = [(i, k) for i, w in enumerate(words) for k in range(2 if w.startswith("-") else 1, len(w))]
    for cuts in itertools.combinations(spots, missing):
        out = []  # type: List[int]
        for i, w in enumerate(words):
            ks = [k for j, k in cuts if j == i]
            parts = [w[a:b] for a, b in zip([0] + ks, ks + [len(w)])]
            if any(len(p.lstrip("-")) > 1 and p.lstrip("-").startswith("0") for p in parts):
                break
            out += [int(p) for p in parts]
        else:
            yield out


def _where(r: Dict[str, Any]) -> Dict[str, float]:
    return {"x": r["x"] / 100.0, "z": r["y"] / 100.0}


class Decoder:
    """Probe lines in, probe events and state out; keeps what it needs between batches (``to_dict``)."""

    def __init__(self, version: str = "unknown", saved: Optional[Dict[str, Any]] = None):
        saved = saved or {}
        self.version = saved.get("version") or version
        self.last_seq = saved.get("lastSeq")  # type: Optional[int]
        self.last_t = saved.get("lastT")  # type: Optional[int]
        self.tick = saved.get("tick", 0)
        self.in_world = bool(saved.get("inWorld"))
        self.screen = saved.get("screen")  # type: Optional[str]
        self.state = saved.get("state")  # type: Optional[Dict[str, Any]]
        self.accepted = saved.get("accepted", 0)
        self.duplicates = saved.get("duplicates", 0)
        self.missed = saved.get("missed", 0)
        self.late = saved.get("late", 0)
        self.recent = list(saved.get("recent") or [])  # type: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"format": FORMAT, "version": self.version, "lastSeq": self.last_seq, "lastT": self.last_t,
                "tick": self.tick, "inWorld": self.in_world, "screen": self.screen, "state": self.state,
                "accepted": self.accepted, "duplicates": self.duplicates, "missed": self.missed, "late": self.late,
                "recent": self.recent[-RECENT:]}

    def classify(self, r: Dict[str, Any], canonical: str) -> str:
        """``new``, ``duplicate`` (a line already taken, read again from a later screenshot) or ``late``
        (an older line read only now, after a newer one: it is dropped, so ticks never go back)."""
        if canonical in self.recent:
            return "duplicate"
        if (self.last_seq is not None and r["kind"] != "S" and r["seq"] < self.last_seq
                and self.last_seq - r["seq"] <= LATE and r["t"] <= (self.last_t or 0)):
            return "late"
        return "new"

    def feed(self, text: str, wall_ms: int) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """(canonical line or None, events) for one line of text; None when it is not a new probe line."""
        r = parse_line(text)
        if r is None:
            return None, []
        canonical = format_line(r["kind"], r["seq"], r)
        verdict = self.classify(r, canonical)
        if verdict == "duplicate":
            self.duplicates += 1
            return None, []
        if verdict == "late":
            self.late += 1
            return None, []
        if self.last_seq is not None and r["seq"] > self.last_seq + 1 and r["t"] >= (self.last_t or 0):
            self.missed += r["seq"] - self.last_seq - 1
        self.last_seq, self.last_t = r["seq"], r["t"]
        self.accepted += 1
        self.recent = (self.recent + [canonical])[-RECENT:]
        return canonical, self._events(r, wall_ms)

    def feed_all(self, lines: List[str], wall_ms: int) -> Tuple[List[str], List[Dict[str, Any]]]:
        kept, events = [], []  # type: Tuple[List[str], List[Dict[str, Any]]]
        for line in lines:
            canonical, evs = self.feed(line, wall_ms)
            if canonical:
                kept.append(canonical)
                events += evs
        return kept, events

    def _events(self, r: Dict[str, Any], wall: int) -> List[Dict[str, Any]]:
        events = []  # type: List[Dict[str, Any]]
        t, kind = r["t"], r["kind"]
        if kind == "S":
            events.append(dict({"type": "world", "how": "created", "tick": t, "wallTimeMs": wall,
                                "seed": "unseeded"}, **_where(r)))
            self.in_world, self.screen = True, None
        elif not self.in_world or t < self.tick:
            events.append({"type": "world", "how": "loaded", "tick": t, "wallTimeMs": wall})
            self.in_world, self.screen = True, None
        self.tick = t
        if kind in ("P", "S"):
            to = "WORLD" if kind == "S" or r["free"] == 1 else "MENU"
            if to != self.screen:
                events.append({"type": "screen", "from": self.screen, "to": to, "tick": t, "wallTimeMs": wall})
                self.screen = to
            self.state = {"screen": to, "tick": t, "player": dict(_where(r), yawDeg=0), "day": r["day"],
                          "gold": r["gold"], "partySize": r["party"],
                          "menu": MENU_NAMES.get(r.get("menu", 0), r.get("menu")),
                          "openPanels": [] if to == "WORLD" else ["menu"]}
            return events
        e = {"type": EVENT_TYPES[kind], "tick": t, "wallTimeMs": wall}  # type: Dict[str, Any]
        e.update(_where(r))
        for k in KINDS[kind][1]:
            if k not in ("t", "x", "y"):
                e[k] = MENU_NAMES.get(r[k], r[k]) if k == "menu" else r[k]
        e["seq"] = r["seq"]
        events.append(e)
        return events

    def state_json(self, wall_ms: int) -> Dict[str, Any]:
        """The state.json object: the latest P or S line, or only the required fields before any."""
        if self.state is None:
            return {"wallTimeMs": wall_ms, "version": self.version, "screen": "UNKNOWN", "world": False}
        out = {"wallTimeMs": wall_ms, "version": self.version, "world": True, "seed": "unseeded",
               "probeSeq": self.last_seq}  # type: Dict[str, Any]
        out.update(self.state)
        return out


def decode(lines: List[str], wall_ms: int, version: str = "unknown") -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """(state, events) for a whole list of lines at once (a post-mortem reader, and the tests)."""
    d = Decoder(version)
    _, events = d.feed_all(lines, wall_ms)
    return d.state_json(wall_ms), events
