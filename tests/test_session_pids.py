"""Pid files: a session signals only the processes it started (no display needed)."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

import tests.helpers  # noqa: F401  (puts src on sys.path)
from playtester.harness.session import (Session, parse_pid_file, pid_alive, pid_file_text, proc_start_time,
                                        same_process)

LINUX = os.path.isdir("/proc/self")


@unittest.skipUnless(LINUX, "needs /proc")
class PidFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = Session("s01", self.tmp.name)
        os.makedirs(self.session.dir)
        # a harmless process of our own, in its own process group like a game
        self.child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                      start_new_session=True)

    def tearDown(self):
        if self.child.poll() is None:
            self.child.kill()
        self.child.wait()
        self.tmp.cleanup()

    def write(self, name, text, command=None):
        with open(self.session.path(name + ".pid"), "w") as f:
            f.write(text)
        if command is not None:
            with open(self.session.path("session.json"), "w") as f:
                json.dump({"command": command}, f)

    def test_pid_files_record_the_start_time(self):
        text = pid_file_text(self.child.pid)
        pid, start = parse_pid_file(text)
        self.assertEqual(pid, self.child.pid)
        self.assertEqual(start, proc_start_time(self.child.pid))
        self.assertTrue(start.isdigit())
        self.assertEqual(parse_pid_file("123"), (123, None))
        self.assertEqual(parse_pid_file("junk"), (None, None))
        self.assertEqual(parse_pid_file(""), (None, None))

    def test_a_matching_start_time_is_the_same_process(self):
        self.write("game", pid_file_text(self.child.pid))
        self.assertEqual(self.session._pid("game"), self.child.pid)
        self.assertTrue(self.session.game_alive())

    def test_a_different_start_time_is_another_process(self):
        start = int(proc_start_time(self.child.pid))
        self.write("game", "%d %d" % (self.child.pid, start + 1))
        self.assertIsNone(self.session._pid("game"))
        self.assertFalse(self.session.game_alive())
        self.assertFalse(same_process(self.child.pid, str(start + 1), []))

    def test_stop_leaves_a_reused_pid_alone(self):
        start = int(proc_start_time(self.child.pid))
        self.write("game", "%d %d" % (self.child.pid, start + 1))
        self.session.stop()
        time.sleep(0.2)
        self.assertIsNone(self.child.poll(), "stop signalled a process the session did not start")
        self.assertFalse(os.path.exists(self.session.path("game.pid")))

    def test_stop_ends_the_process_it_started(self):
        self.write("game", pid_file_text(self.child.pid))
        self.session.stop()
        self.child.wait(timeout=10)
        self.assertFalse(pid_alive(self.child.pid))
        self.assertFalse(os.path.exists(self.session.path("game.pid")))

    def test_an_old_pid_file_is_trusted_only_for_the_expected_command(self):
        self.write("game", str(self.child.pid), command=["/no/such/game-binary"])
        self.assertIsNone(self.session._pid("game"))
        self.session.stop()
        time.sleep(0.2)
        self.assertIsNone(self.child.poll())

        self.write("game", str(self.child.pid), command=[sys.executable, "-m", "game"])
        self.assertEqual(self.session._pid("game"), self.child.pid)

    def test_an_old_xvfb_pid_file_must_name_xvfb(self):
        self.write("xvfb", str(self.child.pid))
        self.assertIsNone(self.session._pid("xvfb"))
        self.session.stop()
        time.sleep(0.2)
        self.assertIsNone(self.child.poll())

    def test_a_dead_pid_is_not_running(self):
        self.child.kill()
        self.child.wait()
        self.write("game", "%d 1" % self.child.pid)
        self.assertIsNone(self.session._pid("game"))
        self.session.stop()  # nothing to signal; just tidies up
        self.assertFalse(os.path.exists(self.session.path("game.pid")))


if __name__ == "__main__":
    unittest.main()
