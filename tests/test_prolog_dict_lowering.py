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


# ── C-pre: dict-subscript is-RHS lowering — BLOCKED, not implemented ──────────
#
# Task brief: lower goal-position `X is P[key]` to `profile_get(P, key, X)`,
# mirroring the splat-lowering discipline. NOT SHIPPED — probing the target
# semantics first (as the brief itself required) surfaced a real divergence,
# so these tests PIN today's fail-closed behavior rather than exercise a new
# lowering. Full findings: .superpowers/sdd/2026-09-05-class-M/c-pre-report.md
# in the clausify-executor-train repo.
#
# The divergence: the engine's strict subscript read RAISES a catchable
# existence_error(dict_key, Key) on a missing key
# (clausal/logic/runtime/dict_ops.py:_subscript, pinned by
# tests/test_dict_set_compiler.py::test_subscript_missing_throws — see the
# fixture at tests/fixtures/dict_set_patterns.clausal:110-116). `get/3` --
# profile_get's ISO-export target (prolog_dialect.py:223, a straight rename,
# not a semantics change) -- instead FAILS on a missing key by design
# (clausal/logic/builtins/dict_set.py:_get__3's docstring; pinned by
# tests/test_dict_set_compiler.py::test_get_absent_fails). One functor name,
# two incompatible failure modes: `profile_get/3` cannot be both the soft-fail
# target for exported `get/3` calls AND a faithful target for the throwing
# subscript read. Shipping `X is P[key] -> profile_get(P, key, X)` as
# specified would silently turn "profile is missing a required field" (an
# error, on the live engine) into "clause fails" (a quiet no) in every
# exported program -- the same worst-direction collapse the `"[]"`/`{}`
# literal fix (f47e1a8e's parent) was written to stop, not repeat.
#
# So: still untranslatable, on purpose, for both shapes named in the task
# brief -- goal-position `is`-RHS and nested/argument position alike (the
# pre-existing generic "unsupported expression" fallback already fails
# closed for both; nothing here changes translator behavior).

def test_subscript_goal_position_is_rhs_still_untranslatable():
    """`V is P[key]` in goal position -- the task's target shape for the
    profile_get lowering. Blocked (see module docstring above): still
    refuses rather than emitting a silently-divergent `profile_get/3`."""
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError, match=r"P\[ground\]"):
        clausal_source_to_prolog("x(P, V) <- (V is P[ground])\n", strict=True)


def test_subscript_goal_position_is_lhs_still_untranslatable():
    """`P[key] is V` -- the mirror-image goal-position shape the corpus
    witness (eu/procurement/exclusion_grounds/queries.clausal) actually
    uses three times (`PROFILE[grounds] is GROUND_LIST`). `is`/2 is
    symmetric, so this is the same target shape with sides swapped; still
    blocked for the same reason."""
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError, match=r"P\[grounds\]"):
        clausal_source_to_prolog(
            "x(P, V) <- (P[grounds] is V)\n", strict=True)


def test_subscript_nested_position_still_untranslatable():
    """`q(P) <- r(P[ground])` -- a dict-subscript reaching `_convert_expr`
    in argument/nested position (not the executed `is`-RHS). Already
    fail-closed today via the generic fallback; the corpus witness has two
    real instances of this shape (`PROFILE[grounds]` as `member/2`'s
    second argument via `IN...IN PROFILE[grounds]`, and
    `INSTANCE[event_date]` as a call argument to `expiry_date/3`), both of
    which already refuse under strict mode -- pins that this keeps
    refusing loudly rather than silently emitting an inert data term."""
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError, match=r"P\[ground\]"):
        clausal_source_to_prolog("q(P) <- r(P[ground])\n", strict=True)
