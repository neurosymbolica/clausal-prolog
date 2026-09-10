"""TitleCase-identifier lint: ``Foo``-shaped names have no role in Clausal.

Identifiers in a ``.clausal`` file are lowercase (predicates, atoms,
functors) or ALL_CAPS / underscore-led (logic variables).  TitleCase — an
initial capital followed by at least one lowercase letter — is neither, so
the transformer lints it once per (file, identifier).  Python classes are
reached through the ``++ClassName`` escape, which the lint does not read.
"""
import textwrap
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.templating import term_rewriting
from clausal.templating.term_rewriting import (
    ClausalLintWarning,
    ClausalTitleCaseIdentifierWarning,
)


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tlt_{name}", str(path))


def _titlecase_warnings(tmp_path, name, text):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, name, text)
    return [w for w in rec
            if issubclass(w.category, ClausalTitleCaseIdentifierWarning)]


def _named(ws):
    """The identifier each warning names, in order."""
    out = []
    for w in ws:
        msg = str(w.message)
        out.append(msg.split("`")[1])
    return out


def test_lowercase_head_and_body_do_not_warn(tmp_path):
    assert _titlecase_warnings(
        tmp_path, "a", "bar(1),\nfoo(X) <- (bar(X))\n") == []


def test_titlecase_head_warns_once_naming_it_and_the_convention(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "b", "bar(1),\nFoo(X) <- (bar(X))\n")
    assert _named(ws) == ["Foo"]
    msg = str(ws[0].message)
    assert "TitleCase" in msg
    assert "lowercase" in msg and "ALL_CAPS" in msg
    assert "++" in msg  # the Python-class escape is the named alternative
    assert "b.clausal:2" in msg  # located like the other lints
    assert issubclass(ws[0].category, ClausalLintWarning)


def test_titlecase_body_call_warns(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "c", "Bar(1),\nfoo(X) <- (Bar(X))\n")
    assert _named(ws) == ["Bar"]


def test_titlecase_term_functor_warns(tmp_path):
    ws = _titlecase_warnings(tmp_path, "d", "foo(Point(1, 2)),\n")
    assert _named(ws) == ["Point"]


def test_python_escape_is_not_read(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "e",
        "foo(X) <- (X == ++SomeClass(1))\n")
    assert ws == []


def test_string_literal_is_not_read(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "f",
        '-double_quotes(atom)\nfoo("Hello"),\nbar(X) <- (X == f"Hello {X}")\n')
    assert ws == []


def test_same_identifier_warns_once_per_file(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "g",
        "Foo(1),\nFoo(2),\nbar(X) <- (Foo(X))\n")
    assert _named(ws) == ["Foo"]


def test_all_caps_and_underscore_led_do_not_warn(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "h",
        "foo(FOO, _foo) <- (FOO == _foo)\n")
    assert ws == []


def test_two_titlecase_names_warn_twice(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "i",
        "Foo(1),\nBar(X) <- (Foo(X))\n")
    assert sorted(_named(ws)) == ["Bar", "Foo"]


def test_python_truth_constants_do_not_warn(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "j",
        "foo(X) <- (X == True),\nbar(X) <- (X == False),\nbaz(None),\n")
    assert ws == []


def test_import_from_list_names_are_declared_not_warned(tmp_path):
    """A name the file imports by ``-import_from`` is foreign: its spelling
    is the exporter's business, so neither the list nor a use warns."""
    ws = _titlecase_warnings(
        tmp_path, "k",
        "-import_from(clausal.modules.units, [Metre, alias(Second, Sec)])\n"
        "foo(X) <- (X == 5(Metre))\n"
        "bar(X) <- (X == 5(Sec))\n")
    assert ws == []


def test_severity_flips_to_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        term_rewriting, "TITLECASE_IDENTIFIER_SEVERITY", "error")
    with pytest.raises(SyntaxError, match="`Foo` is TitleCase"):
        _load(tmp_path, "l", "Foo(1),\n")


@pytest.mark.parametrize("ident, expected", [
    ("Foo", "foo"), ("FooBar", "foo_bar"), ("HTTPServer", "http_server"),
    ("Len", "len"), ("If", "if_"), ("Not", "not_"),
])
def test_rename_suggestion(ident, expected):
    assert term_rewriting._titlecase_to_snake(ident) == expected


def test_injected_runtime_class_suggests_the_escape(tmp_path):
    ws = _titlecase_warnings(tmp_path, "m", "foo(V) <- (V is Var())\n")
    assert _named(ws) == ["Var"]
    msg = str(ws[0].message)
    assert "`Var` is a Python class; reach it as `++Var`" in msg
    assert "Rename" not in msg


