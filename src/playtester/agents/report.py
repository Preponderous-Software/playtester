"""Checks an agent's report.json against the report schema.

    pt report                      (the current session's report.json)
    python3 -m playtester.agents.report SESSION_DIR/report.json
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

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


def check_file(path: str) -> List[str]:
    try:
        with open(path, encoding="utf-8") as f:
            report = json.load(f)
    except OSError as e:
        return ["%s: cannot read: %s" % (path, e.strerror)]
    except ValueError as e:
        return ["%s: not valid JSON: %s" % (path, e)]
    return check_report(report, report_dir=os.path.dirname(os.path.abspath(path)))


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    errors = check_file(argv[1])
    for e in errors:
        print(e)
    if not errors:
        with open(argv[1], encoding="utf-8") as f:
            print("ok: %s is a valid report (%d findings)" % (argv[1], len(json.load(f)["findings"])))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
