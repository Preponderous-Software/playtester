"""CI smoke test, run under xvfb-run with a 1280x720 virtual screen.

Imports the package (pyautogui needs a display), captures real screenshots of
the virtual screen and drives GameAutomator through four cycles with the
mocked decision engine and executor, so no input reaches any real window.
"""
from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import GameAction, MockedAIDecisionEngine
from playtester.action_executor import MockedActionExecutor
from playtester.games import OphidianAutomator, RoamAutomator  # noqa: F401  (import check)

capture = ScreenshotCapture()
w, h = capture.get_screen_size()
assert (w, h) == (1280, 720), (w, h)
shot = capture.capture_full_screen()
assert shot.size == (1280, 720), shot.size
assert capture.capture_region(10, 20, 64, 48).size == (64, 48)

actions = [GameAction.MOVE_UP, GameAction.MOVE_DOWN, GameAction.ACTION_PRIMARY]
executor = MockedActionExecutor(delay_between_actions=0)
auto = GameAutomator(capture, MockedAIDecisionEngine(actions), executor, loop_delay=0)
results = [auto.run_single_cycle(region=(0, 0, 100, 100)) for _ in range(4)]
assert [r["action"] for r in results] == actions + actions[:1], results
assert all(r["success"] for r in results)
assert [e["action"] for e in executor.get_execution_history()] == actions + actions[:1]
print("ok: screen", (w, h), "- 4 automation cycles:", [r["action"].name for r in results])
