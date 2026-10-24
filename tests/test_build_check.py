"""pt start's build check: does the running build match the checkout's commit? (no display needed)"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest

import tests.helpers  # noqa: F401  (puts src on sys.path)
from playtester.harness import profile as profiles
from playtester.harness.session import build_check

GIT = shutil.which("git") is not None


def git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
                   + list(args), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def touch(path, when):
    with open(path, "a"):
        pass
    os.utime(path, (when, when))


@unittest.skipUnless(GIT, "needs git")
class BuildCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        self.source = os.path.join(self.repo, "game.c")
        with open(self.source, "w") as f:
            f.write("int main(void) { return 0; }\n")
        git(self.repo, "add", "game.c")
        git(self.repo, "commit", "-q", "-m", "first")
        self.committed = int(subprocess.run(["git", "-C", self.repo, "log", "-1", "--format=%ct"],
                                            stdout=subprocess.PIPE, universal_newlines=True).stdout)
        os.utime(self.source, (self.committed - 60, self.committed - 60))
        self.binary = os.path.join(self.repo, "game")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_build_after_the_commit_is_current(self):
        touch(self.binary, self.committed + 60)
        check = build_check(self.repo, self.binary)
        self.assertEqual(check["warnings"], [])
        self.assertIs(check["dirty"], False)
        self.assertEqual(check["builtAtMs"], (self.committed + 60) * 1000)

    def test_a_build_before_the_commit_is_stale(self):
        touch(self.binary, self.committed - 3600)
        check = build_check(self.repo, self.binary)
        self.assertEqual(len(check["warnings"]), 1)
        self.assertIn("before the checkout's HEAD commit", check["warnings"][0])

    def test_an_uncommitted_edit_after_the_build_is_stale(self):
        touch(self.binary, self.committed + 60)
        with open(self.source, "a") as f:
            f.write("/* edited */\n")
        os.utime(self.source, (self.committed + 120, self.committed + 120))
        check = build_check(self.repo, self.binary)
        self.assertIs(check["dirty"], True)
        self.assertEqual(len(check["warnings"]), 1)
        self.assertIn("uncommitted edits to game.c", check["warnings"][0])

    def test_an_uncommitted_edit_before_the_build_is_dirty_but_built(self):
        with open(self.source, "a") as f:
            f.write("/* edited */\n")
        os.utime(self.source, (self.committed + 30, self.committed + 30))
        touch(self.binary, self.committed + 60)
        check = build_check(self.repo, self.binary)
        self.assertIs(check["dirty"], True)
        self.assertEqual(check["warnings"], [])

    def test_untracked_files_do_not_make_the_checkout_dirty(self):
        touch(self.binary, self.committed + 60)
        touch(os.path.join(self.repo, "notes.txt"), time.time())
        self.assertIs(build_check(self.repo, self.binary)["dirty"], False)

    def test_no_artifact_records_no_build_time(self):
        check = build_check(self.repo, None)
        self.assertIsNone(check["builtAtMs"])
        self.assertEqual(check["warnings"], [])
        self.assertIsNone(build_check(self.repo, os.path.join(self.repo, "missing"))["builtAtMs"])


class NotACheckoutTest(unittest.TestCase):
    def test_outside_git_nothing_is_claimed(self):
        with tempfile.TemporaryDirectory() as d:
            binary = os.path.join(d, "game")
            touch(binary, 1000)
            check = build_check(d, binary)
            self.assertIsNone(check["dirty"])
            self.assertEqual(check["warnings"], [])
            self.assertEqual(check["builtAtMs"], 1000000)


class ArtifactTest(unittest.TestCase):
    def test_a_profile_can_name_its_artifact(self):
        plan = profiles.launch_plan(profiles.load("beyond-nations"), "/games/bn", "/s", 960, 540, None, [], False)
        self.assertEqual(plan["artifact"], "/games/bn/src/BeyondNations.Desktop/bin/Release/net8.0/BeyondNations.Desktop.dll")

    def test_the_executable_in_the_checkout_is_the_default_artifact(self):
        plan = profiles.launch_plan(profiles.load("atman"), "/games/atman", "/s", 1280, 720, None, [], False)
        self.assertEqual(plan["artifact"], "/games/atman/build/atman")

    def test_an_interpreter_outside_the_checkout_is_no_artifact(self):
        plan = profiles.launch_plan(profiles.load("demo"), "/g", "/s", 640, 360, None, [], False)
        self.assertIsNone(plan["artifact"])


if __name__ == "__main__":
    unittest.main()
