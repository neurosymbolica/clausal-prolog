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


def test_undeclared_constant_reference_is_syntax_error(tmp_path):
    with pytest.raises(SyntaxError, match="_PI_"):
        _load(tmp_path, "e", "area(R, A) <- (A is ++(_PI_ * R))\n")


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
