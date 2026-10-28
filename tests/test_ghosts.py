"""pt ghosts: reading recorded runs, laying out the trails, and rendering them with Strata."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from tests.helpers import HERE
from playtester import ghosts
from playtester.ghosts import (Bounds, GhostsError, Sample, build_frame, fade, find_stalls, load_run, load_runs,
                               nice_step, parse_args)
from playtester.harness import cli, probe
from playtester.harness.session import Session

FIXTURE = os.path.join(HERE, "fixtures", "ghosts")


def strata_or_none():
    """(strata module, Library) when the binding and a libstrata are available, else None."""
    try:
        return ghosts.load_strata()
    except GhostsError:
        return None


class LoadRunTest(unittest.TestCase):
    def test_a_track_on_a_game_clock_runs_in_game_seconds(self):
        run = load_run(os.path.join(FIXTURE, "s01"))
        self.assertEqual(run.name, "s01")
        self.assertEqual(run.clock, "game")
        self.assertEqual(run.source, "track.jsonl")
        self.assertEqual(run.samples[0].t, 0.0)
        self.assertAlmostEqual(run.duration, 1350 / 30.0)
        self.assertEqual(len(run.samples), 22, "the state read twice is one sample")

    def test_the_stall_the_death_and_the_end_are_marked(self):
        run = load_run(os.path.join(FIXTURE, "s01"))
        kinds = [m.kind for m in run.markers]
        self.assertEqual(kinds, ["stall", "death", "end"])
        stall = run.markers[0]
        self.assertAlmostEqual(stall.t, 10.0)
        self.assertAlmostEqual(stall.seconds, 30.0)
        self.assertAlmostEqual(stall.x, 10.15, places=2)
        death = run.markers[1]
        self.assertEqual((death.x, death.z), (10.0, 6.0), "placed at the position nearest its tick")
        end = run.markers[2]
        self.assertEqual((end.x, end.z), (10.0, 10.0))

    def test_an_older_session_falls_back_to_the_walkto_trace_on_the_wall_clock(self):
        run = load_run(os.path.join(FIXTURE, "s02"))
        self.assertEqual(run.clock, "wall")
        self.assertEqual(run.source, "trace.jsonl+events.jsonl")
        self.assertAlmostEqual(run.duration, 14.0)
        death = [m for m in run.markers if m.kind == "death"][0]
        self.assertEqual((death.x, death.z), (-6.5, 5.5), "an event with x and z is placed exactly")

    def test_a_single_events_file_can_be_read(self):
        run = load_run(os.path.join(FIXTURE, "s02", "events.jsonl"))
        self.assertEqual(len(run.samples), 1)

    def test_a_session_without_positions_says_where_they_come_from(self):
        with self.assertRaises(GhostsError) as e:
            load_run(os.path.join(FIXTURE, "s03"))
        self.assertIn("track.jsonl", str(e.exception))

    def test_a_run_directory_skips_sessions_with_nothing_to_draw(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            runs = load_runs([FIXTURE])
        self.assertEqual([r.name for r in runs], ["s01", "s02"])
        self.assertIn("skipped", err.getvalue())

    def test_a_run_directory_with_no_positions_at_all_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(os.path.join(FIXTURE, "s03"), os.path.join(d, "s03"))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(GhostsError):
                load_runs([d])

    def test_the_same_session_name_from_two_runs_is_told_apart(self):
        with tempfile.TemporaryDirectory() as d:
            for run in ("0.1.1", "0.1.2"):
                shutil.copytree(os.path.join(FIXTURE, "s01"), os.path.join(d, run, "s01"))
            runs = load_runs([os.path.join(d, "0.1.1"), os.path.join(d, "0.1.2")])
        self.assertEqual([r.name for r in runs], ["0.1.1/s01", "0.1.2/s01"])

    def test_a_tick_going_backwards_is_a_new_world_and_the_clock_carries_on(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "session.json"), "w") as f:
                json.dump({"ticksPerSecond": 10}, f)
            with open(os.path.join(d, "track.jsonl"), "w") as f:
                for t, tick, x in ((1000, 0, 0), (2000, 100, 5), (3000, 0, 50), (4000, 50, 52)):
                    f.write(json.dumps({"t": t, "tick": tick, "x": x, "z": 0}) + "\n")
            run = load_run(d)
        self.assertEqual([s.t for s in run.samples], [0.0, 10.0, 10.0, 15.0])
        self.assertEqual([s.brk for s in run.samples], [False, False, True, False])

    def test_a_line_cut_short_by_a_crash_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "track.jsonl"), "w") as f:
                f.write('{"t": 1000, "tick": 1, "x": 1, "z": 2}\n{"t": 2000, "tick": 2, "x"')
            run = load_run(d)
        self.assertEqual(len(run.samples), 1)


class StallTest(unittest.TestCase):
    def samples(self, points):
        return [Sample(t, None, None, x, z) for t, x, z in points]

    def test_standing_still_long_enough_is_a_stall(self):
        s = self.samples([(0, 0, 0), (5, 0.1, 0), (30, 0.2, 0), (31, 9, 9)])
        stalls = find_stalls(s, stall_secs=20, radius=1)
        self.assertEqual(len(stalls), 1)
        self.assertEqual(stalls[0].seconds, 30)

    def test_moving_on_in_time_is_not(self):
        s = self.samples([(0, 0, 0), (5, 0.1, 0), (10, 3, 0), (40, 9, 0)])
        self.assertEqual(find_stalls(s, stall_secs=20, radius=1), [])

    def test_a_new_world_ends_a_stall(self):
        s = self.samples([(0, 0, 0), (10, 0, 0), (25, 0, 0)])
        s[2].brk = True
        self.assertEqual(find_stalls(s, stall_secs=20, radius=1), [])


class LayoutTest(unittest.TestCase):
    def setUp(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.runs = load_runs([FIXTURE])
        self.bounds = Bounds(self.runs)

    def test_the_ground_covers_every_run_with_a_margin(self):
        b = self.bounds
        for r in self.runs:
            for s in r.samples:
                self.assertLess(abs(s.x - b.cx), b.width / 2)
                self.assertLess(abs(s.z - b.cz), b.depth / 2)

    def test_a_run_that_never_moves_still_gets_a_ground(self):
        b = Bounds([ghosts.Run("x", [Sample(0, 0, 0, 3, 3)], [], "game", "t")])
        self.assertGreaterEqual(b.width, 4.0)

    def test_grid_steps_are_round_numbers(self):
        self.assertEqual(nice_step(20), 2)
        self.assertEqual(nice_step(450), 50)
        self.assertEqual(nice_step(0.9), 0.1)

    def test_trails_fade_with_age_down_to_a_floor(self):
        self.assertEqual(fade(0, 10), 1.0)
        self.assertGreater(fade(2, 10), fade(8, 10))
        self.assertEqual(fade(100, 10), ghosts.MIN_ALPHA)

    def test_a_whole_run_is_brightest_at_its_end(self):
        run = self.runs[0]
        no_rings = ghosts.Run(run.name, run.samples, [m for m in run.markers if m.kind != "stall"], run.clock, "")
        frame = build_frame([no_rings], self.bounds)
        trail = [ln for ln in frame.lines if ln[0][1] == ghosts.TRAIL_Y and ln[1][:3] == ghosts.colour(0)]
        self.assertEqual(len(trail), 3 * (len(self.runs[0].samples) - 1), "three lines side by side a step")
        self.assertLess(trail[0][1][3], trail[-1][3][3])
        self.assertEqual(trail[-1][3][3], 1.0)

    def test_each_run_has_its_own_colour_and_its_markers(self):
        frame = build_frame(self.runs, self.bounds, title="Kindling 0.1.2")
        colours = {ln[1][:3] for ln in frame.lines if ln[0][1] == ghosts.TRAIL_Y}
        self.assertTrue({ghosts.colour(0), ghosts.colour(1)} <= colours)
        kinds = [p[0] for p in frame.primitives]
        self.assertEqual(kinds[0], "cube", "the ground")
        self.assertEqual(kinds.count("sphere"), 2, "a pin where each run ended")
        self.assertEqual(kinds.count("cylinder"), 3, "s01's stall, and the pins' posts")
        texts = [t[4] for t in frame.texts]
        self.assertEqual(texts[0], "Kindling 0.1.2")
        self.assertTrue(texts[1].startswith("s01  0:45 game, 1 death, 1 stall"), texts[1])
        self.assertIn("rendered with Strata", texts[-1])

    def test_a_replay_frame_shows_only_what_has_happened(self):
        frame = build_frame(self.runs[:1], self.bounds, now=5.0, window=10.0)
        kinds = [p[0] for p in frame.primitives]
        self.assertEqual(kinds, ["cube"], "no stall, death or end yet")
        heads = [p for p in frame.points if not p[4] and p[1] == 9.0]
        self.assertEqual(len(heads), 1)
        self.assertAlmostEqual(heads[0][0][0], 5.0, msg="halfway along the first ten seconds' walk")


class CliTest(unittest.TestCase):
    def test_options(self):
        o = parse_args(["a", "b", "--gif", "g.gif", "--size", "320x180", "--stall-secs", "5", "--frames", "8"])
        self.assertEqual(o["paths"], ["a", "b"])
        self.assertEqual((o["gif"], o["png"], o["size"], o["stall_secs"], o["frames"]), ("g.gif", None, (320, 180), 5.0, 8))
        self.assertEqual(parse_args(["a"])["png"], "ghosts.png")
        for bad in (["--gif", "x"], ["a", "--size", "big"], ["a", "--wat"], ["a", "--fps", "0"], ["a", "--gif"]):
            with self.assertRaises(GhostsError):
                parse_args(bad)

    def test_dry_run_prints_each_run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["ghosts", FIXTURE, "--dry-run"]), 0)
        rows = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([r["run"] for r in rows], ["s01", "s02"])
        self.assertEqual([m["kind"] for m in rows[0]["markers"]], ["stall", "death", "end"])

    def test_without_the_strata_binding_it_says_how_to_get_it(self):
        err = io.StringIO()
        with mock.patch.dict(sys.modules, {"strata": None}), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["ghosts", os.path.join(FIXTURE, "s01"), "-o", "x.png"]), 1)
        self.assertIn("bindings/python", err.getvalue())

    def test_a_missing_path_is_an_error_not_a_traceback(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["ghosts", "/nonexistent/run", "--dry-run"]), 1)
        self.assertIn("not a session", err.getvalue())


class TrackTest(unittest.TestCase):
    """The harness's track.jsonl, written from state.json whenever pt reads it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.session = Session("s01", self.tmp)
        os.makedirs(self.session.probe_dir)
        probe._last_tracked.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_state(self, **fields):
        st = {"wallTimeMs": 1000, "version": "1", "screen": "WORLD", "world": True, "tick": 30, "seed": 1,
              "player": {"x": 1.5, "z": -2.0, "yawDeg": 0}}
        st.update(fields)
        with open(probe.state_path(self.session), "w") as f:
            json.dump(st, f)

    def track(self):
        try:
            with open(self.session.path("track.jsonl")) as f:
                return [json.loads(line) for line in f]
        except OSError:
            return []

    def test_reading_a_world_state_records_the_position_once(self):
        self.write_state()
        probe.read_state(self.session)
        probe.read_state(self.session)
        self.assertEqual(self.track(), [{"t": 1000, "tick": 30, "x": 1.5, "z": -2.0, "screen": "WORLD"}])
        self.write_state(wallTimeMs=1500, tick=45, player={"x": 2.0, "y": 0.5, "z": -2.0, "yawDeg": 0})
        probe.read_state(self.session)
        self.assertEqual(self.track()[-1], {"t": 1500, "tick": 45, "x": 2.0, "z": -2.0, "y": 0.5, "screen": "WORLD"})

    def test_off_the_world_nothing_is_recorded(self):
        self.write_state(world=False, screen="TITLE")
        probe.read_state(self.session)
        self.write_state(player={"yawDeg": 0})
        probe.read_state(self.session)
        self.assertEqual(self.track(), [])

    def test_the_track_draws(self):
        for k in range(5):
            self.write_state(wallTimeMs=1000 + k * 500, tick=k * 15, player={"x": k, "z": 0, "yawDeg": 0})
            probe.read_state(self.session)
        with open(self.session.path("session.json"), "w") as f:
            json.dump({"ticksPerSecond": 30}, f)
        run = load_run(self.session.dir)
        self.assertEqual(run.clock, "game")
        self.assertEqual([s.x for s in run.samples], [0, 1, 2, 3, 4])


