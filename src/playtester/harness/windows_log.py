"""The log probe: a game's own log file turned into the probe's events and state.

Some games cannot write ``state.json`` themselves but do write a log. A
Mount&Blade: Warband module writes ``rgl_log.txt`` (``display_log_message``
text lands there), so a test build can print lines such as::

    PTPROBE screen to=WORLD
    PTPROBE state screen=WORLD day=3 gold=1200 player.x=12.5 player.z=-4
    PTPROBE quest_started id=qst_errand title="The smith's errand"
    PTPROBE {"type": "battle_won", "enemies": 12}

For a session whose profile names a log (``windows.log``), every ``pt``
command first reads what the log gained since the last read (``sync``):

- each new line is appended to the session's ``game.log`` (so ``pt log``,
  ``crash_patterns`` and the aggregator see it);
- a line containing the prefix (``windows.log_prefix``, default ``PTPROBE``)
  becomes an event in ``out/events.jsonl``; a ``state`` line is merged into
  ``out/state.json`` instead (dotted names nest: ``player.x``), and a
  ``screen`` event's ``to`` sets the state's screen;
- a line matching one of ``windows.log_error_patterns`` becomes a
  ``log_error`` event with the line.

Parsing is permissive: the prefix may stand anywhere in the line, may be
followed by ``:``, and what follows is JSON or ``TYPE key=value ...`` (values
in double quotes may hold spaces; numbers and true/false are converted). A
game that prints no such lines leaves the session screenshot-only.
"""

import contextlib
import fcntl
import json
import os
import re
import shlex
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import ptline

DEFAULT_PREFIX = "PTPROBE"
OFFSET_FILE = "log.offset"
LOCK_FILE = OFFSET_FILE + ".lock"     # one lock for every writer of the probe files
DECODER_FILE = "probe.decoder.json"
LINES_FILE = "probe-lines.txt"
_TYPE = re.compile(r"[^a-z0-9]+")


def now_ms() -> int:
    return int(time.time() * 1000)


def coerce(value: str) -> Any:
    """``"12"`` -> 12, ``"1.5"`` -> 1.5, ``"true"`` -> True; anything else stays a string."""
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        f = float(value)
        if f == f and f not in (float("inf"), float("-inf")):
            return f
    except ValueError:
        pass
    return value


def event_type(name: str) -> str:
    """A type name in the probe contract's lower_snake_case."""
    return _TYPE.sub("_", name.strip().lower()).strip("_") or "probe"


def set_dotted(target: Dict[str, Any], key: str, value: Any) -> None:
    """``target["player"]["x"] = value`` for key ``player.x``."""
    parts = [p for p in key.split(".") if p]
    if not parts:
        return
    for part in parts[:-1]:
        nxt = target.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            target[part] = nxt
        target = nxt
    target[parts[-1]] = value


def parse_probe_line(line: str, prefix: str = DEFAULT_PREFIX) -> Optional[Dict[str, Any]]:
    """The fields of one probe line (with ``type``), or None if the line has no prefix.

    ``PTPROBE screen to=WORLD`` -> ``{"type": "screen", "to": "WORLD"}``;
    ``PTPROBE {"type": "x", "n": 1}`` -> that object; words without ``=``
    after the type are joined into ``text``.
    """
    at = line.find(prefix)
    if at < 0:
        return None
    rest = line[at + len(prefix):].strip().lstrip(":|-").strip()
    if rest.startswith("{"):
        try:
            obj = json.loads(rest)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            obj["type"] = event_type(str(obj.get("type") or "probe"))
            return obj
    try:
        tokens = shlex.split(rest, posix=True)
    except ValueError:
        tokens = rest.split()
    fields = {}  # type: Dict[str, Any]
    words = []  # type: List[str]
    kind = None  # type: Optional[str]
    for tok in tokens:
        if "=" in tok and not tok.startswith("="):
            key, value = tok.split("=", 1)
            set_dotted(fields, key.strip(), coerce(value))
        elif kind is None and not fields:
            kind = tok
        else:
            words.append(tok)
    fields["type"] = event_type(kind or str(fields.get("type") or "probe"))
    if words:
        fields["text"] = " ".join(words)
    return fields


def compile_patterns(patterns: List[str]) -> List[Any]:
    out = []
    for p in patterns or []:
        try:
            out.append(re.compile(p))
        except re.error:
            continue
    return out


def is_error(line: str, patterns: List[Any]) -> bool:
    return any(p.search(line) for p in patterns)


def decode(raw: bytes) -> str:
    """A log line as text: UTF-8, or Windows-1252 (what Warband writes) when it is not UTF-8."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def complete_lines(data: bytes) -> Tuple[List[bytes], int]:
    """The complete lines in ``data`` and how many bytes they take (a partial last line waits for the next read)."""
    end = data.rfind(b"\n")
    if end < 0:
        return [], 0
    return [l.rstrip(b"\r") for l in data[:end].split(b"\n")], end + 1


def process_lines(lines: List[str], prefix: str, errors: List[Any], state: Dict[str, Any],
                  wall_ms: Optional[int] = None) -> Tuple[List[Dict[str, Any]], bool]:
    """Events for ``lines`` and whether ``state`` (updated in place) changed."""
    events = []  # type: List[Dict[str, Any]]
    changed = False
    wall = wall_ms or now_ms()
    for line in lines:
        probe = parse_probe_line(line, prefix) if prefix else None
        if probe is not None:
            if probe["type"] == "state":
                probe.pop("type")
                for key, value in probe.items():
                    if key == "text":
                        continue
                    if isinstance(value, dict) and isinstance(state.get(key), dict):
                        state[key].update(value)
                    else:
                        state[key] = value
                changed = True
                continue
            if probe["type"] == "screen" and probe.get("to") is not None:
                probe.setdefault("from", state.get("screen"))
                state["screen"] = str(probe["to"])
                changed = True
            if isinstance(probe.get("tick"), bool) or not isinstance(probe.get("tick"), int):
                probe["tick"] = state.get("tick") if isinstance(state.get("tick"), int) else 0
            probe.setdefault("wallTimeMs", wall)
            events.append(probe)
        elif is_error(line, errors):
            events.append({"type": "log_error", "line": line.strip(), "tick": 0, "wallTimeMs": wall})
    return events, changed


def finish_state(state: Dict[str, Any], wall_ms: int) -> Dict[str, Any]:
    """The probe contract's required fields, filled in where the game has not given them."""
    state["wallTimeMs"] = wall_ms
    state.setdefault("version", "unknown")
    state.setdefault("screen", "UNKNOWN")
    state.setdefault("world", False)
    return state


