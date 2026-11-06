"""The input layer: the xdotool commands sent, and the drive-channel events (no display, no game)."""

import os
import tempfile
import unittest
from unittest import mock

import tests.helpers  # noqa: F401  (puts src on sys.path)
from playtester.harness import inputs, strata_keys, xdo

ENV = {"DISPLAY": ":77"}
SHIFT = strata_keys.MOD_LSHIFT


class XdoCase(unittest.TestCase):
    """Runs xdo functions with xdotool and the sleeps replaced; ``calls`` holds each xdotool argv."""

    def setUp(self):
        self.calls = []
        self.sleeps = []
        patcher = mock.patch.object(xdo.subprocess, "run", side_effect=self.fake_run)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(xdo.time, "sleep", side_effect=self.sleeps.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_run(self, argv, **kwargs):
        self.assertEqual(argv[0], "xdotool")
        self.assertEqual(kwargs["env"], ENV)  # never another session's display
        self.calls.append(argv[1:])
        return mock.Mock(returncode=0, stdout="out\n")

    def pointer_moves(self):
        return [c for c in self.calls if c[0] == "mousemove"]


class XdoRunTest(XdoCase):
    def test_arguments_become_strings_and_stdout_is_returned(self):
        self.assertEqual(xdo.run(ENV, "mousedown", 3), "out\n")
        self.assertEqual(self.calls, [["mousedown", "3"]])

    def test_a_failure_raises_only_when_checked(self):
        with mock.patch.object(xdo.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="")):
            self.assertEqual(xdo.run(ENV, "key", "a"), "")
            with self.assertRaisesRegex(RuntimeError, "xdotool key a failed"):
                xdo.run(ENV, "key", "a", check=True)


class ComboTest(XdoCase):
    def test_combo_parts(self):
        self.assertEqual(xdo.combo_parts("w"), ["w"])
        self.assertEqual(xdo.combo_parts("Shift_L+w"), ["Shift_L", "w"])
        self.assertEqual(xdo.combo_parts("+"), ["plus"])

    def test_keys_are_released_in_reverse_order(self):
        xdo.hold(ENV, "Control_L+Shift_L+s", 1.5)
        self.assertEqual(self.calls, [["keydown", "Control_L"], ["keydown", "Shift_L"], ["keydown", "s"],
                                      ["keyup", "s"], ["keyup", "Shift_L"], ["keyup", "Control_L"]])
        self.assertEqual(self.sleeps, [1.5])

    def test_a_negative_hold_does_not_sleep_negatively(self):
        xdo.hold(ENV, "w", -1)
        self.assertEqual(self.sleeps, [0.0])

    def test_a_tap_holds_the_key_then_leaves_a_gap(self):
        xdo.tap(ENV, "space")
        self.assertEqual(self.calls, [["keydown", "space"], ["keyup", "space"]])
        self.assertEqual(self.sleeps, [xdo.TAP_HOLD, xdo.TAP_GAP])


