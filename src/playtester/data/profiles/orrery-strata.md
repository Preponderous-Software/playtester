The program starts on the solar system, centred on the Sun, at today's date
unless `--date` was given. This session runs headless on the Strata driver:
there is no window, and a driven orrery never reads or writes mission records.

| Input | Action |
|---|---|
| Left drag (`pt drag X1 Y1 X2 Y2 SECS 1`) | orbit the camera |
| Page Up / Page Down (`Prior` / `Next`) | zoom in / out |
| Tab, Shift+Tab | focus the next / previous body; Home focuses the Sun |
| Space | pause or resume time |
| `,` / `.` (`comma` / `period`) | slow down / speed up time |
| O, L, B, X | orbits, labels, small bodies, axes on or off |
| M, I, N, J | the mission list, information, the next event, jump to a date |
| V | board the ship (V again leaves it); in the ship W/S throttle, arrows or A/D steer, Q/E roll, T autopilot, G land |
| H | the help overlay |
| Esc | quit: avoid it |

Practical notes:

- No probe yet: steer by screenshots.
- Give `--date 2026-10-24` (after `--` on `pt start`) for a sky that is the
  same on every run; with `--clock stepped` the whole session repeats.
