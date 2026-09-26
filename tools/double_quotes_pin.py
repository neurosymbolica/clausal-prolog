#!/usr/bin/env python
"""Pin or migrate the ``-double_quotes`` mode of Clausal sources.

Written for the 2026-09-26 flip of the engine default from ``atom`` to
``chars`` (a ``"..."`` literal is a STRING, as in Scryer/Trealla), so that a
source relying on the OLD meaning keeps it -- by declaration, not by luck.

Three jobs, one per subcommand:

``pin PATH...``
    Every ``.clausal`` / ``.seam`` file under the paths that (a) declares no
    ``-double_quotes`` and (b) has at least one double-quoted literal outside
    a docstring / comment gets ``-double_quotes(atom)`` inserted after its
    leading comment block.  Meaning-preserving by construction: the directive
    names the mode the file was written under.

``pin-py PATH...``
    The same for CLAUSAL SOURCE EMBEDDED IN PYTHON TEST FILES: a str constant
    (plain, implicitly concatenated, f-string or ``.format`` template) that
    looks like Clausal source -- a directive, a ``<-`` rule, a ``test(...)``
    head, or a fact line ending in ``),`` -- and contains a double-quoted
    literal gets the directive as its first line.  Heuristic, so the caller
    verifies with the test suite; a string the heuristic pins that was not a
    source (an expected-output string, say) fails its test visibly.  A
    string that already carries the directive is left alone; ``--exclude``
    names files whose helper PREPENDS a ``-double_quotes(chars)`` header to
    every source they write, where pinning the body would override it.
    ``--hints FILE`` restricts pinning to files named in the hint TSV (one
    ``path`` per line; other columns ignored), for a measured population.

``convert PATH...``
    The PROPER migration for user-facing sources (``clausal/examples``): every
    ``"..."`` literal that meant an atom is respelled ``'...'``, which is an
    atom in every mode.  Left alone: a ``test("...")`` description (a string
    is the natural spelling of human text and the runner accepts both), a
    DCG terminal (the right side of ``>>``, chars in every mode), hosted
    Python, docstrings and comments.

Every subcommand prints the SIZE of what it scanned and what it changed;
``--check`` reports without writing.
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
import tokenize

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clausal.templating.quote_map import build_quote_map, quote_of  # noqa: E402

DIRECTIVE = "-double_quotes(atom)"
_MODE_RE = re.compile(r"(?m)^\s*-\s*double_quotes\s*\(")
_HOSTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import,
           ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.If,
           ast.For, ast.While, ast.With, ast.Try, ast.Return, ast.Global)
# What makes a Python string "Clausal source": a directive, a rule, a test
# head, or a fact/clause line ending in ``),`` (with an optional comment).
# ``{name}(`` is an f-string's interpolated functor.
_CLAUSAL_SHAPE = re.compile(
    r"(?m)^\s*(-[a-z_]+(\(|\s*$)|test\(|(\{[A-Za-z_]+\}|[a-z_])[A-Za-z0-9_.]*(\(.*\))?\s*(<-|>>)|"
    r"(\{[A-Za-z_]+\}|[a-z_])[A-Za-z0-9_.]*\(.*\),\s*(#.*)?$)")
# What makes it NOT Clausal source: hosted-Python-only shapes (a Python
# program written to a file, a subprocess probe) and Prolog (``:-`` rules,
# ``.``-terminated clauses).
_NOT_CLAUSAL = re.compile(
    r"(?m)^\s*(import |from \S+ import |def |print\(|sys\.)|:-|^\s*[a-z_]+\(.*\)\.\s*$")


# ── shared ───────────────────────────────────────────────────────────────────

def _docstring_ids(tree) -> set[int]:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)):
            b = n.body
            if (b and isinstance(b[0], ast.Expr)
                    and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                out.add(id(b[0].value))
    return out


def _is_seam(n) -> bool:
    return (isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub)
            and isinstance(n.operand, ast.UnaryOp)
            and isinstance(n.operand.op, ast.USub))


def _dq_literals(source: str, path: str):
    """``[(node, in_dcg_body, is_test_name)]`` for every double-quoted str
    literal that the compiler would read by the -double_quotes mode: top-level
    Clausal statements in full, and only the ``--`` seams of hosted Python."""
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source, filename=path)
    qm = build_quote_map(lines)
    docs = _docstring_ids(tree)
    out = []

    def walk(node, in_seam, only_seams, in_dcg):
        stack = [(node, in_seam, in_dcg)]
        while stack:
            n, s, d = stack.pop()
            if isinstance(n, ast.JoinedStr):
                continue
            if _is_seam(n):
                s = True
            if (isinstance(n, ast.Constant) and type(n.value) is str
                    and id(n) not in docs and (s or not only_seams)):
                try:
                    q = quote_of(qm, n)
                except SyntaxError:
                    q = None
                if q == '"':
                    out.append((n, d, False))
            for c in ast.iter_child_nodes(n):
                stack.append((c, s, d))

    for st in tree.body:
        if isinstance(st, _HOSTED):
            walk(st, False, True, False)
            continue
        if isinstance(st, ast.Expr):
            v = st.value
            if isinstance(v, ast.Constant) and id(v) in docs:
                continue
            head = v
            if isinstance(v, ast.Compare) and v.left is not None:
                head = v.left
            elif isinstance(v, ast.Tuple) and v.elts:
                head = v.elts[0]
            elif isinstance(v, ast.BinOp) and isinstance(v.op, ast.RShift):
                # A DCG rule: the body's literals are terminals in every
                # mode; only the head is read by the -double_quotes mode.
                head = v.left
                walk(v.left, False, False, False)
                walk(v.right, False, False, True)
                continue
            if (isinstance(head, ast.Call) and isinstance(head.func, ast.Name)
                    and head.func.id in ("test", "Test") and head.args
                    and isinstance(head.args[0], ast.Constant)
                    and type(head.args[0].value) is str):
                name = head.args[0]
                try:
                    q = quote_of(qm, name)
                except SyntaxError:
                    q = None
                if q == '"':
                    out.append((name, False, True))
                docs.add(id(name))
            walk(v, False, False, False)
        else:
            walk(st, False, True, False)
    return out


def _clausal_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs
                       if d not in ("__pycache__", "venv", ".git", "node_modules")]
            for f in sorted(files):
                if f.endswith((".clausal", ".seam")):
                    yield os.path.join(root, f)


def _py_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs
                       if d not in ("__pycache__", "venv", ".git", "node_modules")]
            for f in sorted(files):
                if f.endswith(".py"):
                    yield os.path.join(root, f)


# ── pin: .clausal / .seam files ──────────────────────────────────────────────

def _insertion_line(lines: list[str]) -> int:
    """Index of the line the directive goes BEFORE: after the leading run of
    comment and blank lines (a shebang-style header stays a header)."""
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1
    return i


def pin_file(path: str, check: bool) -> str:
    """``"pinned"`` / ``"declared"`` / ``"no-literal"`` / ``"error: ..."``."""
    source = open(path, encoding="utf-8").read()
    if _MODE_RE.search(source):
        return "declared"
    try:
        lits = _dq_literals(source, path)
    except SyntaxError as exc:
        return f"error: {exc}"
    if not lits:
        return "no-literal"
    lines = source.splitlines(keepends=True)
    at = _insertion_line(lines)
    # Exactly ONE line, so a test that names a line of the file shifts by
    # exactly one -- after the leading comment block, before the blank line
    # that usually follows it.
    if at > 0 and not lines[at - 1].strip():
        at -= 1
    new = "".join(lines[:at]) + DIRECTIVE + "\n" + "".join(lines[at:])
    if not check:
        open(path, "w", encoding="utf-8").write(new)
    return "pinned"


# ── pin-py: Clausal source inside Python strings ─────────────────────────────

def _string_segments(source: str):
    """``[(start_offset, end_offset, raw_segment)]`` for every str-valued
    Constant / JoinedStr in *source* that is not a docstring, in reverse
    source order so edits do not disturb later offsets."""
    tree = ast.parse(source)
    docs = _docstring_ids(tree)
    line_starts = [0]
    for line in source.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))

    def off(lineno, col):
        # col_offset is in UTF-8 BYTES; convert on the line's text.
        line = source[line_starts[lineno - 1]:line_starts[lineno]]
        return line_starts[lineno - 1] + len(line.encode("utf-8")[:col].decode("utf-8", "replace"))

    segs = []
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr) or (
                isinstance(n, ast.Constant) and type(n.value) is str
                and id(n) not in docs):
            if getattr(n, "end_lineno", None) is None:
                continue
            a, b = off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset)
            segs.append((a, b, source[a:b]))
    # a JoinedStr's parts are Constants too: keep only the outermost span
    segs.sort()
    kept, last_end = [], -1
    for a, b, raw in segs:
        if a < last_end:
            continue
        kept.append((a, b, raw))
        last_end = b
    return sorted(kept, reverse=True)


def _pin_segment(raw: str) -> str | None:
    """*raw* with the directive as its first line, or None when it is not a
    Clausal source with a double-quoted literal (or is already declared).

    The directive is inserted right after the OPENING quote of the first
    part, so an implicit concatenation whose parts use different quote
    characters, or that ends in an f-string, is never re-terminated."""
    m = re.match(r"([rRbBfFuU]*)(\"\"\"|'''|'|\")", raw)
    if not m:
        return None
    prefix, quote = m.group(1), m.group(2)
    if "b" in prefix.lower():
        return None
    try:
        # Parenthesised: an implicit concatenation spans lines, and may carry
        # comments between its parts.  An f-string is judged as the plain
        # string of its own text (``{name}(`` is a shape the regex knows).
        plain = prefix.replace("f", "").replace("F", "") + raw[len(prefix):]
        value = ast.literal_eval("(" + plain + "\n)")
    except (SyntaxError, ValueError):
        return None
    if not isinstance(value, str):
        return None
    if _MODE_RE.search(value) or _NOT_CLAUSAL.search(value):
        return None
    # The FIRST statement line must be Clausal-shaped: a fragment that
    # starts mid-clause (the tail of a ``"..." + expr + "..."`` splice) is
    # not a place a directive can go.
    lines = [l for l in value.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines or not _CLAUSAL_SHAPE.match(lines[0]):
        return None
    if value.count('"') < 2:
        return None                      # no double-quoted literal inside
    head, rest = raw[:m.end()], raw[m.end():]
    if quote in ("'", '"'):
        # a one-line string: its newlines are ``\n`` escapes, so is this one
        return head + DIRECTIVE + "\\n" + rest
    for lead in ("\n", "\\\n"):
        # Content starts on the NEXT line (a newline, or a backslash-newline
        # continuation that ``textwrap.dedent`` callers use): the directive
        # goes on its own line there, at that line's indentation.
        if rest.startswith(lead):
            body = rest[len(lead):]
            indent = re.match(r"[ \t]*", body).group(0)
            return head + lead + indent + DIRECTIVE + "\n" + body
    return head + DIRECTIVE + "\n" + rest


def pin_py_file(path: str, check: bool) -> int:
    """Number of strings pinned in *path*."""
    source = open(path, encoding="utf-8").read()
    try:
        segs = _string_segments(source)
    except SyntaxError:
        return 0
    n = 0
    for a, b, raw in segs:
        new = _pin_segment(raw)
        if new is None:
            continue
        source = source[:a] + new + source[b:]
        n += 1
    if n and not check:
        open(path, "w", encoding="utf-8").write(source)
    return n


# ── convert: "..." -> '...' for user-facing sources ──────────────────────────

def _respell(text: str) -> str:
    """The single-quoted spelling of a double-quoted literal's SOURCE text
    (quotes included)."""
    inner = text[1:-1]
    inner = inner.replace('\\"', '"').replace("'", "\\'")
    return "'" + inner + "'"


def convert_file(path: str, check: bool) -> tuple[int, int]:
    """``(converted, kept)`` literal counts for *path*."""
    source = open(path, encoding="utf-8").read()
    if _MODE_RE.search(source):
        return 0, 0
    lits = _dq_literals(source, path)
    lines = source.splitlines(keepends=True)
    line_starts = [0]
    for line in lines:
        line_starts.append(line_starts[-1] + len(line))
    edits = []
    kept = 0
    for node, in_dcg, is_test_name in lits:
        if in_dcg or is_test_name:
            kept += 1
            continue
        line = lines[node.lineno - 1]
        a = line_starts[node.lineno - 1] + len(line.encode("utf-8")[:node.col_offset].decode("utf-8", "replace"))
        end_line = lines[node.end_lineno - 1]
        b = line_starts[node.end_lineno - 1] + len(end_line.encode("utf-8")[:node.end_col_offset].decode("utf-8", "replace"))
        edits.append((a, b))
    for a, b in sorted(edits, reverse=True):
        source = source[:a] + _respell(source[a:b]) + source[b:]
    if edits and not check:
        open(path, "w", encoding="utf-8").write(source)
    return len(edits), kept


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("pin", "pin-py", "convert"))
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--check", action="store_true", help="report, do not write")
    ap.add_argument("--hints", help="pin-py: TSV of files to consider (first column)")
    ap.add_argument("--exclude", default="",
                    help="pin-py: comma-separated files to leave alone (a test "
                         "whose helper PREPENDS a -double_quotes(chars) header "
                         "to every source it writes, say)")
    args = ap.parse_args(argv)

    if args.command == "pin":
        tally: dict[str, list] = {}
        for p in _clausal_files(args.paths):
            tally.setdefault(pin_file(p, args.check), []).append(p)
        scanned = sum(len(v) for v in tally.values())
        print(f"pin: scanned {scanned} files")
        for k, v in sorted(tally.items()):
            print(f"  {k}: {len(v)}")
        for p in tally.get("pinned", []):
            print(f"    {p}")
        for k, v in tally.items():
            if k.startswith("error"):
                print(f"  {k}: {v}")
        return 0

    if args.command == "pin-py":
        allowed = None
        if args.hints:
            allowed = {os.path.abspath(l.split("\t")[0].strip())
                       for l in open(args.hints) if l.strip()}
        excluded = {os.path.abspath(x) for x in args.exclude.split(",") if x}
        files = [p for p in _py_files(args.paths)
                 if (allowed is None or os.path.abspath(p) in allowed)
                 and os.path.abspath(p) not in excluded]
        total = 0
        changed = []
        for p in files:
            n = pin_py_file(p, args.check)
            if n:
                changed.append((p, n))
                total += n
        print(f"pin-py: scanned {len(files)} files; pinned {total} strings in {len(changed)} files")
        for p, n in changed:
            print(f"    {n:3d} {p}")
        return 0

    conv = kept = 0
    files = list(_clausal_files(args.paths))
    for p in files:
        c, k = convert_file(p, args.check)
        conv += c
        kept += k
        if c or k:
            print(f"    {p}: converted {c}, kept {k}")
    print(f"convert: scanned {len(files)} files; converted {conv} literals, kept {kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
