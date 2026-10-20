"""is_dict_t/2 on each surface, and as an if_/3 condition.

if_/3 calls a closure condition with the truth value appended
(``call(If_1, T)``, Scryer's library(reif)), so ``if_(is_dict_t(P), A, B)``
runs ``is_dict_t(P, T)`` -- a builtin, which both front ends accept as the
closure's ``p/N+1``.  Unit rows are in tests/test_is_dict_t.py.
"""
from __future__ import annotations

import textwrap

import pytest


def _load(native, name, text, **kw):
    return native.load(name, textwrap.dedent(text), **kw)


# A dict, the empty dict, a list, [] and an atom, in that order.
_CLAUSAL_KINDS = """\
    kind(D) :- dict_pairs(D, [a-1]).
    kind(D) :- dict_pairs(D, []).
    kind([1, 2]).
    kind([]).
    kind(a).
    """


@pytest.mark.parametrize("suffix", [".clausal", ".pl"])
def test_if_with_is_dict_t_on_the_iso_surfaces(native, ans, suffix):
    mod = _load(native, f"idt_if{suffix[1:]}", """\
        :- use_module(library(reif)).
        """ + _CLAUSAL_KINDS + """\
        q(R) :- kind(P), if_(is_dict_t(P), R = dict, R = other).
        t(T) :- kind(P), is_dict_t(P, T).
        n(N) :- findall(T, is_dict_t(a, T), Ts), length(Ts, N).
        e(E) :- catch(is_dict_t(_, _), error(E, _), true).
        ie(E) :- catch(if_(is_dict_t(_), true, true), error(E, _), true).
        """, suffix=suffix)
    assert ans(mod, "q") == ["dict", "dict", "other", "other", "other"]
    assert ans(mod, "t") == [True, True, False, False, False]
    assert ans(mod, "n") == [1]
    assert ans(mod, "e") == ["instantiation_error"]
    assert ans(mod, "ie") == ["instantiation_error"]


def test_if_with_is_dict_t_in_the_seam(native, ans):
    mod = _load(native, "idt_if_seam", """\
        -private([a, dict, other])
        kind({"a": 1}),
        kind({}),
        kind([1, 2]),
        kind([]),
        kind(a),
        q(R) <- (kind(P), if_(is_dict_t(P), R is dict, R is other))
        t(T) <- (kind(P), is_dict_t(P, T))
        """, suffix=".seam", frontend=None)
    assert ans(mod, "q") == ["dict", "dict", "other", "other", "other"]
    assert ans(mod, "t") == [True, True, False, False, False]


def test_a_plain_python_dict_from_the_seam(native, ans):
    mod = _load(native, "idt_plain_seam", """\
        t(T) <- is_dict_t(++dict(a=1), T)
        """, suffix=".seam", frontend=None)
    assert ans(mod, "t") == [True]
