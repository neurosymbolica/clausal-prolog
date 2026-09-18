"""P2 Task 1: census of PredicateMeta INSTANCE sites, for the terms-as-tuples rewrite.

Walks ``clausal/**/*.py``, ``clausal/**/*.c`` and ``packages/**/*.py`` (excluding any
path containing ``/build/``) for the eight spellings the plan names as INSTANCE
sites -- a PredicateMeta instance being built, a data-functor class being minted,
or fields being read off one:

    is_term_instance(            term_field_names(            term_field_names_of_class(
    make_predicate(               _make_functor_class_ast(     ._fields   (attribute read)
    PredicateMeta_type            (C)                          isinstance(<x>, PredicateMeta)

Each pattern is matched independently, so a line matching two patterns (rare)
yields two rows. Prints the POPULATION SIZE (files scanned) before the match
count and asserts the population is non-empty -- an extraction that silently
yields nothing is this lane's dominant failure mode (see the sibling
``check_p1.py`` docstring and the operator's memory note on instruments that
fail open).

Writes ``P2_SITES.tsv``: file, line, qualname, pattern, kind, disposition, note.
``qualname`` is the enclosing def/class for a .py site (dotted, via ``ast``) or
the enclosing C function for a .c site (via a brace-depth scan that tolerates
nested same-line braces; "(module scope)" when a match sits outside any
function, e.g. the module-level ``PredicateMeta_type`` variable declaration).
``kind``, ``disposition`` and ``note`` are written blank; Task 1 Step 3 fills
``kind`` by reading each site's enclosing function, one at a time, and never
from the matched line alone.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # tools/predmeta_census -> tools -> repo root
CLAUSAL = ROOT / "clausal"
PACKAGES = ROOT / "packages"
OUT_TSV = HERE / "P2_SITES.tsv"

# Patterns matched inside .py source (clausal/ and packages/).
PY_PATTERNS = [
    ("term_field_names_of_class(", re.compile(r"\bterm_field_names_of_class\(")),
    ("is_term_instance(", re.compile(r"\bis_term_instance\(")),
    ("term_field_names(", re.compile(r"\bterm_field_names\(")),
    ("make_predicate(", re.compile(r"\bmake_predicate\(")),
    ("_make_functor_class_ast(", re.compile(r"\b_make_functor_class_ast\(")),
    ("._fields", re.compile(r"\._fields\b")),
    ("isinstance(<x>, PredicateMeta)", re.compile(r"\bisinstance\(\s*[^,()]+(?:\([^)]*\))?[^,()]*,\s*PredicateMeta\s*\)")),
]

# Pattern matched inside .c source (clausal/ only -- packages/ carries no C).
C_PATTERNS = [
    ("PredicateMeta_type (C)", re.compile(r"\bPredicateMeta_type\b")),
]


def iter_source_files():
    """Yield (path, language) for every file in the walked population."""
    py_roots = [CLAUSAL, PACKAGES]
    for root in py_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "/build/" in path.as_posix():
                continue
            yield path, "py"
    if CLAUSAL.is_dir():
        for path in sorted(CLAUSAL.rglob("*.c")):
            if "/build/" in path.as_posix():
                continue
            yield path, "c"


# ---------------------------------------------------------------------------
# Python qualname resolution: the innermost enclosing def/class, dotted.

class _ScopeVisitor(ast.NodeVisitor):
    def __init__(self):
        self.scopes = []  # (start_line, end_line, dotted_qualname)
        self._stack = []

    def _enter(self, node):
        self._stack.append(node.name)
        end = getattr(node, "end_lineno", node.lineno)
        self.scopes.append((node.lineno, end, ".".join(self._stack)))
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node):
        self._enter(node)

    def visit_AsyncFunctionDef(self, node):
        self._enter(node)

    def visit_ClassDef(self, node):
        self._enter(node)


def py_qualname_index(source: str):
    """Return a function line -> innermost dotted qualname, given file source.

    Returns None if the file does not parse (the walker then falls back to
    "(unparsed)" for every row in that file -- a human reads it directly).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    visitor = _ScopeVisitor()
    visitor.visit(tree)
    scopes = visitor.scopes

    def lookup(lineno: int) -> str:
        best = None
        best_span = None
        for start, end, name in scopes:
            if start <= lineno <= end:
                span = end - start
                if best_span is None or span < best_span:
                    best, best_span = name, span
        return best if best is not None else "(module scope)"

    return lookup


# ---------------------------------------------------------------------------
# C qualname resolution: brace-depth scan, comments/strings stripped first.

def _strip_c_comments_and_literals(lines):
    out = []
    in_block_comment = False
    for line in lines:
        buf = []
        i = 0
        n = len(line)
        in_str = False
        in_chr = False
        while i < n:
            c = line[i]
            if in_block_comment:
                if c == "*" and i + 1 < n and line[i + 1] == "/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    in_str = False
                i += 1
                continue
            if in_chr:
                if c == "\\":
                    i += 2
                    continue
                if c == "'":
                    in_chr = False
                i += 1
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "*":
                in_block_comment = True
                i += 2
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if c == '"':
                in_str = True
                i += 1
                continue
            if c == "'":
                in_chr = True
                i += 1
                continue
            buf.append(c)
            i += 1
        out.append("".join(buf))
    return out


