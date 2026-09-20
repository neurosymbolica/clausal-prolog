"""-constants: declared, ground at module load, folded into clause terms."""
import textwrap
import pytest

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tc_{name}", str(path))


def _values(module, goal_name, *args):
    v = Var()
    return [deref(v) for _ in call(goal_name, *args, v,
                                   module=module.__dict__["$module"])]


def test_scalar_constant_in_arithmetic(tmp_path):
    m = _load(tmp_path, "a", """
        -constant_value(c_pi, 3.14159)
        area(R, A) <- (A is ++(c_pi * R * R))
    """)
    [a] = _values(m, "area", 2.0)
    assert abs(a - 3.14159 * 4.0) < 1e-9


def test_constant_as_plain_argument(tmp_path):
    m = _load(tmp_path, "b", """
        -constant_value(c_max, 3)
        limit(++c_max),
        got(X) <- limit(X)
    """)
    v = Var()
    results = [deref(v) for _ in call("limit", v, module=m.__dict__["$module"])]
    assert results == [3]


def test_constant_from_prior_constant_and_arithmetic(tmp_path):
    m = _load(tmp_path, "c", """
        -constant_value(c_base, 10)
        -constant_value(c_limit, c_base * 4 + 2)
        lim(++c_limit),
    """)
    v = Var()
    assert [deref(v) for _ in call("lim", v, module=m.__dict__["$module"])] == [42]


def test_plusplus_rhs(tmp_path):
    m = _load(tmp_path, "d", """
        -constant_value(c_pi, ++__import__('math').pi)
        pi(++c_pi),
    """)
    import math
    v = Var()
    assert [deref(v) for _ in call("pi", v, module=m.__dict__["$module"])] == [math.pi]


def test_plusplus_rhs_undeclared_name_is_a_load_time_name_error(tmp_path):
    """A free name in a ``-constants`` ``++`` RHS fails when the module runs.

    This used to be a located SyntaxError, from a scan that recognised an
    undeclared CONSTANT by its shape. A constant name is atom-shaped since
    2026-09-11, so no scan can tell one from ``math`` or a helper, and the
    scan is gone. The RHS is evaluated at module level, so the failure is
    still at LOAD time -- it just names the Python name rather than offering
    a constants-specific remedy.
    """
    with pytest.raises(NameError, match="c_b"):
        _load(tmp_path, "d2", "-constant_value(c_a, ++(c_b * 2))\np(++c_a),\n")


def test_plusplus_rhs_declared_earlier_constant_still_works(tmp_path):
    """A constant declared by an earlier -constants entry IS legal inside a
    later ++ RHS — by exec time it is already a bound module global. Keeps
    the existing passing ``++`` RHS behaviour green alongside the new scan."""
    m = _load(tmp_path, "d3", """
        -constant_value(c_base, 10)
        -constant_value(c_scaled, ++(c_base * 2))
        scaled(++c_scaled),
    """)
    v = Var()
    assert [deref(v) for _ in call("scaled", v, module=m.__dict__["$module"])] == [20]


def test_plusplus_rhs_comprehension_target_matching_constant_shape_is_not_flagged(tmp_path):
    """Same exemption as the ordinary ++() escape: a comprehension's own loop
    variable is locally bound, not a reference to any module global, even
    when it happens to be constant-shaped."""
    m = _load(tmp_path, "d4", """
        -constant_value(c_total, ++sum((c_item for c_item in range(5))))
        total(++c_total),
    """)
    v = Var()
    assert [deref(v) for _ in call("total", v, module=m.__dict__["$module"])] == [10]


def test_a_free_name_in_a_clause_escape_fails_when_the_clause_runs(tmp_path):
    """The clause-body counterpart of the RHS case above, and it is the one
    place the diagnostic genuinely got LATER rather than merely different.

    A ``++`` escape in a clause body is a thunk, so the module loads and the
    NameError arrives when the goal is called. That is the deal every other
    name in a ``++`` escape already had; a constant is no longer special
    enough to be checked, because nothing distinguishes its spelling.
    """
    m = _load(tmp_path, "e", "area(R, A) <- (A is ++(c_pi * R))\n")
    v = Var()
    with pytest.raises(NameError, match="c_pi"):
        list(call("area", 2.0, v, module=m.__dict__["$module"]))


def test_constant_usable_inside_arrow_lambda_body(tmp_path):
    """CRITICAL regression: the arrow-lambda sub-transformer used to be
    built with no constants=, so it always got the default frozenset() and
    any declared constant referenced inside a lambda body (the
    ``call_goal((X <- (body)), ...)`` form) fell through to the
    undeclared-constant SyntaxError even though it was properly declared.
    Loading must succeed AND the folded value must actually be used at solve
    time — not just silently accepted — so this checks both a passing and a
    failing comparison against the same declared threshold."""
    m = _load(tmp_path, "m", """
        -constant_value(c_k, 5)
        p(R) <- call_goal((X <- (X > ++c_k)), R)
    """)
    module = m.__dict__["$module"]
    assert list(call("p", 7, module=module))       # 7 > 5: folded value used, solves
    assert list(call("p", 3, module=module)) == []  # 3 > 5: same fold, correctly fails


def test_the_retired_keyword_directive_says_what_replaced_it(tmp_path):
    """``-constants(name = value, ...)`` is retired in favour of the
    -constant_value family. Both the bare and the parenthesised spellings
    reach the same message, so a file written the old way is told what to
    write rather than failing on argument shape."""
    for source in ("-constants\np(X) <- (X == 1)\n",
                   "-constants(pi = 3.14)\np(X) <- (X == 1)\n"):
        with pytest.raises(SyntaxError, match="-constant_value"):
            _load(tmp_path, "e3", source)


def test_the_directive_family_rejects_a_wrong_argument_count(tmp_path):
    with pytest.raises(SyntaxError, match="takes 2 arguments"):
        _load(tmp_path, "e4", "-constant_value(pi)\np(X) <- (X == 1)\n")
    with pytest.raises(SyntaxError, match="takes 3 arguments"):
        _load(tmp_path, "e5", "-constant_number_units(f, 1)\np(X) <- (X == 1)\n")


def test_the_units_form_refuses_something_that_is_not_a_unit(tmp_path):
    with pytest.raises(SyntaxError, match="not a unit expression"):
        _load(tmp_path, "e6",
              "-constant_number_units(f, 1, \"euro\")\np(X) <- (X == 1)\n")


def test_unground_rhs_raises_at_load(tmp_path):
    from clausal.logic.constants import ConstantNotGroundError
    with pytest.raises(ConstantNotGroundError):
        _load(tmp_path, "f", """
            -constant_value(c_v, ++__import__('clausal.logic.variables', fromlist=['Var']).Var())
            p(++c_v),
        """)


def test_structured_list_constant(tmp_path):
    m = _load(tmp_path, "s1", """
        -constant_value(c_codes, ['au', 'al', 'za'])
        codes(X) <- (X is ++c_codes)
    """)
    v = Var()
    assert [deref(v) for _ in call("codes", v, module=m.__dict__["$module"])] == \
        [['au', 'al', 'za']]


