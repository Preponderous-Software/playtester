"""playtester.schema: each keyword the mini validator implements, checked directly."""

import unittest

import tests.helpers  # noqa: F401  (puts src on sys.path)
from playtester.schema import load_schema, validate


class TypeTest(unittest.TestCase):
    def test_each_type_name_accepts_its_values(self):
        for name, value in (("object", {}), ("array", []), ("string", ""), ("integer", 3), ("number", 2.5),
                            ("number", 4), ("boolean", False), ("null", None)):
            self.assertEqual(validate(value, {"type": name}), [], name)

    def test_a_wrong_type_is_named_and_stops_further_checks(self):
        self.assertEqual(validate("x", {"type": "integer", "enum": [1]}), ["$: expected integer, got str"])

    def test_booleans_are_neither_integers_nor_numbers(self):
        self.assertEqual(validate(True, {"type": "integer"}), ["$: expected integer, got bool"])
        self.assertEqual(validate(False, {"type": "number"}), ["$: expected number, got bool"])

    def test_floats_are_not_integers(self):
        self.assertEqual(validate(1.5, {"type": "integer"}), ["$: expected integer, got float"])

    def test_a_list_of_types_accepts_any_of_them(self):
        schema = {"type": ["integer", "null"]}
        self.assertEqual(validate(None, schema), [])
        self.assertEqual(validate(7, schema), [])
        self.assertEqual(validate("7", schema), ["$: expected integer or null, got str"])


class ValueTest(unittest.TestCase):
    def test_const(self):
        self.assertEqual(validate("a", {"const": "a"}), [])
        self.assertEqual(validate("b", {"const": "a"}), ["$: must be 'a'"])

    def test_enum(self):
        self.assertEqual(validate("low", {"enum": ["low", "high"]}), [])
        self.assertEqual(validate("mid", {"enum": ["low", "high"]}), ["$: 'mid' is not one of low, high"])

    def test_string_length_bounds_are_inclusive(self):
        schema = {"minLength": 2, "maxLength": 3}
        self.assertEqual(validate("ab", schema), [])
        self.assertEqual(validate("abc", schema), [])
        self.assertEqual(validate("a", schema), ["$: shorter than 2 characters"])
        self.assertEqual(validate("abcd", schema), ["$: longer than 3 characters"])

    def test_pattern_is_searched_not_fully_matched(self):
        self.assertEqual(validate("v1.2", {"pattern": r"\d"}), [])
        self.assertEqual(validate("v1.2", {"pattern": r"^\d"}), ["$: 'v1.2' does not match ^\\d"])

    def test_string_keywords_ignore_other_types(self):
        self.assertEqual(validate(5, {"minLength": 2, "pattern": "x"}), [])

    def test_numeric_bounds_are_inclusive(self):
        schema = {"minimum": 1, "maximum": 5}
        self.assertEqual(validate(1, schema), [])
        self.assertEqual(validate(5.0, schema), [])
        self.assertEqual(validate(0, schema), ["$: 0 is below 1"])
        self.assertEqual(validate(5.5, schema), ["$: 5.5 is above 5"])

    def test_numeric_bounds_ignore_booleans_and_strings(self):
        self.assertEqual(validate(True, {"minimum": 2}), [])
        self.assertEqual(validate("0", {"minimum": 2}), [])


class ObjectTest(unittest.TestCase):
    def test_every_missing_required_key_is_reported(self):
        self.assertEqual(validate({"a": 1}, {"required": ["a", "b", "c"]}),
                         ["$: missing required 'b'", "$: missing required 'c'"])

    def test_properties_are_checked_at_their_path(self):
        schema = {"properties": {"n": {"type": "integer"}, "inner": {"properties": {"s": {"type": "string"}}}}}
        self.assertEqual(validate({"n": "x", "inner": {"s": 1}}, schema),
                         ["$.n: expected integer, got str", "$.inner.s: expected string, got int"])

    def test_additional_properties_are_allowed_by_default(self):
        self.assertEqual(validate({"extra": 1}, {"properties": {}}), [])

    def test_additional_properties_false_rejects_unknown_keys(self):
        schema = {"properties": {"a": {}}, "additionalProperties": False}
        self.assertEqual(validate({"a": 1, "b": 2}, schema), ["$.b: unexpected property"])

    def test_additional_properties_schema_checks_unknown_keys(self):
        schema = {"properties": {"a": {}}, "additionalProperties": {"type": "integer"}}
        self.assertEqual(validate({"a": "known", "b": 2, "c": "x"}, schema), ["$.c: expected integer, got str"])


class ArrayTest(unittest.TestCase):
    def test_min_items(self):
        self.assertEqual(validate([1], {"minItems": 1}), [])
        self.assertEqual(validate([], {"minItems": 1}), ["$: fewer than 1 items"])

    def test_items_are_checked_with_their_index(self):
        self.assertEqual(validate([1, "two", 3, None], {"items": {"type": "integer"}}),
                         ["$[1]: expected integer, got str", "$[3]: expected integer, got NoneType"])


class CombinatorTest(unittest.TestCase):
    def test_all_of_collects_every_failure(self):
        schema = {"allOf": [{"minimum": 10}, {"maximum": 0}]}
        self.assertEqual(validate(5, schema), ["$: 5 is below 10", "$: 5 is above 0"])

    def test_any_of_passes_when_one_form_matches(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        self.assertEqual(validate(3, schema), [])

    def test_any_of_names_the_first_problem_of_each_form(self):
        schema = {"anyOf": [{"type": "string"}, {"required": ["a", "b"]}]}
        self.assertEqual(validate({}, schema),
                         ["$: matches none of the allowed forms "
                          "($: expected string, got dict; $: missing required 'a')"])

    def test_then_applies_only_when_if_matches(self):
        schema = {"if": {"properties": {"kind": {"const": "x"}}}, "then": {"required": ["x"]}}
        self.assertEqual(validate({"kind": "x"}, schema), ["$: missing required 'x'"])
        self.assertEqual(validate({"kind": "y"}, schema), [])

    def test_else_applies_only_when_if_fails(self):
        schema = {"if": {"properties": {"kind": {"const": "x"}}}, "then": {"required": ["x"]},
                  "else": {"required": ["other"]}}
        self.assertEqual(validate({"kind": "y"}, schema), ["$: missing required 'other'"])
        self.assertEqual(validate({"kind": "x", "x": 1}, schema), [])

    def test_if_errors_themselves_are_never_reported(self):
        self.assertEqual(validate({"kind": "y"}, {"if": {"properties": {"kind": {"const": "x"}}}}), [])


class RefTest(unittest.TestCase):
    def test_local_refs_resolve_against_the_root_schema(self):
        schema = {"$defs": {"pos": {"type": "integer", "minimum": 1}},
                  "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/pos"}}}}
        self.assertEqual(validate({"items": [1, 0]}, schema), ["$.items[1]: 0 is below 1"])

    def test_a_non_local_ref_is_refused(self):
        with self.assertRaises(ValueError):
            validate(1, {"$ref": "other.json#/x"})


class BundledSchemaTest(unittest.TestCase):
    def test_every_bundled_schema_loads_and_is_an_object(self):
        for name in ("event.schema.json", "profile.schema.json", "report.schema.json", "state.schema.json"):
            schema = load_schema(name)
            self.assertEqual(schema.get("type"), "object", name)
            self.assertNotEqual(validate({}, schema), [], name)


if __name__ == "__main__":
    unittest.main()
