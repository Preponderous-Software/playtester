"""Merges every session of a playtest run into summary.md and summary.json.

    pt aggregate RUN_DIR [--profile NAME] [--ticks-per-second N]

RUN_DIR holds one directory per session (``PT_ROOT/<session>``), each with
the agent's ``report.json`` and, for a game with a probe, the game's
``out/events.jsonl``. The summary has a per-goal outcome table, the findings
of every agent grouped so that near-duplicates reported by different agents
become one entry, counts by severity, objective timings across sessions
taken from events.jsonl, and links to the screenshots.

Game time comes from event ticks divided by the game's ticks per second,
which each session records in ``session.json`` from its profile. For runs
whose sessions do not name a profile (older evidence), ``--profile`` gives
one, and ``--ticks-per-second`` overrides it.
"""

import datetime
import difflib
import json
import os
import re
import statistics
import sys
from typing import Any, Dict, List, Optional, Tuple

from .report import check_report
from ..schema import load_schema

SEVERITIES = ["blocker", "major", "minor", "polish"]
SIMILAR = 0.6
STOPWORDS = {"a", "an", "the", "is", "are", "was", "be", "of", "to", "in", "on", "at", "and", "or", "it", "its",
             "when", "while", "with", "for", "by", "from", "after", "can", "not", "no", "does", "do", "this", "that",
             "you", "your", "player", "players", "my", "but", "so", "any", "only", "there", "here", "than", "then",
             "into", "out", "up", "all", "every"}
# Words agents use interchangeably for the same problem. Multi-word and
# apostrophe forms are replaced in the text before it is split.
PHRASES = {"can't": "cannot", "can not": "cannot", "couldn't": "cannot", "won't": "cannot", "no way": "cannot",
           "re-laid": "reflow", "re-lays": "reflow", "re-layout": "reflow"}
SYNONYMS = {"cant": "cannot", "unable": "cannot", "couldnt": "cannot", "talked": "talk", "gifted": "gift",
            "invited": "invite", "reflows": "reflow", "relaid": "reflow", "relays": "reflow", "reorders": "reflow",
            "npc": "pawn", "npcs": "pawn", "pawns": "pawn", "villagers": "pawn", "residents": "pawn",
            "cutoff": "clipped", "cut": "clipped", "truncated": "clipped", "truncates": "clipped"}
# Shared words that make two titles one finding even when one title says more:
# at least this many, most of the shorter title's words ...
MIN_SHARED_WORDS = 3
# ... or this many, whatever else either title says.
STRONG_SHARED_WORDS = 5


def read_json(path: str) -> Tuple[Optional[Any], Optional[str]]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except OSError:
        return None, "missing"
    except ValueError as e:
        return None, "not valid JSON (%s)" % e


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
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


def derive_metrics(events: List[Dict[str, Any]], ticks_per_second: Optional[float]) -> Dict[str, Any]:
    """The standard metrics, from the game's own events rather than the agent's account."""
    objectives, progress, deaths, saves, loads = [], [], 0, 0, 0
    counts = {}  # type: Dict[str, int]
    world_started = None
    for e in events:
        kind = e.get("type")
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "world":
            # timings run from the latest new world; a load continues a world
            if e.get("how") == "created" or world_started is None:
                world_started = e.get("wallTimeMs")
            if e.get("how") == "loaded":
                loads += 1
        elif kind == "objective_completed":
            wall = None
            if world_started is not None and e.get("wallTimeMs") is not None:
                wall = round((e["wallTimeMs"] - world_started) / 1000.0, 1)
            seconds = None
            if isinstance(e.get("tick"), int) and ticks_per_second:
                seconds = round(e["tick"] / float(ticks_per_second), 1)
            objectives.append({"number": e.get("number"), "title": e.get("title"), "seconds": seconds,
                               "wallSeconds": wall, "tick": e.get("tick")})
        elif kind in ("era_changed", "stage_changed"):
            progress.append(e.get("to"))
        elif kind == "player_death":
            deaths += 1
        elif kind == "save":
            saves += 1
    return {
        "objectivesCompleted": len(objectives),
        "objectives": objectives,
        "progressReached": progress[-1] if progress else None,
        "deaths": deaths,
        "saves": saves,
        "loads": loads,
        "eventCounts": counts,
        "lastTick": max([e.get("tick", 0) for e in events if isinstance(e.get("tick"), int)] or [0]),
    }


