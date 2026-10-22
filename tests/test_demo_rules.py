"""The demo game's rules and probe, without a display."""

import json
import os
import tempfile
import unittest

import tests.helpers  # noqa: F401
from playtester.demo import REACH, WOOD_GOAL, Game, Probe
from playtester.probecheck import check_dir


class DemoTest(unittest.TestCase):
    def test_a_whole_game_writes_conforming_probe_output(self):
        with tempfile.TemporaryDirectory() as d:
            game = Game(7, Probe(d))
            game.probe.state(game, force=True)
            game.press("space")
            self.assertEqual(game.screen, "WORLD")
            for _ in range(WOOD_GOAL):
                tree = game.nearest_trees()[0]
                # turn toward it, then walk until within reach, as the harness would
                while abs(game.nearest_trees()[0]["bearing"]) > 2:
                    game.step(1 if game.nearest_trees()[0]["bearing"] > 0 else -1, 0)
                while game.nearest_trees()[0]["distance"] > REACH - 0.2:
                    game.step(0, 1)
                self.assertEqual(game.nearest_trees()[0]["id"], tree["id"])
                game.press("e")
            game.probe.state(game, force=True)
            self.assertEqual(check_dir(d, require_world=True), [])
            with open(os.path.join(d, "events.jsonl")) as f:
                events = [json.loads(l) for l in f]
            done = [e for e in events if e["type"] == "objective_completed"]
            self.assertEqual([e["title"] for e in done], ["Gather wood"])
            self.assertEqual([e["type"] for e in events[:3]], ["screen", "screen", "world"])

    def test_turning_right_raises_the_heading_and_moves_bearings_left(self):
        game = Game(7, Probe(None))
        game.press("space")
        before = game.nearest_trees()[0]
        game.step(1, 0)
        after = [t for t in game.nearest_trees() if t["id"] == before["id"]][0]
        self.assertAlmostEqual(game.yaw, 183.0)
        self.assertLess(after["bearing"], before["bearing"])

    def test_nothing_happens_off_the_world(self):
        game = Game(7, Probe(None))
        game.step(1, 1)
        game.press("e")
        self.assertEqual((game.tick, game.wood, game.screen), (0, 0, "TITLE"))


if __name__ == "__main__":
    unittest.main()
