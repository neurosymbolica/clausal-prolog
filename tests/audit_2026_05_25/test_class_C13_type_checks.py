"""C13 — Type-check predicates.

5 findings (1 bug + 3 design-gap + 1 smell). The type-check predicate
family is incomplete (string/1, atomic/1 unregistered), inconsistent
(is_list rejects str despite strings-as-lists), and unsafe
(ground/1 says non-ground SegList is ground).

F080 has a lock-in test in tests/test_string_list_builtins.py.

Findings tested here:
- F080 (design-gap) is_list("abc") fails despite strings-as-lists
- F081 (design-gap) string/1 not registered as builtin
- F082 (design-gap) atomic/1 not registered as builtin
- F083 (bug) ground/1 returns True for non-ground SegList/SegString
- F084 (smell) callable_/1 succeeds for any str including ""
"""

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var
from clausal.terms import SegList, SegString, VarSeg
from clausal.logic.builtins import get_builtin_predicate
from tests.audit_2026_05_25._helpers import load_inline_clausal


def _check(mod, pred: str, value) -> str:
    """Return "T" / "F" / "UNDEF" for a single type-check builtin call.

    T = succeeds (≥1 solution)
    F = fails (0 solutions)
    UNDEF = builtin not registered (KeyError/None from get_builtin_predicate)
    """
    try:
        if get_builtin_predicate(pred, 1, mod) is None:
            return "UNDEF"
    except Exception:
        return "UNDEF"
    try:
        for _ in call(pred, value, module=mod):
            return "T"
        return "F"
    except Exception:
        return "UNDEF"


