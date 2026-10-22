"""Keyboard and mouse input through xdotool, into one session's virtual display.

Every function takes the session's environment (``DISPLAY`` set to its own
Xvfb), so input can never reach another session's game or the desktop.
Coordinates are window coordinates, as in screenshots.
"""

import subprocess
import time
from typing import Dict, List

# A key tap: down, held this long, up, then this long before the next key.
TAP_HOLD = 0.12
TAP_GAP = 0.25
# Immediate-mode UIs at a few frames a second miss a click unless the pointer
# hovers for a few frames first (learned on Dear ImGui at 3-10 fps).
HOVER_BEFORE_CLICK = 0.3
CLICK_HOLD = 0.15


def run(env: Dict[str, str], *args, check: bool = False) -> str:
    """Runs xdotool with ``args``; returns its standard output."""
    r = subprocess.run(["xdotool"] + [str(a) for a in args], env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, universal_newlines=True)
    if check and r.returncode != 0:
        raise RuntimeError("xdotool %s failed" % " ".join(str(a) for a in args))
    return r.stdout


def combo_parts(combo: str) -> List[str]:
    """``Shift_L+w`` -> ``["Shift_L", "w"]``; a lone ``+`` is the plus key."""
    if combo == "+":
        return ["plus"]
    return [p for p in combo.split("+") if p]


def combo_down(env: Dict[str, str], combo: str) -> None:
    for key in combo_parts(combo):
        run(env, "keydown", key)


def combo_up(env: Dict[str, str], combo: str) -> None:
    for key in reversed(combo_parts(combo)):
        run(env, "keyup", key)


def focus(env: Dict[str, str], window: str) -> None:
    if window:
        run(env, "windowfocus", window)


def tap(env: Dict[str, str], combo: str) -> None:
    combo_down(env, combo)
    time.sleep(TAP_HOLD)
    combo_up(env, combo)
    time.sleep(TAP_GAP)


def hold(env: Dict[str, str], combo: str, seconds: float) -> None:
    combo_down(env, combo)
    time.sleep(max(0.0, seconds))
    combo_up(env, combo)


def move(env: Dict[str, str], window: str, x: int, y: int) -> None:
    run(env, "mousemove", "--window", window, int(x), int(y))


def move_relative(env: Dict[str, str], dx: int, dy: int, step: int = 120, pause: float = 0.02) -> None:
    """Relative pointer motion, in steps: games in relative mouse mode (mouse look) read the deltas."""
    dx, dy = int(dx), int(dy)
    steps = max(1, (max(abs(dx), abs(dy)) + step - 1) // step)
    sent_x = sent_y = 0
    for i in range(1, steps + 1):
        tx, ty = dx * i // steps, dy * i // steps
        run(env, "mousemove_relative", "--", tx - sent_x, ty - sent_y)
        sent_x, sent_y = tx, ty
        time.sleep(pause)


def click(env: Dict[str, str], window: str, x: int, y: int, button: int = 1) -> None:
    move(env, window, x, y)
    time.sleep(HOVER_BEFORE_CLICK)
    run(env, "mousedown", button)
    time.sleep(CLICK_HOLD)
    run(env, "mouseup", button)
    time.sleep(0.2)


def button_hold(env: Dict[str, str], seconds: float, button: int = 1) -> None:
    """Holds a mouse button where the pointer is (for games where holding the button works on a target)."""
    run(env, "mousedown", button)
    time.sleep(max(0.0, seconds))
    run(env, "mouseup", button)


def drag(env: Dict[str, str], window: str, x1: int, y1: int, x2: int, y2: int, seconds: float, button: int = 3) -> None:
    move(env, window, x1, y1)
    time.sleep(HOVER_BEFORE_CLICK)
    run(env, "mousedown", button)
    steps = max(10, int(seconds * 30))
    for i in range(1, steps + 1):
        move(env, window, x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
        time.sleep(seconds / steps)
    time.sleep(0.1)
    run(env, "mouseup", button)


def type_text(env: Dict[str, str], text: str) -> None:
    run(env, "type", "--delay", 80, "--", text)


def scroll(env: Dict[str, str], clicks: int) -> None:
    """Mouse wheel: positive scrolls down (button 5), negative up (button 4)."""
    button = 5 if clicks > 0 else 4
    for _ in range(abs(int(clicks))):
        run(env, "click", button)
        time.sleep(0.08)