class PointerTest(XdoCase):
    def test_focus_needs_a_window(self):
        xdo.focus(ENV, "")
        self.assertEqual(self.calls, [])
        xdo.focus(ENV, "123")
        self.assertEqual(self.calls, [["windowfocus", "123"]])

    def test_move_truncates_to_whole_window_coordinates(self):
        xdo.move(ENV, "9", 10.7, 20)
        self.assertEqual(self.calls, [["mousemove", "--window", "9", "10", "20"]])

    def test_a_click_hovers_before_it_presses(self):
        xdo.click(ENV, "9", 5, 6, button=3)
        self.assertEqual(self.calls, [["mousemove", "--window", "9", "5", "6"], ["mousedown", "3"], ["mouseup", "3"]])
        self.assertEqual(self.sleeps[:2], [xdo.HOVER_BEFORE_CLICK, xdo.CLICK_HOLD])

    def test_button_hold_stays_where_the_pointer_is(self):
        xdo.button_hold(ENV, 2.0, 1)
        self.assertEqual(self.calls, [["mousedown", "1"], ["mouseup", "1"]])
        self.assertEqual(self.sleeps, [2.0])

    def relative_deltas(self):
        for call in self.calls:
            self.assertEqual(call[:2], ["mousemove_relative", "--"])
        return [(int(c[2]), int(c[3])) for c in self.calls]

    def test_relative_motion_is_split_into_steps_that_add_up_exactly(self):
        xdo.move_relative(ENV, 250, -100)
        deltas = self.relative_deltas()
        self.assertEqual(len(deltas), 3)  # 250 is more than two steps of 120
        self.assertEqual(sum(d[0] for d in deltas), 250)
        self.assertEqual(sum(d[1] for d in deltas), -100)
        self.assertTrue(all(abs(d[0]) <= 120 and abs(d[1]) <= 120 for d in deltas))

    def test_a_negative_motion_is_exact_too(self):
        xdo.move_relative(ENV, -7, 1000, step=64)
        deltas = self.relative_deltas()
        self.assertEqual((sum(d[0] for d in deltas), sum(d[1] for d in deltas)), (-7, 1000))

    def test_no_motion_is_still_one_step(self):
        xdo.move_relative(ENV, 0, 0)
        self.assertEqual(self.relative_deltas(), [(0, 0)])

    def test_a_drag_presses_at_the_start_and_releases_at_the_end(self):
        xdo.drag(ENV, "9", 0, 100, 30, 40, 1.0, button=2)
        kinds = [c[0] for c in self.calls]
        self.assertEqual(kinds[:2], ["mousemove", "mousedown"])
        self.assertEqual(kinds[-1], "mouseup")
        self.assertEqual(self.calls[0], ["mousemove", "--window", "9", "0", "100"])
        self.assertEqual(self.calls[1], ["mousedown", "2"])
        self.assertEqual(self.calls[-1], ["mouseup", "2"])
        moves = self.pointer_moves()
        self.assertEqual(len(moves), 1 + 30)  # 30 steps a second
        self.assertEqual(moves[-1], ["mousemove", "--window", "9", "30", "40"])

    def test_a_short_drag_still_takes_ten_steps(self):
        xdo.drag(ENV, "9", 0, 0, 10, 10, 0.1)
        self.assertEqual(len(self.pointer_moves()), 1 + 10)
        self.assertEqual(self.calls[1], ["mousedown", "3"])  # the default button

    def test_typing_ends_options_so_text_may_start_with_a_dash(self):
        xdo.type_text(ENV, "--hello")
        self.assertEqual(self.calls, [["type", "--delay", "80", "--", "--hello"]])

    def test_scroll_down_is_button_5_and_up_is_button_4(self):
        xdo.scroll(ENV, 2)
        self.assertEqual(self.calls, [["click", "5"], ["click", "5"]])
        del self.calls[:]
        xdo.scroll(ENV, -3)
        self.assertEqual(self.calls, [["click", "4"]] * 3)
        del self.calls[:]
        xdo.scroll(ENV, 0)
        self.assertEqual(self.calls, [])


class X11InputTest(XdoCase):
    def test_commands_reach_the_sessions_display_and_window(self):
        inp = inputs.X11Input(ENV, "42")
        self.assertFalse(inp.stepped)
        inp.move(1, 2)
        inp.look(3, 4)
        inp.scroll(1)
        inp.type_text("hi")
        self.assertEqual(self.calls, [["mousemove", "--window", "42", "1", "2"],
                                      ["mousemove_relative", "--", "3", "4"],
                                      ["click", "5"],
                                      ["type", "--delay", "80", "--", "hi"]])

    def test_wait_never_sleeps_a_negative_time(self):
        inputs.X11Input(ENV, "42").wait(-2)
        self.assertEqual(self.sleeps, [0.0])


