"""The probe contract's schemas and pt probe-check."""

import json
import os
import tempfile
import unittest

from tests.helpers import FIXTURE_RUN
from playtester.probecheck import check_dir, check_events_lines, check_state, main as probecheck_main

WORLD_STATE = {
    "wallTimeMs": 1792642042971, "version": "0.4.1", "screen": "WORLD", "fps": 13, "world": True, "tps": 49.8,
    "openPanels": ["tip"], "seed": 42, "tick": 1420,
    "player": {"x": 117.63, "z": 14.23, "yawDeg": 64, "speed": 25, "alive": True},
    "objective": {"number": 1, "title": "Gather wood", "progress": "Wood 4/10", "completed": 0},
    "nearest": {"tree": [{"name": "Tree", "id": "8efc84cd", "distance": 2.5, "bearing": -8.1}], "rock": []},
    "era": "Camp",
}


class StateTest(unittest.TestCase):
    def test_a_world_state_in_the_documented_shape_conforms(self):
        self.assertEqual(check_state(WORLD_STATE), [])

    def test_off_the_world_only_the_core_fields_are_needed(self):
        self.assertEqual(check_state({"wallTimeMs": 1, "version": "1.0", "screen": "TITLE", "world": False}), [])

    def test_a_world_without_its_fields_is_named(self):
        problems = "\n".join(check_state({"wallTimeMs": 1, "version": "1.0", "screen": "WORLD", "world": True}))
        for field in ("tick", "seed", "player"):
            self.assertIn("missing required '%s'" % field, problems)

    def test_bearings_are_relative_and_bounded(self):
        bad = json.loads(json.dumps(WORLD_STATE))
        bad["nearest"]["tree"][0]["bearing"] = 270
        self.assertTrue(any("bearing" in p and "above 180" in p for p in check_state(bad)))

    def test_games_may_add_their_own_fields(self):
        extra = dict(WORLD_STATE, mare={"hunger": 0.4}, checklist=[])
        self.assertEqual(check_state(extra), [])


class EventsTest(unittest.TestCase):
    def lines(self, *events):
        return [json.dumps(e) for e in events]

    def test_the_standard_types_need_their_fields(self):
        problems = check_events_lines(self.lines(
            {"type": "screen", "tick": 0, "wallTimeMs": 1, "to": "TITLE"},
            {"type": "world", "tick": 0, "wallTimeMs": 2, "how": "imported"},
            {"type": "objective_completed", "tick": 5, "wallTimeMs": 3},
            {"type": "Bad Type", "tick": 6, "wallTimeMs": 4},
        ))
        joined = "\n".join(problems)
        self.assertIn("line 1 $: missing required 'from'", joined)
        self.assertIn("line 2 $.how: 'imported' is not one of", joined)
        self.assertIn("line 3 $: missing required 'title'", joined)
        self.assertIn("line 4 $.type", joined)

    def test_game_specific_types_are_welcome(self):
        self.assertEqual(check_events_lines(self.lines(
            {"type": "world", "tick": 0, "wallTimeMs": 1, "how": "created", "seed": 1},
            {"type": "chronicle", "tick": 3, "wallTimeMs": 2, "kind": "WAR", "text": "..."},
        )), [])

    def test_ticks_go_forward_within_a_world_and_restart_with_a_new_one(self):
        ok = self.lines(
            {"type": "world", "tick": 0, "wallTimeMs": 1, "how": "created"},
            {"type": "status", "tick": 50, "wallTimeMs": 2, "text": "a"},
            {"type": "world", "tick": 10, "wallTimeMs": 3, "how": "loaded"},
            {"type": "status", "tick": 12, "wallTimeMs": 4, "text": "b"},
        )
        self.assertEqual(check_events_lines(ok), [])
        backwards = self.lines({"type": "status", "tick": 50, "wallTimeMs": 1, "text": "a"},
                               {"type": "status", "tick": 40, "wallTimeMs": 2, "text": "b"})
        self.assertIn("before the previous event", "\n".join(check_events_lines(backwards)))

    def test_not_json_is_named(self):
        self.assertIn("line 1: not valid JSON", "\n".join(check_events_lines(["{nope"])))

    def test_recorded_events_from_a_real_game_conform(self):
        for name in ("s01", "s02", "s03"):
            with open(os.path.join(FIXTURE_RUN, name, "out", "events.jsonl"), encoding="utf-8") as f:
                self.assertEqual(check_events_lines(f.readlines()), [], name)


class EventsOnlyTest(unittest.TestCase):
    def test_one_recorded_events_file(self):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            code = probecheck_main(["probecheck", "--events-only", os.path.join(FIXTURE_RUN, "s01", "out", "events.jsonl")])
        self.assertEqual(code, 0, out.getvalue())


class DirTest(unittest.TestCase):
    def test_a_directory_with_both_files(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sorted(check_dir(d)), ["events.jsonl: missing in " + d, "state.json: missing in " + d])
            with open(os.path.join(d, "state.json"), "w") as f:
                json.dump(WORLD_STATE, f)
            with open(os.path.join(d, "events.jsonl"), "w") as f:
                f.write(json.dumps({"type": "screen", "tick": 0, "wallTimeMs": 1, "from": None, "to": "WORLD"}) + "\n")
            self.assertEqual(check_dir(d, require_world=True), [])


if __name__ == "__main__":
    unittest.main()
