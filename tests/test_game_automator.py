"""The mocked decide and act seams and GameAutomator's cycle, with PIL, pyautogui and pynput stubbed (no display needed)."""

import importlib
import sys
import types
import unittest
from unittest import mock

import tests.helpers  # noqa: F401  (puts src on sys.path)


class FakeCapture:
    """Stands in for ScreenshotCapture: records which capture method was called."""

    def __init__(self):
        self.screenshot_count = 0
        self.calls = []

    def capture_full_screen(self):
        self.screenshot_count += 1
        self.calls.append(("full",))
        return "shot-%d" % self.screenshot_count

    def capture_region(self, x, y, width, height):
        self.screenshot_count += 1
        self.calls.append(("region", x, y, width, height))
        return "shot-%d" % self.screenshot_count


def automation_stubs():
    """Module stubs for PIL, pyautogui and pynput, which the automation classes import."""
    pil = types.ModuleType("PIL")
    pil.Image = types.ModuleType("PIL.Image")
    pil.Image.Image = object
    pyautogui = types.ModuleType("pyautogui")
    pyautogui.press = mock.Mock()
    pynput = types.ModuleType("pynput")
    pynput.keyboard = types.ModuleType("pynput.keyboard")
    pynput.keyboard.Key = mock.Mock()
    pynput.keyboard.Controller = mock.Mock
    pynput.mouse = types.ModuleType("pynput.mouse")
    pynput.mouse.Button = mock.Mock()
    pynput.mouse.Controller = mock.Mock
    return {
        "PIL": pil, "PIL.Image": pil.Image, "pyautogui": pyautogui,
        "pynput": pynput, "pynput.keyboard": pynput.keyboard, "pynput.mouse": pynput.mouse,
    }