def test_python_builtin_exception_suggests_the_escape(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "n",
        "-implicit_atoms\nbar(1),\nfoo(X) <- catch(bar(X), ValueError, true)\n")
    assert _named(ws) == ["ValueError"]
    assert "reach it as `++ValueError`" in str(ws[0].message)


def test_user_name_still_suggests_snake_case(tmp_path):
    ws = _titlecase_warnings(tmp_path, "o", "FooBar(1),\n")
    assert _named(ws) == ["FooBar"]
    assert "Rename `FooBar` -> `foo_bar`" in str(ws[0].message)


# --- Hosted Python positions are not linted -------------------------------
#
# A ``.clausal`` file is Python syntax with clause statements embedded.  The
# ruling ("TitleCase has no role in Clausal code; a Python class is reached
# as ``++ClassName``") applies to CLAUSAL positions only: clause heads,
# clause bodies, bodyless facts, directive arguments and ``--`` seams —
# the places where a bare ``Foo(...)`` really is rewritten and ``++`` is
# the escape.  Everywhere else the file is plain Python, where TitleCase
# classes are legitimate and ``++X`` is Python's double unary plus (which
# fails on a ``Var``), so the lint's remedy would be wrong advice.

_HOSTED_PYTHON_MODULE = """
from fractions import Fraction
from clausal import Var
A = Var()
HALF = Fraction(1, 2)
if False:
    raise SystemExit(1)
try:
    pass
except AssertionError:
    pass
isinstance(1, Fraction)
class Helper:
    pass
def mk():
    return Fraction(3, 4)
p(X) <- (X is 1)
"""


