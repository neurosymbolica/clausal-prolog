"""Classify each Python test function as infra / behavior / mixed / unknown.

Heuristic: walk the AST of each `test_*` function and inspect the set of
names/attributes it references. Membership in INFRA_NAMES vs BEHAVIOR_NAMES
decides the label.

  behavior  — exercises the Clausal language through solve/query/once/call/
              run_file and asserts on answers. Migration candidate → .clausal.
  infra     — exercises Python-level implementation: AST nodes, compiler passes,
              Database/PredicateMeta internals, Var/Trail, parser, bytecode
              cache, Python adapters. Stays in Python.
  mixed     — touches both; needs manual split.
  unknown   — touches neither set; review manually.
"""
from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"

BEHAVIOR_NAMES = {
    # query entry points — hitting these means we're running Clausal
    "solve", "once", "query", "call", "call_goal",
    "query_wfs", "solve_all",
    "run_file", "run_test", "load_clausal_module", "collect_tests",
    "phrase",
    # high-level meta predicates (used as query-level tests)
    "find_all", "bag_of", "set_of", "for_all",
}

INFRA_NAMES = {
    # compiler pipeline
    "compile_predicate", "compile_predicate_trampoline", "compile_goal",
    "compile_module", "compile_clause", "_install",
    "TermTransformer", "EmbedTransformer", "term_to_ast_expr",
    "run_term_expansion", "run_goal_expansion",
    "predicate_to_source", "visualize",
    # runtime primitives
    "Var", "Trail", "deref", "structural_unify", "unify",
    # database / registry
    "Database", "Module", "PredicateMeta", "PredicateTable",
    "get_builtin_predicate", "BuiltinPredicate",
    "is_term_instance", "term_field_names", "make_predicate",
    # parser / AST
    "ast", "parse_clausal", "parse_module", "parse_file",
    # caching / import
    "import_hook", "LogicModule",
    # tabling / constraint internals
    "TableEntry", "SuspendedConsumer",
    "FDVar", "Domain", "BDDNode",
    # dialect/prolog infra
    "OperatorTable", "Dialect", "PrologAST",
    "Token", "TokenType", "tokenize", "TokenizeError",
    "parse", "parse_term", "ParseError", "PrologParser",
    "PAtom", "PVar", "PNumber", "PString", "PCompound", "PList",
    "PCurly", "PClause", "PDCGRule", "PDirective", "PQuery", "PModule",
    # numeric / analytic wrappers — their unit tests are Python-only
    "Unit", "Quantity", "Dimension",  # units infra
    "np", "numpy", "torch",  # direct numeric lib usage is infra-adjacent
}

# Attribute accesses we treat as infra regardless of the base name
INFRA_ATTRS = {
    "_clauses", "_dispatch_fn", "_signature", "_locked", "_fields",
    "_get_dispatch", "set_dispatch", "get_dispatch",
    "_lazy_recompile", "module_dict",
    "__signatures__", "__match_args__", "__slots__",
    "emit", "parse", "tokenize",  # prolog pipeline attrs
}

# Helper-name hints (treat as behavior when used): local drivers that wrap a
# clausal call, common across many test files.
BEHAVIOR_HELPERS = {
    "_goal_succeeds", "_goal_fails", "_run", "_solve", "_once",
    "_query", "_drive", "_drive_result_get", "_expect",
    "_first_solution", "_all_solutions",
}
BEHAVIOR_NAMES |= BEHAVIOR_HELPERS

# AST-node constructors imported from clausal.terms count as infra use
# (building queries by hand in Python rather than using .clausal syntax).
TERM_AST_NODES = {
    "Compound", "Call", "LoadName", "LoadAttr",
    "Evaluate", "Add", "Sub", "Mult", "FloorDiv", "Mod", "Pow", "Negate",
    "Lt", "LtE", "Gt", "GtE", "Eq", "NotEq",
    "And", "Or", "Not", "IfExpr", "FindAll", "BagOf", "SetOf", "ForAll",
    "DictTerm", "SetTerm",
}

