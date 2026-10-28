The game starts at the trailhead, through Sisyphus's eyes, with the boulder
just ahead of him up the path and the controls along the bottom (F1 hides or
shows them). This session runs headless on the Strata driver: there is no
window, the game does not save and is silent, and with `--clock stepped` the
world waits for your commands.

| Input | Action |
|---|---|
| The mouse (`pt look DX DY`) | look (exact relative motion: no window edge to stop it) |
| W A S D | walk; walk into the boulder from below (facing up the hill) to push it |
| Shift (`Shift_L`) | hurry |
| E (held: `pt hold e 3`) | patch the module the crosshair is on (within about 3 m) |
| R (held) | retire the module the crosshair is on |
| F (held) | refactor the module the crosshair is on into the module it uses |
| Q | sit and look at the view (walking gets up) |
| V | a view from straight behind him, or back to his eyes |
| M | sound (a driven session is silent anyway) |
| F1 | show or hide the controls |
| Esc | free the mouse (Esc again quits the game: avoid it) |

Practical notes:

- There is no probe yet, so `state`, `await`, `face` and `walkto` are not
  available: steer by screenshots (`pt shot NAME`) after each move. The HUD,
  top left, says the version, the users, health and weight, how far the next
  release is, and the open issues, worst first.
- Pushing is walking into it: `pt hold w 5` from just below the boulder,
  facing up the hill, pushes for five seconds.
- Patching needs the key held for one to five seconds; the prompt under the
  crosshair shows a bar while it works.
- On a terrace you can also push the boulder from its uphill side (facing
  down the hill) to roll it back and turn it, which brings modules from
  underneath into reach. It stops at the terrace's edge.
- Since 0.2.0: modules use one another (the prompt says which), and a
  module that is down makes the ones using it rot fast; pushing and working
  tire him (a stamina bar appears in the HUD), and sitting (Q) rests him;
  each time the boulder rolls back to the trailhead a cairn is raised there,
  and standing at one shows how that climb went.
- In a stepped session `pt wait 2` runs exactly two seconds of game time;
  `pt step N` runs N frames.
- F5 and F9 do nothing in a driven session: it never touches a save.
