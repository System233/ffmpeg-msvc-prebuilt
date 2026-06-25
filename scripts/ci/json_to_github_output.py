#!/usr/bin/env python3
"""Read a JSON object from stdin and write it as ``key=value`` lines to
the file pointed to by the ``GITHUB_OUTPUT`` environment variable.

Usage::

    echo '{"foo": "bar", "baz": true}' | python scripts/ci/json_to_github_output.py
"""

from __future__ import annotations

import json
import os
import sys


def _stringify(value: object) -> str:
    """Convert *value* to a string suitable for a GitHub Actions output line.

    * Strings are returned as-is.
    * Booleans become lowercase ``"true"`` / ``"false"``.
    * ``None`` / ``null`` is treated as an empty value (``""``).
    * Everything else (int, float, list, dict) is serialised with
      :func:`json.dumps`.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return json.dumps(value)


def main() -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print(
            "error: GITHUB_OUTPUT environment variable is not set",
            file=sys.stderr,
        )
        raise SystemExit(1)

    raw = sys.stdin.read()
    if not raw.strip():
        print("error: stdin is empty – expected a JSON object", file=sys.stderr)
        raise SystemExit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON on stdin: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if not isinstance(data, dict):
        print(
            f"error: expected a JSON object (dict), got {type(data).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    with open(github_output, "a", encoding="utf-8") as fh:
        for key, value in data.items():
            fh.write(f"{key}={_stringify(value)}\n")


# NOTE: Currently supports only single-line key=value output.
# Multiline values require the <<EOF heredoc syntax, which is not yet implemented.
if __name__ == "__main__":
    main()
