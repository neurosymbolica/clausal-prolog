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
        -constants(c_pi = 3.14159)
        area(R, A) <- (A is ++(c_pi * R * R))
    """)
    [a] = _values(m, "area", 2.0)
    assert abs(a - 3.14159 * 4.0) < 1e-9


def test_constant_as_plain_argument(tmp_path):
    m = _load(tmp_path, "b", """
        -constants(c_max = 3)
        limit(c_max),
        got(X) <- limit(X)
    """)
    v = Var()
    results = [deref(v) for _ in call("limit", v, module=m.__dict__["$module"])]
    assert results == [3]


def test_constant_from_prior_constant_and_arithmetic(tmp_path):
    m = _load(tmp_path, "c", """
        -constants(c_base = 10, c_limit = c_base * 4 + 2)
        lim(c_limit),
    """)
    v = Var()
    assert [deref(v) for _ in call("lim", v, module=m.__dict__["$module"])] == [42]


def test_plusplus_rhs(tmp_path):
    m = _load(tmp_path, "d", """
        -constants(c_pi = ++__import__('math').pi)
        pi(c_pi),
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
        _load(tmp_path, "d2", "-constants(c_a = ++(c_b * 2))\np(c_a),\n")


def test_plusplus_rhs_declared_earlier_constant_still_works(tmp_path):
    """A constant declared by an earlier -constants entry IS legal inside a
    later ++ RHS — by exec time it is already a bound module global. Keeps
    the existing passing ``++`` RHS behaviour green alongside the new scan."""
    m = _load(tmp_path, "d3", """
        -constants(c_base = 10, c_scaled = ++(c_base * 2))
        scaled(c_scaled),
    """)
    v = Var()
    assert [deref(v) for _ in call("scaled", v, module=m.__dict__["$module"])] == [20]


def test_plusplus_rhs_comprehension_target_matching_constant_shape_is_not_flagged(tmp_path):
    """Same exemption as the ordinary ++() escape: a comprehension's own loop
    variable is locally bound, not a reference to any module global, even
    when it happens to be constant-shaped."""
    m = _load(tmp_path, "d4", """
        -constants(c_total = ++(sum(c_item for c_item in range(5))))
        total(c_total),
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
        -constants(c_k = 5)
        p(R) <- call_goal((X <- (X > c_k)), R)
    """)
    module = m.__dict__["$module"]
    assert list(call("p", 7, module=module))       # 7 > 5: folded value used, solves
    assert list(call("p", 3, module=module)) == []  # 3 > 5: same fold, correctly fails


def test_bare_constants_directive_raises_usage_syntax_error(tmp_path):
    """IMPORTANT: ``-constants`` with no parens hands a bare Name operand to
    _handle_constants_directive, which used to assume a Call and blow up
    with ``AttributeError: 'Name' object has no attribute 'keywords'``
    instead of the ordinary usage SyntaxError every other malformed
    ``-constants(...)`` gets."""
    with pytest.raises(SyntaxError, match="-constants takes name = value pairs"):
        _load(tmp_path, "e3", "-constants\np(X) <- (X == 1)\n")


def test_unground_rhs_raises_at_load(tmp_path):
    from clausal.logic.constants import ConstantNotGroundError
    with pytest.raises(ConstantNotGroundError):
        _load(tmp_path, "f", """
            -constants(c_v = ++__import__('clausal.logic.variables',
                                           fromlist=['Var']).Var())
            p(c_v),
        """)


def test_structured_list_constant(tmp_path):
    m = _load(tmp_path, "s1", """
        -constants(c_codes = ['au', 'al', 'za'])
        codes(X) <- (X is c_codes)
    """)
    v = Var()
    assert [deref(v) for _ in call("codes", v, module=m.__dict__["$module"])] == \
        [['au', 'al', 'za']]


