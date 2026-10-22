The game starts in the world, in first person in the cabin's yard, with the
mouse captured for looking and the help (controls) shown in a corner; F1
hides or shows it.

| Input | Action |
|---|---|
| Arrow keys (`pt hold Right 0.5`), or the mouse (`pt look DX DY`) | look: Left/Right turn about 90 degrees a second, Up/Down tilt about 57 degrees a second |
| W A S D | walk |
| Shift (`Shift_L`) | hurry |
| 1 to 9 | take a tool: broom, scrub brush, shovel, saw, pry bar, hammer, axe, matches, curry comb (`` ` `` for bare hands; the xdotool name is `grave`) |
| Left mouse held (`pt mousehold 3`) | work with the tool on what the crosshair is on; with a plank or shingles in hand, work them in |
| E | pick up or put down (debris put down outdoors is hauled out; furnishings go where they belong; E at the wagon puts a thing back) |
| R | turn what you carry |
| L | light or put out your lantern |
| T | play the restoration back again, once the settler is home |
| F5 / F9 | save now / reload the last save (it also autosaves every two minutes) |
| F1 | show or hide the help |
| Esc | free the mouse (Esc again quits the game: avoid it) |

Practical notes:

- Look with the arrow keys: `pt face DEG` turns precisely with them, and
  `pt hold Up 0.3` / `pt hold Down 0.3` tilt the view. Mouse look (`pt look
  100 0`, about 7 pixels a degree) works for small nudges, but relative
  motion through the virtual display is clamped at the window's edge.
- What you work on is what the crosshair (the centre of the screen) is on, so
  tilt the view down to the floor or debris, and up to the roof.
- `pt walkto door`, `hearth`, `window`, `wagon`, `chopping_block`, `mare` or
  `debris` walks there (into the cabin only through the door: walk to the
  door first).
- What the crosshair is on is named at the centre of the screen; the work you
  are doing shows progress there.
- The restoration goes in steps (survey, clear, repair, furnish, kindle); the
  checklist in the corner says what is next.
- There is no combat and no way to lose.
