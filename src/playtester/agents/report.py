"""Checks an agent's report.json against the report schema.

    pt report                      (the current session's report.json)
    python3 -m playtester.agents.report SESSION_DIR/report.json

``pt report`` also checks that every question in the session's profile
(``questions``) has an answer in the report's ``answers``.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

from ..schema import load_schema, validate


def check_report(report: Any, schema: Optional[Dict[str, Any]] = None, report_dir: Optional[str] = None) -> List[str]:
    """Schema problems, plus screenshots that do not exist (relative paths are taken from ``report_dir``)."""
    schema = schema or load_schema("report.schema.json")
    errors = validate(report, schema)
    if not errors and report_dir is not None:
        for i, finding in enumerate(report.get("findings", [])):
            shot = finding.get("screenshot")
            if shot and not os.path.isfile(shot if os.path.isabs(shot) else os.path.join(report_dir, shot)):
                errors.append("$.findings[%d].screenshot: no such file %s" % (i, shot))
    return errors


def same_question(a: Any, b: Any) -> bool:
    """Questions compare equal ignoring case, spacing and surrounding punctuation."""
    def norm(text: Any) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip(" \t\"'").casefold()
    return norm(a) == norm(b)


def answer_to(report: Any, question: str) -> Optional[str]:
    """The report's answer to ``question``, or None when it has none."""
    answers = report.get("answers") if isinstance(report, dict) else None
    for item in answers if isinstance(answers, list) else []:
        if isinstance(item, dict) and same_question(item.get("question"), question):
            answer = item.get("answer")
            if isinstance(answer, str) and answer.strip():
                return answer
    return None


def unanswered(report: Any, questions: Optional[Sequence[str]]) -> List[str]:
    """One problem for each of the profile's ``questions`` the report does not answer."""
    return ["$.answers: no answer to question %d: %s" % (i, q)
            for i, q in enumerate(questions or [], 1) if answer_to(report, q) is None]


def check_file(path: str, questions: Optional[Sequence[str]] = None) -> List[str]:
    try:
        with open(path, encoding="utf-8") as f:
            report = json.load(f)
    except OSError as e:
        return ["%s: cannot read: %s" % (path, e.strerror)]
    except ValueError as e:
        return ["%s: not valid JSON: %s" % (path, e)]
    errors = check_report(report, report_dir=os.path.dirname(os.path.abspath(path)))
    return errors or unanswered(report, questions)


def main(argv: List[str], questions: Optional[Sequence[str]] = None) -> int:
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    errors = check_file(argv[1], questions)
    for e in errors:
        print(e)
    if not errors:
        with open(argv[1], encoding="utf-8") as f:
            print("ok: %s is a valid report (%d findings)" % (argv[1], len(json.load(f)["findings"])))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
