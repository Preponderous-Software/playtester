"""Probe lines (harness/ptline.py), the OCR reader (harness/windows_ocr.py) and the ptline log path,
plus the Windows driver's launcher click and registry restore. No Windows, no tesseract needed."""

import json
import os
import tempfile
import unittest

from tests.helpers import HERE
from playtester.harness import profile as profiles
from playtester.harness import ptline, windows_log, windows_ocr, windows_session
from playtester.harness.session import Session
from playtester.harness.strata_driver import DriveError

VECTORS = os.path.join(HERE, "data", "ptline_vectors.json")


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


class VectorsTest(unittest.TestCase):
    """tests/data/ptline_vectors.json: lines in, the new lines, events, state and counts out."""

    @classmethod
    def setUpClass(cls):
        with open(VECTORS, encoding="utf-8") as f:
            cls.v = json.load(f)

    def test_format(self):
        self.assertEqual(self.v["format"], ptline.FORMAT)

    def test_every_case_in_one_batch(self):
        for case in self.v["cases"]:
            with self.subTest(case["name"]):
                d = ptline.Decoder(self.v["version"])
                kept, events = d.feed_all(case["lines"], self.v["wallTimeMs"])
                self.assertEqual(kept, case["canonical"])
                self.assertEqual(events, case["events"])
                self.assertEqual(d.state_json(self.v["wallTimeMs"]), case["state"])
                self.assertEqual({k: getattr(d, k) for k in case["stats"]}, case["stats"])

    def test_every_case_through_the_session_files_a_line_at_a_time(self):
        """windows_log.ingest, one line per call (one capture each), writes the vectors' files."""
        for case in self.v["cases"]:
            with self.subTest(case["name"]), tempfile.TemporaryDirectory() as out:
                for line in case["lines"]:
                    windows_log.ingest(out, [line], self.v["version"], self.v["wallTimeMs"])
                events = read_jsonl(os.path.join(out, "events.jsonl")) if case["events"] else []
                self.assertEqual(events, case["events"])
                with open(os.path.join(out, "state.json")) as f:
                    self.assertEqual(json.load(f), case["state"])
                if case["canonical"]:
                    with open(os.path.join(out, windows_log.LINES_FILE)) as f:
                        self.assertEqual(f.read().splitlines(), case["canonical"])

    def test_the_states_and_events_pass_the_probe_checker(self):
        from playtester.probecheck import check_dir
        case = self.v["cases"][0]
        with tempfile.TemporaryDirectory() as out:
            windows_log.ingest(out, case["lines"], self.v["version"], self.v["wallTimeMs"])
            self.assertEqual(check_dir(out), [])


class CodecTest(unittest.TestCase):
    def test_round_trip_and_check_digit(self):
        line = ptline.format_line("E", 12, {"with": 301, "rel": -10, "t": 5, "day": 0, "x": -9000, "y": 2000})
        r = ptline.parse_line(line)
        self.assertEqual((r["kind"], r["seq"], r["with"], r["rel"]), ("E", 12, 301, -10))
        self.assertIsNone(ptline.parse_line(line.replace("-10", "10")))       # a lost minus sign
        self.assertIsNone(ptline.parse_line(line.replace(" 301 ", " 391 ")))   # a misread digit
        words = line.split()
        self.assertIsNone(ptline.parse_line(" ".join(words[:4] + words[5:])))  # a lost word
        self.assertIsNone(ptline.parse_line("PTPROBE v=1 t=21 day=0"))

    def test_any_single_digit_change_is_caught(self):
        line = ptline.format_line("P", 6, dict(t=412, day=17, x=-1234, y=500, gold=1999, party=7, free=1, menu=0))
        self.assertEqual(line, "PT P 6 412 17 -1234 500 1999 7 1 0 6")   # the example in docs/PROBE_LINES.md
        for i, c in enumerate(line):
            if c.isdigit() and i > 4:
                for d in "0123456789":
                    if d != c:
                        self.assertIsNone(ptline.parse_line(line[:i] + d + line[i + 1:]))