def test_structured_tuple_constant(tmp_path):
    m = _load(tmp_path, "s2", """
        -constants(c_pair = (1, 2))
        pair(X) <- (X is c_pair)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("pair", v, module=m.__dict__["$module"])]
    assert result == (1, 2)
    assert isinstance(result, tuple)


def test_structured_set_constant(tmp_path):
    from clausal.terms import SetTerm
    m = _load(tmp_path, "s3", """
        -private([red, green])
        -constants(c_flags = {red, green})
        flags(X) <- (X is c_flags)
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
        -constants(c_limits = {mn: 1, mx: 99})
        limits(X) <- (X is c_limits)
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
        -constants(c_base = 10, c_all = [c_base * 2, tag, point(1, 2), [3, 4]])
        got(X) <- (X is c_all)
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
        -constants(c_origin = point(0, 0))
        origin(X) <- (X is c_origin)
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
        _load(tmp_path, "s7", "-constants(c_p = point(0, 0))\np(X) <- (X is 1)\n")
    exc = exc_info.value
    assert exc.filename == str(tmp_path / "s7.clausal")
    assert exc.lineno == 1


def test_structured_rhs_dict_splat_rejected_and_located(tmp_path):
    with pytest.raises(SyntaxError, match="dict-splat") as exc_info:
        _load(tmp_path, "s7b", "-constants(c_d = {**{1: 2}})\np(X) <- (X is 1)\n")
    exc = exc_info.value
    assert exc.filename == str(tmp_path / "s7b.clausal")
    assert exc.lineno == 1


def test_structured_rhs_generic_unsupported_shape_is_located(tmp_path):
    """The final fallthrough (an RHS shape none of the dedicated branches
    handle, e.g. a comparison expression) is a located SyntaxError too."""
    with pytest.raises(SyntaxError, match="unsupported RHS") as exc_info:
        _load(tmp_path, "s7c", "-constants(c_x = (1 < 2))\np(X) <- (X is 1)\n")
    exc = exc_info.value
    assert exc.filename == str(tmp_path / "s7c.clausal")
    assert exc.lineno == 1


def test_structured_rhs_logic_var_rejected(tmp_path):
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "s8", "-constants(c_l = [1, X, 3])\np(Y) <- (Y is 1)\n")
    exc = exc_info.value
    assert "logic-variable" in str(exc)
    assert exc.filename == str(tmp_path / "s8.clausal")
    assert exc.lineno == 1


def test_structured_rhs_anonymous_var_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="logic-variable"):
        _load(tmp_path, "s9", "-constants(c_l = [1, _, 3])\np(X) <- (X is 1)\n")


def test_structured_rhs_plusplus_element(tmp_path):
    """A ++() escape is legal as an ELEMENT inside a structured RHS — it
    falls out naturally because container branches recurse through the
    same _transform_constant_rhs that already has the ++ branch."""
    m = _load(tmp_path, "s10", """
        -constants(c_l = [1, ++(2 + 3), 3])
        got(X) <- (X is c_l)
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
    m = _load(tmp_path, "s11", "-constants(c_l = [1, 2, 3])\n")
    assert m.__dict__["c_l"] is m.__dict__["$module"].constants["c_l"]


def test_structured_list_constant_mutation_via_plusplus_raises_typeerror(tmp_path):
    m = _load(tmp_path, "s12", """
        -constants(c_l = [1, 2, 3])
        bad(X) <- (X is ++(c_l.append(4)))
    """)
    v = Var()
    with pytest.raises(TypeError, match="frozen constant"):
        list(call("bad", v, module=m.__dict__["$module"]))
    # Loudly failed, not silently mutated.
    assert m.__dict__["c_l"] == [1, 2, 3]


def test_structured_dict_constant_mutation_via_plusplus_raises_typeerror(tmp_path):
    m = _load(tmp_path, "s13", """
        -constants(c_d = {"k": 1})
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
        -constants(c_d = {"a": 1})
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
        -constants(c_s = ++set([1, 2, 3]))
        bad(X) <- (X is ++(c_s.add(4)))
    """)
    v = Var()
    with pytest.raises(TypeError, match="frozen constant"):
        list(call("bad", v, module=m.__dict__["$module"]))


def test_structured_set_literal_constant_is_already_immutable_by_construction(tmp_path):
    """A source-level {...} set literal lowers to SetTerm (frozenset-backed,
    no public mutator at all) — freezing has nothing to do here."""
    m = _load(tmp_path, "s15", "-private([tag])\n-constants(c_s = {tag})\n")
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
        -constants(c_l = [1, 2, 3])
        get(X) <- (X is c_l)
    """)
    v = Var()
    [result] = [deref(v) for _ in call("get", v, module=m.__dict__["$module"])]
    assert isinstance(result, _FrozenList)
    with pytest.raises(TypeError, match="frozen constant"):
        result.append(99)