class X11ScreenshotTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="pt-inputs-")
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "shot.png")

    def test_the_window_is_captured_and_an_empty_one_means_the_root(self):
        argv = []

        def fake_import(command, **kwargs):
            argv.append(command)
            with open(command[-1], "wb"):
                pass
            return mock.Mock(returncode=0, stderr="")

        with mock.patch.object(inputs.subprocess, "run", side_effect=fake_import):
            self.assertEqual(inputs.X11Input(ENV, "42").screenshot(self.path), self.path)
            inputs.X11Input(ENV, "").screenshot(self.path)
        self.assertEqual(argv, [["import", "-window", "42", self.path], ["import", "-window", "root", self.path]])

    def test_a_failed_capture_reports_why(self):
        failed = mock.Mock(returncode=1, stderr="  no such window \n")
        with mock.patch.object(inputs.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(inputs.InputError, "screenshot failed: no such window$"):
                inputs.X11Input(ENV, "42").screenshot(self.path)

    def test_a_capture_that_wrote_no_file_is_a_failure(self):
        quiet = mock.Mock(returncode=0, stderr="")
        with mock.patch.object(inputs.subprocess, "run", return_value=quiet):
            with self.assertRaises(inputs.InputError):
                inputs.X11Input(ENV, "42").screenshot(self.path)


class Utf8ChunksTest(unittest.TestCase):
    def test_nothing_is_no_chunks(self):
        self.assertEqual(inputs.utf8_chunks(""), [])

    def test_a_chunk_stops_before_a_character_that_would_not_fit(self):
        self.assertEqual(inputs.utf8_chunks("abé", limit=3), ["ab", "é"])
        self.assertEqual(inputs.utf8_chunks("abc", limit=3), ["abc"])


class FakeChannel:
    """Records every request as ``(op, fields)``; ``shot`` writes the file unless told not to."""

    def __init__(self, writes_shot=True):
        self.requests = []
        self.writes_shot = writes_shot

    def request(self, op, **fields):
        self.requests.append((op, fields))
        if op == "shot" and self.writes_shot:
            with open(fields["path"], "wb"):
                pass
        return {"ok": True, "op": op}

    def log(self):
        """The requests as short tuples: ``("step", n)`` or ``(event type, field, ...)`` in sorted field order."""
        out = []
        for op, fields in self.requests:
            if op == "step":
                out.append(("step", fields["frames"]))
            elif op == "event":
                rest = {k: v for k, v in fields.items() if k != "type"}
                out.append((fields["type"],) + tuple(v for _, v in sorted(rest.items())))
            else:
                out.append((op,))
        return out


class StrataCase(unittest.TestCase):
    """A stepped session at 0.05 s a frame, with the free clock's sleeps recorded."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="pt-strata-input-")
        self.addCleanup(self.dir.cleanup)
        self.pointer = os.path.join(self.dir.name, "pointer")
        self.channel = FakeChannel()
        self.sleeps = []
        patcher = mock.patch.object(inputs.time, "sleep", side_effect=self.sleeps.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stepped(self):
        return inputs.StrataInput(self.channel, "stepped", 0.05, self.pointer)

    def free(self):
        return inputs.StrataInput(self.channel, "free", 0.05, self.pointer)


class StrataClockTest(StrataCase):
    def test_frames_round_to_whole_frames_and_never_to_none(self):
        inp = self.stepped()
        self.assertEqual(inp.frames(1.0), 20)
        self.assertEqual(inp.frames(0.12), 2)
        self.assertEqual(inp.frames(0.001), 1)
        self.assertEqual(inp.frames(-1), 1)

    def test_a_stepped_wait_runs_frames_and_does_not_sleep(self):
        self.stepped().wait(0.5)
        self.assertEqual(self.channel.log(), [("step", 10)])
        self.assertEqual(self.sleeps, [])

    def test_waiting_no_time_on_a_stepped_clock_runs_no_frame(self):
        self.stepped().wait(0)
        self.assertEqual(self.channel.log(), [])

    def test_a_free_wait_sleeps(self):
        self.free().wait(0.5)
        self.free().wait(-1)
        self.assertEqual(self.channel.log(), [])
        self.assertEqual(self.sleeps, [0.5, 0.0])

    def test_step_on_a_free_clock_is_refused(self):
        with self.assertRaisesRegex(inputs.InputError, "stepped"):
            self.free().step(1)

    def test_step_timeout_grows_with_the_frames(self):
        inp = self.stepped()
        inp.step(10)
        inp.step(100)
        self.assertEqual([f["timeout"] for _, f in self.channel.requests], [60.0, 200.0])


class StrataKeysTest(StrataCase):
    def test_modifiers_are_held_going_down_and_let_go_coming_up(self):
        self.stepped().hold("Shift_L+w", 1.0)
        self.assertEqual(self.channel.log(), [
            ("key_down", SHIFT, 225),
            ("key_down", SHIFT, 26),
            ("step", 20),
            ("key_up", SHIFT, 26),   # shift is still down when w comes up
            ("key_up", 0, 225),      # and gone in the event that releases it
            ("step", 1),             # the release has been applied before the command returns
        ])

    def test_a_stepped_tap_is_a_whole_number_of_frames(self):
        self.stepped().tap("space")
        self.assertEqual(self.channel.log(), [("key_down", 0, 44), ("step", 2), ("key_up", 0, 44), ("step", 1)])
        self.assertEqual(self.sleeps, [])

    def test_a_free_tap_uses_the_x11_timings(self):
        self.free().tap("space")
        self.assertEqual(self.sleeps, [xdo.TAP_HOLD, xdo.TAP_GAP])
        self.assertEqual(self.channel.log(), [("key_down", 0, 44), ("key_up", 0, 44)])

    def test_an_unknown_key_sends_nothing(self):
        with self.assertRaises(strata_keys.UnknownKey):
            self.stepped().tap("Shift_L+Hyper_Q")
        self.assertEqual(self.channel.log(), [])


class StrataPointerTest(StrataCase):
    def test_move_reports_the_delta_from_the_last_position(self):
        inp = self.stepped()
        inp.move(10, 20)
        inp.move(13, 16)
        self.assertEqual(self.channel.log(), [("mouse_motion", 10, 20, 10, 20), ("step", 1),
                                              ("mouse_motion", 3, -4, 13, 16), ("step", 1)])

    def test_the_pointer_lasts_between_commands(self):
        self.stepped().move(10, 20)
        del self.channel.requests[:]
        self.stepped().move(11, 20)  # every pt command builds a new StrataInput
        self.assertEqual(self.channel.log()[0], ("mouse_motion", 1, 0, 11, 20))

    def test_no_pointer_file_or_a_garbled_one_starts_at_the_origin(self):
        inp = inputs.StrataInput(self.channel, "stepped", 0.05)
        inp.move(4, 5)
        inp.move(4, 5)  # nowhere to remember the first move
        self.assertEqual(self.channel.log()[2], ("mouse_motion", 4, 5, 4, 5))
        del self.channel.requests[:]
        with open(self.pointer, "w", encoding="utf-8") as f:
            f.write("not a position")
        self.stepped().move(2, 3)
        self.assertEqual(self.channel.log()[0], ("mouse_motion", 2, 3, 2, 3))

    def test_a_click_moves_there_presses_and_releases(self):
        self.stepped().click(30, 40, button=3)
        self.assertEqual(self.channel.log(), [("mouse_motion", 30, 40, 30, 40),
                                              ("mouse_button_down", 3, 30, 40),
                                              ("step", 2),
                                              ("mouse_button_up", 3, 30, 40),
                                              ("step", 1)])

    def test_a_free_click_has_no_hover_delay(self):
        self.free().click(1, 2)
        self.assertEqual(self.sleeps, [xdo.CLICK_HOLD])

    def test_button_hold_presses_where_the_pointer_was_left(self):
        inp = self.stepped()
        inp.move(7, 8)
        del self.channel.requests[:]
        inp.button_hold(0.5)
        self.assertEqual(self.channel.log(), [("mouse_button_down", 1, 7, 8), ("step", 10),
                                              ("mouse_button_up", 1, 7, 8), ("step", 1)])

    def test_look_is_one_exact_relative_motion(self):
        self.stepped().look(-500, 12)
        self.assertEqual(self.channel.log(), [("mouse_motion", -500, 12), ("step", 1)])
        self.assertFalse(os.path.exists(self.pointer))  # looking does not move the pointer

    def test_a_stepped_drag_moves_one_step_a_frame_and_ends_exactly(self):
        self.stepped().drag(0, 0, 10, -5, 0.1, button=2)
        log = self.channel.log()
        self.assertEqual(log[:3], [("mouse_motion", 0, 0, 0, 0), ("step", 1), ("mouse_button_down", 2, 0, 0)])
        self.assertEqual(log[3:9], [("mouse_motion", 5, -3, 5, -3), ("step", 1),
                                    ("mouse_motion", 5, -2, 10, -5), ("step", 1),
                                    ("mouse_button_up", 2, 10, -5), ("step", 1)])
        with open(self.pointer, encoding="utf-8") as f:
            self.assertEqual(f.read(), "10 -5")

    def test_a_free_drag_takes_at_least_ten_steps_over_its_duration(self):
        self.free().drag(0, 0, 10, 10, 0.1)
        motions = [e for e in self.channel.log() if e[0] == "mouse_motion"]
        self.assertEqual(len(motions), 1 + 10)
        self.assertEqual(len(self.sleeps), 10)
        self.assertAlmostEqual(sum(self.sleeps), 0.1)


class StrataTextAndWheelTest(StrataCase):
    def test_positive_scroll_is_down_which_is_a_negative_wheel(self):
        self.stepped().scroll(2)
        self.assertEqual(self.channel.log(), [("mouse_wheel", -1.0), ("mouse_wheel", -1.0), ("step", 1)])

    def test_negative_scroll_is_up(self):
        self.stepped().scroll(-1)
        self.assertEqual(self.channel.log(), [("mouse_wheel", 1.0), ("step", 1)])

    def test_long_text_goes_in_character_safe_chunks(self):
        text = "é" * 20
        self.stepped().type_text(text)
        sent = [f["text"] for op, f in self.channel.requests if op == "event"]
        self.assertEqual(sent, ["é" * 15, "é" * 5])
        self.assertEqual(self.channel.log()[-1], ("step", 1))


class StrataScreenshotTest(StrataCase):
    def test_the_engine_is_given_an_absolute_path(self):
        path = os.path.join(self.dir.name, "s.png")
        relative = os.path.relpath(path)
        self.assertEqual(self.stepped().screenshot(relative), relative)
        self.assertEqual(self.channel.requests, [("shot", {"path": os.path.abspath(path)})])

    def test_a_reply_with_no_file_is_a_failure(self):
        self.channel.writes_shot = False
        with self.assertRaisesRegex(inputs.InputError, "screenshot failed"):
            self.stepped().screenshot(os.path.join(self.dir.name, "s.png"))


if __name__ == "__main__":
    unittest.main()
