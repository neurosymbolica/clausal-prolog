import pytest
from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog, UntranslatableConstructError,
)
from clausal.tools.prolog_dialect import Dialect

OVERRIDE_KEY = """override_key(DICT, KEY, VALUE, NEW_DICT) <- (
    NEW_DICT is {**DICT, KEY: VALUE}
)
"""


def test_is_rhs_splat_lowers_to_attrs_put():
    out = clausal_source_to_prolog(OVERRIDE_KEY, strict=True)
    assert "attrs_put(Dict, [attribute(Key, Value)], New_dict)" in out
    assert "**" not in out and "is" not in out.split(":-")[1]


def test_multiple_pairs_sorted():
    out = clausal_source_to_prolog(
        "p(D, OUT) <- (OUT is {**D, zeta: 1, alpha: 2})\n", strict=True
    )
    assert "attrs_put(D, [attribute(alpha, 2), attribute(zeta, 1)], Out)" in out


def test_multi_splat_still_untranslatable():
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("p(A, B, X) <- (X is {**A, **B})\n", strict=True)


def test_splat_outside_is_rhs_still_untranslatable():
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("p(D) <- q({**D, k: v})\n", strict=True)


def test_kit_query_combinators_translates_strict():
    import pathlib
    src = pathlib.Path(
        "/workspace/clausify-executor-train/kit/query_combinators.clausal"
    ).read_text()
    out = clausal_source_to_prolog(src, strict=True)  # must not raise
    assert "attrs_put(" in out


def test_is_rhs_splat_in_argument_position_still_untranslatable():
    """Regression (design-review CRITICAL finding): the is-RHS splat
    rewrite is a goal-only lowering. `attrs_put/3` is a predicate meant to
    be called as a goal, not embedded as inert data inside another goal's
    argument list — `q(X is {**D, k: v})` puts the `is`-comparison in a
    Call-argument (data) position, never executed, so it must still hit
    the generic dict-splat warning/strict-raise path, exactly as it did
    before this task's rewrite existed. Reviewer's exact probe."""
    src = "p(D, X) <- q(X is {**D, k: v})\n"
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog(src, strict=True)

    out = clausal_source_to_prolog(src)  # lenient: no raise, no attrs_put
    assert "attrs_put(" not in out
    assert "untranslatable" in out  # warning comment survives, not silent


def test_swi_dialect_never_emits_attrs_put():
    """Regression: `attrs_put/3` is an ISO-export staging predicate — it
    does not exist under SWI dict semantics. Before this fix, the
    `is`-RHS splat gate fired regardless of dialect, so `Dialect.swi()`
    (has_dicts=True) emitted `attrs_put(...)` applied to a SWI dict_create
    compound: a call to a predicate that was never defined anywhere in
    the SWI world. The has_dicts path must keep its pre-existing
    dict_create behavior instead."""
    src = "p(D, X) <- (X is {**D, k: 1})\n"
    out = clausal_source_to_prolog(src, dialect=Dialect.swi())
    assert "attrs_put(" not in out
    assert "dict_create(" in out

    # ISO output is unchanged by the dialect check.
    iso_out = clausal_source_to_prolog(src)
    assert "attrs_put(D, [attribute(k, 1)], X)" in iso_out


def test_zero_pair_splat_at_goal_position():
    """`X is {**D}` (splat-first, zero explicit pairs) is still within the
    brief's translatable shape ("one splat first, zero or more explicit
    pairs") when it *is* the goal — attrs_put(D, [], X)."""
    out = clausal_source_to_prolog(
        "p(D, X) <- (X is {**D})\n", strict=True
    )
    assert "attrs_put(D, [], X)" in out