class FakeChannel:
    def __init__(self, focus_ok=True, client=(100, 50, 2000, 1000)):
        self.calls = []
        self.focus_ok = focus_ok
        self.client = list(client)
        self.alive = True

    def request(self, op, timeout=None, **fields):
        self.calls.append(dict(fields, op=op))
        if op == "window":
            return {"ok": True, "window": {"client": self.client, "minimized": False}}
        if op == "alive":
            return {"ok": True, "alive": self.alive}
        if op == "focus":
            return {"ok": True, "foreground": self.focus_ok, "window": {"client": self.client}}
        return {"ok": True}

    def close(self):
        pass


class OcrReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        profile = profiles.load("warband")
        with open(os.path.join(self.dir, "profile.json"), "w") as f:
            json.dump(profile, f)
        with open(os.path.join(self.dir, "session.json"), "w") as f:
            json.dump({"hwnd": 77, "gamePid": 4242, "module": "TestModule", "client": [0, 0, 2000, 1000]}, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_settings_region_and_requests(self):
        cfg = windows_ocr.settings({"ocr": {"color": "#00FF80"}})
        self.assertEqual((cfg["color"], cfg["tolerance"], cfg["psm"]), ("#00FF80", 90, 6))
        self.assertIsNone(windows_ocr.settings({}))
        self.assertEqual(windows_ocr.rgb("#FF00ff"), [255, 0, 255])
        self.assertEqual(windows_ocr.region([100, 50, 2000, 1000], [0.0, 0.5, 0.5, 0.9]), [100, 550, 1000, 400])
        req = windows_ocr.shot_request([0, 0, 2000, 1000], dict(cfg, rect=[0, 0.5, 0.5, 1.0], scale=2), "C:\\x.png")
        self.assertEqual(req, {"rect": [0, 500, 1000, 500], "width": 2000, "height": 1000, "path": "C:\\x.png",
                               "keep": [0, 255, 128, 90]})
        cmd = windows_ocr.tesseract_command("f.png", cfg)
        self.assertEqual(cmd[:5], ["tesseract", "f.png", "stdout", "--psm", "6"])
        self.assertEqual(cmd[-1], "tessedit_char_whitelist=PTSMEB0123456789- ")

    def test_captures_become_probe_files_and_repeats_are_kept_once(self):
        lines = [ptline.format_line("S", 1, dict(t=0, day=0, x=-9589, y=2606, gold=500, party=1)),
                 ptline.format_line("P", 2, dict(t=1, day=0, x=-9589, y=2606, gold=500, party=1, free=1, menu=0))]
        screens = [["Paused", lines[0]], [lines[0], lines[1].replace("0", "O")], [lines[0], lines[1]], []]
        ch = FakeChannel()
        reader = windows_ocr.Reader(self.dir, ch, to_windows_path=lambda p: "W:" + p,
                                    ocr_text=lambda png, cfg: screens.pop(0))
        got = [reader.poll() for _ in range(4)]
        self.assertEqual(got, [[lines[0]], [lines[1]], [], []])
        shot = [c for c in ch.calls if c["op"] == "shot"][0]
        self.assertEqual(shot["rect"], windows_ocr.region([100, 50, 2000, 1000], reader.cfg["rect"]))
        self.assertEqual(shot["keep"], [255, 0, 255, 90])
        self.assertTrue(shot["path"].startswith("W:" + self.dir))
        out = os.path.join(self.dir, "out")
        events = read_jsonl(os.path.join(out, "events.jsonl"))
        self.assertEqual([e["type"] for e in events], ["world", "screen"])
        with open(os.path.join(out, "state.json")) as f:
            state = json.load(f)
        self.assertEqual((state["tick"], state["screen"], state["gold"], state["version"]),
                         (1, "WORLD", 500, "TestModule (Mount&Blade: Warband)"))
        with open(os.path.join(out, "ocr.json")) as f:
            self.assertEqual(json.load(f)["new"], 2)
        self.assertEqual(sorted(os.listdir(os.path.join(out, "ocr", "frames"))), [])  # the fake wrote no png

    def test_without_tesseract_it_says_so_and_stops(self):
        reader = windows_ocr.Reader(self.dir, FakeChannel())
        old = os.environ.get("PATH")
        os.environ["PATH"] = self.dir
        try:
            self.assertEqual(reader.run(once=True), 2)
        finally:
            os.environ["PATH"] = old
        with open(os.path.join(self.dir, "out", "ocr.log")) as f:
            self.assertIn("tesseract is not installed", f.read())

    def test_it_stops_when_the_game_is_gone(self):
        ch = FakeChannel()
        ch.alive = False
        reader = windows_ocr.Reader(self.dir, ch, ocr_text=lambda png, cfg: [])
        self.assertEqual(reader.run(), 0)

    def test_the_warband_profile_reads_magenta_lines_off_the_screen(self):
        win = profiles.load("warband")["windows"]
        self.assertEqual(win["probe_format"], "ptline")
        self.assertEqual(windows_ocr.settings(win)["color"], "#FF00FF")
        self.assertNotIn("log_prefix", win)


class PtlineLogTest(unittest.TestCase):
    def test_sync_decodes_probe_lines_and_errors_from_the_log(self):
        with tempfile.TemporaryDirectory() as root:
            session = Session("s01", root)
            os.makedirs(session.dir)
            log = os.path.join(root, "rgl_log.txt")
            with open(session.path("session.json"), "w") as f:
                json.dump({"driver": "windows", "logPath": log, "module": "TestModule"}, f)
            with open(session.path("profile.json"), "w") as f:
                json.dump({"name": "w", "title": "W", "windows": {"probe_format": "ptline",
                                                                  "log_error_patterns": ["SCRIPT ERROR"]}}, f)
            start = ptline.format_line("S", 1, dict(t=0, day=0, x=100, y=200, gold=5, party=1))
            with open(log, "w") as f:
                f.write("Starting new log file.\n%s\nSCRIPT ERROR ON OPCODE 1\n%s\n" % (start.replace(" ", "_"), start))
            self.assertEqual(windows_log.sync(session), 4)
            events = read_jsonl(session.path("out", "events.jsonl"))
            self.assertEqual([e["type"] for e in events], ["world", "screen", "log_error"])
            self.assertEqual(events[2]["line"], "SCRIPT ERROR ON OPCODE 1")
            with open(session.path("out", "state.json")) as f:
                self.assertEqual(json.load(f)["version"], "TestModule (W)")


class LauncherAndRegistryTest(unittest.TestCase):
    def test_a_launcher_that_will_not_come_forward_is_clicked(self):
        class Ch(FakeChannel):
            def request(self, op, timeout=None, **fields):
                if op == "windows":
                    self.calls.append({"op": op})
                    if any(c["op"] == "button" for c in self.calls):
                        return {"ok": True, "windows": [{"hwnd": 2, "title": "Game", "client": [0, 0, 1920, 1080]}]}
                    return {"ok": True, "windows": [{"hwnd": 1, "title": "Game", "client": [650, 350, 620, 385]}]}
                return super().request(op, timeout, **fields)
        ch = Ch(focus_ok=False, client=[650, 350, 620, 385])
        notes = []
        win = {"min_width": 1024, "launcher": {"keys": ["Return"], "click": [0.215, 0.345], "attempts": 3}}
        got = windows_session.await_window(ch, 1, None, win, "^Game", 20, True, notes.append)
        self.assertEqual(got["hwnd"], 2)
        self.assertIn({"op": "move", "x": 650 + 133, "y": 350 + 133}, ch.calls)
        self.assertEqual([c["up"] for c in ch.calls if c["op"] == "button"], [False, True])
        self.assertFalse([c for c in ch.calls if c["op"] == "key"])
        self.assertIn("clicked the launcher", notes[0])

    def test_restore_puts_back_or_deletes_and_keeps_what_failed(self):
        class Ch(FakeChannel):
            def request(self, op, timeout=None, **fields):
                self.calls.append(dict(fields, op=op))
                if fields.get("name") == "broken":
                    raise DriveError("regset: the helper is gone")
                return {"ok": True}
        ch = Ch()
        entries = [{"key": "HKCU:\\S", "name": "a", "existed": True, "value": "Old", "set": "New"},
                   {"key": "HKCU:\\S", "name": "b", "existed": False, "value": None, "set": "New"},
                   {"key": "HKCU:\\S", "name": "broken", "existed": True, "value": "x", "set": "y"}]
        left = windows_session._restore_registry(ch, entries)
        self.assertEqual(left, [entries[2]])
        self.assertEqual([(c["op"], c["name"]) for c in ch.calls], [("regset", "broken"), ("regdel", "b"), ("regset", "a")])


if __name__ == "__main__":
    unittest.main()
