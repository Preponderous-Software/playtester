"""The probe layer: state summaries, events and the closed loops (no display needed: the game is simulated)."""

import json
import os
import tempfile
import unittest
from unittest import mock

import tests.helpers  # noqa: F401  (puts src on sys.path)
from playtester.harness import probe
from playtester.harness.session import Session

MOVEMENT = {
    "turn": {"method": "keys", "left": "a", "right": "d", "degrees_per_second": 90},
    "yaw_increases": "right",
    "forward_key": "w",
    "default_speed": 4.0,
    "stop_distance": 2.0,
    "face_tolerance": 8.0,
    "nearest_kinds": ["tree", "rock"],
}


def movement(**changes):
    return dict(MOVEMENT, **changes)


class SimulatedGame:
    """The game behind the closed loops: input changes the yaw and bearing, or closes the distance."""

    stepped = False

    def __init__(self, mv, yaw=0.0, targets=None, stride=1.0, turn_works=True, screen_after_turn=None):
        self.mv = mv
        self.yaw = yaw
        self.targets = targets if targets is not None else []
        self.stride = stride
        self.turn_works = turn_works
        self.screen = "WORLD"
        self.screen_after_turn = screen_after_turn
        self.holds = []
        self.looks = []

    def state(self, *_args, **_kwargs):
        return {"screen": self.screen, "fps": 60, "wallTimeMs": 1,
                "player": {"x": 0, "z": 0, "yawDeg": self.yaw, "speed": 4},
                "nearest": {"tree": [dict(t) for t in self.targets]}}

    def _turned(self, degrees_right):
        if self.screen_after_turn:
            self.screen = self.screen_after_turn
        if self.turn_works:
            grows_right = self.mv.get("yaw_increases", "left") == "right"
            self.yaw += degrees_right if grows_right else -degrees_right
            for t in self.targets:
                t["bearing"] -= degrees_right

    def hold(self, key, seconds):
        self.holds.append((key, seconds))
        turn = self.mv["turn"]
        if turn["method"] == "keys" and key in (turn["left"], turn["right"]):
            sign = 1 if key == turn["right"] else -1
            self._turned(sign * seconds * turn["degrees_per_second"])
        else:
            for t in self.targets:
                t["distance"] = max(0.0, t["distance"] - self.stride)

    def look(self, dx, dy):
        self.looks.append((dx, dy))
        self._turned(dx / self.mv["turn"]["pixels_per_degree"])


class SessionTestCase(unittest.TestCase):
    """A real session directory holding a saved profile; the game behind it is simulated."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.session = Session("s01", self.tmp.name)
        os.makedirs(self.session.probe_dir)

    def save_profile(self, mv=None, **fields):
        profile = dict({"name": "game", "probe": {"flag": "--probe"}, "movement": mv}, **fields)
        with open(self.session.path("profile.json"), "w") as f:
            json.dump(profile, f)

    def write_state(self, st):
        with open(probe.state_path(self.session), "w") as f:
            json.dump(st, f)

    def write_events(self, text):
        with open(os.path.join(self.session.probe_dir, "events.jsonl"), "w") as f:
            f.write(text)

    def play(self, game):
        """Serves ``game``'s state to the closed loops, without their wall-clock waits."""
        self.save_profile(game.mv)
        self.session.input = mock.Mock(return_value=game)
        patcher = mock.patch.object(probe, "fresh_state", side_effect=game.state)
        patcher.start()
        self.addCleanup(patcher.stop)


class NormaliseTest(unittest.TestCase):
    def test_angles_land_in_the_half_open_range(self):
        cases = {0: 0, 190: -170, -190: 170, 180: 180, -180: 180, 540: 180, 725: 5}
        for degrees, expected in cases.items():
            self.assertEqual(probe.normalise(degrees), expected, degrees)


