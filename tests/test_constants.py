"""-constants: declared, ground at module load, folded into clause terms."""
import textwrap
import pytest

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
        -constants(_PI_ = 3.14159)
        area(R, A) <- (A is ++(_PI_ * R * R))
    """)
    [a] = _values(m, "area", 2.0)
    assert abs(a - 3.14159 * 4.0) < 1e-9


def test_constant_as_plain_argument(tmp_path):
    m = _load(tmp_path, "b", """
        -constants(_MAX_ = 3)
        limit(_MAX_),
        got(X) <- limit(X)
    """)
    v = Var()
    results = [deref(v) for _ in call("limit", v, module=m.__dict__["$module"])]
    assert results == [3]


def test_constant_from_prior_constant_and_arithmetic(tmp_path):
    m = _load(tmp_path, "c", """
        -constants(_BASE_ = 10, _LIMIT_ = _BASE_ * 4 + 2)
        lim(_LIMIT_),
    """)
    v = Var()
    assert [deref(v) for _ in call("lim", v, module=m.__dict__["$module"])] == [42]


def test_plusplus_rhs(tmp_path):
    m = _load(tmp_path, "d", """
        -constants(_PI_ = ++__import__('math').pi)
        pi(_PI_),
    """)
    import math
    v = Var()
    assert [deref(v) for _ in call("pi", v, module=m.__dict__["$module"])] == [math.pi]


def test_plusplus_rhs_undeclared_constant_is_syntax_error(tmp_path):
    """The ``++`` RHS of a -constants declaration never passes through
    visit_Name (it is emitted verbatim as raw Python), so an undeclared
    constant reference inside it used to fall through to a raw NameError at
    load time instead of the located, remedy-bearing SyntaxError every other
    undeclared-constant reference gets."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "d2", "-constants(_A_ = ++(_B_ * 2))\np(_A_),\n")
    exc = exc_info.value
    assert "_B_" in str(exc)
    assert "drop one of the underscores" in str(exc)
    assert exc.filename == str(tmp_path / "d2.clausal")
    assert exc.lineno == 1


def test_plusplus_rhs_declared_earlier_constant_still_works(tmp_path):
    """A constant declared by an earlier -constants entry IS legal inside a
    later ++ RHS — by exec time it is already a bound module global. Keeps
    the existing passing ``++`` RHS behaviour green alongside the new scan."""
    m = _load(tmp_path, "d3", """
        -constants(_BASE_ = 10, _SCALED_ = ++(_BASE_ * 2))
        scaled(_SCALED_),
    """)
    v = Var()
    assert [deref(v) for _ in call("scaled", v, module=m.__dict__["$module"])] == [20]


def test_plusplus_rhs_comprehension_target_matching_constant_shape_is_not_flagged(tmp_path):
    """Same exemption as the ordinary ++() escape: a comprehension's own loop
    variable is locally bound, not a reference to any module global, even
    when it happens to be constant-shaped."""
    m = _load(tmp_path, "d4", """
        -constants(_TOTAL_ = ++(sum(_ITEM_ for _ITEM_ in range(5))))
        total(_TOTAL_),
    """)
    v = Var()
    assert [deref(v) for _ in call("total", v, module=m.__dict__["$module"])] == [10]


def test_undeclared_constant_reference_is_syntax_error(tmp_path):
    with pytest.raises(SyntaxError, match="_PI_"):
        _load(tmp_path, "e", "area(R, A) <- (A is ++(_PI_ * R))\n")


def test_undeclared_constant_error_has_location_and_underscore_remedy(tmp_path):
    """IMPORTANT: the raise sites hold the AST node, so filename/lineno must
    land on the SyntaxError itself — both for a readable location and to
    qualify for clausal_syntax_diagnostics's caret/window enrichment, which
    requires exc.filename == filename and a valid exc.lineno (see
    syntax_diagnostics.enrich_syntax_error). The message must also offer the
    most likely remedy for legacy code that meant a logic variable."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "e2", "area(R, A) <- (A is ++(_PI_ * R))\n")
    exc = exc_info.value
    assert exc.filename == str(tmp_path / "e2.clausal")
    assert exc.lineno == 1
    assert "drop one of the underscores" in str(exc)


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
        -constants(_K_ = 5)
        p(R) <- call_goal((X <- (X > _K_)), R)
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
            -constants(_V_ = ++__import__('clausal.logic.variables',
                                           fromlist=['Var']).Var())
            p(_V_),
        """)


