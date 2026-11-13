"""Key names for the Windows driver: X keysym names to PC scancodes (set 1).

Profiles and agents name keys the way xdotool does (``Left``, ``F1``,
``space``, ``Shift_L+w``). The Windows driver sends them with ``SendInput``
and ``KEYEVENTF_SCANCODE``, because games that read DirectInput (Mount&Blade:
Warband among them) ignore virtual-key-only events such as ``keybd_event``.
Keys from the extended block (arrows, Insert/Delete/Home/End/Page, right
Control and Alt, keypad Enter and Divide) carry ``KEYEVENTF_EXTENDEDKEY``.

A name that is not here is an error, never a silent no-op. Letters are
case-insensitive (``W`` is the W key, without Shift).
"""

from typing import List, Tuple

# name -> (scancode, extended)
SCANCODES = {}  # type: Dict[str, Tuple[int, bool]]

for _row, _start in (("qwertyuiop", 0x10), ("asdfghjkl", 0x1E), ("zxcvbnm", 0x2C)):
    for _i, _c in enumerate(_row):
        SCANCODES[_c] = (_start + _i, False)
for _i, _c in enumerate("1234567890"):
    SCANCODES[_c] = (0x02 + _i, False)
for _i in range(10):
    SCANCODES["F%d" % (_i + 1)] = (0x3B + _i, False)
SCANCODES["F11"] = (0x57, False)
SCANCODES["F12"] = (0x58, False)

SCANCODES.update({
    "Escape": (0x01, False), "minus": (0x0C, False), "equal": (0x0D, False), "plus": (0x0D, False),
    "BackSpace": (0x0E, False), "Tab": (0x0F, False), "bracketleft": (0x1A, False),
    "bracketright": (0x1B, False), "Return": (0x1C, False), "Control_L": (0x1D, False),
    "semicolon": (0x27, False), "apostrophe": (0x28, False), "grave": (0x29, False), "Shift_L": (0x2A, False),
    "backslash": (0x2B, False), "comma": (0x33, False), "period": (0x34, False), "slash": (0x35, False),
    "Shift_R": (0x36, False), "KP_Multiply": (0x37, False), "Alt_L": (0x38, False), "space": (0x39, False),
    "Caps_Lock": (0x3A, False), "Num_Lock": (0x45, False), "Scroll_Lock": (0x46, False),
    "KP_7": (0x47, False), "KP_8": (0x48, False), "KP_9": (0x49, False), "KP_Subtract": (0x4A, False),
    "KP_4": (0x4B, False), "KP_5": (0x4C, False), "KP_6": (0x4D, False), "KP_Add": (0x4E, False),
    "KP_1": (0x4F, False), "KP_2": (0x50, False), "KP_3": (0x51, False), "KP_0": (0x52, False),
    "KP_Decimal": (0x53, False),
    "KP_Enter": (0x1C, True), "Control_R": (0x1D, True), "KP_Divide": (0x35, True), "Alt_R": (0x38, True),
    "Home": (0x47, True), "Up": (0x48, True), "Prior": (0x49, True), "Left": (0x4B, True),
    "Right": (0x4D, True), "End": (0x4F, True), "Down": (0x50, True), "Next": (0x51, True),
    "Insert": (0x52, True), "Delete": (0x53, True), "Super_L": (0x5B, True), "Super_R": (0x5C, True),
})

ALIASES = {
    "Enter": "Return", "enter": "Return", "Esc": "Escape", "esc": "Escape", "Page_Up": "Prior",
    "Page_Down": "Next", "Backspace": "BackSpace", "Space": "space",
    "ctrl": "Control_L", "Ctrl": "Control_L", "control": "Control_L", "shift": "Shift_L", "Shift": "Shift_L",
    "alt": "Alt_L", "Alt": "Alt_L", "super": "Super_L", "Super": "Super_L", "Meta_L": "Alt_L",
}


class UnknownKey(ValueError):
    """A key name the Windows driver has no scancode for."""


def scancode(name: str) -> Tuple[int, bool]:
    """``(scancode, extended)`` of one key name; raises UnknownKey."""
    key = ALIASES.get(name, name)
    if key in SCANCODES:
        return SCANCODES[key]
    if len(key) == 1 and key.lower() in SCANCODES:
        return SCANCODES[key.lower()]
    raise UnknownKey("no scancode for key %r (the Windows driver knows: letters, digits, F1-F12, arrows, "
                     "Return, Escape, space, Tab, BackSpace, punctuation names, KP_*, Home/End/Prior/Next/"
                     "Insert/Delete, and Shift/Control/Alt/Super _L/_R)" % name)


def combo_scancodes(parts: List[str]) -> List[List[object]]:
    """``[[scancode, extended], ...]`` for the keys of one combo, in press order (JSON-ready)."""
    return [list(scancode(p)) for p in parts]
