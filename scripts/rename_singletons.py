"""Rename per-clause singleton variable occurrences to NAME_UNUSED.

.clausal files are Python-parseable; each top-level statement is one clause.
Edits are applied per exact (lineno, col_offset) occurrence, bottom-up so
earlier spans stay valid. Directives (-name(...) => USub statements) are
skipped. Names already suffixed _UNUSED, bare `_`, and non-variable names
are left alone.
"""
import ast, pathlib, sys
from collections import Counter


def is_var(name):
    if name == "_" or name.startswith("__"):
        return False
    if (len(name) >= 3 and name[0] == "_" and name[-1] == "_"
            and name[1] != "_" and name[-2] != "_" and not name[1].isdigit()):
        return False  # constant-shaped: not a variable
    return name.startswith("_") or name.isupper()


def singleton_sites(tree):
    for stmt in tree.body:
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.UnaryOp)
                and isinstance(stmt.value.op, ast.USub)):
            continue
        names = [n for n in ast.walk(stmt)
                 if isinstance(n, ast.Name) and is_var(n.id)]
        counts = Counter(n.id for n in names)
        for n in names:
            if counts[n.id] == 1 and not n.id.endswith("_UNUSED"):
                yield n


def rewrite(path):
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    sites = sorted(singleton_sites(tree),
                   key=lambda n: (n.lineno, n.col_offset), reverse=True)
    for n in sites:
        ln = n.lineno - 1
        col = n.col_offset
        assert lines[ln][col:col + len(n.id)] == n.id, (path, n.lineno, n.id)
        lines[ln] = (lines[ln][:col] + n.id + "_UNUSED"
                     + lines[ln][col + len(n.id):])
    if sites:
        path.write_text("".join(lines))
    return len(sites)


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    total = 0
    for p in sorted(root.rglob("*.clausal")):
        if ".claude" in p.parts:
            continue
        total += rewrite(p)
    print(f"renamed {total} occurrences")
