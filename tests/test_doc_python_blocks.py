"""Execute the ```python doc blocks that teach the Python query API.

``test_doc_snippet_coverage`` compiles ```clausal blocks; nothing ran the
```python ones, so an API change could leave them teaching a form that no
longer works (the predicate-handle flip did exactly that: ``pred(X := Var())``
became a TypeError, and iterating a builtin's cell walked the tuple).

Each case names a block by a substring unique among the page's ```python
blocks, runs it VERBATIM in a fresh interpreter (a doc block imports modules
by name, so in-process runs would share ``sys.modules``), and checks what it
prints. ``modules`` builds the ``.clausal`` files the block imports -- taken
from the page's own ```clausal blocks where the page defines them, else from
``clausal/examples``. ``post`` is appended to make a block that only builds a
value show it: a block whose last statement is a bare expression (a
``Solutions(...)`` display) has that value bound to ``_doc_value`` -- the
block's OWN object, not a rebuilt one -- and ``_show(_doc_value)`` renders it
through the IPython display protocol (``_repr_html_``, what Jupyter calls) as
plain text.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"
_FENCE = re.compile(r"^([ \t]*)```(\w*)[^\n]*\n(.*?)^\1```", re.M | re.S)


def _blocks(page: str, lang: str) -> list[str]:
    text = (_DOCS / page).read_text()
    out = []
    for m in _FENCE.finditer(text):
        if m.group(2) != lang:
            continue
        indent = len(m.group(1))
        out.append("\n".join(line[indent:] for line in m.group(3).split("\n")))
    return out


def _block(page: str, lang: str, anchor: str) -> str:
    hits = [b for b in _blocks(page, lang) if anchor in b]
    assert len(hits) == 1, f"{page}: {anchor!r} matches {len(hits)} {lang} blocks"
    return hits[0]


def _capture_last_expression(code: str) -> str:
    """*code* with a trailing bare expression bound to ``_doc_value``."""
    tree = ast.parse(code)
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body[-1]
        tree.body[-1] = ast.Assign(
            targets=[ast.Name("_doc_value", ast.Store())], value=last.value)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    return code


# Renders a Solutions display as the text a notebook shows.
_SHOW = """
import html as _html, re as _re
def _show(solutions):
    h = _re.sub(r'<style.*?</style>', '', solutions._repr_html_(), flags=_re.S)
    t = _html.unescape(_re.sub(r'<br\\s*/?>|<div', lambda m: '\\n' + m.group(0), h))
    print(_re.sub(r'<[^>]+>', '', t))
