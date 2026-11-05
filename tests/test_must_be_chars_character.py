"""must_be/2 and can_be/2 for the ``chars`` and ``character`` types.

Operator ruling 2026-11-05: in Clausal the type test for a string (a list
of chars) is library(error)'s ``must_be(chars, Cs)`` / ``can_be(chars,
Cs)``, as Scryer's.  Every expected answer below was measured on Scryer
(v0.10.0-137, the oracle ``tests/_oracles.py`` names), context included:
Scryer's ``must_be(chars, _)`` runs ``can_be(chars, _)`` first, so its TYPE
errors carry ``can_be/2`` while its instantiation error carries
``must_be/2``.  Trealla agrees for must_be; its ``can_be(chars, _)``
succeeds for every term, and Scryer is followed there.

The order of the checks: no list (``type_error(list, Term)``) before a bad
element (``type_error(character, E)``) before an open list or unbound
element (``instantiation_error`` for must_be, success for can_be).
"""

import re

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.testing import load_clausal_module

# (name, term as Clausal Prolog source)
_TERMS = [
    ("dq", '"ab"'),
    ("dq_empty", '""'),
    ("list", "[a,b]"),
    ("nil", "[]"),
    ("atom", "ab"),
    ("ints", "[1,2]"),
    ("long_atom", "[ab]"),
    ("empty_atom", "['']"),
    ("float", "[1.0]"),
    ("partial", "[a|_]"),
    ("var", "_"),
    ("int", "1"),
    ("compound", "f(x)"),
    ("unbound_elem", "[a,_]"),
    ("only_unbound", "[_]"),
    ("open_open", "[_|_]"),
    ("bad_then_open", "[a,1|_]"),
    ("long_then_open", "[ab|_]"),
    ("unbound_then_bad", "[_,1]"),
    ("bad_then_unbound", "[1,_]"),
    ("unbound_improper", "[_|b]"),
    ("improper", "[a|b]"),
    ("improper2", "[a,b|c]"),
    ("bad_improper", "[1|b]"),
    ("bad_mid_improper", "[a,1|b]"),
    ("dq_tail", '[a|"bc"]'),
    ("code", "[97]"),
]

_CHARACTER_TERMS = [
    ("c_a", "a"),
    ("c_accent", "'é'"),
    ("c_ab", "ab"),
    ("c_empty", "''"),
    ("c_int", "1"),
    ("c_float", "1.0"),
    ("c_var", "_"),
    ("c_compound", "f(x)"),
    ("c_list", "[a]"),
    ("c_dq", '"a"'),
    ("c_nil", "[]"),
]


def _source():
    lines = []
    for name, term in _TERMS:
        lines.append(f"mb_{name} :- must_be(chars, {term}).")
        lines.append(f"cb_{name} :- can_be(chars, {term}).")
    for name, term in _CHARACTER_TERMS:
        lines.append(f"mb_{name} :- must_be(character, {term}).")
        lines.append(f"cb_{name} :- can_be(character, {term}).")
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("must_be_chars") / "must_be_chars.clausal"
    p.write_text(_source())
    return load_clausal_module(p)


def _outcome(mod, goal):
    try:
        return len(list(solve(goal, mod)))
    except LogicException as e:
        return str(e).split("exception: ", 1)[-1]


_INST = "error(instantiation_error,must_be/2)"


def _te(kind, culprit):
    return f"error(type_error({kind},{culprit}),can_be/2)"


# name: (must_be answer, can_be answer) -- Scryer's, measured.
_CHARS = {
    "dq": (1, 1),
    "dq_empty": (1, 1),
    "list": (1, 1),
    "nil": (1, 1),
    "atom": (_te("list", "ab"),) * 2,
    "ints": (_te("character", "1"),) * 2,
    "long_atom": (_te("character", "ab"),) * 2,
    "empty_atom": (_te("character", "''"),) * 2,
    "float": (_te("character", "1.0"),) * 2,
    "partial": (_INST, 1),
    "var": (_INST, 1),
    "int": (_te("list", "1"),) * 2,
    "compound": (_te("list", "f(x)"),) * 2,
    "unbound_elem": (_INST, 1),
    "only_unbound": (_INST, 1),
    "open_open": (_INST, 1),
    "bad_then_open": (_te("character", "1"),) * 2,
    "long_then_open": (_te("character", "ab"),) * 2,
    "unbound_then_bad": (_te("character", "1"),) * 2,
    "bad_then_unbound": (_te("character", "1"),) * 2,
    "unbound_improper": (_te("list", "[_|b]"),) * 2,
    "improper": (_te("list", "[a|b]"),) * 2,
    "improper2": (_te("list", "[a,b|c]"),) * 2,
    "bad_improper": (_te("list", "[1|b]"),) * 2,
    "bad_mid_improper": (_te("list", "[a,1|b]"),) * 2,
    "dq_tail": (1, 1),
    "code": (_te("character", "97"),) * 2,
}


