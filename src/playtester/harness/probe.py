"""Reading a game's probe output, and the closed-loop commands built on it.

A game that implements the probe contract (docs/PROBE_CONTRACT.md) writes
``state.json`` (rewritten about twice a second) and ``events.jsonl`` (one
event a line) to the directory given with its probe flag. ``face`` and
``walkto`` steer by them: they turn or walk a little, re-read the state, and
repeat, using the turn and move keys (or mouse) from the game's profile.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from . import xdo
from .session import Session, append_json, now_ms, read_json


def normalise(deg: float) -> float:
    """An angle in degrees, to the range (-180, 180]."""
    d = deg % 360.0
    if d > 180.0:
        d -= 360.0
    return d


def state_path(session: Session) -> str:
    return os.path.join(session.probe_dir, "state.json")


def read_state(session: Session) -> Optional[Dict[str, Any]]:
    return read_json(state_path(session))


def fresh_state(session: Session, after_ms: int, timeout: float = 4.0) -> Optional[Dict[str, Any]]:
    """The first state written after ``after_ms``."""
    deadline = time.time() + timeout
    st = None
    while time.time() < deadline:
        st = read_state(session)
        if st is not None and st.get("wallTimeMs", 0) > after_ms:
            return st
        time.sleep(0.08)
    return st


def read_events(session: Session) -> List[Dict[str, Any]]:
    rows = []
    try:
        with open(os.path.join(session.probe_dir, "events.jsonl"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return rows


def need_probe(session: Session) -> Dict[str, Any]:
    profile = session.profile()
    if not profile.get("_probe", profile.get("probe")):
        raise RuntimeError("this session has no probe (the %s profile has none, or it was started with --no-probe): "
                           "use screenshots" % profile.get("name"))
    return profile


def compact(st: Optional[Dict[str, Any]], kinds: List[str]) -> Dict[str, Any]:
    """The parts of a state an agent reads every time, on one line."""
    if st is None:
        return {"error": "no state.json yet (is the game running with its probe?)"}
    skip = {"wallTimeMs", "nearest", "player", "world", "openPanels", "version"}
    c = {"screen": st.get("screen")}  # type: Dict[str, Any]
    for key in ("fps", "tps", "tick", "seed"):
        if key in st:
            c[key] = st[key]
    if st.get("openPanels"):
        c["panels"] = st["openPanels"]
    player = st.get("player")
    if isinstance(player, dict):
        c["player"] = player
    for key, value in st.items():
        if key not in skip and key not in c and value not in (None, "", [], {}):
            c[key] = value
    near = {}
    for kind, items in (st.get("nearest") or {}).items():
        if items and (not kinds or kind in kinds):
            near[kind] = ["%s %.1fm %+.0f" % (t.get("name", kind), t["distance"], t["bearing"]) for t in items]
    if "nearest" in st:
        c["nearest"] = near
    return c


def _trace(session: Session, what: str, **fields) -> None:
    fields.update({"t": now_ms(), "what": what})
    append_json(session.path("trace.jsonl"), fields)


def _clockwise(yaw: float, movement: Dict[str, Any]) -> float:
    """The yaw as degrees turned to the right, whichever way the game's yaw grows."""
    return yaw if movement.get("yaw_increases", "left") == "right" else -yaw


def _turn(session: Session, env: Dict[str, str], movement: Dict[str, Any], degrees_right: float) -> None:
    turn = movement["turn"]
    if turn["method"] == "keys":
        key = turn["right"] if degrees_right > 0 else turn["left"]
        # a little short of the whole turn: key holds overshoot by up to a frame
        xdo.hold(env, key, max(0.03, abs(degrees_right) / float(turn["degrees_per_second"]) * 0.9))
    else:
        xdo.move_relative(env, int(round(degrees_right * float(turn["pixels_per_degree"]))), 0)


def world_screen(st: Optional[Dict[str, Any]], profile: Dict[str, Any]) -> bool:
    screens = (profile.get("probe") or {}).get("world_screens") or ["WORLD"]
    return bool(st) and st.get("screen") in screens


