"""End to end on a real virtual display, with the bundled demo game.

Skipped where Xvfb, xdotool or ImageMagick's import is missing. CI installs
them, so there these run: start and stop, input, screenshots, the closed-loop
face and walkto, the scripted smoke, and three sessions at once.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from tests.helpers import SRC
from playtester.harness.session import Session, pid_alive

TOOLS = all(shutil.which(t) for t in ("Xvfb", "xdotool", "import"))


def pt(root, session, *args, timeout=120):
    env = dict(os.environ, PT_ROOT=root, PT_SESSION=session, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "playtester"] + list(args), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout)


@unittest.skipUnless(TOOLS, "needs Xvfb, xdotool and ImageMagick")
class LiveTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pt-live-")
        self.sessions = []

    def tearDown(self):
        for name in self.sessions:
            pt(self.root, name, "stop")
        shutil.rmtree(self.root, ignore_errors=True)

    def start(self, name, *args):
        self.sessions.append(name)
        r = pt(self.root, name, "start", "--profile", "demo", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_one_session_from_title_to_objective(self):
        info = self.start("s1", "--seed", "7")
        self.assertEqual(info["version"], "1.0.0")
        r = pt(self.root, "s1", "shot", "title")
        self.assertTrue(os.path.isfile(r.stdout.strip()), r.stderr)
        self.assertEqual(pt(self.root, "s1", "key", "space").returncode, 0)
        self.assertEqual(pt(self.root, "s1", "await", "WORLD", "10").returncode, 0)
        r = pt(self.root, "s1", "face", "90")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLessEqual(abs(json.loads(r.stdout)["offBy"]), 6)
        for _ in range(3):
            r = pt(self.root, "s1", "walkto", "tree", "30")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            pt(self.root, "s1", "key", "e")
        deadline = time.time() + 5
        while time.time() < deadline and "objective_completed" not in pt(self.root, "s1", "events", "50").stdout:
            time.sleep(0.2)
        self.assertIn('"title":"Gather wood"', pt(self.root, "s1", "events", "50").stdout)
        self.assertEqual(pt(self.root, "s1", "probe-check").returncode, 0)
        note = pt(self.root, "s1", "note", "--shot", "done", "all three trees chopped")
        self.assertEqual(json.loads(note.stdout)["screenshot"], "shots/done.png")
        session = Session("s1", self.root)
        game, xvfb = session._pid("game"), session._pid("xvfb")
        self.assertEqual(pt(self.root, "s1", "stop").returncode, 0)
        self.assertFalse(pid_alive(game) or pid_alive(xvfb))

    def test_three_sessions_at_once_never_share_a_display_or_input(self):
        names = ["p1", "p2", "p3"]
        procs = [subprocess.Popen([sys.executable, "-m", "playtester", "start", "--profile", "demo", "--seed", str(i)],
                                  env=dict(os.environ, PT_ROOT=self.root, PT_SESSION=n, PYTHONPATH=SRC),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                 for i, n in enumerate(names)]
        self.sessions.extend(names)
        infos = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err)
            infos.append(json.loads(out))
        self.assertEqual(len({i["display"] for i in infos}), 3)
        pt(self.root, "p2", "key", "space")  # only p2 leaves its title screen
        time.sleep(1.5)
        screens = {n: json.loads(pt(self.root, n, "state").stdout)["screen"] for n in names}
        self.assertEqual(screens, {"p1": "TITLE", "p2": "WORLD", "p3": "TITLE"})

    def test_a_game_that_cannot_start_fails_loudly_and_cleans_up(self):
        self.sessions.append("bad")
        r = pt(self.root, "bad", "start", "--profile", "demo", "--", "--no-such-flag")
        self.assertEqual(r.returncode, 1)
        self.assertIn("did not come up", r.stderr)
        self.assertIn("unknown argument --no-such-flag", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "bad", "xvfb.pid")))

    def test_the_demo_smoke(self):
        env = dict(os.environ, PT_ROOT=os.path.join(self.root, "smoke"), PYTHONPATH=SRC)
        r = subprocess.run([sys.executable, "-m", "playtester", "smoke", "--profile", "demo"], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS", r.stdout)


if __name__ == "__main__":
    unittest.main()
