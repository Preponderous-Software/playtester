"""A small JSON Schema checker, standard library only.

Playtester validates agent reports, game profiles and probe output (state.json
and events.jsonl) against the schemas in ``playtester/data/schemas``. Pulling
in the ``jsonschema`` package for that would make the harness depend on a
third-party library everywhere it runs, so this module implements just the
keywords those schemas use:

``type``, ``enum``, ``const``, ``required``, ``properties``,
``additionalProperties`` (true, false or a schema), ``items``, ``minItems``,
``minimum``, ``maximum``, ``minLength``, ``maxLength``, ``pattern``,
``allOf``, ``anyOf``, ``if``/``then`` and local ``$ref`` (``#/$defs/name``).

Unknown keywords are ignored, as JSON Schema itself does. ``validate`` returns
a list of ``"path: problem"`` strings, empty when the value is valid.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SCHEMA_DIR = os.path.join(DATA_DIR, "schemas")

TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def load_schema(name: str) -> Dict[str, Any]:
    """One of the bundled schemas by file name, e.g. ``report.schema.json``."""
    with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _resolve(ref: str, root: Dict[str, Any]) -> Dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError("only local $ref values are supported, not %r" % ref)
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate(value: Any, schema: Dict[str, Any], path: str = "$", root: Optional[Dict[str, Any]] = None) -> List[str]:
    """Every way ``value`` fails ``schema``, as ``"path: problem"`` strings."""
    if root is None:
        root = schema
    if "$ref" in schema:
        return validate(value, _resolve(schema["$ref"], root), path, root)
    errors = []  # type: List[str]
    expected = schema.get("type")
    if expected is not None:
        names = expected if isinstance(expected, list) else [expected]
        if not any(TYPES[name](value) for name in names):
            return ["%s: expected %s, got %s" % (path, " or ".join(names), type(value).__name__)]
    if "const" in schema and value != schema["const"]:
        errors.append("%s: must be %r" % (path, schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: %r is not one of %s" % (path, value, ", ".join(map(str, schema["enum"]))))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("%s: shorter than %d characters" % (path, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append("%s: longer than %d characters" % (path, schema["maxLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append("%s: %r does not match %s" % (path, value, schema["pattern"]))
    if TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: %s is below %s" % (path, value, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: %s is above %s" % (path, value, schema["maximum"]))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append("%s: missing required '%s'" % (path, key))
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            where = "%s.%s" % (path, key)
            if key in properties:
                errors.extend(validate(item, properties[key], where, root))
            elif extra is False:
                errors.append("%s: unexpected property" % where)
            elif isinstance(extra, dict):
                errors.extend(validate(item, extra, where, root))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append("%s: fewer than %d items" % (path, schema["minItems"]))
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(validate(item, schema["items"], "%s[%d]" % (path, i), root))
    for sub in schema.get("allOf", []):
        errors.extend(validate(value, sub, path, root))
    if "anyOf" in schema:
        attempts = [validate(value, sub, path, root) for sub in schema["anyOf"]]
        if all(attempts):
            errors.append("%s: matches none of the allowed forms (%s)" % (path, "; ".join(a[0] for a in attempts)))
    if "if" in schema and not validate(value, schema["if"], path, root):
        if "then" in schema:
            errors.extend(validate(value, schema["then"], path, root))
    elif "if" in schema and "else" in schema:
        errors.extend(validate(value, schema["else"], path, root))
    return errors