class CompactTest(unittest.TestCase):
    def test_no_state_says_so(self):
        self.assertIn("no state.json", probe.compact(None, [])["error"])

    def test_keeps_what_an_agent_reads_and_drops_the_rest(self):
        st = {"screen": "WORLD", "fps": 60, "tick": 0, "wallTimeMs": 1, "version": "1", "world": True,
              "openPanels": ["map"], "player": {"x": 1}, "wood": 0, "status": None, "note": "", "bag": []}
        self.assertEqual(probe.compact(st, []), {"screen": "WORLD", "fps": 60, "tick": 0, "panels": ["map"],
                                                 "player": {"x": 1}, "wood": 0})

    def test_nearest_is_one_line_a_thing_named_or_by_kind(self):
        st = {"nearest": {"tree": [{"name": "Oak", "distance": 2.54, "bearing": -8.1}],
                          "rock": [{"distance": 10, "bearing": 90}], "bush": []}}
        self.assertEqual(probe.compact(st, [])["nearest"], {"tree": ["Oak 2.5m -8"], "rock": ["rock 10.0m +90"]})

    def test_kinds_narrow_nearest_and_an_empty_result_stays_visible(self):
        st = {"nearest": {"tree": [{"distance": 1, "bearing": 0}], "rock": [{"distance": 1, "bearing": 0}]}}
        self.assertEqual(list(probe.compact(st, ["rock"])["nearest"]), ["rock"])
        self.assertEqual(probe.compact(st, ["bush"])["nearest"], {})
        self.assertNotIn("nearest", probe.compact({"screen": "T"}, []))


class EventsTest(SessionTestCase):
    def test_no_file_is_no_events(self):
        self.assertEqual(probe.read_events(self.session), [])

    def test_blank_and_torn_lines_are_skipped(self):
        self.write_events('{"type":"a"}\n\n{"type":\n{"type":"b"}\n')
        self.assertEqual([e["type"] for e in probe.read_events(self.session)], ["a", "b"])

    def test_a_match_needs_every_field(self):
        event = {"type": "pickup", "item": "wood", "n": 1}
        self.assertTrue(probe.event_matches(event, {"type": "pickup", "item": "wood"}))
        self.assertTrue(probe.event_matches(event, {}))
        self.assertFalse(probe.event_matches(event, {"type": "pickup", "item": "stone"}))
        self.assertFalse(probe.event_matches(event, {"absent": 1}))

    def test_await_event_starts_after_since(self):
        self.write_events('{"type":"hit","n":1}\n{"type":"hit","n":2}\n')
        self.assertEqual(probe.await_event(self.session, {"type": "hit"}, 0)["n"], 1)
        self.assertEqual(probe.await_event(self.session, {"type": "hit"}, 0, since=1)["n"], 2)
        self.assertIsNone(probe.await_event(self.session, {"type": "hit"}, 0, since=2))

    def test_await_event_keeps_looking_until_the_event_arrives(self):
        with mock.patch.object(probe.time, "sleep", side_effect=lambda _s: self.write_events('{"type":"hit"}\n')):
            self.assertEqual(probe.await_event(self.session, {"type": "hit"}, 30), {"type": "hit"})


class NeedProbeTest(SessionTestCase):
    def test_returns_the_profile_of_a_session_with_a_probe(self):
        self.save_profile()
        self.assertEqual(probe.need_probe(self.session)["name"], "game")

    def test_a_profile_without_a_probe_is_refused(self):
        self.save_profile(probe=None)
        with self.assertRaisesRegex(RuntimeError, "no probe"):
            probe.need_probe(self.session)

    def test_no_probe_at_start_overrides_the_profile(self):
        self.save_profile(_probe=False)
        with self.assertRaisesRegex(RuntimeError, "no probe"):
            probe.need_probe(self.session)


class WorldScreenTest(unittest.TestCase):
    def test_world_is_the_default_and_a_profile_can_replace_it(self):
        self.assertTrue(probe.world_screen({"screen": "WORLD"}, {}))
        self.assertFalse(probe.world_screen({"screen": "TITLE"}, {}))
        profile = {"probe": {"world_screens": ["OVERWORLD", "CAVE"]}}
        self.assertTrue(probe.world_screen({"screen": "CAVE"}, profile))
        self.assertFalse(probe.world_screen({"screen": "WORLD"}, profile))

    def test_no_state_is_not_the_world(self):
        self.assertFalse(probe.world_screen(None, {}))