class AutomationTestCase(unittest.TestCase):
    """Imports the automation modules fresh against the stubs, with time.sleep patched out."""

    MODULES = ("ai_decision_engine", "action_executor", "screenshot_capture", "game_automator")

    def setUp(self):
        patcher = mock.patch.dict(sys.modules, automation_stubs())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.forget_stubbed_submodules)
        for name in self.MODULES:
            sys.modules.pop("playtester." + name, None)
        self.engine_mod = importlib.import_module("playtester.ai_decision_engine")
        self.executor_mod = importlib.import_module("playtester.action_executor")
        self.automator_mod = importlib.import_module("playtester.game_automator")
        self.GameAction = self.engine_mod.GameAction
        sleep = mock.patch("time.sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def forget_stubbed_submodules(self):
        """Drop the package attributes the stubbed imports set, so later tests import afresh."""
        package = sys.modules["playtester"]
        for name in self.MODULES:
            package.__dict__.pop(name, None)

    def automator(self, actions, loop_delay=1.0):
        """A GameAutomator over a fake capture, the mocked engine and the mocked executor."""
        engine = self.engine_mod.MockedAIDecisionEngine(actions)
        executor = self.executor_mod.MockedActionExecutor(delay_between_actions=0.25)
        return self.automator_mod.GameAutomator(FakeCapture(), engine, executor, loop_delay=loop_delay)


class MockedAIDecisionEngineTest(AutomationTestCase):
    def test_cycles_through_the_given_actions_in_order(self):
        actions = [self.GameAction.MOVE_LEFT, self.GameAction.WAIT, self.GameAction.QUIT]
        engine = self.engine_mod.MockedAIDecisionEngine(actions)
        decided = [engine.analyze_and_decide("shot") for _ in range(7)]
        self.assertEqual(decided, actions * 2 + [self.GameAction.MOVE_LEFT])
        self.assertEqual(engine.decision_count, 7)

    def test_confidence_is_zero_until_a_decision_then_fixed(self):
        engine = self.engine_mod.MockedAIDecisionEngine([self.GameAction.MENU])
        self.assertEqual(engine.get_decision_confidence(), 0.0)
        engine.analyze_and_decide("shot", {"goal": "ignored"})
        self.assertEqual(engine.get_decision_confidence(), 0.7)

    def test_abstract_engine_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            self.engine_mod.AIDecisionEngine([self.GameAction.WAIT])


class MockedActionExecutorTest(AutomationTestCase):
    def test_records_each_action_with_its_params_and_waits(self):
        executor = self.executor_mod.MockedActionExecutor(delay_between_actions=0.25)
        self.assertTrue(executor.execute_action(self.GameAction.MOVE_UP))
        self.assertTrue(executor.execute_action(self.GameAction.ACTION_PRIMARY, {"hold": 2}))
        history = executor.get_execution_history()
        self.assertEqual([entry["action"] for entry in history],
                         [self.GameAction.MOVE_UP, self.GameAction.ACTION_PRIMARY])
        self.assertEqual([entry["params"] for entry in history], [None, {"hold": 2}])
        self.assertEqual(executor.action_count, 2)
        self.assertEqual(self.sleep.call_args_list, [mock.call(0.25), mock.call(0.25)])

    def test_presses_no_keys(self):
        executor = self.executor_mod.MockedActionExecutor()
        executor.execute_action(self.GameAction.QUIT)
        sys.modules["pyautogui"].press.assert_not_called()


class GameAutomatorTest(AutomationTestCase):
    def test_single_cycle_captures_decides_and_executes(self):
        automator = self.automator([self.GameAction.MOVE_RIGHT, self.GameAction.MOVE_DOWN])
        first = automator.run_single_cycle()
        second = automator.run_single_cycle()
        self.assertEqual((first["cycle"], first["action"]), (1, self.GameAction.MOVE_RIGHT))
        self.assertEqual((second["cycle"], second["action"]), (2, self.GameAction.MOVE_DOWN))
        self.assertEqual(first["confidence"], 0.7)
        self.assertTrue(first["success"])
        self.assertIsInstance(first["timestamp"], float)
        self.assertEqual(automator.capture.calls, [("full",), ("full",)])
        self.assertEqual([entry["action"] for entry in automator.executor.get_execution_history()],
                         [self.GameAction.MOVE_RIGHT, self.GameAction.MOVE_DOWN])

    def test_region_captures_that_region(self):
        automator = self.automator([self.GameAction.WAIT])
        automator.run_single_cycle(region=(10, 20, 300, 200))
        self.assertEqual(automator.capture.calls, [("region", 10, 20, 300, 200)])

    def test_engine_receives_the_screenshot_and_merged_context(self):
        automator = self.automator([self.GameAction.WAIT])
        automator.set_game_context({"goal": "wood", "lives": 3})
        automator.set_game_context({"lives": 2})
        with mock.patch.object(automator.decision_engine, "analyze_and_decide",
                               wraps=automator.decision_engine.analyze_and_decide) as decide:
            automator.run_single_cycle()
        decide.assert_called_once_with("shot-1", {"goal": "wood", "lives": 2})

    def test_failed_execution_is_reported_and_still_counts_the_cycle(self):
        automator = self.automator([self.GameAction.MENU])
        automator.executor.execute_action = mock.Mock(return_value=False)
        info = automator.run_single_cycle()
        self.assertFalse(info["success"])
        self.assertEqual(automator.cycle_count, 1)

    def test_continuous_stops_at_max_cycles_and_sleeps_between(self):
        automator = self.automator([self.GameAction.MOVE_UP, self.GameAction.MOVE_DOWN], loop_delay=0.5)
        infos = list(automator.run_continuous(max_cycles=3))
        self.assertEqual([info["cycle"] for info in infos], [1, 2, 3])
        self.assertEqual([info["action"] for info in infos],
                         [self.GameAction.MOVE_UP, self.GameAction.MOVE_DOWN, self.GameAction.MOVE_UP])
        loop_sleeps = [c for c in self.sleep.call_args_list if c == mock.call(0.5)]
        self.assertEqual(len(loop_sleeps), 3)

    def test_continuous_stops_when_the_condition_holds(self):
        automator = self.automator([self.GameAction.WAIT])
        infos = list(automator.run_continuous(stop_condition=lambda: automator.cycle_count >= 2))
        self.assertEqual(len(infos), 2)

    def test_continuous_max_cycles_zero_runs_no_cycles(self):
        # 0 is a limit of zero cycles, not "no limit" (only None means that).
        automator = self.automator([self.GameAction.WAIT])
        infos = list(automator.run_continuous(max_cycles=0,
                                              stop_condition=lambda: automator.cycle_count >= 4))
        self.assertEqual(infos, [])
        self.assertEqual(automator.cycle_count, 0)
        self.assertEqual(automator.executor.get_execution_history(), [])
        self.assertEqual(automator.capture.calls, [])

    def test_stop_ends_a_running_loop_after_the_current_cycle(self):
        automator = self.automator([self.GameAction.WAIT])
        loop = automator.run_continuous()
        next(loop)
        self.assertTrue(automator.is_running)
        automator.stop()
        self.assertEqual(list(loop), [])
        self.assertEqual(automator.cycle_count, 1)

    def test_stats_count_cycles_actions_and_screenshots(self):
        automator = self.automator([self.GameAction.MOVE_LEFT])
        list(automator.run_continuous(max_cycles=2))
        automator.run_single_cycle(region=(0, 0, 1, 1))
        self.assertEqual(automator.get_stats(),
                         {"total_cycles": 3, "actions_executed": 3, "screenshots_taken": 3})


if __name__ == "__main__":
    unittest.main()
