Getting into a world: `pt start`, then any key leaves the title (`pt key
space`), **Start** on the main menu is at about (480, 315), and **Begin** on
the New World screen is at about (480, 315) too; the seed box is already
filled in. Confirm with screenshots; layouts can change. `pt start --continue`
(a game argument, passed through) continues the last save.

Keys in the world (the in-game **? Controls** screen lists them all):
W/A/S/D move and turn, Shift sprint (`Shift_L`), Space jump, **E interact**
(chop, mine, talk, enter or leave a settlement), N create a nation, J join
one, L leave, F found a settlement, B build a market stall, K build a
building, P plant a sapling, H go home, I inventory, O nations (laws,
diplomacy), C crafting, Y cycle the chronicle, V first/third person, Escape
pause menu (Save, Load, Share, Main Menu).

Practical notes:

- `pt walkto` knows `tree`, `rock`, `pawn`, `chicken`, `settlement` and
  `stall`, and stops within reach (interact range 5); then press `e`.
- Interact acts on the nearest thing within 5 units, in this order:
  settlement, pawn, tree, rock, chicken. A pawn standing by your tree gets
  talked to instead.
- The interface is Dear ImGui: at a few frames a second it only registers a
  click after the pointer hovers, which `pt click` does for you.
- The world runs at 50 ticks a second of game time; a day is 10 minutes of
  game time.
- When the world waits on a world event choice, the sheet covers the
  screen; `pt state` lists the options. Click one.
- `pt stop` kills the game without saving. To test saving, use the pause
  menu's Save (or quit from the main menu), then `pt start --continue` or Load.
