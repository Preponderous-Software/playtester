"""Input, screenshots and waiting, for either driver.

Every harness command reaches the game through one of these, so ``pt`` and the
closed-loop probe commands (``face``, ``walkto``) work the same on both:

``X11Input``     the game's window in the session's own Xvfb, through xdotool
                 and ImageMagick (the default driver, ``"driver": "x11"``)
``StrataInput``  a Strata game's drive channel (``"driver": "strata"``):
                 injected events, a free or stepped clock, engine screenshots

``wait(seconds)`` is how a command lets game time pass. With the X11 driver
and the Strata driver's free clock it sleeps. With a stepped clock it steps
``round(seconds / step)`` frames, so a hold or a closed-loop turn lasts the
same game time on every run, whatever the machine's load.
"""

import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from . import strata_keys, xdo


class InputError(RuntimeError):
    """An input command that could not be carried out."""


class X11Input:
    stepped = False

    def __init__(self, env: Dict[str, str], window: str):
        self.env = env
        self.window = window

    def tap(self, combo: str) -> None:
        xdo.tap(self.env, combo)

    def hold(self, combo: str, seconds: float) -> None:
        xdo.hold(self.env, combo, seconds)

    def click(self, x: int, y: int, button: int = 1) -> None:
        xdo.click(self.env, self.window, x, y, button)

    def button_hold(self, seconds: float, button: int = 1) -> None:
        xdo.button_hold(self.env, seconds, button)

    def move(self, x: int, y: int) -> None:
        xdo.move(self.env, self.window, x, y)

    def look(self, dx: int, dy: int) -> None:
        xdo.move_relative(self.env, dx, dy)

    def drag(self, x1: int, y1: int, x2: int, y2: int, seconds: float, button: int = 3) -> None:
        xdo.drag(self.env, self.window, x1, y1, x2, y2, seconds, button)

    def scroll(self, clicks: int) -> None:
        xdo.scroll(self.env, clicks)

    def type_text(self, text: str) -> None:
        xdo.type_text(self.env, text)

    def wait(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))

    def screenshot(self, path: str) -> str:
        r = subprocess.run(["import", "-window", self.window or "root", path], env=self.env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, universal_newlines=True)
        if r.returncode != 0 or not os.path.isfile(path):
            raise InputError("screenshot failed: %s" % r.stderr.strip())
        return path


def utf8_chunks(text: str, limit: int = 31) -> List[str]:
    """``text`` split into pieces of at most ``limit`` UTF-8 bytes, never inside a character."""
    chunks, current = [], ""
    for ch in text:
        if len((current + ch).encode("utf-8")) > limit:
            chunks.append(current)
            current = ""
        current += ch
    if current:
        chunks.append(current)
    return chunks