@pytest.mark.xfail(
    strict=True,
    reason="ledger F080: is_list(\"abc\") fails despite strings-as-lists",
)
def test_F080_is_list_rejects_str_strings_as_lists_gap():
    """is_list("abc") should succeed under strings-as-lists contract.

    Every list builtin (in_/2, length/2, append/3, reverse/2, maplist/N)
    accepts str as a character sequence. is_list/1 rejects it — a caller
    who writes foo(X) :- is_list(X), maplist(p, X, Y) will see foo("abc")
    fail, but maplist(p, "abc", Y) succeed. The two type-tests disagree.

    The lock-in test in tests/test_string_list_builtins.py:405 codifies
    is_list("hello") returning False as intended behaviour. Phase 2
    will need to reconcile that test with this finding.

    Expected: is_list("abc") succeeds (1 solution) under the consistent
    strings-as-lists contract.

    Actual (design-gap): is_list("abc") fails (0 solutions).
    """
    # Load an empty module to get access to the database and builtins.
    mod = load_inline_clausal("c13_f080", "").__dict__["$module"]

    # The expected behaviour: is_list("abc") should succeed.
    result = _check(mod, "is_list", "abc")
    assert result == "T", (
        f"is_list(\"abc\") should succeed under strings-as-lists contract, "
        f"got {result} (expected T)"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F081: string/1 not registered as builtin",
)
def test_F081_string_predicate_not_registered():
    """string/1 builtin is not registered; only is_str/1 exists.

    ISO Prolog and SWI expose string/1 as the canonical test "is this
    a Prolog string?". Users porting code will expect string(X) to work
    but will get KeyError (builtin not registered). Meanwhile, the
    internal type-check table _check_type in the same file accepts
    "string" as a synonym, so must_be(string, X) works but string(X)
    does not — inconsistent.

    Expected: string/1 builtin is registered and succeeds for strings,
    fails for non-strings. string("abc") == 1 solution.

    Actual (design-gap): get_builtin_predicate("string", 1, db) returns
    None (UNDEF).
    """
    # Load an empty module to get access to the database and builtins.
    mod = load_inline_clausal("c13_f081", "").__dict__["$module"]

    # The expected behaviour: string("abc") should succeed (1 solution).
    result = _check(mod, "string", "abc")
    assert result == "T", (
        f"string(\"abc\") should succeed (builtin registered and matches), "
        f"got {result} (expected T)"
    )

    # And it should fail for a non-string.
    result = _check(mod, "string", ["a", "b", "c"])
    assert result == "F", (
        f"string([\"a\",\"b\",\"c\"]) should fail (not a string), "
        f"got {result} (expected F)"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F082: atomic/1 not registered as builtin",
)
def test_F082_atomic_predicate_not_registered():
    """atomic/1 builtin is not registered.

    ISO Prolog and SWI expose atomic/1 as the standard test for
    "not a Var and not compound". No such builtin is registered.
    get_builtin_predicate("atomic", 1, db) returns None.

    Users porting from Prolog will expect atomic(X) to work but will
    see "predicate not defined" instead of a type test.

    Expected: atomic/1 is registered and succeeds for str, int, float,
    bool, None, and zero-arity PredicateMeta; fails for Compound,
    KWTerm, list, dict, term-instances, SegList, SegString.

    Actual (design-gap): atomic/1 is undefined (get_builtin_predicate
    returns None).
    """
    # Load an empty module to get access to the database and builtins.
    mod = load_inline_clausal("c13_f082", "").__dict__["$module"]

    # The expected behaviour: atomic("abc") should succeed.
    result = _check(mod, "atomic", "abc")
    assert result == "T", (
        f"atomic(\"abc\") should succeed (str is atomic), "
        f"got {result} (expected T)"
    )

    # And it should fail for a list (compound structure).
    result = _check(mod, "atomic", ["a", "b", "c"])
    assert result == "F", (
        f"atomic([\"a\",\"b\",\"c\"]) should fail (list is not atomic), "
        f"got {result} (expected F)"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F083: ground/1 returns True for non-ground SegList/SegString",
)
def test_F083_ground_blind_to_varseg_in_seglist():
    """ground/1 returns True for SegList with unbound VarSeg — critical bug.

    ground/1 is the canonical test for "no unbound Vars anywhere in the term".
    The Python fallback _is_ground_py and C implementation c_is_ground both
    enumerate known container shapes (list, Compound, KWTerm, etc.) and
    fall through to return True for any other object — including SegList
    and SegString. The Var inside a VarSeg is never visited.

    Consequence: ground(SegList([VarSeg(X)])) == True even though the
    SegList explicitly contains a hole. This contradicts ground/1's purpose
    and breaks downstream predicates that gate on ground/1 before hashing
    or indexing into a Var-keyed dict — they will crash.

    This is a *real correctness bug* (not just a design-gap).

    Expected: _is_ground recurses into SegList/SegString segments,
    visiting VarSeg.var. ground(SegList([VarSeg(X)])) == False.

    Actual (bug): Seg* shapes are invisible to _is_ground. ground(SegList([VarSeg(X)])) == True
    (silently wrong answer).
    """
    # Load an empty module to get access to the database and builtins.
    mod = load_inline_clausal("c13_f083", "").__dict__["$module"]

    # The bug: ground/1 returns True for SegList with unbound VarSeg.
    x = Var()
    seg_list = SegList([VarSeg(x)])
    result = _check(mod, "ground", seg_list)
    assert result == "F", (
        f"ground(SegList([VarSeg(unbound)])) should fail (contains unbound Var), "
        f"got {result} (expected F, got T indicates bug F083)"
    )

    # Symmetric case: SegString with unbound VarSeg.
    y = Var()
    seg_string = SegString(["a", VarSeg(y)])
    result = _check(mod, "ground", seg_string)
    assert result == "F", (
        f"ground(SegString([\"a\", VarSeg(unbound)])) should fail "
        f"(contains unbound Var), "
        f"got {result} (expected F, got T indicates bug F083)"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F084: callable_/1 succeeds for any str including \"\"",
)
def test_F084_callable_lax_on_arbitrary_strings():
    """callable_/1 succeeds for any str, even strings that are not predicate names.

    callable_/1 succeeds whenever the dereffed term is a str (line 98:
    isinstance(x_val, (str, Compound, KWTerm))). That includes arbitrary
    strings like "this is not a predicate name" or even "". In Prolog
    tradition callable/1 should succeed for "an atom or a compound" —
    strings specifically should either be restricted to registered
    predicate names or documented as lax.

    The audit flags this as a smell (not a bug) because SWI's callable/1
    also says any atom is callable, even unknown ones. What the audit
    wants to flag is the lack of documentation and overly permissive
    behaviour.

    Expected (desired fix): Either restrict to strings that resolve to
    a registered predicate, or document the lax semantics. In any case,
    callable_("") for the empty string and arbitrary non-predicate
    strings is problematic.

    Actual (smell): Any str trivially succeeds; the predicate is effectively
    isinstance(x, (str, Compound, KWTerm, term-instance)). This is overly
    permissive and the test asserts the EXPECTED desired behaviour
    (should fail or raise for arbitrary/empty strings).
    """
    # Load an empty module to get access to the database and builtins.
    mod = load_inline_clausal("c13_f084", "").__dict__["$module"]

    # The desired behaviour: callable_("abc") should fail or raise for
    # an arbitrary unregistered string, not silently succeed.
    result = _check(mod, "callable_", "abc")
    assert result != "T", (
        f"callable_(\"abc\") should fail or raise (arbitrary unregistered string), "
        f"but it succeeds — this is the smell F084. "
        f"Either restrict to registered predicates or document the lax semantics."
    )

    # Worse: callable_("") for empty string should definitely fail.
    result = _check(mod, "callable_", "")
    assert result != "T", (
        f"callable_(\"\") should fail or raise (empty string is not callable), "
        f"but it succeeds — this is the smell F084. "
        f"The empty string is neither a registered predicate nor a valid atom."
    )