@unittest.skipIf(strata_or_none() is None, "needs the Strata Python binding and a libstrata (STRATA_LIBRARY)")
class RenderTest(unittest.TestCase):
    """Real renders through Strata, headless (llvmpipe works)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with contextlib.redirect_stderr(io.StringIO()):
            self.runs = load_runs([FIXTURE])

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_a_still_png(self):
        png = os.path.join(self.tmp, "g.png")
        written = ghosts.render(self.runs, png=png, size=(320, 180))
        self.assertEqual(written["png"], png)
        with open(png, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertEqual(written["strata"], strata_or_none()[1].version)

    def test_the_trails_are_drawn(self):
        strata_mod, lib = strata_or_none()
        bounds = Bounds(self.runs)
        with ghosts.Renderer(strata_mod, lib, (320, 180)) as r:
            r.setup(bounds)
            r.draw(build_frame(self.runs, bounds, size=(320, 180), credit=""), os.path.join(self.tmp, "a.png"))
            rgba = r.engine.read_pixels()[0]
        pixels = [tuple(rgba[i:i + 3]) for i in range(0, len(rgba), 4)]
        orange = [p for p in pixels if p[0] > 180 and p[2] < 90 and p[0] > p[1] + 40]
        blue = [p for p in pixels if p[2] > 180 and p[0] < 120 and p[2] > p[1] + 20]
        self.assertGreater(len(orange), 30, "run 1's trail")
        self.assertGreater(len(blue), 30, "run 2's trail")

    @unittest.skipIf(not shutil.which("convert") and not shutil.which("magick"), "a GIF needs ImageMagick or Pillow")
    def test_an_animated_gif(self):
        gif = os.path.join(self.tmp, "g.gif")
        ghosts.render(self.runs, gif=gif, size=(160, 90), frames=4, fps=4)
        with open(gif, "rb") as f:
            self.assertEqual(f.read(6), b"GIF89a")


if __name__ == "__main__":
    unittest.main()
