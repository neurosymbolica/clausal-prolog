"""Builtins raise ISO errors on bad arguments instead of FAILING silently.

todo/done/builtins-fail-silently-on-bad-arguments-2026-09-27.md.  Each goal
runs as ``catch((G, R is no_error), E, R is E)``; before the fix every row
below had NO answer at all.  The expected error terms are ISO 13211-1's,
checked against Scryer Prolog (/workspace/scryer-prolog, 2026-09-30).
"""
import importlib
import sys

import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from tests._suffix import SEAM

_CASES = [
    # (goal source, expected error formal as a tuple, culprit indicator)
    ("functor(_, foo, -1)", ("domain_error", "not_less_than_zero", -1), "functor"),
    ("functor(_, _, 1)", "instantiation_error", "functor"),
    ("functor(_, foo, _)", "instantiation_error", "functor"),
    ("functor(_, foo, a)", ("type_error", "integer", "a"), "functor"),
    ("arg(x, f(a), _)", ("type_error", "integer", "x"), "arg"),
    ("arg(1, _, _)", "instantiation_error", "arg"),
    ("arg(1, a, _)", ("type_error", "compound", "a"), "arg"),
    ("arg(1, 3, _)", ("type_error", "compound", 3), "arg"),
    ("arg(-1, f(a), _)", ("domain_error", "not_less_than_zero", -1), "arg"),
    ("sort(a, _)", ("type_error", "list", "a"), "sort"),
    ("sort([a, *_], _)", "instantiation_error", "sort"),
    ("sort(_, _)", "instantiation_error", "sort"),
    ("sort([b, a], x)", ("type_error", "list", "x"), "sort"),
    # ISO error order: List is checked before Sorted.
    ("sort(_, x)", "instantiation_error", "sort"),
    ("sort(a, x)", ("type_error", "list", "a"), "sort"),
    ("msort(a, _)", ("type_error", "list", "a"), "msort"),
    ("sub_atom(abc, _, -1, _, _)", ("domain_error", "not_less_than_zero", -1), "sub_atom"),
    ("sub_atom(abc, -1, _, _, _)", ("domain_error", "not_less_than_zero", -1), "sub_atom"),
    ("sub_atom(abc, _, _, -1, _)", ("domain_error", "not_less_than_zero", -1), "sub_atom"),
    ("sub_atom(abc, a, _, _, _)", ("type_error", "integer", "a"), "sub_atom"),
    ("sub_atom(abc, _, _, _, 1)", ("type_error", "atom", 1), "sub_atom"),
    ("char_code(_, -1)", ("representation_error", "character_code"), "char_code"),
    ("char_code(_, 1114112)", ("representation_error", "character_code"), "char_code"),
    ("atom_length(a, -1)", ("domain_error", "not_less_than_zero", -1), "atom_length"),
    ("atom_length(a, x)", ("type_error", "integer", "x"), "atom_length"),
]

_ARITY = {"functor": 3, "arg": 3, "sort": 2, "msort": 2, "sub_atom": 5,
          "char_code": 2, "atom_length": 2}

_MOD = "bbae_cases"


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("bbae")
    lines = ["-allow_singletons",
             "-private([a, b, abc, foo, x, f(_), no_error])"]
    for i, (goal, _, _) in enumerate(_CASES):
        lines.append(
            f"t{i}(R) <- (catch(({goal}, R is no_error), E, R is E))")
    # Positive controls: the good-argument modes still answer.
    lines += [
        "ok_sort(S) <- sort([b, a, b], S)",
        "ok_arg(A) <- arg(1, f(a), A)",
        "ok_arg0(A) <- arg(0, f(a), A)",
        "ok_functor(T) <- functor(T, foo, 2)",
        "ok_sub(S) <- sub_atom(abc, 1, 1, _, S)",
        "ok_code(C) <- char_code(C, 97)",
        "ok_len(N) <- atom_length(abc, N)",
        "ok_seg(S) <- (L is [X, a, *T], T is [], X is b, sort(L, S))",
        # a filled-in SegList with an UNBOUND element is still a proper list
        "ok_seg_var(N) <- (L is [X, a, *T], T is [], sort(L, S), length(S, N))",
    ]
    (d / f"{_MOD}{SEAM}").write_text("\n".join(lines) + "\n")
    sys.path.insert(0, str(d))
    try:
        yield importlib.import_module(_MOD)
    finally:
        sys.path.remove(str(d))
        sys.modules.pop(_MOD, None)


def _answers(mod, pred):
    v = Var()
    return [_deref_walk(v) for _ in solve((pred, v), mod)]


@pytest.mark.parametrize("i", range(len(_CASES)),
                         ids=[c[0] for c in _CASES])
def test_bad_argument_raises_the_iso_error(mod, i):
    goal, formal, name = _CASES[i]
    assert _answers(mod, f"t{i}") == [
        ("error", formal, ("/", name, _ARITY[name]))], goal


def test_good_arguments_still_answer(mod):
    assert _answers(mod, "ok_sort") == [["a", "b"]]
    assert _answers(mod, "ok_arg") == ["a"]
    assert _answers(mod, "ok_arg0") == []          # ISO: fails, no error
    [t] = _answers(mod, "ok_functor")
    assert t[0] == "foo" and len(t) == 3
    assert _answers(mod, "ok_sub") == ["b"]
    assert _answers(mod, "ok_code") == ["a"]
    assert _answers(mod, "ok_len") == [3]
    assert _answers(mod, "ok_seg") == [["a", "b"]]
    assert _answers(mod, "ok_seg_var") == [2]
