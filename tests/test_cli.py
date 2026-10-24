"""pt's argument handling and the commands that need no display."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tests.helpers import FIXTURE_RUN
from playtester.harness import cli
from playtester.harness.session import HarnessError, Session


def run(*argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    old = dict(os.environ)
    os.environ.update(env or {})
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
    finally:
        os.environ.clear()
        os.environ.update(old)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_help_and_profiles(self):
        code, out, _ = run("help")
        self.assertEqual(code, 0)
        self.assertIn("walkto KIND", out)
        code, out, _ = run("profiles")
        self.assertEqual(code, 0)
        self.assertIn("kindling", out)

    def test_session_names_are_checked(self):
        with self.assertRaises(HarnessError):
            Session("")
        with self.assertRaises(HarnessError):
            Session("../escape")
        self.assertTrue(Session("s01", "/tmp/r").dir.endswith("/tmp/r/s01"))

    def test_an_unknown_command_fails(self):
        code, _, err = run("fly")
        self.assertEqual(code, 1)
        self.assertIn("unknown command", err)

    def test_start_options_and_game_arguments_are_told_apart(self):
        opts = cli.parse_start(["--profile", "demo", "--seed", "42", "--season", "autumn", "--no-probe", "--", "--seed", "x"])
        self.assertEqual((opts["profile"], opts["seed"], opts["probe"]), ("demo", "42", False))
        self.assertEqual(opts["extra"], ["--season", "autumn", "--seed", "x"])

    def test_input_without_a_running_game_explains(self):
        with tempfile.TemporaryDirectory() as root:
            code, _, err = run("key", "e", env={"PT_ROOT": root, "PT_SESSION": "s01"})
            self.assertEqual(code, 1)
            self.assertIn("not running", err)
            with open(os.path.join(root, "s01", "actions.jsonl")) as f:
                self.assertEqual(json.loads(f.readline())["cmd"], "key")

    def test_report_and_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "run")
            shutil.copytree(FIXTURE_RUN, run_dir)
            code, out, _ = run("report", env={"PT_ROOT": run_dir, "PT_SESSION": "s01"})
            self.assertEqual(code, 0, out)
            self.assertIn("ok:", out)
            code, out, _ = run("aggregate", run_dir)
            self.assertEqual(code, 0)
            self.assertIn("3 sessions", out)
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "summary.md")))

    def test_report_checks_the_sessions_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "run")
            shutil.copytree(FIXTURE_RUN, run_dir)
            with open(os.path.join(run_dir, "s01", "profile.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "x", "questions": ["What was it about?"]}, f)
            env = {"PT_ROOT": run_dir, "PT_SESSION": "s01"}
            code, out, _ = run("report", env=env)
            self.assertEqual(code, 1)
            self.assertIn("no answer to question 1: What was it about?", out)
            path = os.path.join(run_dir, "s01", "report.json")
            with open(path, encoding="utf-8") as f:
                report = json.load(f)
            report["answers"] = [{"question": "What was it about?", "answer": "Nations."}]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f)
            code, out, _ = run("report", env=env)
            self.assertEqual(code, 0, out)

    def test_prompt_from_a_profile_goal(self):
        code, out, _ = run("prompt", "--profile", "beyond-nations", "--goal-index", "3", "--session", "s03",
                           "--run-dir", "/tmp/run", "--game-dir", "/games/bn")
        self.assertEqual(code, 0)
        self.assertIn("Survive the first winter", out)
        self.assertIn("--seed 103 --season autumn", out)
        self.assertIn("60 minutes", out)


if __name__ == "__main__":
    unittest.main()
