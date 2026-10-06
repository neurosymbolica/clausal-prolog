"""Execute the ```python doc blocks that teach the Python query API.

``test_doc_snippet_coverage`` compiles ```seam blocks; nothing ran the
```python ones, so an API change could leave them teaching a form that no
longer works (the predicate-handle flip did exactly that: ``pred(X := Var())``
became a TypeError, and iterating a builtin's cell walked the tuple).

Each case names a block by a substring unique among the page's ```python
blocks, runs it VERBATIM in a fresh interpreter (a doc block imports modules
by name, so in-process runs would share ``sys.modules``), and checks what it
prints. ``modules`` builds the ``.clausal`` files the block imports -- taken
from the page's own ```seam blocks where the page defines them, else from
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

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES, SEAM_SUFFIX
from clausal.tools.doc_snippet_check import SEAM_FENCE_LANGS
from tests._suffix import seam_path

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"
_FENCE = re.compile(r"^([ \t]*)```(\w*)[^\n]*\n(.*?)^\1```", re.M | re.S)


def _blocks(page: str, lang: str) -> list[str]:
    text = (_DOCS / page).read_text()
    langs = SEAM_FENCE_LANGS if lang in SEAM_FENCE_LANGS else (lang,)
    out = []
    for m in _FENCE.finditer(text):
        if m.group(2) not in langs:
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
    return seam_path(_ROOT / "clausal" / "examples" / f"{name}.clausal").read_text()


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
    ("pi-builtin-class", "python_integration.md", 'goal = append([1, 2], [3]',
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
     {"hello": "greeting('hello'),\ngreeting('hi'),\n"}, "", ["hello", "hi"]),
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
    # The home page's query is a .seam file in a ```python fence: no Python
    # block runs; the case imports it.
    ("index", "index.md", None,
     {"fibonacci": None, "report": None}, "import report", ["55"]),
    ("tutorial-greeting", "tutorial.md", 'solve(("greeting", "hello")',
     {"hello": None}, "", ["yes"]),
    ("tutorial-reachable", "tutorial.md", 'solve(("reachable"',
     {"graph": None}, "", ["['b', 'c', 'd']"]),
]

# A module whose source is ``None`` is the page's own block that defines it,
# found by this substring: a seam block (written as ``.seam``) by default, or
# a ```prolog block (written as ``.clausal``, Clausal Prolog) when the anchor
# is a ``("prolog", substring)`` pair, or a ```python block holding seam source
# (written as ``.seam``) for a ``("python", substring)`` pair.
_PAGE_MODULE_ANCHORS = {
    ("index.md", "fibonacci"): ("prolog", ":- module(fibonacci,"),
    ("index.md", "report"): ("python", "# report.seam"),
    ("tutorial.md", "hello"): ("prolog", ":- module(hello,"),
    ("tutorial.md", "graph"): ("prolog", ":- module(graph,"),
}


@pytest.mark.parametrize(
    "page, anchor, modules, post, expected",
    [c[1:] for c in _CASES], ids=[c[0] for c in _CASES],
)
def test_doc_python_block_runs(tmp_path, page, anchor, modules, post, expected):
    # nv
    for name, source in modules.items():
        suffix = SEAM_SUFFIX
        if source is None:
            module_anchor = _PAGE_MODULE_ANCHORS[(page, name)]
            if isinstance(module_anchor, tuple):
                lang, module_anchor = module_anchor
                # ```prolog is Clausal Prolog; a ```python block named
                # ``# x.seam`` is seam source shown in a python fence.
                if lang == "prolog":
                    suffix = CLAUSAL_PROLOG_SUFFIXES[0]
            else:
                lang = "seam"
            source = _block(page, lang, module_anchor)
        (tmp_path / f"{name}{suffix}").write_text(source)
    code = (
        f"import sys; sys.path[0:0] = [{str(_ROOT)!r}, '.']\n"
        "import clausal\n"
        f"assert clausal.__file__.startswith({str(_ROOT)!r}), clausal.__file__\n"
        + _SHOW
        + (_capture_last_expression(_block(page, "python", anchor))
           if anchor is not None else "") + "\n"
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


# ```python blocks that state each printed value in a trailing comment:
# ``print(expr)   # <value>   prose``.  The block's stdout, line for line, must
# be exactly those values -- so a stale shape in a comment (the pre-flip
# ``('bar',)``) fails here instead of teaching the wrong representation.
_PRINTS_WHAT_IT_SAYS = [
    ("pi-atom-api", "python_integration.md",
     "from clausal.logic.atoms import mint, is_atom, spelling, char_atom", {}),
    ("pi-module-attr", "python_integration.md", "import my_module",
     {"my_module": "-module(my_module, [])\n-private([bar])\n"}),
]

_PRINT_CLAIM = re.compile(r"^print\(.*\)\s+#\s+(\S+)", re.M)


def _run_block(tmp_path, modules, body):
    for name, source in modules.items():
        (tmp_path / f"{name}{SEAM_SUFFIX}").write_text(source)
    code = (
        f"import sys; sys.path[0:0] = [{str(_ROOT)!r}, '.']\n"
        "import clausal\n"
        f"assert clausal.__file__.startswith({str(_ROOT)!r}), clausal.__file__\n"
        + body + "\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    return r.stdout.splitlines()


@pytest.mark.parametrize(
    "page, anchor, modules",
    [c[1:] for c in _PRINTS_WHAT_IT_SAYS],
    ids=[c[0] for c in _PRINTS_WHAT_IT_SAYS],
)
def test_doc_python_block_prints_what_it_says(tmp_path, page, anchor, modules):
    block = _block(page, "python", anchor)
    claims = _PRINT_CLAIM.findall(block)
    assert claims, f"{anchor!r}: no `print(...)  # value` lines"
    assert _run_block(tmp_path, modules, block) == claims


# The seam's hosted-Python example is a ```seam block (the Python lives in
# a .seam file).  Every top-level line with a trailing ``# value`` comment
# is a claim: ``NAME = --...  # value`` says what the module attribute is,
# ``expr  # value`` what the expression evaluates to in that module.  Both are
# checked against the loaded module, so the example cannot drift from the
# engine again (it once claimed ``('permitted',)`` atoms and an equality that
# was False).
_SEAM_CLAIM = re.compile(r"^([A-Za-z_][^\n#]*?)\s+#\s+(.+?)\s*$", re.M)


def test_doc_seam_example_claims_hold(tmp_path):
    block = _block("python_integration.md", "seam", "WANT = --order(")
    claims = [(lhs, want) for lhs, want in _SEAM_CLAIM.findall(block)
              if not lhs.startswith(("def ", "return "))]
    assert len(claims) >= 4, claims
    checks = []
    for lhs, want in claims:
        m = re.fullmatch(r"([A-Za-z_]\w*) = .*", lhs)
        expr = m.group(1) if m else lhs
        checks.append(f"print(repr(eval({expr!r}, vars(shop))))")
    out = _run_block(tmp_path, {"shop": block},
                     "import shop\n" + "\n".join(checks))
    assert out == [want for _, want in claims]