def test_clause_solution_dict_constant_backing_is_frozen(tmp_path):
    from clausal.logic.constants import _FrozenDict
    m = _load(tmp_path, "s16c", """
        -constants(c_d = {"k": 1})
        get(X) <- (X is c_d)
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
    m = _load(tmp_path, "s16d", "-constants(c_l = [1, 2, 3])\n")
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
    m = _load(tmp_path, "s16e", "-constants(c_l = [1, 2, 3])\n")
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
    m = _load(tmp_path, "s16f", "-constants(c_fs = ++frozenset({1, 2}))\n")
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
        -constants(c_b = true, c_f = false, c_u = undefined)
        got_b(X) <- (X is c_b)
        got_f(X) <- (X is c_f)
        got_u(X) <- (X is c_u)
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
        -constants(c_l = [1, 2, 3])
        matches(X) <- (c_l is [X, 2, 3])
    """)
    v = Var()
    assert [deref(v) for _ in call("matches", v, module=m.__dict__["$module"])] == [1]


def test_multiple_constants_directives(tmp_path):
    """Two -constants directives in one file; the second references the
    first's constant. (Already worked pre-2026-08-25 — pinned directly.)"""
    m = _load(tmp_path, "s17", """
        -constants(c_base = 10)
        -constants(c_double = c_base * 2)
        got(X) <- (X is c_double)
    """)
    v = Var()
    assert [deref(v) for _ in call("got", v, module=m.__dict__["$module"])] == [20]


def test_module_export_list_rejects_constant_names(tmp_path):
    """The -module-specific "cannot list constant" message is gone with the
    shape that triggered it; the collision check gives the accurate one,
    because a listed lowercase name IS an atom."""
    with pytest.raises(SyntaxError, match="constant AND listed as a bare atom"):
        _load(tmp_path, "h", "-module(h, [c_pi])\n-constants(c_pi = 3.14)\n")


def test_non_constant_shaped_declaration_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="constant name"):
        _load(tmp_path, "i", "-constants(PI = 3.14)\np(X) <- (X == 1)\n")


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
    _load(tmp_path, "own1", "-constants(c_pi = 3.14159)\npi(c_pi),\n")
    m = _load(tmp_path, "use1", """
        -import_from(tc_own1, [c_pi])
        twopi(X) <- (X is ++(c_pi * 2))
    """)
    v = Var()
    [x] = [deref(v) for _ in call("twopi", v, module=m.__dict__["$module"])]
    assert abs(x - 6.28318) < 1e-4


def test_import_constant_alias(tmp_path):
    _load(tmp_path, "own2", "-constants(c_pi = 3.14159)\n")
    m = _load(tmp_path, "use2", """
        -import_from(tc_own2, [alias(c_pi, c_mypi)])
        p(c_mypi),
    """)
    v = Var()
    assert [deref(v) for _ in call("p", v, module=m.__dict__["$module"])] == [3.14159]


def test_qualified_constant_access(tmp_path):
    _load(tmp_path, "own4", "-constants(c_pi = 3.14159)\n")
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
    _load(tmp_path, "own7", "-constants(c_pi = 3.14159)\n")
    with pytest.raises(SyntaxError, match="already bound"):
        _load(tmp_path, "use7", """
            -constants(c_pi = 3)
            -import_from(tc_own7, [c_pi])
        """)


def test_constant_in_private_is_now_the_collision_error(tmp_path):
    """A DELIBERATELY DROPPED behaviour, pinned so the drop is visible.

    -private used to accept a constant-shaped name as documentation ("this
    one is an implementation detail"), a recorded no-op. A listed lowercase
    name is an atom, and there is no lexical way to tell the two apart any
    more, so the listing now collides with the declaration and the file is
    refused. Write the atom quoted if both readings are wanted.
    """
    with pytest.raises(SyntaxError, match="constant AND listed as a bare atom"):
        _load(tmp_path, "pdoc1", """
            -constants(c_pi = 3.14159)
            -private([helper, c_pi])
            helper,
            q(X) <- (X is c_pi)
        """)