class FreshStateTest(SessionTestCase):
    def test_free_clock_waits_for_a_newer_state(self):
        self.write_state({"wallTimeMs": 100, "screen": "OLD"})

        def newer(_seconds):
            self.write_state({"wallTimeMs": 200, "screen": "NEW"})

        with mock.patch.object(probe.time, "sleep", side_effect=newer) as sleep:
            st = probe.fresh_state(self.session, 150)
        self.assertEqual(st["screen"], "NEW")
        self.assertEqual(sleep.call_count, 1)

    def test_free_clock_gives_back_the_stale_state_at_the_deadline(self):
        self.write_state({"wallTimeMs": 100, "screen": "OLD"})
        with mock.patch.object(probe.time, "sleep"):
            st = probe.fresh_state(self.session, 150, timeout=0.01)
        self.assertEqual(st["screen"], "OLD")

    def test_stepped_clock_steps_one_frame_a_look_until_a_state_is_fresh(self):
        written = iter([100, 120, 200])
        inp = mock.Mock(stepped=True)
        inp.step.side_effect = lambda _frames: self.write_state({"wallTimeMs": next(written), "screen": "S"})
        with mock.patch.object(probe.time, "sleep") as sleep:
            st = probe.fresh_state(self.session, 150, inp=inp)
        self.assertEqual(st["wallTimeMs"], 200)
        self.assertEqual(inp.step.call_args_list, [mock.call(1)] * 3)
        sleep.assert_called_with(probe.STATE_INTERVAL_SEC)

    def test_stepped_clock_gives_up_after_the_timeout_in_looks(self):
        inp = mock.Mock(stepped=True)
        inp.step.side_effect = lambda _frames: self.write_state({"wallTimeMs": 1, "screen": "OLD"})
        with mock.patch.object(probe.time, "sleep"):
            st = probe.fresh_state(self.session, 150, timeout=1.1, inp=inp)
        self.assertEqual(st["screen"], "OLD")
        self.assertEqual(inp.step.call_count, 3)


class AwaitScreenTest(SessionTestCase):
    def test_free_clock_finds_the_screen(self):
        self.write_state({"screen": "WORLD"})
        self.assertEqual(probe.await_screen(self.session, "WORLD", 5), {"ok": True, "screen": "WORLD"})

    def test_free_clock_times_out_naming_the_screen_it_saw(self):
        self.write_state({"screen": "TITLE"})
        with mock.patch.object(probe.time, "sleep"):
            r = probe.await_screen(self.session, "WORLD", 0.01)
        self.assertEqual(r, {"ok": False, "error": "still not on WORLD", "screen": "TITLE"})

    def stepped_session(self, screens):
        """A stepped session whose next state comes from ``screens`` each time a frame batch ends."""
        with open(self.session.path("session.json"), "w") as f:
            json.dump({"driver": "strata", "clock": "stepped"}, f)
        screens = iter(screens)
        inp = mock.Mock(stepped=True, step_seconds=0.05)
        inp.step.side_effect = lambda frames: frames == 1 and self.write_state(
            {"wallTimeMs": probe.now_ms() + 60000, "screen": next(screens)})
        self.session.input = mock.Mock(return_value=inp)
        return inp

    def test_stepped_clock_counts_game_frames(self):
        inp = self.stepped_session(["TITLE", "WORLD"])
        with mock.patch.object(probe.time, "sleep"):
            r = probe.await_screen(self.session, "WORLD", 10)
        self.assertEqual(r, {"ok": True, "screen": "WORLD", "frames": 2 * probe.AWAIT_FRAMES})
        self.assertEqual(sum(c[0][0] for c in inp.step.call_args_list), r["frames"])

    def test_stepped_clock_gives_up_on_game_time_not_wall_time(self):
        self.stepped_session(["TITLE"] * 5)
        with mock.patch.object(probe.time, "sleep"):
            r = probe.await_screen(self.session, "WORLD", 1.0)
        self.assertEqual(r, {"ok": False, "error": "still not on WORLD", "screen": "TITLE"})


