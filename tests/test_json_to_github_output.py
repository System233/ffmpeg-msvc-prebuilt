"""Tests for scripts/ci/json_to_github_output.py."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from json_to_github_output import _stringify, main


class TestStringify(unittest.TestCase):
    """Unit tests for the ``_stringify()`` helper."""

    def test_string_passthrough(self):
        self.assertEqual(_stringify("hello"), "hello")

    def test_bool_true(self):
        self.assertEqual(_stringify(True), "true")

    def test_bool_false(self):
        self.assertEqual(_stringify(False), "false")

    def test_none_is_empty(self):
        self.assertEqual(_stringify(None), "")

    def test_integer(self):
        self.assertEqual(_stringify(42), "42")
        self.assertEqual(_stringify(-7), "-7")
        self.assertEqual(_stringify(0), "0")

    def test_float(self):
        self.assertEqual(_stringify(3.14), "3.14")

    def test_list(self):
        self.assertEqual(_stringify([1, 2, 3]), "[1, 2, 3]")

    def test_nested_object(self):
        self.assertEqual(
            _stringify({"x": 1, "y": [True, None]}),
            '{"x": 1, "y": [true, null]}',
        )


class TestMain(unittest.TestCase):
    """Integration-style tests for ``main()`` that exercise the real
    ``GITHUB_OUTPUT`` file, stdin, and error paths."""

    def _run_main(self, stdin_text: str, *, env: dict | None = None) -> str:
        """Inject *stdin_text* as stdin, set *env* vars, call ``main()``,
        and return the contents of the GITHUB_OUTPUT temp file.

        Raises ``SystemExit`` if ``main()`` exits non-zero.
        """
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, encoding="utf-8", suffix=".txt"
        ) as tmp:
            tmp_path = tmp.name

        full_env = {"GITHUB_OUTPUT": tmp_path}
        if env:
            full_env.update(env)

        saved_stdin = sys.stdin
        saved_environ = os.environ.copy()
        try:
            sys.stdin = io.StringIO(stdin_text)
            os.environ.clear()
            os.environ.update(full_env)
            main()
        finally:
            sys.stdin = saved_stdin
            os.environ.clear()
            os.environ.update(saved_environ)

        return Path(tmp_path).read_text(encoding="utf-8")

    def test_basic_json_dict(self):
        """Basic JSON dict produces correct GITHUB_OUTPUT format."""
        output = self._run_main('{"foo": "bar"}')
        self.assertEqual(output, "foo=bar\n")

    def test_multiple_keys(self):
        """Multiple keys are each written on their own line."""
        output = self._run_main('{"a": "1", "b": "2", "c": "3"}')
        self.assertEqual(output, "a=1\nb=2\nc=3\n")

    def test_integer_values(self):
        """Integer values are stringified."""
        output = self._run_main('{"count": 99, "zero": 0}')
        self.assertEqual(output, "count=99\nzero=0\n")

    def test_boolean_values(self):
        """Boolean values become lowercase true/false."""
        output = self._run_main('{"enabled": true, "disabled": false}')
        self.assertEqual(output, "enabled=true\ndisabled=false\n")

    def test_empty_values(self):
        """Empty string values are written as ``key=``."""
        output = self._run_main('{"name": ""}')
        self.assertEqual(output, "name=\n")

    def test_null_values(self):
        """Null values are written as empty (``key=``)."""
        output = self._run_main('{"name": null}')
        self.assertEqual(output, "name=\n")

    def test_nested_objects(self):
        """Nested objects have their JSON string representation as the value."""
        output = self._run_main('{"data": {"x": 1, "y": [2, 3]}}')
        self.assertEqual(output, 'data={"x": 1, "y": [2, 3]}\n')

    def test_missing_github_output_env(self):
        """Exit 1 when GITHUB_OUTPUT env var is not set."""
        saved = os.environ.copy()
        try:
            os.environ.pop("GITHUB_OUTPUT", None)
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_empty_stdin(self):
        """Exit 1 when stdin is empty."""
        with self.assertRaises(SystemExit) as ctx:
            self._run_main("")
        self.assertEqual(ctx.exception.code, 1)

    def test_whitespace_only_stdin(self):
        """Exit 1 when stdin contains only whitespace."""
        with self.assertRaises(SystemExit) as ctx:
            self._run_main("   \n  \t  ")
        self.assertEqual(ctx.exception.code, 1)

    def test_invalid_json(self):
        """Exit 1 when stdin is not valid JSON."""
        with self.assertRaises(SystemExit) as ctx:
            self._run_main("not json at all")
        self.assertEqual(ctx.exception.code, 1)

    def test_json_array_instead_of_object(self):
        """Exit 1 when stdin is a JSON array instead of an object."""
        with self.assertRaises(SystemExit) as ctx:
            self._run_main("[1, 2, 3]")
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
