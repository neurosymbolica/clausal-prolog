import re

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def test_dict_lowers_to_sorted_attribute_list():
    out = clausal_source_to_prolog(
        "profile_for(s1, {zeta: True, alpha: False}),\n", strict=True
    )
    assert "profile_for(s1, [attribute(alpha, false), attribute(zeta, true)])." in out


def test_empty_dict_lowers_to_empty_list():
    out = clausal_source_to_prolog("profile_for(s2, {}),\n", strict=True)
    assert "profile_for(s2, [])." in out


def test_nested_dict_lowers_recursively():
    out = clausal_source_to_prolog(
        "cfg(x, {outer: {inner: True}}),\n", strict=True
    )
    assert "cfg(x, [attribute(outer, [attribute(inner, true)])])." in out


def test_dict_in_rule_body():
    out = clausal_source_to_prolog(
        "q_limb_a(P) <- (P is {technique_subliminal: True})\n", strict=True
    )
    assert "[attribute(technique_subliminal, true)]" in out


def test_dict_splat_still_untranslatable():
    # Splat not first: task 2 only lowers the splat-FIRST `is`-RHS shape
    # (X is {**D, k: v, ...}) to attrs_put/3; splat-not-first stays
    # untranslatable.
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog(
            "p(X) <- (X is {a: 1, **base_profile()})\n", strict=True)


def test_get_maps_to_profile_get():
    out = clausal_source_to_prolog(
        "v(P, V) <- get(P, exception_d_supports_human_assessment, V)\n",
        strict=True,
    )
    assert "profile_get(P, exception_d_supports_human_assessment, V)" in out
    # Word-boundary check, not a plain substring: "profile_get(P," itself
    # contains the substring "get(P," as a tail, so a naive `"get(P," not in
    # out` can never pass once the mapping fires. \b does not match between
    # "_" and "g" (both word chars), so this only catches an *unmapped*,
    # standalone "get(P," call.
    assert re.search(r"\bget\(P,", out) is None


def test_tri_get_passes_through():
    out = clausal_source_to_prolog("v(P, V) <- tri_get(P, k, V)\n", strict=True)
    assert "tri_get(P, k, V)" in out


# ── C-pre: dict-subscript is-RHS lowering — REMEDIED via profile_get_strict ──
#
# Task brief (original): lower goal-position `X is P[key]` to
# `profile_get(P, key, X)`, mirroring the splat-lowering discipline. That
# exact mapping was BLOCKED (not shipped) on first pass: `profile_get` is a
# straight rename of the `get/3` builtin, which FAILS on a missing key by
# design, while the engine's strict subscript read RAISES a catchable
# existence_error on a missing key (clausal/logic/runtime/dict_ops.py:
# _subscript, pinned by
# tests/test_dict_set_compiler.py::test_subscript_missing_throws). One
# functor cannot be both the soft-fail target for exported `get/3` calls and
# a faithful target for the throwing subscript read.
#
# Controller-ruled remedy (2026-09-05): a NEW, distinctly-named staging
# predicate, `profile_get_strict/3`, companion-defined in
# tools/iso_export/companion/clausal_profiles.pl (trunk repo) to mirror the
# engine's throw-on-missing semantics exactly, rather than reusing
# `profile_get`'s fail semantics. This module lowers to THAT name. Full
# findings: .superpowers/sdd/2026-09-05-class-M/c-pre-report.md in the
# clausify-executor-train repo.
#
# `is`/2 is symmetric in Clausal (`_convert_compare` treats `X is Y` and
# `Y is X` identically — both sides just get `_convert_expr`'d), and the
# corpus witness (eu/procurement/exclusion_grounds) actually uses BOTH
# orders: `V is P[K]` (the shape named in the brief) and `P[K] is V` (three
# real sites in queries.clausal, e.g. `PROFILE[grounds] is GROUND_LIST`) —
# so the lowering matches a subscript on EITHER side of a goal-position `is`.
#
# Nested/argument position (not the executed `is`-RHS/LHS) stays refused,
# exactly like nested splats: the corpus witness has two real instances
# (`PROFILE[grounds]` as `member/2`'s second argument via
# `INSTANCE in PROFILE[grounds]`, and `INSTANCE[event_date]` as a call
# argument to `expiry_date/3`), both still fail-closed under strict mode.
#
# Chained subscripts (`P[a][b]`) and subscript-on-a-call-result (`f()[a]`)
# also stay refused — the corpus census (clausify-domains, 850 files) found
# zero instances of either shape, so there is nothing to support beyond
# falling through to the existing generic "unsupported expression" fallback.

def test_subscript_goal_position_is_rhs_lowers_to_profile_get_strict():
    """`V is P[key]` in goal position -- the task's original target shape,
    now unblocked via profile_get_strict/3 (not profile_get/3)."""
    out = clausal_source_to_prolog(
        "x(P, V) <- (V is P[ground])\n", strict=True)
    assert "profile_get_strict(P, ground, V)" in out


def test_subscript_goal_position_is_rhs_str_key_lowers_same_as_name_key():
    """A str-literal key converts through the same `_convert_expr` path as a
    bare-Name key -- both denote the SAME atom post str-literal migration
    (R2), so `P["ground"]` and `P[ground]` must lower identically."""
    out = clausal_source_to_prolog(
        'x(P, V) <- (V is P["ground"])\n', strict=True)
    assert "profile_get_strict(P, ground, V)" in out


def test_subscript_goal_position_is_lhs_lowers_to_profile_get_strict():
    """`P[key] is V` -- the mirror-image goal-position shape the corpus
    witness (eu/procurement/exclusion_grounds/queries.clausal) actually
    uses three times (`PROFILE[grounds] is GROUND_LIST`). `is`/2 is
    symmetric, so this lowers the same way with sides swapped."""
    out = clausal_source_to_prolog(
        "x(P, V) <- (P[grounds] is V)\n", strict=True)
    assert "profile_get_strict(P, grounds, V)" in out


def test_subscript_nested_position_still_untranslatable():
    """`q(P) <- r(P[ground])` -- a dict-subscript reaching `_convert_expr`
    in argument/nested position (not the executed `is`-RHS/LHS). Still
    fail-closed via the generic fallback -- the corpus witness has two real
    instances of this shape (see module docstring), both of which refuse
    under strict mode -- pins that this keeps refusing loudly rather than
    silently emitting an inert data term."""
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError, match=r"P\[ground\]"):
        clausal_source_to_prolog("q(P) <- r(P[ground])\n", strict=True)


def test_subscript_in_membership_position_still_untranslatable():
    """`INSTANCE in PROFILE[grounds]` -- the corpus witness's own nested
    shape: a dict-subscript as the second (list) argument of `in`/member,
    not itself an executed `is`-RHS/LHS. Still fail-closed."""
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError, match=r"PROFILE\[grounds\]"):
        clausal_source_to_prolog(
            "g(PROFILE, X) <- (X in PROFILE[grounds])\n", strict=True)


def test_chained_subscript_still_untranslatable():
    """`P[a][b]` -- chained subscript. Zero corpus instances (census:
    clausify-domains, 850 files, 41 subscript sites, 0 chained); refuses
    rather than trying to invent semantics for an unwitnessed shape."""
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("x(P, V) <- (V is P[a][b])\n", strict=True)


def test_subscript_on_call_result_still_untranslatable():
    """`f()[a]` -- subscript on a call result. Zero corpus instances (same
    census); refuses for the same reason."""
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("x(V) <- (V is base_profile()[a])\n", strict=True)
