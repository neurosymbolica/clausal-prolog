"""TitleCase-identifier lint: ``Foo``-shaped names have no role as FUNCTORS.

Since 2026-09-10 the lint is POSITIONAL.  A capital-initial identifier
standing where a VALUE goes is a logic variable like ``FOO`` and ``_foo``
(``test_titlecase_is_a_variable``), and is not linted at all.  In FUNCTOR
position -- a clause head's functor, a goal called in a body, at any nesting
depth -- it is still refused once per (file, identifier), because a variable
there is not ``call/N`` but the unit-annotation sugar: reading it as one
turns a bare Python class in a clause body into a Quantity that fails much
later complaining about SI prefixes.

Python classes are reached through the ``++ClassName`` escape, which the
lint does not read.
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


#: The severity the engine ships with.  Read at import, before any test's
#: monkeypatch — ``test_default_severity_is_error`` pins it.
_SHIPPED_SEVERITY = term_rewriting.TITLECASE_IDENTIFIER_SEVERITY


@pytest.fixture(autouse=True)
def _lint_as_warning(monkeypatch):
    """The lint's WALK — which positions it reads, which names it exempts,
    which remedy it names — is exercised through its warning form, so every
    test here demotes the severity.  The error form (the default) is pinned
    by the ``Severity`` tests below, which set it back explicitly."""
    monkeypatch.setattr(
        term_rewriting, "TITLECASE_IDENTIFIER_SEVERITY", "warn")


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


# --- Severity: the shipped default is an error ------------------------------
#
# The positive control for the gate itself.  A TitleCase name in a Clausal
# position stops the file from loading, at the identifier's site, with the
# rename (or the ``++`` escape) in the message; the lowercase spelling of
# the same file loads.

def test_default_severity_is_error():
    assert _SHIPPED_SEVERITY == "error"


def _as_error(monkeypatch):
    monkeypatch.setattr(
        term_rewriting, "TITLECASE_IDENTIFIER_SEVERITY", "error")


def test_titlecase_head_fails_to_load_naming_old_and_new(tmp_path, monkeypatch):
    _as_error(monkeypatch)
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, "sev_head", "bar(1),\nFoo(X) <- (bar(X))\n")
    err = ei.value
    assert "`Foo` is TitleCase" in str(err)
    assert "Rename `Foo` -> `foo`" in str(err)
    assert err.filename.endswith("sev_head.clausal") and err.lineno == 2
    assert "Foo(X) <- (bar(X))" in (err.text or "")


def test_lowercase_head_loads(tmp_path, monkeypatch):
    _as_error(monkeypatch)
    mod = _load(tmp_path, "sev_ok", "bar(1),\nfoo(X) <- (bar(X))\n")
    assert mod.foo is not None


def test_bare_python_class_in_body_fails_naming_the_escape(
        tmp_path, monkeypatch):
    _as_error(monkeypatch)
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, "sev_cls",
              "from fractions import Fraction\nq(X) <- (X is Fraction(1, 3))\n")
    assert "`Fraction` is a Python class; reach it as `++Fraction`" in str(
        ei.value)
    assert "Rename" not in str(ei.value)


def test_escaped_python_class_in_body_loads(tmp_path, monkeypatch):
    _as_error(monkeypatch)
    mod = _load(tmp_path, "sev_esc",
                "from fractions import Fraction\n"
                "q(X) <- (X is ++Fraction(1, 3))\n")
    assert mod.q is not None


@pytest.mark.parametrize("text", [
    "'Foo'(1),\n",                       # a fact through the string-callable sugar
    "bar(1),\ngo(X) <- ('Foo'(X))\n",     # a body goal through it
])
def test_string_callable_sugar_is_linted(tmp_path, monkeypatch, text):
    """``'Foo'(...)`` is sugar for the name ``Foo``; it is rewritten AFTER the
    lint reads the raw tree, so the lint must read the string callable
    itself or the sugar bypasses the gate."""
    _as_error(monkeypatch)
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, "sev_sugar", text)
    assert "`Foo` is TitleCase" in str(ei.value)
    assert "Rename `Foo` -> `foo`" in str(ei.value)


def test_string_callable_sugar_lowercase_still_works(tmp_path, monkeypatch):
    """The sugar itself is untouched: ``'bar'(X)`` in a body calls bar/1."""
    _as_error(monkeypatch)
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    mod = _load(tmp_path, "sev_sugar_ok", "bar(1),\ngo(X) <- ('bar'(X))\n")
    x = Var()
    assert [deref(x) for _ in call("go", x, module=mod.__dict__["$module"])] == [1]


def test_string_callable_sugar_fact_lowercase_loads(tmp_path, monkeypatch):
    """``'foo'(1),`` reads as the fact ``foo(1),`` (it used to fall through
    as hosted Python and die at exec with ``'str' object is not callable``)."""
    _as_error(monkeypatch)
    from clausal.logic.solve import call
    mod = _load(tmp_path, "sev_sugar_fact", "'foo'(1),\n")
    assert len(list(call("foo", 1, module=mod.__dict__["$module"]))) == 1


def test_a_file_that_binds_its_own_Test_class_is_told_the_escape(
        tmp_path, monkeypatch):
    """The renamed-spelling carve-out speaks for the LANGUAGE, so it must
    not overrule a class the FILE ITSELF binds.

    ``Test`` is in ``_TITLECASE_RENAMED_SPELLINGS`` because ``Test/1`` was
    the old spelling of the test predicate.  But a module whose hosted
    Python defines its own ``Test`` means that class, and "Rename `Test` ->
    `test`" names a predicate that does not exist — the wrong-advice
    failure this lint exists to prevent.  The paired test below is the
    control: with no such binding in the file, the carve-out still holds.
    """
    _as_error(monkeypatch)
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, "own_test_class",
              "class Test:\n    pass\n\ngo(X) <- (Test(X))\n")
    msg = str(ei.value)
    assert "`++Test`" in msg
    assert "Rename `Test` -> `test`" not in msg


@pytest.mark.parametrize("old, new, text", [
    ("If", "if_", "c(X, L) <- If(X >= 0, L is 1, L is 2)\n"),
    ("Test", "test", 'Test("one") <- (1 == 1)\n'),
])
def test_renamed_spelling_names_the_rename_not_the_escape(
        tmp_path, monkeypatch, old, new, text):
    """``If`` is also a seeded AST node class; the language renamed the
    spelling, so the remedy is ``if_``, never ``++If``."""
    _as_error(monkeypatch)
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, f"sev_{new}", text)
    assert f"Rename `{old}` -> `{new}`" in str(ei.value)
    assert f"`{old}` is a Python class" not in str(ei.value)


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


def test_python_builtin_exception_suggests_the_escape():
    # Transformer only, no load: loading this under ``-implicit_atoms`` would
    # mint ``ValueError`` into the process-wide atom pool and poison every
    # later module that reaches the builtin bare (a ``++ValueError`` catcher
    # then evaluates to the atom).
    #
    # FUNCTOR position, so still linted.  The catcher ARGUMENT spelling this
    # used to use is a TERM position and is now a variable -- see
    # ``test_builtin_exception_as_a_catcher_is_a_variable_now`` below.
    ws = _titlecase_warnings_cell(
        "bar(1),\nfoo(X) <- (bar(X), ValueError(X))\n")
    assert _named(ws) == ["ValueError"]
    assert "reach it as `++ValueError`" in str(ws[0].message)


def test_builtin_exception_as_a_catcher_is_a_variable_now():
    """The narrowing, stated as the consequence a reader most needs to see.

    ``catch(G, ValueError, R)`` used to be refused: TitleCase in any position
    was an error.  The catcher is a TERM position, so ``ValueError`` there is
    now an ordinary logic variable -- which, as in ISO Prolog, makes it a
    CATCH-ALL rather than a filter on that class.  No file relied on the old
    reading (it did not load), but the spelling is no longer flagged, so the
    lint is not what stops someone writing it."""
    assert _titlecase_warnings_cell(
        "bar(1),\nfoo(X) <- catch(bar(X), ValueError, true)\n") == []


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


def test_directive_keyword_argument_value_is_a_term_and_is_not_warned():
    """A keyword argument's VALUE is a term position, so it is a variable
    now.  (The keyword NAME was never a ``Name`` node and was never read.)"""
    assert _titlecase_warnings_cell(
        "-specialize(solve, natnum_program, alias=Foo)\n") == []


def test_directive_argument_in_functor_position_still_warns(tmp_path):
    """Narrowing the walk must not stop it descending into directives: a
    CALL nested inside a directive argument is still a functor position.

    As with the term-position case above, ``-constants`` refuses the RHS
    afterwards; the lint runs on the raw arguments first, so it is the
    warning -- not the load -- that this pins."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        with pytest.raises(SyntaxError):
            _load(tmp_path, "s_dir_functor",
                  "-constants(_L_ = [Foo(1), bar])\n")
    ws = [w for w in rec
          if issubclass(w.category, ClausalTitleCaseIdentifierWarning)]
    assert _named(ws) == ["Foo"]


def test_constants_directive_list_element_is_a_term_and_is_not_warned(
        tmp_path):
    """A list element is a term position, so ``Foo`` is a variable and the
    lint says nothing.  ``-constants`` still refuses the RHS -- for the
    better reason that a constant may not be built from a variable -- so the
    file does not load either way."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        with pytest.raises(SyntaxError, match="-constants"):
            _load(tmp_path, "s_const", "-constants(_L_ = [Foo, bar])\n")
    ws = [w for w in rec
          if issubclass(w.category, ClausalTitleCaseIdentifierWarning)]
    assert _named(ws) == []


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
    # A FUNCTOR position: ``P is Name`` puts the name in TERM position, where
    # it is a variable now and carries no lint.
    ws = _titlecase_warnings(
        tmp_path, f"pb_{name}", binding + f"q(P) <- (P is {name}())\n")
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