def test_private_declaration_no_longer_carries_a_constants_list():
    """The other half of the dropped behaviour: PrivateDeclaration.constants
    is gone, so a -private directive reifies with one argument."""
    from clausal.reflection import reify_source, ModuleDirective
    items = reify_source("-private([helper, other])\nhelper,\nother,\n")
    (priv,) = [d for d in items
               if isinstance(d, ModuleDirective) and d.name == "private"]
    assert priv.args == [["helper", "other"]]


def test_module_export_list_still_rejects_constants(tmp_path):
    """Still refused with the directives in the other order -- the check
    runs once the whole module has been walked."""
    with pytest.raises(SyntaxError, match="constant AND listed as a bare atom"):
        _load(tmp_path, "pdoc3", """
            -constants(c_pi = 3.14)
            -module(pdoc3, [c_pi])
        """)


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
            -constants(c_bad = wrap(1, 2))
            p(X) <- (X is c_bad)
        """)


def test_constants_rhs_functor_unknown_field_is_a_load_error(tmp_path):
    _load_const_functor_owner()
    with pytest.raises(SyntaxError, match=r"pair/2"):
        _load(tmp_path, "cfo2", """
            -import_from(tests.fixtures.const_functor_owner, [pair])
            -constants(c_bad = pair(NOPE=1))
            p(X) <- (X is c_bad)
        """)


def test_constants_rhs_functor_partial_construction_is_a_load_error(tmp_path):
    """A constant must be GROUND, so an omitted slot -- which would backfill
    with a fresh Var in a clause body -- is named as the error it is."""
    _load_const_functor_owner()
    with pytest.raises(SyntaxError, match=r"unfilled"):
        _load(tmp_path, "cfo3", """
            -import_from(tests.fixtures.const_functor_owner, [pair])
            -constants(c_bad = pair(1))
            p(X) <- (X is c_bad)
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
            -constants(c_d = {{{key}: 1}})
            lookup(X) <- (X is c_d)
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
        -constants(c_d = {alpha: 1})
        lookup(X) <- (X is c_d)
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
        -constants(max_fine = 5000)
    """)
    assert m.max_fine == 5000


def test_underscored_constant_spelling_is_refused(tmp_path):
    """The retired spelling fails loudly, and the message says what to write."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "c_old", """
            -constants(_MAX_FINE_ = 5000)
        """)
    message = str(excinfo.value)
    assert "_MAX_FINE_" in message
    assert "max_fine" in message, "the message must offer the new spelling"


def test_capital_initial_constant_name_is_refused(tmp_path):
    """A capital initial is a logic variable everywhere now, with no
    exceptions -- so it cannot name a constant either."""
    with pytest.raises(SyntaxError, match="capital-initial"):
        _load(tmp_path, "c_caps", """
            -constants(MaxFine = 5000)
        """)


def test_underscore_led_constant_name_is_refused(tmp_path):
    """The other half of the variable rule, so the two tests together pin
    the constant class as its exact complement."""
    with pytest.raises(SyntaxError, match="underscore-led"):
        _load(tmp_path, "c_under", """
            -constants(_max_fine = 5000)
        """)


def test_an_uncased_script_can_name_a_constant(tmp_path):
    """The constant class is the COMPLEMENT of the variable rule, not
    ``islower()``.  An uncased script has no lowercase form either, so an
    ``islower()`` test would refuse this name while offering no alternative
    -- it is not a variable, so no leading underscore would help."""
    m = _load(tmp_path, "c_jp", """
        -constants(円周率 = 3.14159)
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
        -constants(max_fine = 5000)

        big(thing) <- (++max_fine > 4000)
        small(thing) <- (++max_fine > 6000)
    """)
    assert len(list(call("big", m.thing, module=m.__dict__["$module"]))) == 1
    assert len(list(call("small", m.thing, module=m.__dict__["$module"]))) == 0


def test_bare_name_folds_and_the_escape_looks_up(tmp_path):
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
        -module(c_bind, [bare/1, escaped/1])
        -constants(max_fine = 5000)

        bare(max_fine),
        escaped(X) <- (X is ++max_fine)
    """)
    mod = m.__dict__["$module"]

    def ask(goal):
        v = Var()
        return [deref(v) for _ in call(goal, v, module=mod)]

    assert ask("bare") == [5000]
    assert ask("escaped") == [5000]
    m.max_fine = 9999
    assert ask("bare") == [5000], "a bare reference folded at construction"
    assert ask("escaped") == [9999], "++ resolves the global at solve time"