_C_NAME_RE = re.compile(r"([A-Za-z_]\w*)\s*\(")


def c_function_regions(raw_lines):
    """Return [(start_1based, end_1based, name)] for each top-level C function.

    A function's opening brace is assumed alone on its own line at column 0
    (this file's consistent style, checked against the 8 known
    PredicateMeta_type-bearing functions). The true close is found by brace
    counting on comment/string-stripped text, so a nested if/for block whose
    own brace also happens to sit alone on its line does not truncate the
    region early.
    """
    stripped = _strip_c_comments_and_literals(raw_lines)
    n = len(raw_lines)
    regions = []
    depth = 0
    i = 0
    while i < n:
        if depth == 0 and raw_lines[i].strip() == "{":
            j = i - 1
            sig_lines = []
            while j >= 0:
                t = raw_lines[j].strip()
                if t == "" or t == "}":
                    break
                sig_lines.append(raw_lines[j])
                j -= 1
                if t.endswith(";"):
                    break
            sig_lines.reverse()
            sig_text = " ".join(sig_lines)
            sig_text = re.sub(r"/\*.*?\*/", " ", sig_text)
            m = _C_NAME_RE.search(sig_text)
            name = m.group(1) if m else "(unknown)"
            start = i
            depth = 1
            k = i + 1
            while k < n and depth > 0:
                depth += stripped[k].count("{") - stripped[k].count("}")
                k += 1
            end = k - 1 if k <= n else n - 1
            regions.append((start + 1, end + 1, name))
            i = k
            depth = 0
            continue
        depth += stripped[i].count("{") - stripped[i].count("}")
        i += 1
    return regions


def c_qualname_lookup(raw_lines):
    regions = c_function_regions(raw_lines)

    def lookup(lineno: int) -> str:
        for start, end, name in regions:
            if start <= lineno <= end:
                return name
        return "(module scope)"

    return lookup


# ---------------------------------------------------------------------------
# Walk.

def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def scan_py_file(path: pathlib.Path, rows: list):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    lookup = py_qualname_index(text)
    for lineno, line in enumerate(lines, start=1):
        for pattern_label, regex in PY_PATTERNS:
            for _ in regex.finditer(line):
                qualname = lookup(lineno) if lookup is not None else "(unparsed)"
                rows.append([rel(path), str(lineno), qualname, pattern_label, "", "", ""])


def scan_c_file(path: pathlib.Path, rows: list):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    lookup = c_qualname_lookup(lines)
    for lineno, line in enumerate(lines, start=1):
        for pattern_label, regex in C_PATTERNS:
            for _ in regex.finditer(line):
                qualname = lookup(lineno)
                rows.append([rel(path), str(lineno), qualname, pattern_label, "", "", ""])


def main():
    files = list(iter_source_files())
    print(f"POPULATION: {len(files)} files scanned "
          f"({sum(1 for _, lang in files if lang == 'py')} .py, "
          f"{sum(1 for _, lang in files if lang == 'c')} .c)")
    assert files, "population is empty -- the walk found nothing, which is a bug, not a result"

    rows = []
    for path, lang in files:
        if lang == "py":
            scan_py_file(path, rows)
        else:
            scan_c_file(path, rows)

    print(f"MATCHES: {len(rows)} rows across {len({r[0] for r in rows})} files")
    assert rows, "match count is zero -- the pattern set or the walk is broken"

    by_pattern = {}
    for r in rows:
        by_pattern[r[3]] = by_pattern.get(r[3], 0) + 1
    for label, _ in PY_PATTERNS + C_PATTERNS:
        print(f"  {label:38s} {by_pattern.get(label, 0)}")

    header_comment = (
        "# P2 Task 1 census -- every PredicateMeta INSTANCE site (constructor, decomposer,\n"
        "# type test, C arm, package) that P2's three rewrites touch. Generated by\n"
        "# p2_census.py; kind is filled by hand afterwards (Task 1 Step 3), one row at a\n"
        "# time, by reading the enclosing function -- never the matched line alone.\n"
        "# kind in {constructor, decomposer, typetest-compound, typetest-predicate,\n"
        "#          c-arm, package, definition, annotation}.\n"
        "# disposition: needs-db when the row needs field NAMES and no db is in scope\n"
        "# (the plan stops the sweep there); otherwise blank at this stage.\n"
        "# file\tline\tqualname\tpattern\tkind\tdisposition\tnote\n"
    )
    with OUT_TSV.open("w", encoding="utf-8") as fh:
        fh.write(header_comment)
        for r in rows:
            fh.write("\t".join(r) + "\n")
    print(f"wrote {OUT_TSV.relative_to(ROOT)}: {len(rows)} rows")


if __name__ == "__main__":
    sys.exit(main())
