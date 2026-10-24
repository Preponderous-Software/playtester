The colony starts running, on a map view of its tiles, settlers and
stockpile; the game's own help prints to its log (`pt log`). This session runs
headless on the Strata driver: there is no window, and the run never
autosaves or saves on exit (only the new colony's slot, in this session's
data directory, is written when it starts).

| Input | Action |
|---|---|
| Space | pause or resume |
| `+` / `-` (`pt key equal`, `pt key minus`) | speed up or slow down |
| Left drag (`pt drag X1 Y1 X2 Y2 SECS 1`) | designate tiles for gathering; Ctrl+drag clears |
| Right click (`pt click X Y 3`) | plan or cancel a hut |
| Tab | switch between the map view and the free-fly camera |
| W A S D, Q / E | fly (free-fly camera); Shift is faster |
| Arrow keys, middle drag | look (free-fly camera) |
| Mouse wheel (`pt scroll N`) | dolly (free-fly camera) |
| H | print the help to the log |
| Esc | quit the game: avoid it |

Practical notes:

- No probe yet: read the colony from screenshots and from `pt log`, where the
  game prints its status every 100 ticks.
- In a stepped session the colony only advances when you step or wait, so
  `pt wait 5` is exactly five seconds of colony time at the current speed.
