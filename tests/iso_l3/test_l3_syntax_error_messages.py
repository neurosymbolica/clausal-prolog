"""A ``.pl`` or ``.clausal`` file that does not read: the message, the caret
and the term (operator ruling 2026-10-24).

The native front end refuses a reader ``SyntaxIssue`` with a
``PrologSyntaxError`` -- a ``SyntaxError``, so ``import`` reports it as one
-- that:

* names the file and the item's line in its message, keeps the parser's
  expected-token explanation and the fault's own ``line:col``, and adds a
  hint where one is cheap and certain (``a float needs a fraction: write
  1.0e+9``);
* points its ``lineno``/``offset`` (so Python's traceback caret, and the
  ``clausal`` command's) at the fault, which may be lines below the item's
  first line;
* carries the ISO term as ``.term``: ``error(syntax_error(Kind),
  context(read_term/3, [line(L), column(C), expected(E), found(F)]))``,
  the same term ``read_term/3`` raises for the text (pinned against Scryer
  row by row in ``tests/iso/test_syntax_error_terms_scryer.py``).
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import PrologSyntaxError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _import_failure(tmp_path, monkeypatch, name, source, suffix=".pl"):
    (tmp_path / f"{name}{suffix}").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    with pytest.raises(SyntaxError) as ei:
        importlib.import_module(name)
    return ei.value


def test_fault_below_the_items_first_line(tmp_path, monkeypatch):
    err = _import_failure(tmp_path, monkeypatch, "l3_syn_a",
                          "ok(1).\nfoo(a,\nbar(b).\nbaz.\n")
    assert isinstance(err, PrologSyntaxError)
    # the message: the file and the item's line, then the explanation at
    # the fault's own position
    assert "l3_syn_a.pl:2: syntax error" in str(err)
    assert "Expected ')', got '.' ('.') at 3:7" in str(err)
    # the caret: on the fault, not the item's first line
    assert (err.lineno, err.offset) == (3, 7)
    assert err.text == "bar(b)."
    assert err.end_lineno == 3 and err.end_offset == 8
    assert err.term == (
        "error", ("syntax_error", "incomplete_reduction"),
        ("context", ("/", "read_term", 3),
         [("line", 3), ("column", 7), ("expected", ")"), ("found", "end")]))


def test_hint_for_a_float_without_a_fraction(tmp_path, monkeypatch):
    err = _import_failure(tmp_path, monkeypatch, "l3_syn_b",
                          "ok(1).\nX = 1e+9.\n")
    assert "at 2:6 (a float needs a fraction: write 1.0e+9)" in str(err)
    assert (err.lineno, err.offset) == (2, 6)
    assert err.term[1] == ("syntax_error", "incomplete_reduction")
    assert dict(err.term[2][2])["found"] == "e"


@pytest.mark.parametrize("text, hint", [
    ("X = 1.e2.", "a float needs a digit after the point: write 1.0e2"),
    ("X = .5.", "a float needs a digit before the point: write 0.5"),
    ("X = 0x.", "0x needs at least one hexadecimal digit"),
    ("X = 0xG.", "'G' is not a hexadecimal digit"),
    ("X = 0b2.", "'2' is not a binary digit"),
    ("X = 0o8.", "'8' is not an octal digit"),
    ("X = 0''.", "the code of a quote is written 0''' (or 0'\\')"),
    ("X = 1.0e400.", "the largest double is about 1.8e308"),
])
def test_number_hints(tmp_path, monkeypatch, text, hint):
    name = "l3_syn_hint_" + str(abs(hash(text)) % 10000)
    err = _import_failure(tmp_path, monkeypatch, name, text + "\n")
    assert f"({hint})" in str(err), str(err)


def test_no_hint_where_none_is_certain(tmp_path, monkeypatch):
    err = _import_failure(tmp_path, monkeypatch, "l3_syn_c", "a :- b :- c.\n")
    assert "operator priority clash" in err.msg
    assert err.msg.endswith("left operand of priority 1200 at 1:8")


def test_unterminated_quote_names_the_quote(tmp_path, monkeypatch):
    err = _import_failure(tmp_path, monkeypatch, "l3_syn_d",
                          "ok(1).\nX = 'abc\nfoo.\n")
    assert "unterminated quoted atom at 2:5" in str(err)
    assert (err.lineno, err.offset) == (2, 5) and err.text == "X = 'abc"
    assert err.term[1] == ("syntax_error", "invalid_single_quoted_character")
    assert dict(err.term[2][2]) == {"line": 2, "column": 5, "expected": "'",
                                    "found": "\n"}


def test_clausal_surface_gets_the_same_term(tmp_path, monkeypatch):
    err = _import_failure(tmp_path, monkeypatch, "l3_syn_e",
                          "ok(1).\np(X) :- X = f(a b).\n", suffix=".clausal")
    assert isinstance(err, PrologSyntaxError)
    assert err.term[1] == ("syntax_error", "incomplete_reduction")
    assert dict(err.term[2][2]) == {"line": 2, "column": 17,
                                    "expected": ")", "found": "b"}


def test_a_refusal_that_is_no_syntax_error_has_no_term(tmp_path, monkeypatch):
    err = _import_failure(tmp_path, monkeypatch, "l3_syn_f",
                          "f(1).\n:- initialization(f(1)).\n")
    assert isinstance(err, PrologSyntaxError) and err.term is None
    assert err.lineno == 2 and err.offset == 1


def test_cli_prints_the_line_and_a_caret(tmp_path):
    (tmp_path / "bad.pl").write_text("ok(1).\nfoo(a,\nbar(b).\n")
    env = dict(os.environ)
    env.pop("CLAUSAL_PL_FRONTEND", None)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-m", "clausal", "bad.pl", "-g", "ok(X)"],
                       cwd=tmp_path, env=env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 1
    assert "bad.pl did not load" in r.stderr
    assert "Expected ')', got '.' ('.') at 3:7" in r.stderr
    lines = r.stderr.rstrip("\n").split("\n")
    assert lines[-2].strip() == "bar(b)." and lines[-1].strip() == "^"
    # the caret sits under column 7 of the source line
    assert lines[-1].index("^") - lines[-2].index("bar") == 6
