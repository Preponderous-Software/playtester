"""Bundled profiles, launch plans, the agent prompt and the installable skill."""

import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

from tests.helpers import ROOT  # noqa: F401
from playtester.agents.prompt import fill
from playtester.harness import cli
from playtester.harness import profile as profiles

BUNDLED = ("atman", "atman-strata", "beyond-nations", "demo", "kindling", "kindling-strata", "orrery-strata", "sisyphus-strata",
           "steading-strata")


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

    def test_atman_is_screenshots_only_at_its_own_size(self):
        p = profiles.load("atman")
        self.assertIsNone(p["probe"])
        self.assertIsNone(p["movement"])
        self.assertEqual((p["window"]["width"], p["window"]["height"]), (1280, 720))
        plan = profiles.launch_plan(p, "/games/atman", "/runs/r/s01", 1280, 720, "3", [], True)
        self.assertEqual(plan["command"], [
            "/games/atman/build/atman", "--width", "1280", "--height", "720",
            "--slot", "/runs/r/s01/data", "--seed", "3"])
        self.assertEqual(len(p["questions"]), 2)
        self.assertIn("the rope and the snake, and the clay and the pots", p["questions"][0])
        self.assertIn("preachy, confusing, or inaccurate", p["questions"][1])

    def test_the_demo_runs_on_this_interpreter(self):
        plan = profiles.launch_plan(profiles.load("demo"), "/g", "/s", 640, 360, "7", [], True)
        self.assertEqual(plan["command"][:3], [sys.executable, "-m", "playtester.demo"])


def minimal_profile(**extra):
    """The smallest profile the schema accepts, with ``extra`` top-level fields added."""
    data = {"name": "tiny", "title": "Tiny", "description": "a test game",
            "launch": {"command": ["{game_dir}/tiny"]}, "window": {"title_regex": "^Tiny$"}}
    data.update(extra)
    return data


