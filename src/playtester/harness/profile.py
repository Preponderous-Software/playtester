"""Game profiles: everything the harness needs to know about one game.

A profile is a JSON file (standard library only, so no TOML before Python
3.11 and no YAML). The bundled ones live in ``playtester/data/profiles``;
any other path can be given instead of a name. ``docs/PROFILES.md`` describes
every field and ``data/schemas/profile.schema.json`` checks them.

Strings in ``launch`` may use placeholders, expanded when a session starts:

``{game_dir}``     the game's checkout (``--game-dir``, ``PT_GAME_DIR`` or the current directory)
``{session_dir}``  this session's directory
``{data_dir}``     ``{session_dir}/data``: the game's saves and settings for this session
``{probe_dir}``    ``{session_dir}/out``: where a probe-capable game writes state.json and events.jsonl
``{width}`` ``{height}``  the window size
``{seed}``         the seed given to ``pt start --seed`` (only in ``launch.seed_args``)
``{python}``       the Python interpreter running the harness
"""

import copy
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

from ..schema import DATA_DIR, load_schema, validate

PROFILE_DIR = os.path.join(DATA_DIR, "profiles")

DEFAULTS = {
    "window": {"width": 960, "height": 540},
    "launch": {"args": [], "env": {}, "env_defaults": {}, "seed_args": [], "start_timeout_sec": 90},
    "probe": None,
    "movement": None,
    "crash_patterns": [],
    "goals": [],
    "cheats": "",
}


class ProfileError(Exception):
    """A profile that cannot be found, read or used."""


def available() -> List[str]:
    """The names of the bundled profiles."""
    return sorted(f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))


def _merge(defaults: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(defaults)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(name_or_path: str) -> Dict[str, Any]:
    """A profile by bundled name (``beyond-nations``) or by path to a JSON file.

    The result has every optional section filled in with its default and a
    ``_source`` entry with the file it came from (agent notes are read
    relative to it).
    """
    if not name_or_path:
        raise ProfileError("no profile given (pt start --profile NAME, or PT_PROFILE); bundled: " + ", ".join(available()))
    path = name_or_path
    if not os.path.isfile(path):
        path = os.path.join(PROFILE_DIR, name_or_path + ".json")
    if not os.path.isfile(path):
        raise ProfileError("no profile %r: not a file and not one of the bundled profiles (%s)"
                           % (name_or_path, ", ".join(available())))
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise ProfileError("%s is not valid JSON: %s" % (path, e))
    errors = validate(data, load_schema("profile.schema.json"))
    if errors:
        raise ProfileError("%s is not a valid profile:\n  %s" % (path, "\n  ".join(errors)))
    profile = _merge(DEFAULTS, data)
    profile["_source"] = os.path.abspath(path)
    return profile


def agent_notes(profile: Dict[str, Any]) -> str:
    """The profile's controls-and-tips text for agents (Markdown), or an empty string."""
    notes = profile.get("agent_notes")
    if not notes:
        return ""
    path = notes if os.path.isabs(notes) else os.path.join(os.path.dirname(profile["_source"]), notes)
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def expand(value: Any, variables: Dict[str, Any]) -> Any:
    """``value`` with ``{name}`` placeholders filled in; unknown names are left alone."""
    if isinstance(value, str):
        def sub(match):
            key = match.group(1)
            return str(variables[key]) if key in variables else match.group(0)
        return os.path.expanduser(_PLACEHOLDER.sub(sub, value)) if value.startswith("~") else _PLACEHOLDER.sub(sub, value)
    if isinstance(value, list):
        return [expand(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: expand(v, variables) for k, v in value.items()}
    return value


def launch_plan(profile: Dict[str, Any], game_dir: str, session_dir: str, width: int, height: int,
                seed: Optional[str], extra_args: List[str], use_probe: bool) -> Dict[str, Any]:
    """The command line, working directory and environment for one start of the game."""
    variables = {
        "game_dir": game_dir,
        "session_dir": session_dir,
        "data_dir": os.path.join(session_dir, "data"),
        "probe_dir": os.path.join(session_dir, "out"),
        "width": width,
        "height": height,
        "python": sys.executable,
    }
    launch = profile["launch"]
    command = expand(list(launch["command"]), variables) + expand(list(launch.get("args", [])), variables)
    if seed is not None:
        command += expand(list(launch.get("seed_args", [])), dict(variables, seed=seed))
    probe = profile.get("probe")
    if use_probe and probe:
        command += [probe["flag"], variables["probe_dir"]]
    command += list(extra_args)
    env = {k: str(v) for k, v in expand(launch.get("env", {}), variables).items()}
    defaults = {}
    for key, value in expand(launch.get("env_defaults", {}), variables).items():
        if not os.environ.get(key) and os.path.exists(str(value)):
            defaults[key] = str(value)
    cwd = expand(launch.get("cwd", "{session_dir}"), variables)
    return {"command": command, "cwd": cwd, "env": dict(defaults, **env)}