"""


def _example(name: str) -> str:
    return (_ROOT / "clausal" / "examples" / f"{name}.clausal").read_text()


# (id, page, anchor, {module file: source}, post, expected lines in stdout)
_CASES = [
    ("pi-solve", "python_integration.md",
     'import fibonacci\n\nfor trail in solve(("fib", 10',
     {"fibonacci": _example("fibonacci")}, "", ["55"]),
    ("pi-once", "python_integration.md", 'once(("fib"',
     {"fibonacci": _example("fibonacci")}, "", ["55"]),
    ("pi-call", "python_integration.md", 'call("fib", 7',
     {"fibonacci": _example("fibonacci")}, "", ["13"]),
    ("pi-harness", "python_integration.md", "def answers(",
     {"fibonacci": _example("fibonacci")},
     "test_fib_10(); print('harness ok')", ["harness ok"]),
    ("pi-load-module", "python_integration.md", "load_clausal_module(",
     {}, "", ["55"]),
    ("pi-bare-module", "python_integration.md", 'Module("graph")',
     {}, "", ["a b", "b c", "c d"]),
    ("pi-builtin-class", "python_integration.md", 'get_builtin_class("append")',
     {}, "", ["[1, 2, 3]"]),
    ("predicates-solve", "predicates.md", 'solve(("fib"', {}, "", ["55"]),
    ("predicates-rows", "predicates.md", "resolve_predicate_row",
     {},
     "print(row.locked, len(row.clauses), db.field_names_at('fib', 2),"
     " resolve_predicate_row(fibonacci.fib, arity=2) is row)",
     ["True 3 ('N', 'F') True"]),
    ("metainterpreters", "metainterpreters.md", "natnum_program", {},
     "print(len(result))", ["1"]),
    ("ipython-solve", "ipython.md", 'solve(("greeting"',
     {"hello": 'greeting("hello"),\ngreeting("hi"),\n'}, "", ["hello", "hi"]),
    ("ipython-solutions-call", "ipython.md", "def gen():", {},
     "_show(_doc_value)",
     ["ROWS is [[1, 5, 6, 8, 9, 4, 3, 2, 7], [9, 2, 8, 7, 3, 1, 4, 5, 6], "
      "[4, 7, 3, 2, 6, 5, 9, 1, 8], [3, 6, 2, 4, 1, 7, 8, 9, 5], "
      "[7, 8, 9, 3, 5, 2, 6, 4, 1], [5, 1, 4, 9, 8, 6, 2, 7, 3], "
      "[8, 3, 1, 5, 4, 9, 7, 6, 2], [6, 9, 7, 1, 2, 3, 5, 8, 4], "
      "[2, 4, 5, 6, 7, 8, 1, 3, 9]]"]),
    ("ipython-solutions-solve", "ipython.md",
     '"problem", 1, ROWS), module=sudoku', {},
     "_show(_doc_value)",
     ["ROWS is [[1, _, _, 8, _, 4, _, _, _], [_, 2, _, _, _, _, 4, 5, 6], "
      "[_, _, 3, 2, _, 5, _, _, _], [_, _, _, 4, _, _, 8, _, 5], "
      "[7, 8, 9, _, 5, _, _, _, _], [_, _, _, _, _, 6, 2, _, 3], "
      "[8, _, 1, _, _, _, 7, _, _], [_, _, _, 1, 2, 3, _, 8, _], "
      "[2, _, 5, _, _, _, _, _, 9]]"]),
    ("index", "index.md", 'solve(("fib"',
     {"fibonacci": None}, "", ["55"]),
    ("tutorial-greeting", "tutorial.md", 'solve(("greeting", "hello")',
     {"hello": None}, "", ["yes"]),
    ("tutorial-reachable", "tutorial.md", 'solve(("reachable"',
     {"graph": None}, "", ["['b', 'c', 'd']"]),
]

# A module whose source is ``None`` is the page's own ```clausal block that
# defines it, found by this substring.
_PAGE_MODULE_ANCHORS = {
    ("index.md", "fibonacci"): "-table(fib/2)",
    ("tutorial.md", "hello"): 'greeting("hello"),',
    ("tutorial.md", "graph"): 'edge("a", "b"),',
}


@pytest.mark.parametrize(
    "page, anchor, modules, post, expected",
    [c[1:] for c in _CASES], ids=[c[0] for c in _CASES],
)
def test_doc_python_block_runs(tmp_path, page, anchor, modules, post, expected):
    # nv
    for name, source in modules.items():
        if source is None:
            source = _block(page, "clausal", _PAGE_MODULE_ANCHORS[(page, name)])
        (tmp_path / f"{name}.clausal").write_text(source)
    code = (
        f"import sys; sys.path[0:0] = [{str(_ROOT)!r}, '.']\n"
        "import clausal\n"
        f"assert clausal.__file__.startswith({str(_ROOT)!r}), clausal.__file__\n"
        + _SHOW
        + _capture_last_expression(_block(page, "python", anchor)) + "\n"
        + post + "\n"
    )
    # Blocks that name a repo path (``clausal/examples/...``) run from the root.
    cwd = _ROOT if "clausal/examples/" in code else tmp_path
    if cwd is _ROOT:
        code = code.replace("'.']", f"{str(tmp_path)!r}]")
    r = subprocess.run([sys.executable, "-c", code], cwd=cwd,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    lines = r.stdout.splitlines()
    for want in expected:
        assert want in lines, f"{want!r} not printed; stdout was:\n{r.stdout}"