class StrataInput:
    """Input through the drive channel (``strata_driver.Channel``).

    Free clock: the same timings as the X11 driver, minus the hover delays
    (an injected click cannot be missed by an immediate-mode UI). Stepped:
    holds and waits are whole frames, and every input command ends by
    stepping one frame, so its effect is in the next screenshot.
    """

    def __init__(self, channel: Any, clock: str, step: float, pointer_file: Optional[str] = None):
        self.channel = channel
        self.stepped = clock == "stepped"
        self.step_seconds = float(step)
        self.pointer_file = pointer_file

    # --- primitives ----------------------------------------------------------

    def event(self, type_: str, **fields: Any) -> None:
        fields["type"] = type_
        self.channel.request("event", **fields)

    def frames(self, seconds: float) -> int:
        return max(1, int(round(max(0.0, seconds) / self.step_seconds)))

    def step(self, frames: int) -> Dict[str, Any]:
        if not self.stepped:
            raise InputError("pt step needs a stepped session (pt start --clock stepped)")
        return self.channel.request("step", frames=int(frames), timeout=max(60.0, frames * 2.0))

    def wait(self, seconds: float) -> None:
        if self.stepped:
            if seconds > 0:
                self.step(self.frames(seconds))
        else:
            time.sleep(max(0.0, seconds))

    def settle(self) -> None:
        """After an input command: one frame (stepped) so it has been applied."""
        if self.stepped:
            self.step(1)

    def _pointer(self) -> List[float]:
        try:
            with open(self.pointer_file or "", encoding="utf-8") as f:
                x, y = f.read().split()
                return [float(x), float(y)]
        except (OSError, ValueError):
            return [0.0, 0.0]

    def _set_pointer(self, x: float, y: float) -> None:
        if self.pointer_file:
            with open(self.pointer_file, "w", encoding="utf-8") as f:
                f.write("%g %g" % (x, y))

    def _keys_down(self, combo: str) -> List[Any]:
        keys = strata_keys.combo_scancodes(xdo.combo_parts(combo))
        for code, mods in keys:
            self.event("key_down", scancode=code, modifiers=mods)
        return keys

    def _keys_up(self, keys: List[Any]) -> None:
        held = keys[-1][1] if keys else 0
        for code, _ in reversed(keys):
            held &= ~strata_keys.MODIFIER_BITS.get(code, 0)
            self.event("key_up", scancode=code, modifiers=held)

    # --- the commands --------------------------------------------------------

    def tap(self, combo: str) -> None:
        keys = self._keys_down(combo)
        self.wait(xdo.TAP_HOLD)
        self._keys_up(keys)
        if self.stepped:
            self.settle()
        else:
            time.sleep(xdo.TAP_GAP)

    def hold(self, combo: str, seconds: float) -> None:
        keys = self._keys_down(combo)
        self.wait(seconds)
        self._keys_up(keys)
        self.settle()

    def move(self, x: int, y: int) -> None:
        px, py = self._pointer()
        self.event("mouse_motion", x=x, y=y, dx=x - px, dy=y - py)
        self._set_pointer(x, y)
        self.settle()

    def click(self, x: int, y: int, button: int = 1) -> None:
        px, py = self._pointer()
        self.event("mouse_motion", x=x, y=y, dx=x - px, dy=y - py)
        self._set_pointer(x, y)
        self.event("mouse_button_down", button=button, x=x, y=y)
        self.wait(xdo.CLICK_HOLD if not self.stepped else 2 * self.step_seconds)
        self.event("mouse_button_up", button=button, x=x, y=y)
        self.settle()

    def button_hold(self, seconds: float, button: int = 1) -> None:
        x, y = self._pointer()
        self.event("mouse_button_down", button=button, x=x, y=y)
        self.wait(seconds)
        self.event("mouse_button_up", button=button, x=x, y=y)
        self.settle()

    def look(self, dx: int, dy: int) -> None:
        # One exact relative motion: a driven engine has no window edge to clamp at.
        self.event("mouse_motion", dx=dx, dy=dy)
        self.settle()

    def drag(self, x1: int, y1: int, x2: int, y2: int, seconds: float, button: int = 3) -> None:
        self.move(x1, y1)
        self.event("mouse_button_down", button=button, x=x1, y=y1)
        steps = self.frames(seconds) if self.stepped else max(10, int(seconds * 30))
        px, py = x1, y1
        for i in range(1, steps + 1):
            x, y = x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps
            self.event("mouse_motion", x=x, y=y, dx=x - px, dy=y - py)
            px, py = x, y
            if self.stepped:
                self.step(1)
            else:
                time.sleep(seconds / steps)
        self._set_pointer(x2, y2)
        self.event("mouse_button_up", button=button, x=x2, y=y2)
        self.settle()

    def scroll(self, clicks: int) -> None:
        # pt scroll: + is down; a wheel's y is + away from the user (up)
        for _ in range(abs(int(clicks))):
            self.event("mouse_wheel", y=-1.0 if clicks > 0 else 1.0)
        self.settle()

    def type_text(self, text: str) -> None:
        for chunk in utf8_chunks(text):
            self.event("text_input", text=chunk)
        self.settle()

    def screenshot(self, path: str) -> str:
        reply = self.channel.request("shot", path=os.path.abspath(path))
        if not os.path.isfile(path):
            raise InputError("screenshot failed: %s" % reply)
        return path
