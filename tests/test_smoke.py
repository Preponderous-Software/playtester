"""pt smoke stops only a session it started (no display needed: the harness is mocked)."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import tests.helpers  # noqa: F401  (puts src on sys.path)
from playtester.harness import smoke
from playtester.harness.session import HarnessError, Session


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"PT_ROOT": self.tmp.name, "PT_SESSION": "agent-s01"})
        self.env.start()
        self.commands = []
        self.stopped = []

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def smoke(self, *args, start_fails=False, already_running=False, event=True):
        def run_command(session, cmd, cmd_args):
            self.commands.append((session.name, cmd))
            if cmd == "start" and start_fails:
                raise HarnessError("session %s is already running (pt stop first)" % session.name)
            return 0

        def stop(session):
            self.stopped.append(session.name)

        events = [{"type": "objective_completed", "title": "Gather wood"}] if event else []
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(smoke, "run_session_command", run_command), \
                mock.patch.object(Session, "stop", stop), \
                mock.patch.object(Session, "game_alive", lambda s: already_running), \
                mock.patch.object(smoke.probe, "read_events", lambda s: events), \
                redirect_stdout(out), redirect_stderr(err):
            code = smoke.main(["--profile", "demo"] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_it_uses_its_own_session_not_pt_session(self):
        code, out, _ = self.smoke()
        self.assertEqual(code, 0, out)
        names = {name for name, _ in self.commands}
        self.assertEqual(names, {"smoke-%d" % os.getpid()})
        self.assertEqual(self.stopped, ["smoke-%d" % os.getpid()])

    def test_it_stops_what_it_started_even_on_failure(self):
        code, _, err = self.smoke(event=False)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", err)
        self.assertEqual(self.stopped, ["smoke-%d" % os.getpid()])

    def test_a_failed_start_stops_nothing(self):
        code, _, err = self.smoke("--session", "agent-s01", start_fails=True)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", err)
        self.assertEqual(self.stopped, [])

    def test_a_running_session_of_the_same_name_is_left_alone(self):
        code, _, err = self.smoke("--session", "agent-s01", already_running=True)
        self.assertEqual(code, 1)
        self.assertIn("already running", err)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.stopped, [])

    def test_keep_leaves_the_session_running(self):
        code, out, _ = self.smoke("--keep")
        self.assertEqual(code, 0)
        self.assertEqual(self.stopped, [])
        self.assertIn("pt stop", out)


if __name__ == "__main__":
    unittest.main()