def test_structured_tuple_constant(tmp_path):
    m = _load(tmp_path, "s2", """
        -constant_value(c_pair, (1, 2))
        pair(X) <- (X is ++c_pair)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("pair", v, module=m.__dict__["$module"])]
    assert result == (1, 2)
    assert isinstance(result, tuple)


def test_structured_set_constant(tmp_path):
    from clausal.terms import SetTerm
    m = _load(tmp_path, "s3", """
        -private([red, green])
        -constant_value(c_flags, {red, green})
        flags(X) <- (X is ++c_flags)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("flags", v, module=m.__dict__["$module"])]
    assert isinstance(result, SetTerm)
    assert len(result) == 2
    assert m.__dict__["red"] in result and m.__dict__["green"] in result


def test_structured_dict_constant(tmp_path):
    from clausal.terms import DictTerm
    m = _load(tmp_path, "s4", """
        -private([mn, mx])
        -constant_value(c_limits, {mn: 1, mx: 99})
        limits(X) <- (X is ++c_limits)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("limits", v, module=m.__dict__["$module"])]
    assert isinstance(result, DictTerm)
    assert result[m.__dict__["mn"]] == 1
    assert result[m.__dict__["mx"]] == 99


def test_structured_rhs_nesting_and_mixing(tmp_path):
    """A structured RHS mixes a prior constant, arithmetic over it, a
    declared atom, a functor call, and a nested list — all inside one
    list — exactly the "nested arbitrarily" requirement."""
    m = _load(tmp_path, "s5", """
        -module(s5, [point(X, Y)])
        -private([tag])
        -constant_value(c_base, 10)
        -constant_value(c_all, [c_base * 2, tag, point(1, 2), [3, 4]])
        got(X) <- (X is ++c_all)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("got", v, module=m.__dict__["$module"])]
    assert result[0] == 20
    assert result[1] == m.__dict__["tag"]
    # P3-2 Task 2 (THE FLIP, R6): ``Point`` is a data functor, so the
    # constant's functor value is the cell ``("Point", 1, 2)`` -- slots, not
    # attributes.
    assert result[2] == ("point", 1, 2)
    assert result[3] == [3, 4]


