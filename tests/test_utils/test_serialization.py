import unittest
import json
import base64
import dataclasses
from funcnodes_core.utils.serialization import JSONEncoder, JSONDecoder


class DummyRepr:
    def _repr_json_(self):
        return {"repr": "dummy"}


@dataclasses.dataclass
class Point:
    x: int
    y: int


class TestSerialization(unittest.TestCase):
    def test_basic_types(self):
        """Test that basic types (int, float, bool, None, str) are unchanged."""
        data = {"int": 1, "float": 3.14, "bool": True, "none": None, "str": "test"}
        encoded = json.dumps(data, cls=JSONEncoder)
        decoded = json.loads(encoded, cls=JSONDecoder)
        self.assertEqual(decoded, data)

    def test_bytes_encoding(self):
        """Test that bytes are encoded to a base64 string."""
        data = b"hello world"
        encoded = json.dumps(data, cls=JSONEncoder)
        decoded = json.loads(encoded, cls=JSONDecoder)
        expected = base64.b64encode(data).decode("utf-8")
        self.assertEqual(decoded, expected)

    def test_dataclass_encoding(self):
        """Test that dataclasses are converted to dictionaries."""
        point = Point(10, 20)
        encoded = json.dumps(point, cls=JSONEncoder)
        decoded = json.loads(encoded, cls=JSONDecoder)
        self.assertEqual(decoded, {"x": 10, "y": 20})

    def test_repr_json(self):
        """Test that objects with a _repr_json_ method are encoded accordingly."""
        dummy = DummyRepr()
        encoded = json.dumps(dummy, cls=JSONEncoder)
        decoded = json.loads(encoded, cls=JSONDecoder)
        self.assertEqual(decoded, {"repr": "dummy"})

    def test_circular_reference_list(self):
        """Test that a circular reference in a list raises a ValueError."""
        a = []
        b = {"self": a}
        a.append(b)
        with self.assertRaises(ValueError) as context:
            JSONEncoder.apply_custom_encoding(a)
        self.assertIn("Circular reference detected", str(context.exception))

    def test_circular_reference_dict(self):
        """Test that a circular reference in a dict raises a ValueError."""
        a = {}
        a["self"] = a
        with self.assertRaises(ValueError) as context:
            JSONEncoder.apply_custom_encoding(a)
        self.assertIn("Circular reference detected", str(context.exception))

    def test_preview_long_string(self):
        """Test that a long string is truncated in preview mode."""
        long_str = "a" * 1100
        previewed = JSONEncoder.apply_custom_encoding(long_str, preview=True)
        self.assertTrue(previewed.endswith("..."))
        self.assertEqual(len(previewed), 1003)  # 1000 characters + "..."

    def test_nested_structure(self):
        """Test a nested structure combining list, dict, bytes, dataclass, and _repr_json_ objects."""
        data = {
            "list": [1, 2, 3, b"bytes", {"dataclass": Point(5, 6)}],
            "repr": DummyRepr(),
        }
        encoded = json.dumps(data, cls=JSONEncoder)
        decoded = json.loads(encoded, cls=JSONDecoder)
        expected = {
            "list": [
                1,
                2,
                3,
                base64.b64encode(b"bytes").decode("utf-8"),
                {"dataclass": {"x": 5, "y": 6}},
            ],
            "repr": {"repr": "dummy"},
        }
        self.assertEqual(decoded, expected)

    def test_fallback_to_str(self):
        """Test that unsupported objects fall back to their string representation."""

        class Unsupported:
            def __str__(self):
                return "unsupported"

        obj = Unsupported()
        result = JSONEncoder.apply_custom_encoding(obj)
        self.assertEqual(result, "unsupported")


if __name__ == "__main__":
    unittest.main()