def crashed(session_dir: str, patterns: List[str]) -> Optional[str]:
    try:
        with open(os.path.join(session_dir, "game.log"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def stem(word: str) -> str:
    """A crude suffix strip, so "truncated", "truncates" and "truncate" compare equal."""
    for suffix in ("ing", "ed", "es", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def normalise_title(title: str) -> str:
    """Lower case, synonyms folded, no punctuation, filler words, sizes or bare numbers, crudely stemmed."""
    text = title.lower().replace("\u2019", "'")
    for phrase, word in PHRASES.items():
        text = text.replace(phrase, word)
    words = [SYNONYMS.get(w, w) for w in re.sub(r"[^a-z0-9 ]+", " ", text).split()]
    return " ".join(stem(w) for w in words
                    if w not in STOPWORDS and len(w) > 1 and not re.fullmatch(r"\d+(x\d+)?", w))


def similarity(a: str, b: str) -> float:
    """Near-duplicate titles: a character ratio, shared words, or one title's words mostly inside the other's."""
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    sa, sb = set(a.split()), set(b.split())
    shared = len(sa & sb)
    jaccard = shared / float(len(sa | sb)) if sa | sb else 0.0
    overlap = shared / float(min(len(sa), len(sb))) if shared >= MIN_SHARED_WORDS else 0.0
    if shared >= STRONG_SHARED_WORDS:
        overlap = max(overlap, SIMILAR)
    return max(ratio, jaccard, overlap)


def _severity_rank(severity: Optional[str]) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else 9


def group_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Greedy grouping, most severe first, so a group is named by its most serious report."""
    ordered = sorted(findings, key=lambda f: _severity_rank(f.get("severity")))
    groups = []  # type: List[Dict[str, Any]]
    for f in ordered:
        key = normalise_title(f.get("title", ""))
        best, best_score = None, 0.0
        for g in groups:
            score = max(similarity(key, k) for k in g["keys"])
            if score > best_score:
                best, best_score = g, score
        if best is not None and best_score >= SIMILAR:
            best["members"].append(f)
            best["keys"].append(key)
        else:
            groups.append({"keys": [key], "members": [f]})
    result = []
    for g in groups:
        members = g["members"]
        lead = members[0]
        result.append({
            "title": lead.get("title"),
            "severity": lead.get("severity"),
            "categories": sorted({m.get("category") for m in members if m.get("category")}),
            "sessions": sorted({m["session"] for m in members}),
            "reports": len(members),
            "detail": lead.get("detail"),
            "repro": next((m.get("repro") for m in members if m.get("repro")), None),
            "screenshots": [m["screenshot"] for m in members if m.get("screenshot")],
            "alsoTitled": sorted({m.get("title") for m in members[1:] if m.get("title") != lead.get("title")}),
        })
    result.sort(key=lambda g: (_severity_rank(g["severity"]), -len(g["sessions"]), g["title"] or ""))
    return result


def relative_shot(run_dir: str, session_dir: str, shot: Optional[str]) -> Optional[str]:
    if not shot:
        return None
    path = shot if os.path.isabs(shot) else os.path.join(session_dir, shot)
    return os.path.relpath(path, run_dir)


def _bundled_profile(name: Optional[str]) -> Dict[str, Any]:
    """The bundled profile a session names, for runs whose profile.json was not kept."""
    if not name:
        return {}
    from ..harness import profile as profiles
    try:
        return profiles.load(name) if name in profiles.available() else {}
    except profiles.ProfileError:
        return {}


def collect(run_dir: str, ticks_per_second: Optional[float] = None, default_profile: Optional[str] = None):
    schema = load_schema("report.schema.json")
    sessions, findings, problems = [], [], []
    for name in sorted(os.listdir(run_dir)):
        session_dir = os.path.join(run_dir, name)
        if not os.path.isdir(session_dir) or name.startswith((".", "_")):
            continue
        if not any(os.path.exists(os.path.join(session_dir, f)) for f in ("report.json", "session.json", "out", "events.jsonl")):
            continue
        report, report_error = read_json(os.path.join(session_dir, "report.json"))
        # a live run keeps the probe's files in out/; committed evidence keeps
        # just the events, beside the report
        events = read_jsonl(os.path.join(session_dir, "out", "events.jsonl")) or \
            read_jsonl(os.path.join(session_dir, "events.jsonl"))
        info, _ = read_json(os.path.join(session_dir, "session.json"))
        info = info if isinstance(info, dict) else {}
        profile, _ = read_json(os.path.join(session_dir, "profile.json"))
        if not isinstance(profile, dict):
            profile = _bundled_profile(info.get("profile") or default_profile)
        tps = ticks_per_second or info.get("ticksPerSecond") or (profile.get("probe") or {}).get("ticks_per_second")
        derived = derive_metrics(events, tps)
        errors = []  # type: List[str]
        if report is None:
            problems.append("%s: report.json %s" % (name, report_error))
        else:
            errors = check_report(report, schema, session_dir)
            for e in errors:
                problems.append("%s: report.json %s" % (name, e))
        crash = crashed(session_dir, profile.get("crash_patterns") or [])
        if crash:
            problems.append("%s: game.log says %s" % (name, crash))
        r = report if isinstance(report, dict) else {}
        sessions.append({
            "session": name,
            "profile": info.get("profile") or profile.get("name") or default_profile,
            "goal": r.get("goal"),
            "outcome": r.get("outcome", "no report"),
            "fun": r.get("fun"),
            "durationSec": r.get("durationSec"),
            "seed": r.get("seed", info.get("seed")),
            "build": r.get("build") or {"version": info.get("version"), "commit": info.get("commit")},
            "verdict": r.get("verdict"),
            "reportValid": report is not None and not errors,
            "reported": r.get("metrics") or {},
            "derived": derived,
            "ticksPerSecond": tps,
            "notes": len(read_jsonl(os.path.join(session_dir, "findings.jsonl"))),
            "crash": crash,
        })
        for f in r.get("findings") or []:
            if not isinstance(f, dict):
                continue
            item = dict(f)
            item["session"] = name
            item["screenshot"] = relative_shot(run_dir, session_dir, f.get("screenshot"))
            findings.append(item)
        if crash and not any(f.get("category") == "crash" for f in r.get("findings") or [] if isinstance(f, dict)):
            findings.append({"session": name, "severity": "blocker", "category": "crash",
                             "title": "Game crashed: " + crash.split(": ", 1)[-1][:100], "detail": crash})
    return sessions, findings, problems


def timings_table(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    titles = []  # type: List[Tuple[int, str]]
    for s in sessions:
        for o in s["derived"]["objectives"]:
            key = (o.get("number") or 0, o.get("title"))
            if key not in titles:
                titles.append(key)
    titles.sort(key=lambda k: (k[0], k[1] or ""))
    rows = []
    for number, title in titles:
        cells = {}
        for s in sessions:
            for o in s["derived"]["objectives"]:
                if o.get("title") == title and o.get("seconds") is not None:
                    cells[s["session"]] = o["seconds"]
                    break
        values = sorted(cells.values())
        rows.append({"number": number, "title": title, "seconds": cells, "sessions": len(values),
                     "min": values[0] if values else None, "median": statistics.median(values) if values else None,
                     "max": values[-1] if values else None})
    return rows


def md_escape(text: Optional[str]) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return "%g" % round(value, 1)
    return str(value)


def render_markdown(run_dir: str, summary: Dict[str, Any]) -> str:
    lines = []
    sessions = summary["sessions"]
    builds = sorted({"%s %s (%s)" % (s.get("profile") or "", s["build"].get("version"), s["build"].get("commit"))
                     for s in sessions if s.get("build")})
    with_progress = any(s["derived"]["progressReached"] for s in sessions)
    lines.append("# Playtest summary: %s" % os.path.basename(os.path.abspath(run_dir)))
    lines.append("")
    lines.append("%d sessions, build %s, generated %s." % (
        len(sessions), ", ".join(b.strip() for b in builds) or "unknown", summary["generated"]))
    lines.append("")
    counts = summary["severityCounts"]
    lines.append("**Findings:** %d reports in %d groups -- %s." % (
        summary["findingReports"], len(summary["findings"]), ", ".join("%d %s" % (counts[s], s) for s in SEVERITIES)))
    lines.append("")
    lines.append("## Outcomes")
    lines.append("")
    head = ["Session", "Goal", "Outcome", "Fun", "Minutes", "Objectives"] + (["Reached"] if with_progress else []) + \
        ["Deaths", "Findings", "Verdict"]
    lines.append("| " + " | ".join(head) + " |")
    lines.append("|" + " --- |" * len(head))
    for s in sessions:
        d = s["derived"]
        n = sum(1 for g in summary["findings"] if s["session"] in g["sessions"])
        minutes = round(s["durationSec"] / 60.0, 1) if isinstance(s.get("durationSec"), (int, float)) else None
        outcome = s["outcome"] + ("" if s["reportValid"] or s["outcome"] == "no report" else " (invalid report)")
        cells = [s["session"], md_escape(s.get("goal")), outcome, fmt(s.get("fun")), fmt(minutes),
                 str(d["objectivesCompleted"])] + ([fmt(d["progressReached"])] if with_progress else []) + \
            [str(d["deaths"]), str(n), md_escape(s.get("verdict"))]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not summary["findings"]:
        lines.append("None reported.")
        lines.append("")
    for i, g in enumerate(summary["findings"], 1):
        lines.append("### %d. [%s] %s" % (i, g["severity"], g["title"]))
        lines.append("")
        lines.append("- **Category:** %s; **reported by** %d agent(s): %s" % (
            ", ".join(g["categories"]) or "-", len(g["sessions"]), ", ".join(g["sessions"])))
        if g["alsoTitled"]:
            lines.append("- **Also reported as:** %s" % "; ".join('"%s"' % t for t in g["alsoTitled"]))
        lines.append("- **Detail:** %s" % md_escape(g["detail"]))
        if g["repro"]:
            lines.append("- **Repro:** %s" % md_escape(g["repro"]))
        if g["screenshots"]:
            lines.append("- **Screenshots:** %s" % " ".join("[%s](%s)" % (os.path.basename(p), p) for p in g["screenshots"]))
        lines.append("")
    lines.append("## Objective timings")
    lines.append("")
    lines.append("Game seconds from the start of the world to each objective (event tick / the game's ticks per second, "
                 "from events.jsonl). Game time, not wall time: with many sessions on one machine a world can run slower "
                 "than real time, and wall-clock timings would mostly measure the machine.")
    lines.append("")
    if not summary["objectiveTimings"]:
        lines.append("No objective was completed (or the game has no probe).")
    else:
        names = [s["session"] for s in sessions]
        lines.append("| # | Objective | " + " | ".join(names) + " | min | median | max |")
        lines.append("| --- | --- | " + " | ".join("---" for _ in names) + " | --- | --- | --- |")
        for row in summary["objectiveTimings"]:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                fmt(row["number"]), md_escape(row["title"]), " | ".join(fmt(row["seconds"].get(n)) for n in names),
                fmt(row["min"]), fmt(row["median"]), fmt(row["max"])))
    lines.append("")
    if summary["problems"]:
        lines.append("## Problems with the run")
        lines.append("")
        for p in summary["problems"]:
            lines.append("- %s" % md_escape(p))
        lines.append("")
    return "\n".join(lines)


def aggregate(run_dir: str, ticks_per_second: Optional[float] = None,
              default_profile: Optional[str] = None) -> Dict[str, Any]:
    """Writes summary.json and summary.md into ``run_dir``; returns the summary."""
    sessions, findings, problems = collect(run_dir, ticks_per_second, default_profile)
    groups = group_findings(findings)
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        if f.get("severity") in counts:
            counts[f["severity"]] += 1
    summary = {
        "runDir": os.path.abspath(run_dir),
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sessions": sessions,
        "severityCounts": counts,
        "findingReports": len(findings),
        "findings": groups,
        "objectiveTimings": timings_table(sessions),
        "problems": problems,
    }
    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(os.path.join(run_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(render_markdown(run_dir, summary) + "\n")
    return summary


def main(argv: List[str]) -> int:
    args = list(argv[1:])
    tps, default_profile = None, None
    if "--ticks-per-second" in args:
        i = args.index("--ticks-per-second")
        tps = float(args[i + 1])
        del args[i:i + 2]
    if "--profile" in args:
        i = args.index("--profile")
        default_profile = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1 or not os.path.isdir(args[0]):
        print(__doc__.strip())
        return 2
    summary = aggregate(args[0], tps, default_profile)
    print("%s: %d sessions, %d findings in %d groups, %d problems" % (
        os.path.join(args[0], "summary.md"), len(summary["sessions"]), summary["findingReports"],
        len(summary["findings"]), len(summary["problems"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