def face(session: Session, relative: float, tolerance: Optional[float] = None, attempts: int = 8) -> Dict[str, Any]:
    """Turns by ``relative`` degrees (+ right), re-reading the yaw after each turn."""
    profile = need_probe(session)
    movement = profile.get("movement")
    if not movement:
        return {"ok": False, "error": "the %s profile has no movement section" % profile["name"]}
    tolerance = float(movement.get("face_tolerance", 8.0) if tolerance is None else tolerance)
    env = session.input_env()
    st = fresh_state(session, now_ms())
    if not world_screen(st, profile) or not isinstance(st.get("player"), dict):
        return {"ok": False, "error": "not in the world", "screen": st and st.get("screen")}
    target = _clockwise(st["player"]["yawDeg"], movement) + relative
    remaining = 0.0
    for attempt in range(attempts):
        remaining = normalise(target - _clockwise(st["player"]["yawDeg"], movement))
        if abs(remaining) <= tolerance:
            return {"ok": True, "yawDeg": st["player"]["yawDeg"], "offBy": round(-remaining, 1), "turns": attempt}
        if not world_screen(st, profile):
            return {"ok": False, "error": "left the world", "screen": st.get("screen")}
        _trace(session, "face", yawDeg=st["player"]["yawDeg"], remaining=round(remaining, 1), fps=st.get("fps"))
        _turn(session, env, movement, remaining)
        st = fresh_state(session, now_ms() + 30) or st
    remaining = normalise(target - _clockwise(st["player"]["yawDeg"], movement))
    return {"ok": abs(remaining) <= tolerance, "yawDeg": st["player"]["yawDeg"], "offBy": round(-remaining, 1),
            "turns": attempts}


def walkto(session: Session, kind: str, max_seconds: float = 60.0) -> Dict[str, Any]:
    """Walks to the nearest ``kind`` in state.json's ``nearest`` until it is within reach."""
    profile = need_probe(session)
    movement = profile.get("movement")
    if not movement:
        return {"ok": False, "error": "the %s profile has no movement section" % profile["name"]}
    kinds = movement.get("nearest_kinds") or []
    if kinds and kind not in kinds:
        return {"ok": False, "error": "kind must be one of " + ", ".join(kinds)}
    stop = float(movement.get("stop_distance", 2.0))
    reach = movement.get("interact_range")
    forward = movement.get("forward_key", "w")
    env = session.input_env()
    started = time.time()
    target_id, best, stalls, walked = None, 0.0, 0, False
    while True:
        st = fresh_state(session, now_ms())
        if not world_screen(st, profile):
            return {"ok": False, "error": "not in the world", "screen": st and st.get("screen")}
        targets = (st.get("nearest") or {}).get(kind) or []
        if not targets:
            return {"ok": False, "error": "no %s nearby" % kind}
        t = targets[0]
        player = st.get("player") or {}
        _trace(session, "walkto", kind=kind, id=t.get("id"), distance=t["distance"], bearing=t["bearing"],
               x=player.get("x"), z=player.get("z"), yawDeg=player.get("yawDeg"), fps=st.get("fps"))
        if t["distance"] < stop:
            result = {"ok": True, "kind": kind, "name": t.get("name"), "id": t.get("id"), "distance": t["distance"],
                      "bearing": t["bearing"], "seconds": round(time.time() - started, 1)}
            if reach is not None:
                result["note"] = "within reach (interact range %g)%s" % (
                    reach, "; press " + movement["interact_key"] if movement.get("interact_key") else "")
            return result
        if time.time() - started > max_seconds:
            return {"ok": False, "error": "timed out", "kind": kind, "distance": t["distance"], "bearing": t["bearing"]}
        # Stuck means walking towards the same target without getting closer.
        # The nearest target can change on the way, and turning on the spot
        # never closes the distance, so neither counts.
        if t.get("id") != target_id:
            target_id, best, stalls = t.get("id"), t["distance"], 0
        elif walked and t["distance"] > best - 0.5:
            stalls += 1
            if stalls >= 4:
                return {"ok": False, "error": "stuck: not getting closer", "kind": kind, "distance": t["distance"],
                        "bearing": t["bearing"], "hint": "take a screenshot; turn 45 degrees, walk a little and retry"}
        else:
            best = min(best, t["distance"])
            stalls = 0 if walked else stalls
        walked = False
        if abs(t["bearing"]) > 10.0:
            face(session, t["bearing"], tolerance=6.0, attempts=5)
            continue
        speed = player.get(movement.get("speed_field", "speed")) or movement.get("default_speed", 4.0)
        xdo.hold(env, forward, min(1.0, max(0.05, (t["distance"] - stop + 0.4 * stop) / float(speed))))
        walked = True


def await_screen(session: Session, screen: str, seconds: float = 15.0) -> Dict[str, Any]:
    deadline = time.time() + seconds
    st = None
    while time.time() < deadline:
        st = read_state(session)
        if st is not None and st.get("screen") == screen:
            return {"ok": True, "screen": screen}
        time.sleep(0.2)
    return {"ok": False, "error": "still not on " + screen, "screen": st and st.get("screen")}


def await_event(session: Session, match: Dict[str, Any], seconds: float, since: int = 0) -> Optional[Dict[str, Any]]:
    """The first event after line ``since`` whose fields include all of ``match``, waiting up to ``seconds``."""
    deadline = time.time() + seconds
    while True:
        for e in read_events(session)[since:]:
            if event_matches(e, match):
                return e
        if time.time() >= deadline:
            return None
        time.sleep(0.2)


def event_matches(event: Dict[str, Any], match: Dict[str, Any]) -> bool:
    return all(event.get(k) == v for k, v in match.items())
