"""Detect duplicated tests across .py and .clausal test files.

Writes DUPLICATE_TESTS.md at repo root, grouped by submodule.
"""
from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"


SUBMODULE_RULES = [
    ("prolog",       re.compile(r"(prolog|gprolog)")),
    ("constraints",  re.compile(r"(clp[a-z]*|coroutin|attribute|global_constraint|reif)")),
    ("scipy_torch",  re.compile(r"(scipy|torch|sklearn|numpy)")),
    ("modules",      re.compile(r"(regex|json|csv|http|yaml|toml|os_module|process|files_module|random|crypto|logging|date_time|chars|python_|ipython|jupyter|list_|dict_set|clausal_modules|sqlite|xml|units|stats|pandas|module_)")),
    ("control",      re.compile(r"(tabl|dif|exception|reified_ite|lambda|meta|higher_order|dcg|edcg|control|metainterp)")),
    ("core",         re.compile(r"(compil|database|predicate_meta|term|unif|builtin|directive|import|search|first_arg|groundness|pycache|codegen|phase5|continuation|body_star|callsite|deep_index|destructive|free_threading|listing|visual)")),
    ("docs",         re.compile(r"(doc_snippet|docs_)")),
]


def classify(path: Path) -> str:
    name = path.stem.lower() if path.suffix == ".py" else path.name.lower()
    for label, rx in SUBMODULE_RULES:
        if rx.search(name):
            return label
    return "misc"


def has_doctest(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    doc = ast.get_docstring(node) or ""
    return ">>>" in doc


def body_without_docstring(node):
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def fn_fingerprint(node) -> str:
    body = body_without_docstring(node)
    if not body:
        return "EMPTY"
    dumps = [ast.dump(stmt, annotate_fields=True) for stmt in body]
    return hashlib.sha1("\n".join(dumps).encode()).hexdigest()


def iter_py_tests():
    for py in sorted(TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                if has_doctest(node):
                    continue
                yield py, node.name, node.lineno, fn_fingerprint(node)


TEST_CLAUSE_RE = re.compile(r'^Test\(("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')\)\s*<-\s*(.+?)\s*$')


def iter_clausal_tests():
    for cl in sorted(TESTS.rglob("*.clausal")):
        try:
            text = cl.read_text()
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            m = TEST_CLAUSE_RE.match(stripped)
            if not m:
                continue
            desc, body = m.group(1), m.group(2)
            body_norm = re.sub(r"\s+", " ", body).strip()
            h = hashlib.sha1(body_norm.encode()).hexdigest()
            yield cl, desc, lineno, h


def main():
    py_groups: dict[str, list] = defaultdict(list)
    for path, name, lineno, fp in iter_py_tests():
        py_groups[fp].append((path, name, lineno))

    cl_groups: dict[str, list] = defaultdict(list)
    for path, desc, lineno, fp in iter_clausal_tests():
        cl_groups[fp].append((path, desc, lineno))

    out_lines = ["# Duplicate Tests Report", ""]

    out_lines.append("## Python test duplicates (identical AST bodies)")
    out_lines.append("")
    py_dupes = [(fp, hits) for fp, hits in py_groups.items() if len(hits) > 1 and fp != "EMPTY"]
    py_dupes.sort(key=lambda kv: -len(kv[1]))
    if not py_dupes:
        out_lines.append("_None found._")
    else:
        by_sub: dict[str, list] = defaultdict(list)
        for fp, hits in py_dupes:
            subs = {classify(p) for p, _, _ in hits}
            key = "+".join(sorted(subs))
            by_sub[key].append((fp, hits))
        for sub in sorted(by_sub):
            out_lines.append(f"### {sub}")
            out_lines.append("")
            for fp, hits in by_sub[sub]:
                out_lines.append(f"- fingerprint `{fp[:10]}` ({len(hits)} copies):")
                for p, name, ln in hits:
                    rel = p.relative_to(REPO)
                    out_lines.append(f"  - `{rel}:{ln}` — `{name}`")
            out_lines.append("")

    out_lines.append("## Empty-body Python tests (suspicious)")
    out_lines.append("")
    empty = py_groups.get("EMPTY", [])
    if not empty:
        out_lines.append("_None._")
    else:
        for p, name, ln in empty:
            out_lines.append(f"- `{p.relative_to(REPO)}:{ln}` — `{name}`")
    out_lines.append("")

    out_lines.append("## .clausal Test(...) duplicates (identical body text)")
    out_lines.append("")
    cl_dupes = [(fp, hits) for fp, hits in cl_groups.items() if len(hits) > 1]
    cl_dupes.sort(key=lambda kv: -len(kv[1]))
    if not cl_dupes:
        out_lines.append("_None found._")
    else:
        by_sub: dict[str, list] = defaultdict(list)
        for fp, hits in cl_dupes:
            subs = {classify(p) for p, _, _ in hits}
            key = "+".join(sorted(subs))
            by_sub[key].append((fp, hits))
        for sub in sorted(by_sub):
            out_lines.append(f"### {sub}")
            out_lines.append("")
            for fp, hits in by_sub[sub]:
                out_lines.append(f"- {len(hits)} copies:")
                for p, desc, ln in hits:
                    rel = p.relative_to(REPO)
                    out_lines.append(f"  - `{rel}:{ln}` — `Test({desc})`")
            out_lines.append("")

    (REPO / "DUPLICATE_TESTS.md").write_text("\n".join(out_lines))
    n_py = sum(len(h) for _, h in py_dupes)
    n_cl = sum(len(h) for _, h in cl_dupes)
    print(f"py duplicate groups: {len(py_dupes)} ({n_py} total copies)")
    print(f"clausal duplicate groups: {len(cl_dupes)} ({n_cl} total copies)")
    print(f"empty py test bodies: {len(empty)}")


if __name__ == "__main__":
    main()