@contextlib.contextmanager
def probe_lock(out: str) -> Iterator[None]:
    """Holds the session's probe lock (``out/log.offset.lock``): the log reader and the OCR reader both
    write the probe files. Not re-entrant: take it once per process."""
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, LOCK_FILE), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def write_json_atomic(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def append_events(out: str, events: List[Dict[str, Any]]) -> None:
    if events:
        with open(os.path.join(out, "events.jsonl"), "a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


def load_decoder(out: str, version: str) -> ptline.Decoder:
    try:
        with open(os.path.join(out, DECODER_FILE), encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = None
    return ptline.Decoder(version, saved if isinstance(saved, dict) else None)


def ingest_locked(out: str, texts: List[str], version: str, wall_ms: Optional[int] = None,
                  extra_events: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """Decodes ``texts`` (ptline) into the probe files; the caller holds ``probe_lock``. Returns the new
    lines (canonical). ``state.json`` is rewritten on every call, so its ``wallTimeMs`` says when the
    probe was last read; ``extra_events`` (log errors) are appended after the decoded ones."""
    wall = wall_ms or now_ms()
    d = load_decoder(out, version)
    kept, events = d.feed_all(texts, wall)
    for e in extra_events or []:
        e.setdefault("tick", d.tick)
        events.append(e)
    append_events(out, events)
    if kept:
        with open(os.path.join(out, LINES_FILE), "a", encoding="utf-8") as f:
            for line in kept:
                f.write(line + "\n")
    write_json_atomic(os.path.join(out, "state.json"), d.state_json(wall))
    write_json_atomic(os.path.join(out, DECODER_FILE), d.to_dict())
    return kept


def ingest(out: str, texts: List[str], version: str, wall_ms: Optional[int] = None) -> List[str]:
    """``ingest_locked`` under the probe lock."""
    with probe_lock(out):
        return ingest_locked(out, texts, version, wall_ms)


def probe_version(session: Any) -> str:
    """The version a ptline session's state reports: the module and the game's title."""
    info = session.info()
    title = session.profile().get("title") or session.profile().get("name") or "game"
    return "%s (%s)" % (info.get("module") or "?", title) if info.get("module") else str(title)


def read_offset(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def sync(session: Any) -> int:
    """Reads what the session's log gained since the last sync; returns the number of new lines.

    Safe to call from several ``pt`` processes at once (an exclusive lock on
    ``out/log.offset.lock``). A log that shrank was started again by the game,
    so it is read from the top.
    """
    info = session.info()
    log = info.get("logPath")
    if info.get("driver") != "windows" or not log:
        return 0
    out = session.probe_dir
    offset_path = os.path.join(out, OFFSET_FILE)
    with probe_lock(out):
        offset = read_offset(offset_path)
        try:
            size = os.path.getsize(log)
        except OSError:
            return 0
        if size < offset:
            offset = 0
        if size == offset:
            return 0
        with open(log, "rb") as f:
            f.seek(offset)
            data = f.read(size - offset)
        raw_lines, used = complete_lines(data)
        if not used:
            return 0
        lines = [decode(r) for r in raw_lines]
        with open(session.path("game.log"), "a", encoding="utf-8") as g:
            for line in lines:
                g.write(line + "\n")
        profile = session.profile()
        win = profile.get("windows") or {}
        state_path = os.path.join(out, "state.json")
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                state = {}
        except (OSError, ValueError):
            state = {}
        wall = now_ms()
        errors = compile_patterns(win.get("log_error_patterns") or [])
        if win.get("probe_format") == "ptline":
            probe_lines = [l for l in lines if ptline.parse_line(l.replace("_", " "))]
            errs = [{"type": "log_error", "line": l.strip(), "wallTimeMs": wall} for l in lines
                    if l not in probe_lines and is_error(l, errors)]
            ingest_locked(out, [l.replace("_", " ") for l in probe_lines], probe_version(session), wall, errs)
            with open(offset_path, "w", encoding="utf-8") as f:
                f.write(str(offset + used))
            return len(lines)
        events, changed = process_lines(lines, win.get("log_prefix", DEFAULT_PREFIX), errors, state, wall)
        if events:
            with open(os.path.join(out, "events.jsonl"), "a", encoding="utf-8") as f:
                for e in events:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
        if changed:
            tmp = state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(finish_state(state, wall), f)
            os.replace(tmp, state_path)
        with open(offset_path, "w", encoding="utf-8") as f:
            f.write(str(offset + used))
        return len(lines)


def module_from_log(path: str) -> Optional[str]:
    """The module named in a Warband log's header (``Module_name =  TestModule``), or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return None
    m = re.search(rb"Module_name\s*=\s*(\S[^\r\n]*)", head)
    return decode(m.group(1)).strip() if m else None
