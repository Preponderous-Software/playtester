# Probe lines

Some games cannot write the probe's files ([PROBE_CONTRACT.md](PROBE_CONTRACT.md))
while they run. Mount&Blade: Warband is one: its module scripts cannot write
files, and its log (`rgl_log.txt`) is written only when the game exits, without
the text of the messages scripts show (measured with Steam Warband 1.174 on
Windows 11, 2026-11-12). What such a game can do is show a line of text. A
mod's test build shows short **probe lines** in its message window; the
Windows driver reads them off the screen with OCR (`harness/windows_ocr.py`)
and turns them into `state.json` and `events.jsonl` (`harness/ptline.py`).

## The format

```
PT <kind> <seq> <field> ... <check>
```

Words are separated by spaces; a game should print **two** spaces between
words, because OCR tends to lose a single space between one-digit numbers
(readers take any run of spaces as one). `kind` is one capital letter; every
other word is a decimal integer, possibly negative, written without leading
zeros. Nothing else appears, so OCR can be limited to `PTSMEB0123456789-`
and a space.

| Kind | Code | Fields after `seq` | Event | |
| --- | --- | --- | --- | --- |
| `P` | 1 | `t day x y gold party free menu` | `screen` when `free` changes | the state, every in-game hour |
| `S` | 2 | `t day x y gold party` | `world` (`created`), `screen` | a new game started |
| `M` | 3 | `menu at t day x y` | `menu` | a settlement menu opened |
| `E` | 4 | `with rel t day x y` | `encounter` | an encounter began |
| `B` | 5 | `with t day x y gold party` | `battle_end` | a battle the player was in ended |

- `seq` counts the game's probe lines (1, 2, ...). It is how a reader keeps a
  line once when it appears in several screenshots.
- `t` is game hours since the campaign began: the probe's `tick`. `day` is
  `t // 24`.
- `x`, `y`: the player's map position in hundredths of a map unit; the probe
  reports `player.x = x / 100`, `player.z = y / 100`.
- `gold`, `party`: the player's gold and party size (`state.gold`,
  `state.partySize`).
- `free`: 1 when the world map runs with nothing open (`screen` `WORLD`),
  else 0 (`MENU`).
- `menu`: 0 none, 1 town, 2 castle, 3 village (`state.menu` and the `menu`
  event's `menu` give the name).
- `at`, `with`: party numbers; `rel`: the relation with the party met.

### The check digit

With weights `W = (1, 3, 7, 9)` and `D(n)` = the sum of the decimal digits of
`|n|`, plus 1 when `n < 0`:

```
check = sum(W[i % 4] * D(n_i) for i, n_i in enumerate([code, seq, field, ...])) % 10
```

Every weight is coprime with 10, so one misread digit, or a lost minus sign,
always changes the check. A line with the wrong number of words for its kind
is dropped too. A game computes it with integer operations only (a digit sum
is ten rounds of `mod 10` and `div 10`).

Example: `PT P 6 412 17 -1234 500 1999 7 1 0 6` (printed `PT  P  6  412 ...`).

A line must also be **plausible**: `seq >= 1`, `t >= 0`, `day == t // 24`,
`free` 0 or 1, `menu` 0 to 3, `gold` and `party` not negative.

## Reading lines back

A reader (`ptline.Decoder`) takes any text lines, in screen order (oldest
first):

1. Lines that are not probe lines, or fail their check or plausibility, are
   ignored. Common OCR slips are mended first: `O` read for `0`, `l` or `I`
   for `1`, `5` for the kind `S`, `8` for `B`, `PTP` for `PT P`. A line with
   up to 4 words too few (lost spaces) is tried with spaces put back in every
   possible place, and taken only when exactly one reading passes.
2. A line already taken (the same canonical text among the last 256) is a
   **duplicate**: it was in an earlier screenshot.
3. A line up to 16 `seq` behind the last one, at no later hour, is **late**
   (OCR missed it in the screenshot that had it, and read it after a newer
   one): it is dropped, so ticks never go back. Skipped `seq` numbers are
   counted as **missed**.
4. Anything else is new. An `S` line starts a world (`world` `created`);
   a line whose hour is earlier than the last one's starts a `loaded` world
   (another game was loaded).

The decoder's state survives between batches (`to_dict`), so a reader that
runs for a whole session and one that reads every line at the end write the
same files. `state.json` holds the latest `P` or `S` line; before any, only
the required fields, with `screen` `UNKNOWN` (no screen is claimed without a
line to show it).

`tests/data/ptline_vectors.json` lists cases (lines in; new lines, events,
state and counts out). Another implementation of the format should keep a
copy and check itself against it.

Limits: a game loaded from a save made less than 16 lines earlier loses
those lines until its `seq` passes the last one seen; two identical lines
(same `seq`, hour, place and numbers) within 256 lines are taken once.

## On the Windows driver

A profile with `"probe_format": "ptline"` and an `ocr` section
([PROFILES.md](PROFILES.md#windows)) gets a reader for the whole session.
Every `interval_sec` it asks the helper for the region `rect` at the
screen's resolution with only the pixels near `color` kept (black on
white), runs `tesseract --psm 6` with the whitelist above, and feeds the
lines to the decoder. It writes:

| File | |
| --- | --- |
| `out/state.json`, `out/events.jsonl` | the probe, as for any game |
| `out/probe-lines.txt` | every new line, canonical, in order: what a post-mortem reader can decode again |
| `out/probe.decoder.json` | the decoder's state between captures |
| `out/ocr.log`, `out/ocr.json` | what OCR read, and counts (captures, lines, new, failed) |
| `out/ocr/last.png`, `out/ocr/frames/` | the latest filtered capture, and the ones that gave new lines |

Why the screen, and not something else (2026-11-12):

- the log: written only at exit, and without the messages' text; it is still
  read after exit for errors (`log_error` events);
- saving the game and reading the save: changes what is tested, touches the
  player's saves, needs input and is slow;
- numbers drawn at a fixed spot by an overlay: takes part of the screen for
  the whole session and needs glyph matching; the message window is already
  there and keeps several lines on screen, so one missed capture loses
  nothing.

Install OCR with `sudo apt install tesseract-ocr`. Without it the reader
writes why to `out/ocr.log` and the session is screenshot-only.
