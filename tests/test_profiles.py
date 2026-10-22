"""Bundled profiles, launch plans, the agent prompt and the installable skill."""

import os
import re
import sys
import tempfile
import unittest

from tests.helpers import ROOT  # noqa: F401
from playtester.agents.prompt import fill
from playtester.harness import cli
from playtester.harness import profile as profiles

BUNDLED = ("beyond-nations", "demo", "kindling")


class ProfileTest(unittest.TestCase):
    def test_every_bundled_profile_loads_and_has_its_notes(self):
        self.assertEqual(tuple(profiles.available()), BUNDLED)
        for name in BUNDLED:
            p = profiles.load(name)
            self.assertTrue(profiles.agent_notes(p), name)
            self.assertTrue(p.get("smoke"), name)
            self.assertTrue(p["goals"], name)
            if p.get("movement"):
                self.assertTrue(p.get("probe"), "%s: face and walkto need a probe" % name)

    def test_an_unknown_profile_lists_the_bundled_ones(self):
        with self.assertRaises(profiles.ProfileError) as e:
            profiles.load("nope")
        self.assertIn("beyond-nations", str(e.exception))

    def test_a_bad_profile_file_is_refused_with_reasons(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"name": "Bad Name", "title": "x", "description": "y", "launch": {}, "window": {"title_regex": "x"}}')
        try:
            with self.assertRaises(profiles.ProfileError) as e:
                profiles.load(f.name)
            self.assertIn("$.name", str(e.exception))
            self.assertIn("missing required 'command'", str(e.exception))
        finally:
            os.unlink(f.name)

    def test_the_launch_plan_fills_placeholders_seed_and_probe(self):
        p = profiles.load("beyond-nations")
        plan = profiles.launch_plan(p, "/games/bn", "/runs/r/s01", 960, 540, "42", ["--season", "autumn"], True)
        self.assertEqual(plan["command"], [
            "/games/bn/src/BeyondNations.Desktop/bin/Release/net8.0/BeyondNations.Desktop",
            "--width", "960", "--height", "540", "--no-usage-reporting",
            "--seed", "42", "--playtest-out", "/runs/r/s01/out", "--season", "autumn"])
        self.assertEqual(plan["env"]["XDG_DATA_HOME"], "/runs/r/s01/data")
        self.assertEqual(plan["cwd"], "/games/bn/src/BeyondNations.Desktop/bin/Release/net8.0")
        plain = profiles.launch_plan(p, "/g", "/s", 640, 360, None, [], False)
        self.assertNotIn("--playtest-out", plain["command"])
        self.assertNotIn("--seed", plain["command"])

    def test_the_demo_runs_on_this_interpreter(self):
        plan = profiles.launch_plan(profiles.load("demo"), "/g", "/s", 640, 360, "7", [], True)
        self.assertEqual(plan["command"][:3], [sys.executable, "-m", "playtester.demo"])


class PromptTest(unittest.TestCase):
    def test_every_placeholder_is_filled_for_every_profile(self):
        for name in BUNDLED:
            text = fill(profiles.load(name), "Do the thing.", "s01", "/tmp/run", "101", 30, "/games/x")
            self.assertNotRegex(text, r"\{\{[A-Z_]+\}\}", name)
            self.assertIn("PT_ROOT=/tmp/run PT_SESSION=s01", text)
            self.assertIn("**Your goal:** Do the thing.", text)
            self.assertIn("Keep every file you create inside your session directory", text)
            self.assertIn('"seed": 101', text)

    def test_a_probe_game_gets_the_probe_commands_and_a_screenshot_only_game_does_not(self):
        bn = fill(profiles.load("beyond-nations"), "g", "s01", "/r", "1")
        self.assertIn("`pt walkto KIND [60]`", bn)
        self.assertIn("ticks / 50 = seconds", bn)
        self.assertIn("F1-F6", bn)
        plain = dict(profiles.load("demo"), probe=None, movement=None)
        text = fill(plain, "g", "s01", "/r", None)
        self.assertNotIn("`pt walkto KIND", text)
        self.assertIn("This game has no probe", text)
        self.assertIn('"seed": null', text)

    def test_text_seeds_are_quoted(self):
        self.assertIn('"seed": "Ironvale"', fill(profiles.load("beyond-nations"), "g", "s10", "/r", "Ironvale"))


class SkillTest(unittest.TestCase):
    def test_install_skill_writes_it_with_the_profile_filled(self):
        with tempfile.TemporaryDirectory() as repo:
            self.assertEqual(cli.main(["install-skill", repo, "--profile", "kindling"]), 0)
            path = os.path.join(repo, ".claude", "skills", "playtest", "SKILL.md")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.startswith("---\nname: playtest\n"))
            self.assertNotIn("{{PROFILE}}", text)
            self.assertIn("PROFILE=kindling", text)


if __name__ == "__main__":
    unittest.main()
