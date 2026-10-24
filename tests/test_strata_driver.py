"""The Strata driver: key table, schema, and whole sessions against a stand-in game.

The live tests run ``pt`` against tests/fake_strata_game.py, which speaks the
drive protocol as a Strata engine does but draws with no GL, so they need
neither a game build nor an X server.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import HERE, SRC
from playtester.harness import inputs, strata_keys
from playtester.harness import profile as profiles
from playtester.harness.session import pid_alive

FAKE_GAME = os.path.join(HERE, "fake_strata_game.py")


def pt(root, session, *args, timeout=60):
    env = dict(os.environ, PT_ROOT=root, PT_SESSION=session, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "playtester"] + list(args), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout)


def fake_profile(directory, probe=True):
    data = {
        "name": "fake-strata",
        "title": "Fake Strata game",
        "description": "a stand-in that speaks the drive protocol",
        "driver": "strata",
        "launch": {"command": ["{python}", FAKE_GAME], "start_timeout_sec": 20},
        "window": {"width": 64, "height": 64},
    }
    if probe:
        data["probe"] = {"flag": "--playtest-out", "ticks_per_second": 60}
    path = os.path.join(directory, "fake-strata.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


class KeyTableTest(unittest.TestCase):
    def test_names_map_to_usb_hid_usage_ids(self):
        self.assertEqual(strata_keys.scancode("a"), 4)
        self.assertEqual(strata_keys.scancode("W"), 26)
        self.assertEqual(strata_keys.scancode("1"), 30)
        self.assertEqual(strata_keys.scancode("0"), 39)
        self.assertEqual(strata_keys.scancode("F1"), 58)
        self.assertEqual(strata_keys.scancode("F12"), 69)
        self.assertEqual(strata_keys.scancode("Right"), 79)
        self.assertEqual(strata_keys.scancode("Up"), 82)
        self.assertEqual(strata_keys.scancode("space"), 44)
        self.assertEqual(strata_keys.scancode("Escape"), 41)
        self.assertEqual(strata_keys.scancode("Esc"), 41)
        self.assertEqual(strata_keys.scancode("Return"), 40)
        self.assertEqual(strata_keys.scancode("Shift_L"), 225)

    def test_combos_carry_the_modifiers_held(self):
        self.assertEqual(strata_keys.combo_scancodes(["Shift_L", "w"]),
                         [(225, strata_keys.MOD_LSHIFT), (26, strata_keys.MOD_LSHIFT)])
        self.assertEqual(strata_keys.combo_scancodes(["Control_L", "Shift_L", "s"])[-1],
                         (22, strata_keys.MOD_LCTRL | strata_keys.MOD_LSHIFT))

    def test_an_unknown_key_is_an_error(self):
        with self.assertRaises(strata_keys.UnknownKey):
            strata_keys.scancode("Hyper_Q")

    def test_text_is_chunked_on_character_boundaries(self):
        text = "café " * 10
        chunks = inputs.utf8_chunks(text)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(c.encode("utf-8")) <= 31 for c in chunks))


class SchemaTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pt-schema-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, data):
        path = os.path.join(self.dir, "p.json")
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_a_strata_profile_needs_no_window_title(self):
        p = profiles.load(fake_profile(self.dir))
        self.assertEqual(p["driver"], "strata")

    def test_an_x11_profile_still_needs_its_window_title(self):
        base = {"name": "x", "title": "x", "description": "x", "launch": {"command": ["x"]}, "window": {}}
        with self.assertRaises(profiles.ProfileError) as e:
            profiles.load(self.write(base))
        self.assertIn("title_regex", str(e.exception))
        self.assertEqual(profiles.load(self.write(dict(base, window={"title_regex": "x"})))["driver"], "x11")

    def test_an_unknown_driver_is_refused(self):
        with self.assertRaises(profiles.ProfileError):
            profiles.load(self.write({"name": "x", "title": "x", "description": "x", "driver": "wayland",
                                      "launch": {"command": ["x"]}, "window": {}}))


class FakeGameSessionTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pt-strata-")
        self.profile = fake_profile(self.root)
        self.sessions = []

    def tearDown(self):
        for name in self.sessions:
            pt(self.root, name, "stop")
        shutil.rmtree(self.root, ignore_errors=True)

    def start(self, name, *args):
        self.sessions.append(name)
        r = pt(self.root, name, "start", "--profile", self.profile, "--game-dir", self.root, *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def ok(self, name, *args):
        r = pt(self.root, name, *args)
        self.assertEqual(r.returncode, 0, "pt %s: %s%s" % (" ".join(args), r.stdout, r.stderr))
        return r.stdout

    def state(self, name):
        return json.loads(self.ok(name, "state", "--full"))

    def stepped_run(self, name):
        info = self.start(name, "--clock", "stepped", "--step", "0.05")
        self.assertEqual(info["driver"], "strata")
        self.assertEqual(info["clock"], "stepped")
        self.assertEqual(info["abi"], "1.9")
        self.assertNotIn("display", info)
        before = self.state(name)["x"]
        self.ok(name, "hold", "Right", "1")       # 20 frames of 0.05 s
        self.assertAlmostEqual(self.state(name)["x"] - before, 60.0, places=3)
        self.ok(name, "key", "space")
        out = json.loads(self.ok(name, "step", "10"))
        self.assertEqual(out["frames_run"], 10)
        self.ok(name, "wait", "0.5")              # 10 more frames
        path = self.ok(name, "shot", "end").strip()
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest(), self.state(name)["tick"]

    def test_two_stepped_runs_give_the_same_frames(self):
        first, ticks1 = self.stepped_run("a")
        second, ticks2 = self.stepped_run("b")
        self.assertEqual(first, second)
        self.assertEqual(ticks1, ticks2)
        with open(os.path.join(self.root, "a", "drive.jsonl")) as f:
            lines = [json.loads(line) for line in f]
        self.assertTrue(any('"scancode": 79' in e["line"] or '"scancode":79' in e["line"] for e in lines
                            if e["dir"] == "to_game"))

    def test_status_step_and_a_clean_stop(self):
        self.start("s", "--clock", "stepped")
        status = json.loads(self.ok("s", "status"))
        self.assertTrue(status["running"])
        self.assertEqual(status["driver"], "strata")
        self.assertEqual(status["clock"], "stepped")
        self.assertIsNone(status["xvfbPid"])
        game = status["gamePid"]
        self.ok("s", "stop")
        self.assertFalse(pid_alive(game))
        with open(os.path.join(self.root, "s", "game.log")) as f:
            self.assertIn("fake game: quit", f.read())  # it was asked to quit, not killed
        self.assertNotEqual(pt(self.root, "s", "key", "space").returncode, 0)

    def test_free_clock_plays_in_real_time_and_refuses_step(self):
        self.start("f")
        before = self.state("f")["x"]
        self.ok("f", "hold", "Right", "0.5")
        self.ok("f", "wait", "0.2")
        self.assertGreater(self.state("f")["x"], before + 5)
        r = pt(self.root, "f", "step", "5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("step", r.stderr)

    def test_an_unknown_key_name_fails_loudly(self):
        self.start("k", "--clock", "stepped")
        r = pt(self.root, "k", "key", "Hyper_Q")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no scancode", r.stderr)

    def test_a_stepped_clock_needs_the_strata_driver(self):
        self.sessions.append("x")
        r = pt(self.root, "x", "start", "--profile", "demo", "--clock", "stepped")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("strata", r.stderr)


if __name__ == "__main__":
    unittest.main()