def test_hosted_python_at_module_level_does_not_warn(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        mod = _load(tmp_path, "hp", _HOSTED_PYTHON_MODULE)
    assert [w for w in rec
            if issubclass(w.category, ClausalTitleCaseIdentifierWarning)] == []
    assert mod.HALF == mod.Fraction(1, 2)
    assert mod.mk() == mod.Fraction(3, 4)


def test_double_plus_in_hosted_python_is_a_type_error_not_a_lint(tmp_path):
    """The lint used to name ``Var`` here and advise ``++Var`` — advice that
    is wrong in hosted Python, where ``++`` is two unary pluses.  Pin both
    facts: no lint, and the TypeError the advice would lead to."""
    text = """
    from fractions import Fraction
    from clausal import Var
    A = ++Var()
    HALF = Fraction(1, 2)
    p(X) <- (X is 1)
    q(X) <- (X is HALF)
    """
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        with pytest.raises(TypeError, match="unary \\+"):
            _load(tmp_path, "hq", text)
    assert [w for w in rec
            if issubclass(w.category, ClausalTitleCaseIdentifierWarning)] == []


def test_clausal_body_position_still_warns_naming_the_escape(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "cb",
        "from fractions import Fraction\nq(X) <- (X is Fraction(1, 3))\n")
    assert _named(ws) == ["Fraction"]
    assert "reach it as `++Fraction`" in str(ws[0].message)


def test_clausal_head_position_still_warns_with_rename(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "ch", "bar(1),\nFoo(X) <- (bar(X))\n")
    assert _named(ws) == ["Foo"]
    assert "Rename `Foo` -> `foo`" in str(ws[0].message)


def test_trailing_comma_fact_still_warns(tmp_path):
    assert _named(_titlecase_warnings(tmp_path, "cf", "Foo(1),\n")) == ["Foo"]


def test_private_directive_argument_still_warns(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "cp",
        "-private([PrivHelper(X)])\nPrivHelper(1),\n")
    assert _named(ws) == ["PrivHelper"]
    assert "cp.clausal:1" in str(ws[0].message)


def test_escaped_body_call_is_silent(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "ce",
        "from fractions import Fraction\nq(X) <- (X is ++Fraction(1, 3))\n")
    assert ws == []


def test_def_body_with_clausal_looking_call_is_hosted(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "cd",
        "class Foo:\n    pass\ndef helper():\n    return Foo(1)\n"
        "p(X) <- (X is 1)\n")
    assert ws == []


def test_comma_optional_fact_of_declared_predicate_still_warns(tmp_path):
    """``foo(Point(1, 2))`` with no trailing comma is a fact once ``foo``
    is declared — a Clausal position — but an undeclared bare call
    (``isinstance(1, Fraction)``) is hosted Python."""
    ws = _titlecase_warnings(
        tmp_path, "co",
        "foo(0),\nfoo(Point(1, 2))\n")
    assert _named(ws) == ["Point"]


def test_goal_seam_operand_still_warns(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "cs",
        "foo(1),\ndef run():\n    if --Bar(X):\n        return X\n"
        "    return None\n")
    assert _named(ws) == ["Bar"]


# --- Every Clausal position the lint reads --------------------------------
#
# One test per call site of ``_lint_titlecase``: the ``--`` goal seams
# (``if``/``for``/``while``), the ``with --{}`` block, a DCG rule, a query,
# a directive keyword argument and a directive list.

def _titlecase_warnings_cell(text):
    """Transform *text* as a REPL cell (a bare ``EmbedTransformer`` on the
    parse tree, no load) and return the TitleCase warnings.  For shapes a
    ``.clausal`` MODULE cannot hold as Python (a ``*(...)`` query) or whose
    directive needs runtime state a bare cell never has."""
    import ast
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        term_rewriting.EmbedTransformer().visit(ast.parse(text))
    return [w for w in rec
            if issubclass(w.category, ClausalTitleCaseIdentifierWarning)]


def test_for_goal_seam_operand_warns(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "s_for",
        "bar(1),\ndef run():\n    out = []\n    for X in --Foo(X):\n"
        "        out.append(X)\n    return out\n")
    assert _named(ws) == ["Foo"]


def test_while_goal_seam_operand_warns(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "s_while",
        "bar(1),\ndef run():\n    while --Foo(X):\n        break\n")
    assert _named(ws) == ["Foo"]


def test_with_dash_block_warns(tmp_path):
    ws = _titlecase_warnings(
        tmp_path, "s_with",
        "with --{} as clauses:\n    Foo(1)\n    bar(2)\n")
    assert _named(ws) == ["Foo"]


def test_dcg_rule_warns(tmp_path):
    ws = _titlecase_warnings(tmp_path, "s_dcg", "Foo(X) >> ([X])\n")
    assert _named(ws) == ["Foo"]


def test_star_query_warns():
    assert _named(_titlecase_warnings_cell("*(Foo(X))\n")) == ["Foo"]


def test_directive_keyword_argument_warns():
    ws = _titlecase_warnings_cell(
        "-specialize(solve, natnum_program, alias=Foo)\n")
    assert _named(ws) == ["Foo"]


def test_constants_directive_list_warns_before_the_directive_rejects_it(
        tmp_path):
    """The lint runs on the directive's raw arguments before the directive
    handler does, so it names ``Foo`` even though ``-constants`` then
    rejects an RHS that references an undeclared name."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        with pytest.raises(SyntaxError, match="-constants"):
            _load(tmp_path, "s_const", "-constants(_L_ = [Foo, bar])\n")
    ws = [w for w in rec
          if issubclass(w.category, ClausalTitleCaseIdentifierWarning)]
    assert _named(ws) == ["Foo"]


# --- Names the file's own Python binds get the ``++`` remedy ---------------

@pytest.mark.parametrize("name, binding", [
    ("Point", "from collections import namedtuple\n"
              "Point = namedtuple('Point', 'x y')\n"),
    ("Rate", "Rate: int = 3\n"),
    ("Mk", "def Mk():\n    return 1\n"),
    ("AMk", "async def AMk():\n    return 1\n"),
    ("Helper", "class Helper:\n    pass\n"),
    ("Frac", "from fractions import Fraction as Frac\n"),
])
def test_python_bound_name_suggests_the_escape(tmp_path, name, binding):
    ws = _titlecase_warnings(
        tmp_path, f"pb_{name}", binding + f"q(P) <- (P is {name})\n")
    assert _named(ws) == [name]
    assert f"reach it as `++{name}`" in str(ws[0].message)
    assert "Rename" not in str(ws[0].message)


# --- The warning is attributed outside the lint's own frames ---------------

def test_warning_is_not_attributed_to_the_rewriter(tmp_path):
    """The message carries the ``.clausal`` site; the Python-side
    attribution must not point into the lint helpers (or the stdlib
    ``ast`` walker driving them), which is where a fixed ``stacklevel``
    inside a recursive walk lands."""
    import os
    ws = _titlecase_warnings(tmp_path, "attr", "Foo(1),\n")
    assert _named(ws) == ["Foo"]
    base = os.path.basename(ws[0].filename)
    assert base not in ("term_rewriting.py", "ast.py"), ws[0].filename