def test_a_mistyped_constant_reference_is_the_strict_atoms_error(tmp_path):
    """The undeclared-constant diagnostic is gone with the shape that
    triggered it; a bare name nothing binds is the ordinary strict-atoms
    error, which is uniform with every other undeclared name."""
    with pytest.raises(NameError) as excinfo:
        _load(tmp_path, "c_typo", """
            -module(c_typo, [holds/1])
            -constants(max_fine = 5000)

            holds(max_fien),
        """)
    assert "max_fien" in str(excinfo.value)


def test_declaring_a_name_as_both_a_constant_and_a_bare_atom_is_refused(tmp_path):
    """The one combination that cannot work.

    A ``-module``/``-private`` atom listing rebinds the module global to the
    atom AFTER the module body has run, so the constant that -constants
    bound, gated and froze is silently overwritten -- measured: the global
    ends as ``('pi',)`` and even ``++pi`` yields the atom rather than the
    value.  Refused rather than resolved.
    """
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "c_clash", """
            -module(c_clash, [holds/1, pi])
            -constants(pi = 5000)

            holds(pi),
        """)
    message = str(excinfo.value)
    assert "pi" in message
    assert "constant" in message and "atom" in message


def test_the_collision_is_refused_in_the_other_order_too(tmp_path):
    """-constants before the listing, and after: the check runs once the
    whole module has been walked, so it cannot depend on statement order."""
    with pytest.raises(SyntaxError, match="pi"):
        _load(tmp_path, "c_clash2", """
            -constants(pi = 5000)
            -module(c_clash2, [holds/1, pi])

            holds(pi),
        """)


def test_a_private_atom_listing_collides_the_same_way(tmp_path):
    """-private rebinds the global exactly as -module does."""
    with pytest.raises(SyntaxError, match="pi"):
        _load(tmp_path, "c_clash3", """
            -module(c_clash3, [holds/1])
            -private([pi])
            -constants(pi = 5000)

            holds(pi),
        """)


def test_a_name_can_be_a_constant_AND_an_atom_via_the_quoted_form(tmp_path):
    """The operator's point, and it holds: only the BARE atom declaration
    collides.  The quoted form reaches the atom without touching the module
    global, so one name carries both readings in one file -- ``pi`` is the
    constant, ``'pi'`` is the atom, and the quoted one is the same atom
    ``global_atom/2`` yields.
    """
    m = _load(tmp_path, "c_both", """
        -module(c_both, [constant_is/1, atom_is/1, agrees/0])
        -constants(pi = 5000)

        constant_is(pi),
        atom_is('pi'),
        agrees <- (global_atom("pi", A), atom_is(A))
    """)
    mod = m.__dict__["$module"]

    def ask(goal):
        v = Var()
        return [deref(v) for _ in call(goal, v, module=mod)]

    assert ask("constant_is") == [5000]
    assert ask("atom_is") == [("pi",)]
    assert len(list(call("agrees", module=mod))) == 1, (
        "the quoted form must be the same atom global_atom/2 yields")


def test_distinct_names_do_not_collide(tmp_path):
    """The negative control: without it, a check that refuses EVERYTHING
    passes every test above."""
    m = _load(tmp_path, "c_noclash", """
        -module(c_noclash, [holds/1, pi])
        -constants(max_fine = 5000)

        holds(pi),
    """)
    assert m.max_fine == 5000


def test_an_imported_constant_is_reached_through_the_escape(tmp_path):
    """An imported constant takes the ordinary imported-name path now.

    The importer cannot tell a constant from an atom or a predicate in
    another module -- that is the OWNER's fact and the name no longer says
    so -- but the emitted ImportFrom binds the owner's module global here,
    which is all ``++name`` needs.
    """
    _load(tmp_path, "own_c1", "-constants(max_fine = 5000)\n")
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
    _load(tmp_path, "own_c2", "-constants(max_fine = 5000)\n")
    m = _load(tmp_path, "use_c2", """
        -module(use_c2, [limit/1])
        -import_from(tc_own_c2, [alias(max_fine, cap)])

        limit(X) <- (X is ++cap)
    """)
    v = Var()
    assert [deref(v) for _ in call("limit", v,
                                   module=m.__dict__["$module"])] == [5000]
