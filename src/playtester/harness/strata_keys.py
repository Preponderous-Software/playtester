"""Key names for the Strata driver: X keysym names to USB HID usage ids.

Profiles and agents name keys the way xdotool does (``Left``, ``F1``,
``space``, ``Shift_L+w``). A Strata game reads ``StrataEvent.scancode``, which
carries USB HID usage ids (the values SDL3 scancodes use). This table maps one
to the other. A name that is not here is an error, never a silent no-op.

Letters are case-insensitive (``W`` is the W key, without Shift).
"""

from typing import Dict, List, Tuple

# SDL3 SDL_Keymod bits, sent in StrataEvent.modifiers while a modifier is held.
MOD_LSHIFT = 0x0001
MOD_RSHIFT = 0x0002
MOD_LCTRL = 0x0040
MOD_RCTRL = 0x0080
MOD_LALT = 0x0100
MOD_RALT = 0x0200
MOD_LGUI = 0x0400
MOD_RGUI = 0x0800

SCANCODES = {}  # type: Dict[str, int]

for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    SCANCODES[_c] = 4 + _i
for _i, _c in enumerate("123456789"):
    SCANCODES[_c] = 30 + _i
SCANCODES["0"] = 39
for _i in range(12):
    SCANCODES["F%d" % (_i + 1)] = 58 + _i
for _i in range(1, 10):
    SCANCODES["KP_%d" % _i] = 88 + _i
SCANCODES["KP_0"] = 98

SCANCODES.update({
    "Return": 40, "Escape": 41, "BackSpace": 42, "Tab": 43, "space": 44,
    "minus": 45, "equal": 46, "plus": 46, "bracketleft": 47, "bracketright": 48, "backslash": 49,
    "semicolon": 51, "apostrophe": 52, "grave": 53, "comma": 54, "period": 55, "slash": 56,
    "Caps_Lock": 57, "Print": 70, "Scroll_Lock": 71, "Pause": 72, "Insert": 73, "Home": 74,
    "Prior": 75, "Delete": 76, "End": 77, "Next": 78,
    "Right": 79, "Left": 80, "Down": 81, "Up": 82,
    "Num_Lock": 83, "KP_Divide": 84, "KP_Multiply": 85, "KP_Subtract": 86, "KP_Add": 87, "KP_Enter": 88,
    "KP_Decimal": 99,
    "Control_L": 224, "Shift_L": 225, "Alt_L": 226, "Super_L": 227,
    "Control_R": 228, "Shift_R": 229, "Alt_R": 230, "Super_R": 231,
})

ALIASES = {
    "Enter": "Return", "enter": "Return", "Esc": "Escape", "esc": "Escape", "Page_Up": "Prior",
    "Page_Down": "Next", "BackSpace": "BackSpace", "Backspace": "BackSpace", "Space": "space",
    "ctrl": "Control_L", "Ctrl": "Control_L", "control": "Control_L", "shift": "Shift_L", "Shift": "Shift_L",
    "alt": "Alt_L", "Alt": "Alt_L", "super": "Super_L", "Super": "Super_L", "Meta_L": "Alt_L",
}

MODIFIER_BITS = {
    224: MOD_LCTRL, 225: MOD_LSHIFT, 226: MOD_LALT, 227: MOD_LGUI,
    228: MOD_RCTRL, 229: MOD_RSHIFT, 230: MOD_RALT, 231: MOD_RGUI,
}


class UnknownKey(ValueError):
    """A key name the Strata driver has no scancode for."""


def scancode(name: str) -> int:
    """The USB HID usage id of one key name; raises UnknownKey."""
    key = ALIASES.get(name, name)
    if key in SCANCODES:
        return SCANCODES[key]
    if len(key) == 1 and key.lower() in SCANCODES:
        return SCANCODES[key.lower()]
    raise UnknownKey("no scancode for key %r (the Strata driver knows: letters, digits, F1-F12, arrows, "
                     "Return, Escape, space, Tab, BackSpace, punctuation names, KP_*, and Shift/Control/Alt/Super "
                     "_L/_R)" % name)


def combo_scancodes(parts: List[str]) -> List[Tuple[int, int]]:
    """``[(scancode, modifiers held while it goes down), ...]`` for the keys of one combo, in press order."""
    held = 0
    out = []
    for part in parts:
        code = scancode(part)
        held |= MODIFIER_BITS.get(code, 0)
        out.append((code, held))
    return out
