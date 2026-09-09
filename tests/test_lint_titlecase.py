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