class FaceTest(SessionTestCase):
    def test_turns_right_with_the_right_key_until_within_tolerance(self):
        game = SimulatedGame(movement())
        self.play(game)
        r = probe.face(self.session, 90)
        self.assertEqual({key for key, _ in game.holds}, {"d"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["turns"], 2)
        self.assertEqual(r["offBy"], -0.9)

    def test_a_turn_stops_short_of_the_whole_angle(self):
        game = SimulatedGame(movement())
        self.play(game)
        probe.face(self.session, 90)
        self.assertAlmostEqual(game.holds[0][1], 0.9)

    def test_negative_is_left(self):
        game = SimulatedGame(movement())
        self.play(game)
        self.assertTrue(probe.face(self.session, -90)["ok"])
        self.assertEqual({key for key, _ in game.holds}, {"a"})

    def test_a_game_whose_yaw_grows_to_the_left(self):
        game = SimulatedGame(movement(yaw_increases="left"))
        self.play(game)
        r = probe.face(self.session, 90)
        self.assertEqual({key for key, _ in game.holds}, {"d"})
        self.assertTrue(r["ok"])
        self.assertLess(r["yawDeg"], 0)

    def test_the_short_way_round_across_the_seam(self):
        game = SimulatedGame(movement(), yaw=170.0)
        self.play(game)
        self.assertTrue(probe.face(self.session, 20)["ok"])
        self.assertEqual({key for key, _ in game.holds}, {"d"})
        self.assertAlmostEqual(sum(seconds for _, seconds in game.holds) * 90, 20, delta=8)

    def test_a_tiny_turn_still_holds_the_key_long_enough_to_register(self):
        game = SimulatedGame(movement())
        self.play(game)
        probe.face(self.session, 1, tolerance=0.5)
        self.assertEqual(game.holds[0], ("d", 0.03))

    def test_mouse_turning_moves_the_pointer_by_pixels_per_degree(self):
        game = SimulatedGame(movement(turn={"method": "mouse", "pixels_per_degree": 4.0}))
        self.play(game)
        r = probe.face(self.session, -45)
        self.assertEqual(game.looks, [(-180, 0)])
        self.assertTrue(r["ok"])
        self.assertEqual(r["turns"], 1)

    def test_already_facing_presses_nothing(self):
        game = SimulatedGame(movement())
        self.play(game)
        r = probe.face(self.session, 5)
        self.assertEqual(game.holds, [])
        self.assertEqual((r["ok"], r["turns"]), (True, 0))

    def test_the_profile_tolerance_and_an_explicit_one(self):
        game = SimulatedGame(movement(face_tolerance=30.0))
        self.play(game)
        self.assertEqual(probe.face(self.session, 20)["turns"], 0)
        self.assertGreater(probe.face(self.session, 20, tolerance=1.0)["turns"], 0)

    def test_gives_up_after_its_attempts_when_turning_does_nothing(self):
        game = SimulatedGame(movement(), turn_works=False)
        self.play(game)
        r = probe.face(self.session, 90, attempts=3)
        self.assertEqual(len(game.holds), 3)
        self.assertEqual((r["ok"], r["turns"], r["offBy"]), (False, 3, -90.0))

    def test_outside_the_world_it_does_not_turn(self):
        game = SimulatedGame(movement())
        game.screen = "TITLE"
        self.play(game)
        r = probe.face(self.session, 90)
        self.assertEqual(r, {"ok": False, "error": "not in the world", "screen": "TITLE"})
        self.assertEqual(game.holds, [])

    def test_no_state_is_not_in_the_world(self):
        self.save_profile(MOVEMENT)
        with mock.patch.object(probe, "fresh_state", return_value=None):
            r = probe.face(self.session, 90, inp=mock.Mock())
        self.assertEqual(r, {"ok": False, "error": "not in the world", "screen": None})

    def test_leaving_the_world_mid_turn_stops_it(self):
        game = SimulatedGame(movement(), screen_after_turn="DEAD")
        self.play(game)
        r = probe.face(self.session, 90)
        self.assertEqual(r, {"ok": False, "error": "left the world", "screen": "DEAD"})
        self.assertEqual(len(game.holds), 1)

    def test_a_profile_with_no_movement_section_is_refused(self):
        self.save_profile(None)
        r = probe.face(self.session, 90)
        self.assertEqual(r, {"ok": False, "error": "the game profile has no movement section"})

    def test_every_turn_is_traced(self):
        game = SimulatedGame(movement())
        self.play(game)
        probe.face(self.session, 90)
        with open(self.session.path("trace.jsonl")) as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([row["what"] for row in rows], ["face", "face"])
        self.assertEqual(rows[0]["remaining"], 90.0)


class WalktoTest(SessionTestCase):
    def tree(self, distance=10.0, bearing=0.0, **fields):
        return dict({"id": "t1", "name": "Tree", "distance": distance, "bearing": bearing}, **fields)

    def test_walks_until_inside_the_stop_distance(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=5.0)])
        self.play(game)
        r = probe.walkto(self.session, "tree")
        self.assertTrue(r["ok"])
        self.assertEqual((r["kind"], r["name"], r["id"], r["distance"]), ("tree", "Tree", "t1", 1.0))
        self.assertEqual({key for key, _ in game.holds}, {"w"})
        self.assertEqual(len(game.holds), 4)

    def test_already_there_it_does_not_move(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=1.0)])
        self.play(game)
        self.assertTrue(probe.walkto(self.session, "tree")["ok"])
        self.assertEqual(game.holds, [])

    def test_turns_towards_the_target_before_walking(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=5.0, bearing=60.0)])
        self.play(game)
        self.assertTrue(probe.walkto(self.session, "tree")["ok"])
        self.assertEqual(game.holds[0][0], "d")
        self.assertEqual(game.holds[-1][0], "w")

    def test_a_small_bearing_is_walked_through_without_turning(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=5.0, bearing=9.0)])
        self.play(game)
        probe.walkto(self.session, "tree")
        self.assertEqual({key for key, _ in game.holds}, {"w"})

    def test_steps_are_sized_by_the_remaining_distance_and_the_speed(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=2.5)])
        self.play(game)
        probe.walkto(self.session, "tree")
        self.assertAlmostEqual(game.holds[0][1], (2.5 - 2.0 + 0.8) / 4)

    def test_a_step_is_at_most_a_second(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=50.0)], stride=25.0)
        self.play(game)
        probe.walkto(self.session, "tree")
        self.assertEqual(game.holds[0], ("w", 1.0))

    def test_speed_comes_from_the_named_field_or_the_default(self):
        game = SimulatedGame(movement(speed_field="pace", default_speed=1.3), targets=[self.tree(distance=2.5)])
        self.play(game)
        probe.walkto(self.session, "tree")
        self.assertAlmostEqual(game.holds[0][1], (2.5 - 2.0 + 0.8) / 1.3)

    def test_the_note_says_how_to_interact(self):
        mv = movement(interact_range=1.5, interact_key="e")
        game = SimulatedGame(mv, targets=[self.tree(distance=1.0)])
        self.play(game)
        self.assertEqual(probe.walkto(self.session, "tree")["note"], "within reach (interact range 1.5); press e")

    def test_no_interact_range_no_note(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=1.0)])
        self.play(game)
        self.assertNotIn("note", probe.walkto(self.session, "tree"))

    def test_a_kind_the_profile_does_not_list_is_refused(self):
        self.save_profile(MOVEMENT)
        r = probe.walkto(self.session, "cow")
        self.assertEqual(r, {"ok": False, "error": "kind must be one of tree, rock"})

    def test_nothing_of_that_kind_nearby(self):
        game = SimulatedGame(movement())
        self.play(game)
        self.assertEqual(probe.walkto(self.session, "tree"), {"ok": False, "error": "no tree nearby"})

    def test_outside_the_world_it_does_not_walk(self):
        game = SimulatedGame(movement(), targets=[self.tree()])
        game.screen = "TITLE"
        self.play(game)
        r = probe.walkto(self.session, "tree")
        self.assertEqual(r, {"ok": False, "error": "not in the world", "screen": "TITLE"})

    def test_a_profile_with_no_movement_section_is_refused(self):
        self.save_profile(None)
        r = probe.walkto(self.session, "tree")
        self.assertEqual(r, {"ok": False, "error": "the game profile has no movement section"})

    def test_time_runs_out(self):
        game = SimulatedGame(movement(), targets=[self.tree()])
        self.play(game)
        r = probe.walkto(self.session, "tree", max_seconds=-1)
        self.assertEqual(r, {"ok": False, "error": "timed out", "kind": "tree", "distance": 10.0, "bearing": 0.0})
        self.assertEqual(game.holds, [])

    def test_walking_into_a_wall_is_stuck_after_four_stalls(self):
        game = SimulatedGame(movement(), targets=[self.tree()], stride=0.0)
        self.play(game)
        r = probe.walkto(self.session, "tree")
        self.assertEqual(r["error"], "stuck: not getting closer")
        self.assertEqual((r["ok"], r["kind"], r["distance"]), (False, "tree", 10.0))
        self.assertIn("hint", r)
        self.assertEqual(len(game.holds), 4)

    def test_slow_progress_is_not_a_stall(self):
        game = SimulatedGame(movement(), targets=[self.tree()], stride=0.2)
        self.play(game)
        self.assertTrue(probe.walkto(self.session, "tree")["ok"])

    def test_turning_on_the_spot_is_not_a_stall(self):
        turning = {"screen": "WORLD", "player": {}, "nearest": {"tree": [self.tree(bearing=90.0)]}}
        arrived = {"screen": "WORLD", "player": {}, "nearest": {"tree": [self.tree(distance=1.0)]}}
        self.save_profile(MOVEMENT)
        self.session.input = mock.Mock(return_value=SimulatedGame(movement()))
        with mock.patch.object(probe, "fresh_state", side_effect=[turning] * 6 + [arrived]):
            with mock.patch.object(probe, "face") as face:
                self.assertTrue(probe.walkto(self.session, "tree")["ok"])
        self.assertEqual(face.call_count, 6)

    def test_a_changing_nearest_target_is_not_a_stall(self):
        states = [{"screen": "WORLD", "player": {}, "nearest": {"tree": [self.tree(id=i)]}} for i in range(8)]
        states.append({"screen": "WORLD", "player": {}, "nearest": {"tree": [self.tree(id=8, distance=1.0)]}})
        self.save_profile(MOVEMENT)
        game = SimulatedGame(movement())
        self.session.input = mock.Mock(return_value=game)
        with mock.patch.object(probe, "fresh_state", side_effect=states):
            self.assertTrue(probe.walkto(self.session, "tree")["ok"])

    def test_current_behaviour_a_target_with_no_id_is_stuck_while_getting_closer(self):
        # A bug, pinned rather than endorsed (issue #26): id is optional in nearest,
        # and without one best stays 0. Invert this test when walkto is fixed.
        anonymous = self.tree()
        del anonymous["id"]
        game = SimulatedGame(movement(), targets=[anonymous], stride=1.0)
        self.play(game)
        r = probe.walkto(self.session, "tree")
        self.assertEqual(r["error"], "stuck: not getting closer")
        self.assertEqual(r["distance"], 6.0)

    def test_every_step_is_traced(self):
        game = SimulatedGame(movement(), targets=[self.tree(distance=3.0)])
        self.play(game)
        probe.walkto(self.session, "tree")
        with open(self.session.path("trace.jsonl")) as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([row["distance"] for row in rows], [3.0, 2.0, 1.0])
        self.assertEqual({row["what"] for row in rows}, {"walkto"})
