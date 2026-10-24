The game starts in the valley in first person, with the mouse captured for
looking and the help shown; F1 hides or shows it. This session runs headless
on the Strata driver: there is no window, the game does not save and is
silent, and with `--clock stepped` the world waits for your commands.

| Input | Action |
|---|---|
| The mouse (`pt look DX DY`) | look (exact relative motion: no window edge to stop it) |
| W A S D | walk |
| Shift (`Shift_L`) | hurry |
| E | use what is here: fill, give, dig, drink, eat, sleep |
| F | the lamp |
| 1 to 4 | at the wheel: throw a pot, then type its name (`pt type NAME`) and press Return |
| B | break the pot in view |
| C | the clay lens |
| Tab | the codex (Up and Down choose a page) |
| V | in the after-mode, step out and watch (and back in) |
| M | mute (a driven session is silent anyway) |
| F1 | show or hide the help |
| Esc | free the mouse (Esc again quits the game: avoid it) |

Practical notes:

- There is no probe yet, so `state`, `await`, `face` and `walkto` are not
  available: steer by screenshots (`pt shot NAME`) after each move.
- In a stepped session `pt wait 2` runs exactly two seconds of game time;
  `pt step N` runs N frames.
- F5 and F9 do nothing in a driven session: it never touches a save.