SUBMODULE_RULES = [
    ("prolog",       ("prolog", "gprolog")),
    ("constraints",  ("clp", "coroutin", "attribute", "global_constraint", "reif")),
    ("scipy_torch",  ("scipy", "torch", "sklearn", "numpy")),
    ("modules",      ("regex", "json", "csv", "http", "yaml", "toml", "os_module",
                      "process", "files_module", "random", "crypto", "logging",
                      "date_time", "chars", "python_", "ipython", "jupyter",
                      "list_", "dict_set", "clausal_modules", "sqlite", "xml",
                      "units", "stats", "pandas", "module_")),
    ("control",      ("tabl", "dif", "exception", "reified_ite", "lambda", "meta",
                      "higher_order", "dcg", "edcg", "control", "metainterp",
                      "wfs")),
    ("core",         ("compil", "database", "predicate_meta", "term", "unif",
                      "builtin", "directive", "import", "search", "first_arg",
                      "groundness", "pycache", "codegen", "phase5", "continuation",
                      "body_star", "callsite", "deep_index", "destructive",
                      "free_threading", "listing", "visual")),
    ("docs",         ("doc_snippet", "docs_")),
    ("conformity",   ("iso_", "conformity")),
]


def classify_path(path: Path) -> str:
    name = path.stem.lower()
    rel = str(path.relative_to(TESTS)).lower()
    for label, keys in SUBMODULE_RULES:
        if any(k in name or k in rel for k in keys):
            return label
    return "misc"


def collect_refs(node):
    """Return (name_set, attr_set) referenced anywhere inside node."""
    names, attrs = set(), set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            attrs.add(sub.attr)
    return names, attrs


def _hits(names: set, attrs: set) -> tuple[set, set]:
    bh = names & BEHAVIOR_NAMES
    ih = (names & INFRA_NAMES) | (names & TERM_AST_NODES) | (attrs & INFRA_ATTRS)
    return bh, ih


