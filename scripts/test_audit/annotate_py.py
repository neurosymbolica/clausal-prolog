"""Annotate every Python test function with '# nv' (needs verification).

Rules:
  - Target: functions named test_* in files under tests/ matching test_*.py.
  - Skip doctest-only tests (docstring contains '>>>').
  - Insert comment as a new line BEFORE the first non-docstring statement,
    indented to match that statement.
  - Idempotent: skip if the first body line is already one of # nv / # NV / # NV!.
  - Escalate:
      # NV!  if body is only `pass` or `...`
      # NV   if body contains `assert True` with no siblings, or bare `except: pass`
      # nv   otherwise
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"


def has_doctest(node) -> bool:
    doc = ast.get_docstring(node) or ""
    return ">>>" in doc


def first_real_stmt(node):
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return body[0] if body else None


def escalation_level(node) -> str:
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return "# NV!"
    if len(body) == 1:
        s = body[0]
        if isinstance(s, ast.Pass):
            return "# NV!"
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis:
            return "# NV!"
        if isinstance(s, ast.Assert) and isinstance(s.test, ast.Constant) and s.test.value is True:
            return "# NV"
    for sub in ast.walk(node):
        if isinstance(sub, ast.ExceptHandler):
            if sub.type is None and len(sub.body) == 1 and isinstance(sub.body[0], ast.Pass):
                return "# NV"
    return "# nv"


def annotate_file(path: Path) -> int:
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return 0
    lines = src.splitlines(keepends=True)

    insertions = []  # list of (insert_before_lineno_1idx, indent, text)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if has_doctest(node):
            continue
        first = first_real_stmt(node)
        if first is None:
            # empty body (shouldn't normally parse, but 'def f(): pass' has Pass as first)
            continue
        ln = first.lineno  # 1-indexed
        indent = " " * first.col_offset
        # idempotency check — look at the target line (the first real stmt line)
        existing = lines[ln - 1] if ln - 1 < len(lines) else ""
        # also check the line directly above (where we'd insert)
        prev = lines[ln - 2] if ln - 2 >= 0 else ""
        if any(tok in prev for tok in ("# nv", "# NV", "# NV!")):
            continue
        if any(existing.lstrip().startswith(tok) for tok in ("# nv", "# NV", "# NV!")):
            continue
        level = escalation_level(node)
        insertions.append((ln, indent, level))

    if not insertions:
        return 0
    # apply in reverse so earlier line numbers stay valid
    insertions.sort(key=lambda x: x[0], reverse=True)
    for ln, indent, text in insertions:
        new_line = f"{indent}{text}\n"
        lines.insert(ln - 1, new_line)

    path.write_text("".join(lines))
    return len(insertions)


def main():
    total = 0
    files = 0
    for py in sorted(TESTS.rglob("test_*.py")):
        n = annotate_file(py)
        if n:
            files += 1
            total += n
    print(f"annotated {total} tests across {files} files")


if __name__ == "__main__":
    main()