def _norm(answer):
    """A fresh variable prints as ``_G123``/``_123``: read every one as ``_``."""
    return re.sub(r"_[A-Za-z]*\d+", "_", answer) if isinstance(answer, str) else answer


def test_table_covers_every_term():
    assert set(_CHARS) == {name for name, _ in _TERMS}


@pytest.mark.parametrize("name", [n for n, _ in _TERMS])
def test_must_be_chars(mod, name):
    assert _norm(_outcome(mod, f"mb_{name}")) == _CHARS[name][0]


@pytest.mark.parametrize("name", [n for n, _ in _TERMS])
def test_can_be_chars(mod, name):
    assert _norm(_outcome(mod, f"cb_{name}")) == _CHARS[name][1]


def _ce(pred, culprit):
    return f"error(type_error(character,{culprit}),{pred}/2)"


# name: (must_be answer, can_be answer) -- Scryer's, measured.  ``[a]`` and
# ``"a"`` are one term; Clausal's writeq spells it ``"a"`` where Scryer's
# spells it ``[a]``.
_CHARACTER = {
    "c_a": (1, 1),
    "c_accent": (1, 1),
    "c_ab": (_ce("must_be", "ab"), _ce("can_be", "ab")),
    "c_empty": (_ce("must_be", "''"), _ce("can_be", "''")),
    "c_int": (_ce("must_be", "1"), _ce("can_be", "1")),
    "c_float": (_ce("must_be", "1.0"), _ce("can_be", "1.0")),
    "c_var": (_INST, 1),
    "c_compound": (_ce("must_be", "f(x)"), _ce("can_be", "f(x)")),
    "c_list": (_ce("must_be", '"a"'), _ce("can_be", '"a"')),
    "c_dq": (_ce("must_be", '"a"'), _ce("can_be", '"a"')),
    "c_nil": (_ce("must_be", "[]"), _ce("can_be", "[]")),
}


@pytest.mark.parametrize("name", [n for n, _ in _CHARACTER_TERMS])
def test_must_be_character(mod, name):
    assert _outcome(mod, f"mb_{name}") == _CHARACTER[name][0]


@pytest.mark.parametrize("name", [n for n, _ in _CHARACTER_TERMS])
def test_can_be_character(mod, name):
    assert _outcome(mod, f"cb_{name}") == _CHARACTER[name][1]


# ── the same rows, reached other ways ───────────────────────────────────

def test_chars_bound_at_run_time(tmp_path):
    """A list closed by a later binding is read through it."""
    p = tmp_path / "late.clausal"
    p.write_text(
        "late_ok :- L = [a|T], T = [b], must_be(chars, L).\n"
        "late_bad :- L = [a|T], T = [1], must_be(chars, L).\n"
        "late_improper :- L = [a|T], T = b, can_be(chars, L).\n"
        "univ_ok :- L =.. ['.', a, []], must_be(chars, L).\n")
    m = load_clausal_module(p)
    assert _outcome(m, "late_ok") == 1
    assert _outcome(m, "late_bad") == _te("character", "1")
    assert _outcome(m, "late_improper") == _te("list", "[a|b]")
    assert _outcome(m, "univ_ok") == 1


def test_seam_surface(tmp_path):
    """The seam passes the type name as a quoted atom and a string literal
    is the same char list."""
    p = tmp_path / "chars_seam.seam"
    p.write_text(
        "seam_ok() <- must_be('chars', \"ab\")\n"
        "seam_list() <- must_be('chars', ['a', 'b'])\n"
        "seam_bad() <- must_be('chars', [1])\n"
        "seam_open() <- can_be('chars', ['a', *_])\n"
        "seam_char() <- must_be('character', 'a')\n"
        "seam_inner_hole() <- must_be('chars', [*_, 'a'])\n"
        "seam_inner_hole_bad() <- can_be('chars', [*_, 1])\n")
    m = load_clausal_module(p)
    assert _outcome(m, "seam_ok") == 1
    assert _outcome(m, "seam_list") == 1
    assert _outcome(m, "seam_bad") == _te("character", "1")
    assert _outcome(m, "seam_open") == 1
    assert _outcome(m, "seam_char") == 1
    # A hole before an element (no ISO spelling): still open, elements checked.
    assert _outcome(m, "seam_inner_hole") == _INST
    assert _outcome(m, "seam_inner_hole_bad") == _te("character", "1")