class ProfileFileTest(unittest.TestCase):
    """``load`` and ``agent_notes`` on profile files written to a temporary directory."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, text):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_no_name_is_refused_and_lists_the_bundled_profiles(self):
        with self.assertRaises(profiles.ProfileError) as e:
            profiles.load("")
        self.assertIn("no profile given", str(e.exception))
        self.assertIn("demo", str(e.exception))

    def test_a_file_that_is_not_json_is_refused(self):
        path = self.write("broken.json", '{"name": ')
        with self.assertRaises(profiles.ProfileError) as e:
            profiles.load(path)
        self.assertIn(path, str(e.exception))
        self.assertIn("is not valid JSON", str(e.exception))

    def test_a_profile_by_path_has_its_defaults_merged_in_depth(self):
        data = minimal_profile(launch={"command": ["x"], "args": ["--fast"], "env": {"A": "1"}})
        data["window"]["width"] = 300
        path = self.write("tiny.json", json.dumps(data))
        p = profiles.load(path)
        self.assertEqual(p["_source"], os.path.abspath(path))
        self.assertEqual(p["driver"], "x11")
        self.assertEqual(p["window"], {"title_regex": "^Tiny$", "width": 300, "height": 540})
        self.assertEqual(p["launch"], {"command": ["x"], "args": ["--fast"], "env": {"A": "1"},
                                       "env_defaults": {}, "seed_args": [], "start_timeout_sec": 90})
        self.assertIsNone(p["probe"])
        self.assertEqual((p["goals"], p["questions"], p["cheats"]), ([], [], ""))

    def test_loading_does_not_change_the_defaults(self):
        path = self.write("tiny.json", json.dumps(minimal_profile()))
        p = profiles.load(path)
        p["launch"]["env"]["CHANGED"] = "1"
        p["goals"].append("changed")
        self.assertEqual(profiles.DEFAULTS["launch"]["env"], {})
        self.assertEqual(profiles.DEFAULTS["goals"], [])
        self.assertEqual(profiles.load(path)["launch"]["env"], {})

    def test_agent_notes_are_read_beside_the_profile_and_stripped(self):
        self.write("tiny.md", "\n  Press W.  \n\n")
        path = self.write("tiny.json", json.dumps(minimal_profile(agent_notes="tiny.md")))
        self.assertEqual(profiles.agent_notes(profiles.load(path)), "Press W.")

    def test_agent_notes_may_be_an_absolute_path(self):
        notes = self.write("elsewhere.md", "Absolute.\n")
        p = {"agent_notes": notes, "_source": "/nowhere/tiny.json"}
        self.assertEqual(profiles.agent_notes(p), "Absolute.")

    def test_a_profile_without_agent_notes_has_none(self):
        self.assertEqual(profiles.agent_notes({"_source": "/nowhere/tiny.json"}), "")
        self.assertEqual(profiles.agent_notes({"agent_notes": "", "_source": "/nowhere/tiny.json"}), "")


class ExpandTest(unittest.TestCase):
    """Placeholder expansion in launch strings."""

    def test_placeholders_are_filled_in_strings_lists_and_dicts(self):
        value = {"a": ["{game_dir}/bin", "-w", "{width}"], "b": {"c": "{session_dir}/data"}}
        self.assertEqual(profiles.expand(value, {"game_dir": "/g", "width": 640, "session_dir": "/s"}),
                         {"a": ["/g/bin", "-w", "640"], "b": {"c": "/s/data"}})

    def test_unknown_names_are_left_alone(self):
        self.assertEqual(profiles.expand("{seed}-{width}-{Width}", {"width": 1}), "{seed}-1-{Width}")

    def test_values_that_are_not_text_are_returned_unchanged(self):
        for value in (3, 1.5, None, True):
            self.assertIs(profiles.expand(value, {"width": 1}), value)

    def test_a_leading_tilde_is_the_home_directory_and_a_later_one_is_not(self):
        with mock.patch.dict(os.environ, {"HOME": "/home/tester"}):
            self.assertEqual(profiles.expand("~/games/{width}", {"width": 7}), "/home/tester/games/7")
            self.assertEqual(profiles.expand("a~/b", {}), "a~/b")


class LaunchPlanTest(unittest.TestCase):
    """``launch_plan`` on hand-built profiles: working directory and environment."""

    def plan(self, launch, **kwargs):
        p = dict(profiles.DEFAULTS, launch=dict(profiles.DEFAULTS["launch"], **launch))
        args = dict(game_dir="/g", session_dir="/s", width=640, height=360, seed=None,
                    extra_args=[], use_probe=False)
        args.update(kwargs)
        return profiles.launch_plan(p, **args)

    def test_the_working_directory_defaults_to_the_session(self):
        self.assertEqual(self.plan({"command": ["/g/x"]})["cwd"], "/s")
        self.assertEqual(self.plan({"command": ["/g/x"], "cwd": "{game_dir}/run"})["cwd"], "/g/run")

    def test_env_values_are_expanded_text(self):
        plan = self.plan({"command": ["/g/x"], "env": {"SAVE": "{data_dir}", "OUT": "{probe_dir}"}})
        self.assertEqual(plan["env"], {"SAVE": "/s/data", "OUT": "/s/out"})

    def test_an_env_default_is_set_only_when_unset_and_an_existing_path(self):
        with tempfile.TemporaryDirectory() as d:
            launch = {"command": ["/g/x"], "env_defaults": {
                "PT_TEST_EXISTS": d, "PT_TEST_MISSING": os.path.join(d, "missing"), "PT_TEST_ALREADY_SET": d}}
            with mock.patch.dict(os.environ, {"PT_TEST_ALREADY_SET": "mine"}):
                os.environ.pop("PT_TEST_EXISTS", None)
                os.environ.pop("PT_TEST_MISSING", None)
                self.assertEqual(self.plan(launch)["env"], {"PT_TEST_EXISTS": d})

    def test_an_env_default_set_to_empty_text_counts_as_unset(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"PT_TEST_EMPTY": ""}):
                plan = self.plan({"command": ["/g/x"], "env_defaults": {"PT_TEST_EMPTY": d}})
            self.assertEqual(plan["env"], {"PT_TEST_EMPTY": d})

    def test_env_wins_over_an_env_default_for_the_same_name(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ):
                os.environ.pop("PT_TEST_BOTH", None)
                plan = self.plan({"command": ["/g/x"], "env": {"PT_TEST_BOTH": "env"},
                                  "env_defaults": {"PT_TEST_BOTH": d}})
            self.assertEqual(plan["env"], {"PT_TEST_BOTH": "env"})

    def test_seed_is_filled_only_in_seed_args(self):
        plan = self.plan({"command": ["/g/x"], "args": ["{seed}"], "seed_args": ["--seed", "{seed}"]}, seed="9")
        self.assertEqual(plan["command"], ["/g/x", "{seed}", "--seed", "9"])

    def test_extra_args_come_last_after_the_probe_flag(self):
        p = dict(profiles.DEFAULTS, launch=dict(profiles.DEFAULTS["launch"], command=["/g/x"]),
                 probe={"flag": "--out"})
        plan = profiles.launch_plan(p, "/g", "/s", 640, 360, None, ["--extra"], True)
        self.assertEqual(plan["command"], ["/g/x", "--out", "/s/out", "--extra"])


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
        demo = fill(profiles.load("demo"), "g", "s01", "/r", "1")
        self.assertIn("| `pt face DEG` |", demo)
        self.assertIn("| `pt face --to YAW` |", demo)
        plain = dict(profiles.load("demo"), probe=None, movement=None)
        text = fill(plain, "g", "s01", "/r", None)
        self.assertNotIn("`pt walkto KIND", text)
        self.assertNotIn("`pt face --to YAW`", text)
        self.assertIn("This game has no probe", text)
        self.assertIn('"seed": null', text)

    def test_a_profile_with_questions_asks_them_and_one_without_does_not(self):
        p = profiles.load("atman")
        text = fill(p, "g", "s01", "/r", "1")
        self.assertIn("## Questions to answer at the end", text)
        for i, q in enumerate(p["questions"], 1):
            self.assertIn("%d. %s" % (i, q), text)
        self.assertIn('"answers": [', text)
        self.assertLess(text.index("## Questions to answer"), text.index("## The report"))
        self.assertIn("This game has no probe", text)
        plain = fill(profiles.load("kindling"), "g", "s01", "/r", "1")
        self.assertNotIn("Questions to answer", plain)
        self.assertIn("\n\n## The report\n", plain)

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
