**This session drives the real Windows desktop.** Mount&Blade: Warband runs
on the Windows machine that hosts WSL, full screen; your keys and clicks are
real input and `pt` brings the game to the front before each command. Only
one session can run at a time. Never press Alt+Tab, the Windows key or
Alt+F4, and never click outside the game.

**Coordinates are screenshot pixels.** `pt shot` saves 1280x720 images of a
game that really runs at a larger size (often full screen at the desktop's
resolution);
give `pt click X Y` the position you see in the screenshot and `pt` scales
it. Screenshots take about a quarter of a second.

**Starting.** `pt start --profile warband --game-dir "/mnt/c/Program Files
(x86)/Steam/steamapps/common/MountBlade Warband" --module <Module>` launches
the game with that module (pt sets the launcher's remembered module in the
registry and puts the old one back at `pt stop`), presses Play in the
launcher and waits for the main menu; loading takes about a minute. If the
game is already open, `pt start ... --attach` drives it as it is (any
module) and `pt stop` leaves it running.

**The world map.** Click on open ground to travel there; click a town,
castle, village or party to go to it (you meet or enter it when you
arrive). Time passes only while you move or wait; "Paused" at the bottom
means time is stopped. The mouse wheel (`pt scroll N`, + is down) zooms;
dragging with the right button held (`pt drag X1 Y1 X2 Y2 SECS 3`) turns
the camera. The bar along the bottom has Camp, Reports, Notes, Inventory,
Character and Party buttons; the hotkeys are `i` (inventory), `c`
(character), `p` (party), `q` (quests), `n` (notes).

**Menus.** Town and encounter menus are lists of text choices: click a
choice. `Escape` closes a screen or backs out; on the world map it opens
the game menu (Options, Save, Quit: do not quit or load a game unless your
goal says so).

**Inventory.** Items move by click-to-pick-up and click-to-drop: click an
item (it sticks to the pointer), then click the slot where it should go.
It is not a drag. Hover an item for its stats. The left pane is the other
side (Discard, a merchant, a chest), the middle your character's equipment,
the right your stock. `Return` (the button) closes it.

**Text fields.** `pt type` does not reach Warband's name fields (a new
character's name, a renamed party or troop); use `pt type --keys "Name"`,
which presses the keys (capitals with Shift); `pt type` is fine elsewhere.

**Battles and scenes.** `w a s d` move (`a`/`d` strafe; they do not turn),
and the mouse turns you: `pt look DX DY` (+ right / + down, in pixels;
`pt look 400 0` turns right; `pt move` does not turn the view at all),
left button attacks (`pt mousehold 0.6 1` for a full swing), right button
blocks, `f` mounts or uses, `Tab` leaves a scene or battle when allowed,
`Backspace` shows orders. Holds: `pt hold w 2`.

**The probe.** Warband writes no file pt can read while it runs (its log,
`rgl_log.txt`, is written when the game exits). A module's test build may
show short probe lines in the message window, in magenta, such as
`PT P 6 412 17 -1234 500 1999 7 1 0 6` (docs/PROBE_LINES.md): pt reads
them off the screen while the session runs, so `pt state` shows the game
hours (`tick`), day, map position, gold and party size of the latest one,
and `pt events` the world, screen, menu, encounter and battle_end events.
They change only while game time passes (travelling or waiting). Ignore
the magenta lines themselves in your report. At `pt stop` the log is read
for errors (`SCRIPT ERROR` and the like), which appear as `log_error`
events: report each one. A module without a test build shows no probe
lines; then screenshots are all you have.
