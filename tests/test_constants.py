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
