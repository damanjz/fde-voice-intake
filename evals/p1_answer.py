"""Load project 1's typed yes/no reader for the eval, read-only.

Project 1 has its own `app` package, which clashes with this project's, so its module cannot be imported. This
parses `app/agent.py` with `ast` and runs only the regexes and the `_typed_answer` function from it, in an
isolated namespace. Nothing in project 1 is changed or imported. Used only by the evals, never by the service.
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Callable
from pathlib import Path

P1_AGENT = Path(os.environ.get("P1_AGENT_PY", str(Path(__file__).resolve().parents[2] / "fde-support-agent" / "app" / "agent.py")))
_NAMES = {"_STRONG_YES_RE", "_HEDGE_RE", "_WEAK_YES_RE", "_NO_START_RE", "_DECLINE_RE"}


def load_typed_answer(path: Path = P1_AGENT) -> Callable[[str], tuple[bool | None, str | None]] | None:
    """P1's `_typed_answer(message) -> (confirm, extra)`, or None if the file or the pieces are not there."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    nodes: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in _NAMES for t in node.targets) or isinstance(node, ast.FunctionDef) and node.name == "_typed_answer":
            nodes.append(node)
    namespace: dict = {"re": re}
    try:
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)  # noqa: S102
    except Exception:  # noqa: BLE001 - a P1 refactor must not break the eval, only disable this column
        return None
    return namespace.get("_typed_answer")


def p1_reads(text: str, fn: Callable | None) -> str | None:
    """'yes', 'no' or None according to P1's typed reader (None as well when it is not available)."""
    if fn is None:
        return None
    confirm, _ = fn(text)
    return {True: "yes", False: "no"}.get(confirm)
