"""Render repository-owned Markdown templates; never evaluate model text."""
from pathlib import Path
from string import Template
import re


TEMPLATE_DIR = Path(__file__).with_name("templates")


def render_template(name: str, **values: str | int) -> str:
    if not re.fullmatch(r"[a-z][a-z-]*\.md", name):
        raise ValueError("Invalid Markdown template name")
    template = Template((TEMPLATE_DIR / name).read_text(encoding="utf-8"))
    # Strict, single-pass substitution. No template logic, evaluation or recursive expansion.
    if set(template.get_identifiers()) != set(values) or not template.is_valid():
        raise ValueError(f"Invalid Markdown template arguments: {name}")
    return template.substitute(values).rstrip("\n")