def test_structured_rhs_rejected_for_now(tmp_path):
    with pytest.raises(SyntaxError, match="structured"):
        _load(tmp_path, "g", "-constants(_L_ = [1, 2, 3])\np(X) <- (X == 1)\n")


def test_module_export_list_rejects_constant_names(tmp_path):
    with pytest.raises(SyntaxError, match="-constants"):
        _load(tmp_path, "h", "-module(h, [_PI_])\n-constants(_PI_ = 3.14)\n")


def test_non_constant_shaped_declaration_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="constant name"):
        _load(tmp_path, "i", "-constants(PI = 3.14)\np(X) <- (X == 1)\n")


def test_comprehension_target_matching_constant_shape_is_not_flagged(tmp_path):
    """A comprehension's own loop variable is locally bound, not a reference
    to any module global — even when it happens to be constant-shaped. The
    undeclared-constant check inside a ``++()`` escape must see past a
    Store-context binding, not just any Name node of the right shape."""
    m = _load(tmp_path, "j", """
        total(R, T) <- (T is ++(sum(_ITEM_ for _ITEM_ in range(int(R)))))
    """)
    v = Var()
    results = [deref(v) for _ in call("total", 5, v, module=m.__dict__["$module"])]
    assert results == [10]


def test_walrus_target_matching_constant_shape_is_not_flagged(tmp_path):
    """Same as the comprehension case, for a walrus target inside a
    ``++()`` escape."""
    m = _load(tmp_path, "k", """
        doubled(R, T) <- (T is ++((_TMP_ := int(R) * 2) + _TMP_))
    """)
    v = Var()
    results = [deref(v) for _ in call("doubled", 3, v, module=m.__dict__["$module"])]
    assert results == [12]


def test_genuinely_free_undeclared_constant_inside_escape_still_raises(tmp_path):
    """The fix for the two cases above must not swallow the real case: a
    constant-shaped name that is truly free (never locally bound) inside a
    ``++()`` escape still raises the load-time SyntaxError."""
    with pytest.raises(SyntaxError, match="_PI_"):
        _load(tmp_path, "l", "area(R, A) <- (A is ++(_PI_ * R))\n")


def test_import_constant_direct(tmp_path):
    _load(tmp_path, "own1", "-constants(_PI_ = 3.14159)\npi(_PI_),\n")
    m = _load(tmp_path, "use1", """
        -import_from(tc_own1, [_PI_])
        twopi(X) <- (X is ++(_PI_ * 2))
    """)
    v = Var()
    [x] = [deref(v) for _ in call("twopi", v, module=m.__dict__["$module"])]
    assert abs(x - 6.28318) < 1e-4


def test_import_constant_alias(tmp_path):
    _load(tmp_path, "own2", "-constants(_PI_ = 3.14159)\n")
    m = _load(tmp_path, "use2", """
        -import_from(tc_own2, [alias(_PI_, _MYPI_)])
        p(_MYPI_),
    """)
    v = Var()
    assert [deref(v) for _ in call("p", v, module=m.__dict__["$module"])] == [3.14159]


def test_import_constant_alias_shape_mismatch_rejected(tmp_path):
    _load(tmp_path, "own3", "-constants(_PI_ = 3.14159)\n")
    with pytest.raises(SyntaxError, match="constant"):
        _load(tmp_path, "use3", "-import_from(tc_own3, [alias(_PI_, Pi)])\n")


def test_qualified_constant_access(tmp_path):
    _load(tmp_path, "own4", "-constants(_PI_ = 3.14159)\n")
    m = _load(tmp_path, "use4", """
        -import_module(tc_own4)
        p(X) <- (X is ++(tc_own4._PI_ + 0))
        q(tc_own4._PI_),
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
    _load(tmp_path, "own7", "-constants(_PI_ = 3.14159)\n")
    with pytest.raises(SyntaxError, match="already bound"):
        _load(tmp_path, "use7", """
            -constants(_PI_ = 3)
            -import_from(tc_own7, [_PI_])
        """)


def test_import_constant_alias_collides_with_earlier_import_rejected(tmp_path):
    _load(tmp_path, "own8", "-constants(_PI_ = 3.14159)\n")
    with pytest.raises(SyntaxError, match="already bound"):
        _load(tmp_path, "use8", """
            -import_from(tc_own8, [_PI_])
            -import_from(tc_own8, [alias(_PI_, _PI_)])
        """)