def test_structured_functor_constant_declared_above_works(tmp_path):
    """-module(m, [point(X, Y)]) precedes -constants: the emitted functor
    class statement executes first (source order), so point is already a
    bound module global by the time the -constants assignment runs."""
    m = _load(tmp_path, "s6", """
        -module(s6, [point(X, Y)])
        -constant_value(c_origin, point(0, 0))
        origin(X) <- (X is ++c_origin)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("origin", v, module=m.__dict__["$module"])]
    # R6: a cell, as in test_structured_rhs_nesting_and_mixing above.
    assert result == ("point", 0, 0)


def test_structured_functor_constant_undeclared_functor_is_syntax_error(tmp_path):
    """Nothing above -constants declares point (no -module/-private/-dynamic,
    no import) — a located, remedy-bearing SyntaxError, not a NameError at
    exec time and not a silently-wrong Call-node embedding."""
    with pytest.raises(SyntaxError, match="not a declared functor") as exc_info:
        _load(tmp_path, "s7", "-constant_value(c_p, point(0, 0))\np(X) <- (X is 1)\n")
    exc = exc_info.value
    assert exc.filename == str(tmp_path / "s7.clausal")
    assert exc.lineno == 1


def test_structured_rhs_dict_splat_rejected_and_located(tmp_path):
    with pytest.raises(SyntaxError, match="dict-splat") as exc_info:
        _load(tmp_path, "s7b", "-constant_value(c_d, {**{1: 2}})\np(X) <- (X is 1)\n")
    exc = exc_info.value
    assert exc.filename == str(tmp_path / "s7b.clausal")
    assert exc.lineno == 1


def test_structured_rhs_generic_unsupported_shape_is_located(tmp_path):
    """The final fallthrough (an RHS shape none of the dedicated branches
    handle, e.g. a comparison expression) is a located SyntaxError too."""
    with pytest.raises(SyntaxError, match="unsupported RHS") as exc_info:
        _load(tmp_path, "s7c", "-constant_value(c_x, 1 < 2)\np(X) <- (X is 1)\n")
    exc = exc_info.value
    assert exc.filename == str(tmp_path / "s7c.clausal")
    assert exc.lineno == 1


def test_structured_rhs_logic_var_rejected(tmp_path):
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "s8", "-constant_value(c_l, [1, X, 3])\np(Y) <- (Y is 1)\n")
    exc = exc_info.value
    assert "logic-variable" in str(exc)
    assert exc.filename == str(tmp_path / "s8.clausal")
    assert exc.lineno == 1


def test_structured_rhs_anonymous_var_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="logic-variable"):
        _load(tmp_path, "s9", "-constant_value(c_l, [1, _, 3])\np(X) <- (X is 1)\n")


def test_structured_rhs_plusplus_element(tmp_path):
    """A ++() escape is legal as an ELEMENT inside a structured RHS — it
    falls out naturally because container branches recurse through the
    same _transform_constant_rhs that already has the ++ branch."""
    m = _load(tmp_path, "s10", """
        -constant_value(c_l, [1, ++(2 + 3), 3])
        got(X) <- (X is ++c_l)
    """)
    v = Var()
    assert [deref(v) for _ in call("got", v, module=m.__dict__["$module"])] == \
        [[1, 5, 3]]


def test_structured_constant_module_global_and_reflection_registry_share_object(tmp_path):
    """"Share, don't copy": the module global and the module_constant/3
    registry entry are the SAME object, not equal copies. (A per-invocation
    CLAUSE solution does NOT preserve identity across use sites — the
    compiler constant-propagates any known-bound global's value into fresh
    construction code at predicate-compile time, a pre-existing behavior
    that applies to any bound global, not something -constants controls —
    so identity is pinned at the one place this codebase actually promises
    it: the constant's own storage.)"""
    m = _load(tmp_path, "s11", "-constant_value(c_l, [1, 2, 3])\n")
    assert m.__dict__["c_l"] is m.__dict__["$module"].constants["c_l"]


def test_structured_list_constant_mutation_via_plusplus_raises_typeerror(tmp_path):
    m = _load(tmp_path, "s12", """
        -constant_value(c_l, [1, 2, 3])
        bad(X) <- (X is ++(c_l.append(4)))
    """)
    v = Var()
    with pytest.raises(TypeError, match="frozen constant"):
        list(call("bad", v, module=m.__dict__["$module"]))
    # Loudly failed, not silently mutated.
    assert m.__dict__["c_l"] == [1, 2, 3]


def test_structured_dict_constant_mutation_via_plusplus_raises_typeerror(tmp_path):
    m = _load(tmp_path, "s13", """
        -constant_value(c_d, {'k': 1})
        bad(X) <- (X is ++(c_d.data.__setitem__("k", 2)))
    """)
    v = Var()
    with pytest.raises(TypeError, match="frozen constant"):
        list(call("bad", v, module=m.__dict__["$module"]))
    assert m.__dict__["c_d"].data["k"] == 1


def test_structured_dict_constant_ior_mutation_raises_typeerror(tmp_path):
    """dict.__ior__ (the ``|=`` operator) mutates in place — a distinct
    code path from __setitem__, and easy to miss when blocking mutators."""
    m = _load(tmp_path, "s13b", """
        -constant_value(c_d, {'a': 1})
        bad(X) <- (X is ++(c_d.data.__ior__({"b": 2})))
    """)
    v = Var()
    with pytest.raises(TypeError, match="frozen constant"):
        list(call("bad", v, module=m.__dict__["$module"]))
    assert m.__dict__["c_d"].data == {"a": 1}
    assert m.__dict__["$module"].constants["c_d"].data == {"a": 1}


def test_plusplus_set_constant_mutation_via_plusplus_raises_typeerror(tmp_path):
    """A ++()-escape-built raw Python set (not a source-level {...} set
    literal, which lowers to the already-immutable SetTerm instead) goes
    through the same freeze pass and is protected the same way."""
    m = _load(tmp_path, "s14", """
        -constant_value(c_s, ++set([1, 2, 3]))
        bad(X) <- (X is ++(c_s.add(4)))
    """)
    v = Var()
    with pytest.raises(TypeError, match="frozen constant"):
        list(call("bad", v, module=m.__dict__["$module"]))


def test_structured_set_literal_constant_is_already_immutable_by_construction(tmp_path):
    """A source-level {...} set literal lowers to SetTerm (frozenset-backed,
    no public mutator at all) — freezing has nothing to do here."""
    m = _load(tmp_path, "s15", "-private([tag])\n-constant_value(c_s, {tag})\n")
    value = m.__dict__["c_s"]
    assert not hasattr(value, "add") and not hasattr(value, "discard")


def test_clause_solution_list_constant_is_frozen_not_just_the_global(tmp_path):
    """DESIGNER RULING (review round 1, finding #2): freezing must survive
    into every clause-body RECONSTRUCTION of the constant, not only the
    module-global-held original — under tabling/answer-caching a
    reconstruction can be shared across consumers, where mutability would
    let one consumer corrupt every other consumer's view of the same
    cached answer."""
    from clausal.logic.constants import _FrozenList
    m = _load(tmp_path, "s16b", """
        -constant_value(c_l, [1, 2, 3])
        get(X) <- (X is ++c_l)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("get", v, module=m.__dict__["$module"])]
    assert isinstance(result, _FrozenList)
    with pytest.raises(TypeError, match="frozen constant"):
        result.append(99)


def test_clause_solution_dict_constant_backing_is_frozen(tmp_path):
    from clausal.logic.constants import _FrozenDict
    m = _load(tmp_path, "s16c", """
        -constant_value(c_d, {'k': 1})
        get(X) <- (X is ++c_d)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("get", v, module=m.__dict__["$module"])]
    assert isinstance(result.data, _FrozenDict)
    with pytest.raises(TypeError, match="frozen constant"):
        result.data["k"] = 2


def test_mutable_copy_escape_route_via_deepcopy(tmp_path):
    """The documented way to get a mutable working copy of a structured
    constant: copy.deepcopy (or list()/dict()/set() for a shallow one)
    returns a PLAIN, unfrozen container that can be freely mutated,
    leaving the constant itself untouched."""
    import copy
    from clausal.logic.constants import _FrozenList
    m = _load(tmp_path, "s16d", "-constant_value(c_l, [1, 2, 3])\n")
    original = m.__dict__["c_l"]
    working_copy = copy.deepcopy(original)
    assert type(working_copy) is list
    working_copy.append(4)
    assert working_copy == [1, 2, 3, 4]
    # The original constant is untouched and still frozen.
    assert original == [1, 2, 3]
    assert isinstance(original, _FrozenList)
    with pytest.raises(TypeError, match="frozen constant"):
        original.append(99)


def test_frozen_containers_pickle_round_trip_to_plain_containers(tmp_path):
    import pickle
    m = _load(tmp_path, "s16e", "-constant_value(c_l, [1, 2, 3])\n")
    original = m.__dict__["c_l"]
    restored = pickle.loads(pickle.dumps(original))
    assert type(restored) is list
    assert restored == [1, 2, 3]
    restored.append(4)  # plain list: mutation just works
    assert restored == [1, 2, 3, 4]


def test_plusplus_frozenset_constant_is_returned_unwrapped(tmp_path):
    """A ++()-escape-built frozenset is already immutable AND hashable —
    _freeze must return it as-is, not wrap it in the mutable-set-derived
    _FrozenSet (which is unhashable, a downgrade)."""
    m = _load(tmp_path, "s16f", "-constant_value(c_fs, ++frozenset({1, 2}))\n")
    value = m.__dict__["c_fs"]
    assert type(value) is frozenset
    assert value == frozenset({1, 2})
    hash(value)  # must not raise


def test_true_false_undefined_as_constant_values(tmp_path):
    """Truth-value aliases fold in a -constants RHS the same way they do
    in ordinary term position — ``true``/``false``/``undefined`` are legal
    RHS spellings, not just their canonical True/False/Undefined forms."""
    from clausal.terms import Undefined
    m = _load(tmp_path, "s16g", """
        -constant_value(c_b, true)
        -constant_value(c_f, false)
        -constant_value(c_u, undefined)
        got_b(X) <- (X is ++c_b)
        got_f(X) <- (X is ++c_f)
        got_u(X) <- (X is ++c_u)
    """)
    module = m.__dict__["$module"]
    v = Var()
    assert [deref(v) for _ in call("got_b", v, module=module)] == [True]
    v = Var()
    assert [deref(v) for _ in call("got_f", v, module=module)] == [False]
    v = Var()
    assert [deref(v) for _ in call("got_u", v, module=module)] == [Undefined]


def test_frozen_list_unifies_with_equal_plain_list_literal(tmp_path):
    """Unification behavior of a frozen container is identical to a
    literal: structural equality, not identity."""
    m = _load(tmp_path, "s16", """
        -constant_value(c_l, [1, 2, 3])
        matches(X) <- (++c_l is [X, 2, 3])
    """)
    v = Var()
    assert [deref(v) for _ in call("matches", v, module=m.__dict__["$module"])] == [1]


def test_multiple_constants_directives(tmp_path):
    """Two -constants directives in one file; the second references the
    first's constant. (Already worked pre-2026-08-25 — pinned directly.)"""
    m = _load(tmp_path, "s17", """
        -constant_value(c_base, 10)
        -constant_value(c_double, c_base * 2)
        got(X) <- (X is ++c_double)
    """)
    v = Var()
    assert [deref(v) for _ in call("got", v, module=m.__dict__["$module"])] == [20]


def test_module_export_list_may_list_a_constant_name(tmp_path):
    """It is not a rejection any more: the listing declares the ATOM, the
    declaration binds the VALUE, and the two coexist. -module used to refuse
    a constant-shaped export outright."""
    m = _load(tmp_path, "h",
              "-module(h, [c_pi])\n-constant_value(c_pi, 3.14)\n")
    assert m.c_pi == 3.14


def test_non_constant_shaped_declaration_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="constant name"):
        _load(tmp_path, "i", "-constant_value(PI, 3.14)\np(X) <- (X == 1)\n")


def test_comprehension_target_matching_constant_shape_is_not_flagged(tmp_path):
    """A comprehension's own loop variable is locally bound, not a reference
    to any module global — even when it happens to be constant-shaped. The
    undeclared-constant check inside a ``++()`` escape must see past a
    Store-context binding, not just any Name node of the right shape."""
    m = _load(tmp_path, "j", """
        total(R, T) <- (T is ++(sum(c_item for c_item in range(int(R)))))
    """)
    v = Var()
    results = [deref(v) for _ in call("total", 5, v, module=m.__dict__["$module"])]
    assert results == [10]


def test_walrus_target_matching_constant_shape_is_not_flagged(tmp_path):
    """Same as the comprehension case, for a walrus target inside a
    ``++()`` escape."""
    m = _load(tmp_path, "k", """
        doubled(R, T) <- (T is ++((c_tmp := int(R) * 2) + c_tmp))
    """)
    v = Var()
    results = [deref(v) for _ in call("doubled", 3, v, module=m.__dict__["$module"])]
    assert results == [12]


def test_import_constant_direct(tmp_path):
    _load(tmp_path, "own1", "-constant_value(c_pi, 3.14159)\npi(++c_pi),\n")
    m = _load(tmp_path, "use1", """
        -import_from(tc_own1, [c_pi])
        twopi(X) <- (X is ++(c_pi * 2))
    """)
    v = Var()
    [x] = [deref(v) for _ in call("twopi", v, module=m.__dict__["$module"])]
    assert abs(x - 6.28318) < 1e-4


def test_import_constant_alias(tmp_path):
    _load(tmp_path, "own2", "-constant_value(c_pi, 3.14159)\n")
    m = _load(tmp_path, "use2", """
        -import_from(tc_own2, [alias(c_pi, c_mypi)])
        p(c_mypi),
    """)
    v = Var()
    assert [deref(v) for _ in call("p", v, module=m.__dict__["$module"])] == [3.14159]


def test_qualified_constant_access(tmp_path):
    _load(tmp_path, "own4", "-constant_value(c_pi, 3.14159)\n")
    m = _load(tmp_path, "use4", """
        -import_module(tc_own4)
        p(X) <- (X is ++(tc_own4.c_pi + 0))
        q(tc_own4.c_pi),
    """)
    v = Var()
    assert [deref(v) for _ in call("p", v, module=m.__dict__["$module"])] == \
        [3.14159]
    # Bare-term qualified access (no ``++`` escape): the dotted chain
    # already lowers to a plain LoadAttr node — the SAME mechanism that
    # already supports a qualified atom reference like ``currency.euro``
    # in value position (see term_to_ast.py's ``_dotted_name_from_loadattr``
    # handling). No visit_Attribute change was needed; this assertion pins
    # that the existing general mechanism covers constants too.
    assert [deref(v) for _ in call("q", v, module=m.__dict__["$module"])] == \
        [3.14159]


def test_import_constant_direct_collides_with_local_constant_rejected(tmp_path):
    _load(tmp_path, "own7", "-constant_value(c_pi, 3.14159)\n")
    with pytest.raises(SyntaxError, match="already bound"):
        _load(tmp_path, "use7", """
            -constant_value(c_pi, 3)
            -import_from(tc_own7, [c_pi])
        """)


def test_a_private_listing_declares_the_atom_and_leaves_the_value(tmp_path):
    """-private used to accept a constant-shaped name as documentation, a
    recorded no-op. It declares the ATOM now, which is a stronger and more
    useful reading -- and the constant keeps the module global."""
    m = _load(tmp_path, "pdoc1", """
        -private([helper, c_pi])
        -constant_value(c_pi, 3.14159)
        helper,
        q(X) <- (X is ++c_pi)
    """)
    v = Var()
    assert [deref(v) for _ in call("q", v, module=m.__dict__["$module"])] == \
        [3.14159]
    assert m.c_pi == 3.14159


def test_private_declaration_no_longer_carries_a_constants_list():
    """The other half of the dropped behaviour: PrivateDeclaration.constants
    is gone, so a -private directive reifies with one argument."""
    from clausal.reflection import reify_source, ModuleDirective, is_v, vfield
    items = reify_source("-private([helper, other])\nhelper,\nother,\n")
    (priv,) = [d for d in items
               if is_v(d, ModuleDirective) and vfield(d, "name") == "private"]
    assert priv.args == [["helper", "other"]]


def test_the_export_listing_works_in_either_order(tmp_path):
    """The declaration before the listing, and after: whichever runs second
    must not bind over the other."""
    m = _load(tmp_path, "pdoc3", """
        -constant_value(c_pi, 3.14)
        -module(pdoc3, [c_pi])
    """)
    assert m.c_pi == 3.14


def test_constants_rhs_can_construct_an_imported_functor():
    """P3-2 Task 2 (THE FLIP, R6): a ``-constants`` RHS that constructs a
    functor this module IMPORTS rather than declares.

    The importer mints no class for an imported functor, and post-R6 the
    owner's name is its interned spelling by the time the import runs — so
    the RHS's old direct ``wrap(...)`` call raised
    ``TypeError: 'str' object is not callable`` from the ``-constants`` line
    and the module failed to LOAD.  The construction is routed through
    ``constants.constant_functor_term`` now, which decides on the binding
    shape at exec time and builds the cell the rest of the module speaks.

    Nesting is covered too (``[wrap(pair(3, 4))]``): the recursion has to
    reach an imported functor inside a structured RHS, not only at the top.
    """
    import pathlib

    from clausal.import_hook import _load_module

    fixtures = pathlib.Path(__file__).parent / "fixtures"
    _load_module("tests.fixtures.const_functor_owner",
                 str(fixtures / "const_functor_owner.clausal"))
    mod = _load_module("tests.fixtures.const_functor_importer",
                       str(fixtures / "const_functor_importer.clausal"))
    lm = mod.__dict__["$module"]

    def one(goal):
        v = Var()
        return [deref(v) for _ in call(goal, v, module=lm)]

    assert one("wrapped") == [("wrap", mint("inner"))]
    assert one("paired") == [("pair", 1, 2)]
    assert one("nested") == [[("wrap", ("pair", 3, 4))]]


def _load_const_functor_owner():
    import pathlib

    from clausal.import_hook import _load_module

    fixtures = pathlib.Path(__file__).parent / "fixtures"
    return _load_module("tests.fixtures.const_functor_owner",
                        str(fixtures / "const_functor_owner.clausal"))


def test_constants_rhs_functor_over_arity_is_a_load_error(tmp_path):
    """The runtime placer reports an over-arity construction the way the
    compile-time one does, naming the functor and its declared fields.

    Asked of an IMPORTED functor deliberately: that is the branch with no
    class to construct through, so it is the placer in
    ``constants.constant_functor_term`` answering rather than
    ``PredicateMeta.__call__`` (which still answers, with its own
    ``ClausalTermConstructionError``, wherever a class does exist).
    """
    _load_const_functor_owner()
    with pytest.raises(SyntaxError, match=r"wrap/1"):
        _load(tmp_path, "cfo1", """
            -import_from(tests.fixtures.const_functor_owner, [wrap])
            -constant_value(c_bad, wrap(1, 2))
            p(X) <- (X is ++c_bad)
        """)


def test_constants_rhs_functor_unknown_field_is_a_load_error(tmp_path):
    """Still a load error naming the functor, but the KEYWORD LINT speaks
    first now (2026-09-19: a term is built positionally), so the arity in the
    message is the WRITTEN one -- ``pair/1`` for ``pair(NOPE=1)`` -- not the
    declared ``pair/2`` the field check would have named."""
    _load_const_functor_owner()
    with pytest.raises(SyntaxError, match=r"pair/1"):
        _load(tmp_path, "cfo2", """
            -import_from(tests.fixtures.const_functor_owner, [pair])
            -constant_value(c_bad, pair(NOPE=1))
            p(X) <- (X is ++c_bad)
        """)


def test_constants_rhs_functor_partial_construction_is_a_load_error(tmp_path):
    """A constant must be GROUND, so an omitted slot -- which would backfill
    with a fresh Var in a clause body -- is named as the error it is."""
    _load_const_functor_owner()
    with pytest.raises(SyntaxError, match=r"unfilled"):
        _load(tmp_path, "cfo3", """
            -import_from(tests.fixtures.const_functor_owner, [pair])
            -constant_value(c_bad, pair(1))
            p(X) <- (X is ++c_bad)
        """)


def test_truth_value_spelling_as_a_constant_dict_key(tmp_path):
    """``undefined`` is a legal ``-constants`` dict key, both spellings.

    ``_transform_constant_dict_key`` is the ``-constants`` twin of
    ``_visit_dict_key``, and it was missed when that one moved to the
    EFFECTIVE variable reading.  ``Undefined`` is capital-initial, so the
    lexical rule called it a variable, the ``$intern_atom`` branch was
    skipped, and the directive refused with "``Undefined`` is a
    logic-variable name".  The alias rewrite just above that site turns a
    lowercase ``undefined`` key into ``Name("Undefined")`` first, so BOTH
    spellings were affected -- and the path's own docstring promises it
    handles the truth-value spellings.
    """
    from clausal.terms import DictTerm
    built = {}
    for tag, key in (("lower", "undefined"), ("canon", "Undefined")):
        m = _load(tmp_path, f"tvkey_{tag}", f"""
            -constant_value(c_d, {{{key}: 1}})
            lookup(X) <- (X is ++c_d)
        """)
        v = Var()
        [result] = [deref(v) for _ in call("lookup", v,
                                           module=m.__dict__["$module"])]
        assert isinstance(result, DictTerm), (tag, result)
        built[tag] = result
    # WHICH KEY, not merely that a dict was built -- the bug was about the key
    # object, and an isinstance check passes with the wrong one.  The
    # invariant is the sibling comment's in ``_visit_dict_key``: the two
    # spellings must not build dicts that fail to unify.
    assert list(built["lower"].keys()) == list(built["canon"].keys()), built
    # And the same dict written in an ordinary CLAUSE agrees, which is the
    # cross-path half -- ``-constants`` has its own key transform, and the
    # two must not drift.
    m2 = _load(tmp_path, "tvkey_clause", """
        lookup(X) <- (X is {undefined: 1})
    """)
    v = Var()
    [from_clause] = [deref(v) for _ in call("lookup", v,
                                            module=m2.__dict__["$module"])]
    assert list(from_clause.keys()) == list(built["lower"].keys()), (
        from_clause, built["lower"])


def test_declared_atom_constant_dict_key_still_works(tmp_path):
    """The control: an ordinary declared atom key is unaffected."""
    from clausal.terms import DictTerm
    m = _load(tmp_path, "tvkey_ctl", """
        -private([alpha])
        -constant_value(c_d, {alpha: 1})
        lookup(X) <- (X is ++c_d)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("lookup", v, module=m.__dict__["$module"])]
    assert isinstance(result, DictTerm)


# ── The lowercase spelling (2026-09-11) ───────────────────────────────────────
#
# A constant is spelled like an atom now and its value is reached with the
# explicit ``++name`` escape.  See
# docs/superpowers/plans/2026-09-11-retire-underscore-constant-spelling.md.


def test_lowercase_constant_name_is_accepted(tmp_path):
    """A constant is spelled like an atom now: lowercase, no underscores."""
    m = _load(tmp_path, "c_lower", """
        -constant_value(max_fine, 5000)
    """)
    assert m.max_fine == 5000


def test_underscored_constant_spelling_is_refused(tmp_path):
    """The retired spelling fails loudly, and the message says what to write."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "c_old", """
            -constant_value(_MAX_FINE_, 5000)
        """)
    message = str(excinfo.value)
    assert "_MAX_FINE_" in message
    assert "max_fine" in message, "the message must offer the new spelling"


def test_capital_initial_constant_name_is_refused(tmp_path):
    """A capital initial is a logic variable everywhere now, with no
    exceptions -- so it cannot name a constant either."""
    with pytest.raises(SyntaxError, match="capital-initial"):
        _load(tmp_path, "c_caps", """
            -constant_value(MaxFine, 5000)
        """)


def test_underscore_led_constant_name_is_refused(tmp_path):
    """The other half of the variable rule, so the two tests together pin
    the constant class as its exact complement."""
    with pytest.raises(SyntaxError, match="underscore-led"):
        _load(tmp_path, "c_under", """
            -constant_value(_max_fine, 5000)
        """)


def test_an_uncased_script_can_name_a_constant(tmp_path):
    """The constant class is the COMPLEMENT of the variable rule, not
    ``islower()``.  An uncased script has no lowercase form either, so an
    ``islower()`` test would refuse this name while offering no alternative
    -- it is not a variable, so no leading underscore would help."""
    m = _load(tmp_path, "c_jp", """
        -constant_value(円周率, 3.14159)
    """)
    assert getattr(m, "円周率") == 3.14159


def test_constant_is_reached_through_the_escape(tmp_path):
    """The whole point of the lowercase spelling: ++name retrieves.

    Both a succeeding and a failing comparison, so the test cannot pass by
    the value simply being absent -- a missing global raises rather than
    quietly answering zero times, but a WRONG value would satisfy only one
    of the two.
    """
    m = _load(tmp_path, "c_escape", """
        -module(c_escape, [big/1, small/1, thing])
        -constant_value(max_fine, 5000)

        big(thing) <- (++max_fine > 4000)
        small(thing) <- (++max_fine > 6000)
    """)
    assert len(list(call("big", m.thing, module=m.__dict__["$module"]))) == 1
    assert len(list(call("small", m.thing, module=m.__dict__["$module"]))) == 0


def test_a_bare_name_is_the_atom_and_the_escape_is_the_value(tmp_path):
    """The two spellings differ in BINDING TIME, and both work.

    A bare reference to a bound module global is folded into the clause term
    when the clause statement executes; ``++name`` builds a thunk that
    resolves the global at solve time.  Rebinding the global afterwards
    therefore moves one answer and not the other -- which is the whole
    reason ``++name`` is the spelling to reach for: it is what makes a
    constant late-bound, so that changing it in ONE place changes every use.

    This is not special to ``-constants``: it is what a bare reference to any
    bound Python global in a seam already does.  See
    ``compiler_v2._process_bare_atom_refs``, which trusts an already-bound
    name unconditionally.
    """
    m = _load(tmp_path, "c_bind", """
        -module(c_bind, [bare/1, escaped/1, max_fine])
        -constant_value(max_fine, 5000)

        bare(max_fine),
        escaped(X) <- (X is ++max_fine)
    """)
    mod = m.__dict__["$module"]

    def ask(goal):
        v = Var()
        return [deref(v) for _ in call(goal, v, module=mod)]

    assert ask("bare") == ["max_fine"], "the bare name is the atom"
    assert ask("escaped") == [5000], "++ is the value"
    # And the escape is a LOOKUP, not a fold: rebinding the global moves it.
    # The atom cannot move -- it was compiled into the clause as a literal.
    m.max_fine = 9999
    assert ask("bare") == ["max_fine"]
    assert ask("escaped") == [9999], "++ resolves the global at solve time"


def test_a_mistyped_constant_reference_is_the_strict_atoms_error(tmp_path):
    """The undeclared-constant diagnostic is gone with the shape that
    triggered it; a bare name nothing binds is the ordinary strict-atoms
    error, which is uniform with every other undeclared name."""
    with pytest.raises(NameError) as excinfo:
        _load(tmp_path, "c_typo", """
            -module(c_typo, [holds/1])
            -constant_value(max_fine, 5000)

            holds(max_fien),
        """)
    assert "max_fien" in str(excinfo.value)


def test_one_name_is_the_atom_bare_and_the_constant_through_the_escape(tmp_path):
    """The operator's rule, 2026-09-11, and the point of the whole design.

    ``pi`` written bare is the ATOM; ``++pi`` is the constant's value. One
    name carries both readings in one file with no conflict, and the atom is
    the SAME atom ``global_atom/2`` yields -- so nothing about writing the
    constant makes the atom a second-class spelling.

    Two things in ``compiler_v2`` are what make it true, and either one
    regressing shows up here: the -module atom listing must not bind over
    the constant's module global, and a DECLARED atom must compile to its
    cell literal rather than reading that global.
    """
    m = _load(tmp_path, "c_both", """
        -module(c_both, [constant_is/1, atom_is/1, agrees/0, pi])
        -constant_value(pi, 5000)

        constant_is(X) <- (X is ++pi)
        atom_is(pi),
        agrees <- (global_atom("pi", A), atom_is(A))
    """)
    mod = m.__dict__["$module"]

    def ask(goal):
        v = Var()
        return [deref(v) for _ in call(goal, v, module=mod)]

    assert ask("constant_is") == [5000], "++pi is the value"
    assert ask("atom_is") == ["pi"], "bare pi is the atom"
    assert len(list(call("agrees", module=mod))) == 1, (
        "the bare form must be the same atom global_atom/2 yields")


def test_the_two_readings_hold_in_either_declaration_order(tmp_path):
    """The constant declared before the -module listing, and after: neither
    binding may win by being later in the file."""
    m = _load(tmp_path, "c_both2", """
        -constant_value(pi, 5000)
        -module(c_both2, [constant_is/1, atom_is/1, pi])

        constant_is(X) <- (X is ++pi)
        atom_is(pi),
    """)
    mod = m.__dict__["$module"]

    def ask(goal):
        v = Var()
        return [deref(v) for _ in call(goal, v, module=mod)]

    assert ask("constant_is") == [5000]
    assert ask("atom_is") == ["pi"]


def test_a_private_atom_listing_works_the_same_way(tmp_path):
    """-private binds the atom exactly as -module does, and must leave the
    constant's global alone in the same way."""
    m = _load(tmp_path, "c_both3", """
        -module(c_both3, [constant_is/1, atom_is/1])
        -private([pi])
        -constant_value(pi, 5000)

        constant_is(X) <- (X is ++pi)
        atom_is(pi),
    """)
    mod = m.__dict__["$module"]

    def ask(goal):
        v = Var()
        return [deref(v) for _ in call(goal, v, module=mod)]

    assert ask("constant_is") == [5000]
    assert ask("atom_is") == ["pi"]


def test_a_constant_name_used_bare_must_still_be_declared_as_an_atom(tmp_path):
    """Declaring a constant does NOT declare the atom.

    A conservative reading of the rule, flagged as such: ``-constant_value``
    could reasonably imply the atom, but starting strict leaves that
    relaxation available later, while starting permissive could not be
    tightened without breaking files. The diagnostic is the ordinary
    strict-atoms one, which says exactly what to add.
    """
    with pytest.raises(NameError, match="pi"):
        _load(tmp_path, "c_undeclared", """
            -module(c_undeclared, [atom_is/1])
            -constant_value(pi, 5000)

            atom_is(pi),
        """)


def test_distinct_names_do_not_interact(tmp_path):
    """The negative control for the pair above: a constant and an unrelated
    atom must not need each other, so a check that refused or accepted
    everything would show here."""
    m = _load(tmp_path, "c_noclash", """
        -module(c_noclash, [holds/1, other]) 
        -constant_value(max_fine, 5000)

        holds(other),
    """)
    assert m.max_fine == 5000


def test_an_imported_constant_is_reached_through_the_escape(tmp_path):
    """An imported constant takes the ordinary imported-name path now.

    The importer cannot tell a constant from an atom or a predicate in
    another module -- that is the OWNER's fact and the name no longer says
    so -- but the emitted ImportFrom binds the owner's module global here,
    which is all ``++name`` needs.
    """
    _load(tmp_path, "own_c1", "-constant_value(max_fine, 5000)\n")
    m = _load(tmp_path, "use_c1", """
        -module(use_c1, [big/1, small/1, thing])
        -import_from(tc_own_c1, [max_fine])

        big(thing) <- (++max_fine > 4000)
        small(thing) <- (++max_fine > 6000)
    """)
    mod = m.__dict__["$module"]
    assert len(list(call("big", m.thing, module=mod))) == 1
    assert len(list(call("small", m.thing, module=mod))) == 0


def test_an_imported_constant_under_an_alias(tmp_path):
    """The alias form carries the value across too."""
    _load(tmp_path, "own_c2", "-constant_value(max_fine, 5000)\n")
    m = _load(tmp_path, "use_c2", """
        -module(use_c2, [limit/1])
        -import_from(tc_own_c2, [alias(max_fine, cap)])

        limit(X) <- (X is ++cap)
    """)
    v = Var()
    assert [deref(v) for _ in call("limit", v,
                                   module=m.__dict__["$module"])] == [5000]


def test_a_constant_named_like_the_unused_marker_warns(tmp_path):
    """The name check for the singleton-suppression suffix had to move with
    the spelling: it used to read ``ident[1:-1]``, which assumed the leading
    and trailing underscores were there to strip. Nothing else covered it.
    """
    import warnings as _warnings
    from clausal.lint_warnings import ClausalLintWarning
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        m = _load(tmp_path, "c_unused", """
            -constant_value(item_UNUSED, 3)
        """)
    assert m.item_UNUSED == 3
    messages = [str(w.message) for w in caught
                if issubclass(w.category, ClausalLintWarning)]
    assert any("item_UNUSED" in msg and "_UNUSED" in msg
               for msg in messages), messages


def test_an_ordinary_constant_name_does_not_warn(tmp_path):
    """Negative control: without it the test above passes on a directive
    that warns about every name it is given."""
    import warnings as _warnings
    from clausal.lint_warnings import ClausalLintWarning
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        _load(tmp_path, "c_quiet", """
            -constant_value(item_count, 3)
        """)
    assert not [w for w in caught
                if issubclass(w.category, ClausalLintWarning)
                and "_UNUSED" in str(w.message)]


# ── The -constant_number_units/3 form ──────────────────────────────────────────


def test_units_form_binds_a_quantity(tmp_path):
    """``-constant_number_units(max_fine, 5000, euro)`` binds
    ``max_fine = Quantity(5000, euro)`` -- the unit kept out of the value,
    which is the whole reason the 3-arity form exists.

    The value is the same object the ``5000 (euro)`` annotation sugar builds:
    both lower to ``$Quantity(<value>, <unit>)``.
    """
    m = _load(tmp_path, "cvu", """
        -module(cvu, [cost/1])
        -import_from(european_union, [euro])
        -constant_number_units(max_fine, 5000, euro)

        cost(X) <- (X is ++max_fine)
    """)
    v = Var()
    [q] = [deref(v) for _ in call("cost", v, module=m.__dict__["$module"])]
    assert q == m.max_fine
    # Same shape the annotation sugar produces for the same source pair.
    sugar = _load(tmp_path, "cvu_sugar", """
        -module(cvu_sugar, [cost/1])
        -import_from(european_union, [euro])

        cost(5000 (euro)),
    """)
    v = Var()
    [from_sugar] = [deref(v) for _ in call("cost", v,
                                           module=sugar.__dict__["$module"])]
    assert q == from_sugar, (q, from_sugar)


# ── A declaration must not overwrite an existing binding ──────────────────────


@pytest.mark.parametrize("label,source", [
    ("an import", "-module(m, [q/0])\nimport math\n"
                  "-constant_value(math, 3)\nq <- (1 == 1)\n"),
    # BELOW the declaration on purpose: a def further down the file
    # overwrites it just as surely as one above, so the check cannot be made
    # at the directive's own position.
    ("a def below it", "-module(m, [q/0])\n-constant_value(helper, 3)\n"
                       "def helper(): return 1\nq <- (1 == 1)\n"),
    ("a predicate", "-module(m, [q/0, helper/1])\n-constant_value(helper, 3)\n"
                    "helper(1),\nq <- (1 == 1)\n"),
])
def test_a_constant_may_not_overwrite_an_existing_binding(tmp_path, label,
                                                          source):
    """A constant declaration writes a module global. Left unchecked it
    silently replaces an import, a helper, or a predicate class -- the value
    would be right and every OTHER use of the name would quietly become the
    constant."""
    with pytest.raises(SyntaxError, match="already bound"):
        _load(tmp_path, "ovw", source)


def test_an_atom_of_the_same_name_is_not_an_overwrite(tmp_path):
    """The negative control, and the intended case: sharing the spelling
    with an ATOM is exactly what this design is for, so the guard must be a
    whitelist rather than a plain "is the name bound"."""
    m = _load(tmp_path, "ovw_ok", """
        -module(ovw_ok, [q/1, pi])
        -constant_value(pi, 3.14)

        q(pi),
    """)
    assert m.pi == 3.14


# ── constant_value/2 ──────────────────────────────────────────────────────────


def test_constant_value_2_reflects_a_declaration(tmp_path):
    """``constant_value(Name, Value)`` -- Markus Triska's name for the
    cross-implementation convention. ``Name`` is an ATOM, not a string."""
    m = _load(tmp_path, "cvref", """
        -module(cvref, [look/1, absent/0, enumerate/2, cvref_pi,
                        cvref_missing])
        -constant_value(cvref_pi, 3.14159)

        look(V) <- constant_value(cvref_pi, V)
        absent <- constant_value(cvref_missing, _)
        enumerate(N, V) <- constant_value(N, V)
    """)
    mod = m.__dict__["$module"]
    v = Var()
    assert [deref(v) for _ in call("look", v, module=mod)] == [3.14159]
    assert len(list(call("absent", module=mod))) == 0, (
        "a name nothing declares must fail, not error")
    n, v2 = Var(), Var()
    pairs = [(deref(n), deref(v2))
             for _ in call("enumerate", n, v2, module=mod)]
    assert ("cvref_pi", 3.14159) in pairs, pairs


def test_constant_value_2_reads_the_name_as_an_atom(tmp_path):
    """The NAME POSITION speaks atoms in and atoms out (spec §6.4).

    Written with the double-quoted spelling deliberately: under the engine
    default ``-double_quotes(atom)`` that IS an atom, so it matches -- and
    the same source under ``-double_quotes(chars)`` is a string, which names
    no constant and fails. Both halves asserted, because the first alone
    would pass on an implementation that ignored the argument's type.
    """
    m = _load(tmp_path, "cvref2", """
        -module(cvref2, [by_quoted/0, cvref2_pi])
        -constant_value(cvref2_pi, 3.14159)

        by_quoted <- constant_value("cvref2_pi", _)
    """)
    assert len(list(call("by_quoted", module=m.__dict__["$module"]))) == 1

    chars = _load(tmp_path, "cvref3", """
        -module(cvref3, [by_string/0, cvref3_pi])
        -double_quotes(chars)
        -constant_value(cvref3_pi, 3.14159)

        by_string <- constant_value("cvref3_pi", _)
    """)
    assert len(list(call("by_string", module=chars.__dict__["$module"]))) == 0, (
        "a string names no constant")


# ── constant_number_units/3 ───────────────────────────────────────────────────
#
# Named for what it can hold: only NUMBERS carry units (operator, 2026-09-11),
# which is why it is not `constant_value_units/3`. The directive and the
# predicate share the name, as `-constant_value` and `constant_value/2` do.


def test_constant_number_units_3_gives_the_magnitude_and_the_unit(tmp_path):
    m = _load(tmp_path, "cnu", """
        -module(cnu, [look/2, cnu1_max_fine])
        -import_from(european_union, [euro])
        -constant_number_units(cnu1_max_fine, 5000, euro)

        look(N, U) <- constant_number_units(cnu1_max_fine, N, U)
    """)
    n, u = Var(), Var()
    [(number, units)] = [(deref(n), deref(u)) for _ in
                         call("look", n, u, module=m.__dict__["$module"])]
    assert number == 5000
    assert units == ("euro",), units


def test_a_compound_unit_comes_back_as_a_term(tmp_path):
    """Division and powers survive as structure, so a caller can take the
    units apart rather than parse a string."""
    m = _load(tmp_path, "cnu2", """
        -module(cnu2, [per/2, sq/2, cnu2_speed, cnu2_area])
        -import_from(py.units, [metre, second])
        -constant_number_units(cnu2_speed, 3, metre / second)
        -constant_number_units(cnu2_area, 7, metre ** 2)

        per(N, U) <- constant_number_units(cnu2_speed, N, U)
        sq(N, U) <- constant_number_units(cnu2_area, N, U)
    """)
    mod = m.__dict__["$module"]

    def one(goal):
        n, u = Var(), Var()
        [pair] = [(deref(n), deref(u)) for _ in call(goal, n, u, module=mod)]
        return pair

    assert one("per") == (3, ("/", ("metre",), ("second",)))
    assert one("sq") == (7, ("**", ("metre",), 2))


def test_a_unitless_constant_has_no_units_solution(tmp_path):
    """It has a VALUE but no units, and `constant_value/2` is the predicate
    that relates it. Failing is the ordinary reading of "no such relation" --
    answering with a dimensionless marker would make every constant look
    united."""
    m = _load(tmp_path, "cnu3", """
        -module(cnu3, [plain/1, both/1, cnu3_pi])
        -constant_value(cnu3_pi, 3.14)

        plain(N) <- constant_number_units(cnu3_pi, N, _)
        both(V) <- constant_value(cnu3_pi, V)
    """)
    mod = m.__dict__["$module"]
    v = Var()
    assert [deref(v) for _ in call("plain", v, module=mod)] == []
    v = Var()
    assert [deref(v) for _ in call("both", v, module=mod)] == [3.14], (
        "the negative control: the constant IS there, via constant_value/2")


def test_constant_number_units_3_enumerates_only_united_constants(tmp_path):
    m = _load(tmp_path, "cnu4", """
        -module(cnu4, [enum/3, cnu4_fine, cnu4_plain])
        -import_from(european_union, [euro])
        -constant_number_units(cnu4_fine, 5000, euro)
        -constant_value(cnu4_plain, 3)

        enum(C, N, U) <- constant_number_units(C, N, U)
    """)
    a, b, c = Var(), Var(), Var()
    rows = [(deref(a), deref(b), deref(c)) for _ in
            call("enum", a, b, c, module=m.__dict__["$module"])]
    names = {r[0] for r in rows}
    # Membership, not equality: constant_number_units/3 is program-WIDE (a
    # builtin never sees its calling module), so every united constant any
    # loaded module declared answers here. Unique names keep this test from
    # depending on what else the suite has loaded.
    assert "cnu4_fine" in names
    assert "cnu4_plain" not in names, "a unitless constant is not united"


@pytest.mark.parametrize("value", ["[1, 2]", "'hello'", "{a: 1}", "True"])
def test_only_a_number_may_carry_units(tmp_path, value):
    """The directive is NAMED for this claim, so it enforces it. Without the
    check the message is a raw InvalidOperation/ConversionSyntax from the
    Decimal layer, naming neither the directive nor the value."""
    with pytest.raises(SyntaxError, match="only numbers carry units"):
        _load(tmp_path, "cnu5", f"""
            -module(cnu5, [q/0, a])
            -import_from(european_union, [euro])
            -constant_number_units(x, {value}, euro)

            q <- (1 == 1)
        """)


def test_a_number_still_carries_units(tmp_path):
    """The negative control for the check above: it must not refuse the case
    the directive exists for."""
    m = _load(tmp_path, "cnu6", """
        -import_from(european_union, [euro])
        -constant_number_units(fee, 12.5, euro)
    """)
    assert m.fee.value == 12.5


def test_constant_number_units_3_reports_the_DECLARED_pair(tmp_path):
    """The operator's ruling, 2026-09-11, and the reason it was needed.

    A unit that is not the base of its own dimension rescales to that base,
    so ``30 day`` is STORED as ``Quantity(2592000, second)`` and neither the
    30 nor the ``day`` survives in the value. Reporting the normalised pair
    would make this predicate a lossy view of ``constant_value/2`` instead of
    a second source of information -- and would make it impossible to check
    that a parameter's declared unit matches the unit its NAME claims, since
    every duration comes back as ``second`` whatever was written.

    The two predicates therefore disagree about the number ON PURPOSE. Both
    assertions are here together so neither can be changed without facing
    the other.
    """
    m = _load(tmp_path, "decl", """
        -module(decl, [declared/2, value/1, decl_standstill])
        -import_from(units, [day])
        -constant_number_units(decl_standstill, 30, day)

        declared(N, U) <- constant_number_units(decl_standstill, N, U)
        value(V) <- constant_value(decl_standstill, V)
    """)
    mod = m.__dict__["$module"]

    n, u = Var(), Var()
    [(number, units)] = [(deref(n), deref(u)) for _ in
                         call("declared", n, u, module=mod)]
    assert number == 30, "the DECLARED magnitude, not the rescaled one"
    assert units == ("day",), "the DECLARED unit, not its base"

    v = Var()
    [value] = [deref(v) for _ in call("value", v, module=mod)]
    assert value.value == 2592000, (
        "constant_value/2 is the VALUE view and still normalises")
    assert not hasattr(value, "day")


def test_a_non_rescaling_unit_agrees_between_the_two_predicates(tmp_path):
    """The negative control for the test above: where the unit IS the base of
    its dimension there is nothing to disagree about, so a bug that always
    reported the declared pair and a bug that always reported the normalised
    one would both pass here. That is why the rescaling case is asserted
    separately."""
    m = _load(tmp_path, "agree", """
        -module(agree, [declared/2, value/1, agree_mass])
        -import_from(units, [kilogram])
        -constant_number_units(agree_mass, 7, kilogram)

        declared(N, U) <- constant_number_units(agree_mass, N, U)
        value(V) <- constant_value(agree_mass, V)
    """)
    mod = m.__dict__["$module"]
    n, u = Var(), Var()
    [(number, units)] = [(deref(n), deref(u)) for _ in
                         call("declared", n, u, module=mod)]
    v = Var()
    [value] = [deref(v) for _ in call("value", v, module=mod)]
    assert (number, units) == (7, ("kilogram",))
    assert value.value == 7


# ── constant/1 — the retrieval form ───────────────────────────────────────────
#
# Operator, 2026-09-11: `++name` says "this is Python", which is exactly what a
# constant reference is not. `constant(name)` names the thing being done, the
# parentheses delimit it, and restricting the inside to a single atom means it
# can never be mistaken for a Python expression.


def test_constant_1_retrieves_the_value(tmp_path):
    m = _load(tmp_path, "c1", """
        -module(c1, [big/1, small/1, thing, c1_max])
        -constant_value(c1_max, 5000)

        big(thing) <- (constant(c1_max) > 4000)
        small(thing) <- (constant(c1_max) > 6000)
    """)
    mod = m.__dict__["$module"]
    assert len(list(call("big", m.thing, module=mod))) == 1
    assert len(list(call("small", m.thing, module=mod))) == 0


def test_constant_1_is_late_bound_like_the_escape_it_replaces(tmp_path):
    """Same binding time as ``++name``: a lookup when the goal runs, not a
    fold at clause construction. Rebinding the global moves the answer."""
    m = _load(tmp_path, "c1lb", """
        -module(c1lb, [v/1, c1lb_max])
        -constant_value(c1lb_max, 5000)

        v(X) <- eval_(constant(c1lb_max), X)
    """)
    mod = m.__dict__["$module"]

    def ask():
        x = Var()
        return [deref(x) for _ in call("v", x, module=mod)]

    assert ask() == [5000]
    m.c1lb_max = 9999
    assert ask() == [9999], "late-bound, as ++name was"


def test_constant_1_refuses_a_name_nothing_declares(tmp_path):
    """The improvement over ``++name``: an undeclared constant is a LOAD
    error naming the directive, where the escape deferred to a Python
    NameError when the goal eventually ran."""
    with pytest.raises(SyntaxError, match="constant"):
        _load(tmp_path, "c1u", """
            -module(c1u, [q/0])
            q <- (constant(never_declared) > 1)
        """)


@pytest.mark.parametrize("bad,why", [
    ("constant(a, b)", "two arguments"),
    ("constant()", "no argument"),
    ("constant(1 + 2)", "an expression, not an atom"),
    ("constant('quoted')", "a quoted form, not a bare atom"),
])
def test_constant_1_takes_exactly_one_bare_atom(tmp_path, bad, why):
    """`The thing inside the parentheses should be a single atom` -- so there
    is no shape for which it could be read as a Python expression."""
    with pytest.raises(SyntaxError, match="constant"):
        _load(tmp_path, "c1bad", f"""
            -module(c1bad, [q/0, a, b])
            -constant_value(x, 1)
            q <- ({bad} > 1)
        """)