def _build_helper_labels(tree):
    """Compute each local helper's own label ('behavior'/'infra'/'mixed'/None).

    A helper is an abstraction boundary: a test that calls it inherits the
    helper's *label*, not the helper's internal refs. This stops Var/Trail
    used inside a thin driver from poisoning every behavior test."""
    helpers: dict[str, tuple[set, set, str | None]] = {}
    direct: dict[str, tuple[set, set]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            direct[node.name] = collect_refs(node)

    # iterate to fixpoint so helper-calls-helper propagates
    for _ in range(5):
        changed = False
        for h, (n, a) in direct.items():
            bh, ih = _hits(n, a)
            # inherit from sub-helpers
            for callee in list(n):
                if callee in direct and callee != h:
                    cb, ci = _hits(*direct[callee])
                    bh |= cb
                    ih |= ci
                    # propagate recursively via names union for next iter
                    new_n = n | direct[callee][0]
                    new_a = a | direct[callee][1]
                    if new_n != n or new_a != a:
                        direct[h] = (new_n, new_a)
                        changed = True
            if bh and ih:
                label = "mixed"
            elif bh:
                label = "behavior"
            elif ih:
                label = "infra"
            else:
                label = None
            helpers[h] = (bh, ih, label)
        if not changed:
            break
    return helpers


def classify_fn(node, helpers=None):
    names, attrs = collect_refs(node)
    bh, ih = _hits(names, attrs)
    if helpers:
        for callee in list(names):
            h = helpers.get(callee)
            if not h:
                continue
            bh |= h[0]
            ih |= h[1]

    has_b = bool(bh)
    has_i = bool(ih)

    if has_b and not has_i:
        label = "behavior"
    elif has_i and not has_b:
        label = "infra"
    elif has_b and has_i:
        label = "mixed"
    else:
        label = "unknown"
    return label, bh, ih


def iter_tests():
    for py in sorted(TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        helpers = _build_helper_labels(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                label, bh, ih = classify_fn(node, helpers)
                yield py, node.name, node.lineno, label, bh, ih


def main():
    # per-file aggregate counts + per-function detail
    file_counts: dict[Path, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_submodule: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    details: list[tuple] = []

    for path, name, ln, label, bh, ih in iter_tests():
        file_counts[path][label] += 1
        per_submodule[classify_path(path)][label] += 1
        details.append((path, name, ln, label, sorted(bh), sorted(ih)))

    # Load duplicate report if present, mark migration-priority entries
    dupe_path = REPO / "DUPLICATE_TESTS.md"
    dupe_fns: set[tuple[str, str]] = set()
    if dupe_path.exists():
        import re
        # lines like "  - `tests/...py:NN` — `test_xxx`"
        rx = re.compile(r'`([^`]+\.py):(\d+)`\s+—\s+`([^`]+)`')
        for m in rx.finditer(dupe_path.read_text()):
            dupe_fns.add((m.group(1), m.group(3)))

    out = ["# Test Migration Candidates", ""]
    out.append("Tests classified as **behavior** exercise the Clausal language via "
               "`solve`/`once`/`query`/`call`/`run_file` and should migrate to `.clausal` "
               "fixtures. **infra** tests assert on Python-level implementation and stay in "
               "Python. **mixed** needs manual split. **unknown** needs review.")
    out.append("")
    out.append("## Summary by submodule")
    out.append("")
    out.append("| submodule | behavior | mixed | unknown | infra |")
    out.append("|---|---:|---:|---:|---:|")
    for sub in sorted(per_submodule):
        c = per_submodule[sub]
        out.append(f"| {sub} | {c['behavior']} | {c['mixed']} | {c['unknown']} | {c['infra']} |")
    out.append("")

    out.append("## Summary by file (files with ≥1 behavior or mixed test)")
    out.append("")
    out.append("| file | behavior | mixed | unknown | infra |")
    out.append("|---|---:|---:|---:|---:|")
    rows = []
    for path, c in file_counts.items():
        if c["behavior"] or c["mixed"]:
            rows.append((classify_path(path), path, c))
    rows.sort(key=lambda r: (r[0], -r[2]["behavior"], -r[2]["mixed"], str(r[1])))
    for sub, path, c in rows:
        rel = path.relative_to(REPO)
        out.append(f"| `{rel}` ({sub}) | {c['behavior']} | {c['mixed']} | {c['unknown']} | {c['infra']} |")
    out.append("")

    out.append("## Per-test classification")
    out.append("")
    out.append("Entries marked **†** are also listed in `DUPLICATE_TESTS.md` — prefer deletion over migration when an equivalent `.clausal` test already covers them.")
    out.append("")

    by_sub: dict[str, list] = defaultdict(list)
    for path, name, ln, label, bh, ih in details:
        by_sub[classify_path(path)].append((path, name, ln, label, bh, ih))

    for sub in sorted(by_sub):
        out.append(f"### {sub}")
        out.append("")
        entries = by_sub[sub]
        # group by file for readability
        by_file: dict[Path, list] = defaultdict(list)
        for e in entries:
            by_file[e[0]].append(e)
        for path in sorted(by_file):
            rel = path.relative_to(REPO)
            out.append(f"<details><summary><code>{rel}</code></summary>")
            out.append("")
            out.append("| line | label | test | behavior-hits | infra-hits |")
            out.append("|---:|---|---|---|---|")
            for _, name, ln, label, bh, ih in sorted(by_file[path], key=lambda x: x[2]):
                dup = "†" if (str(rel), name) in dupe_fns else ""
                bh_s = ", ".join(bh) if bh else ""
                ih_s = ", ".join(ih) if ih else ""
                out.append(f"| {ln} | **{label}**{dup} | `{name}` | {bh_s} | {ih_s} |")
            out.append("")
            out.append("</details>")
            out.append("")

    (REPO / "MIGRATION_CANDIDATES.md").write_text("\n".join(out))
    # tally
    totals = defaultdict(int)
    for _, c in file_counts.items():
        for k, v in c.items():
            totals[k] += v
    print("totals:", dict(totals))
    print("wrote", REPO / "MIGRATION_CANDIDATES.md")


if __name__ == "__main__":
    main()
