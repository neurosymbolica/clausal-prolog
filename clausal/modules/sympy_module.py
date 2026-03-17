"""Backward compatibility — canonical implementation in clausal.modules.py.sympy."""
from clausal.modules.py.sympy import *  # noqa: F401,F403
from clausal.modules.py.sympy import (  # noqa: F401 — re-export internals for tests
    to_sympy, from_sympy, _ConversionContext, _to_sympy, _to_pyval,
    _convert_multi, _simple_to_trampoline, _SympyPredicate, SymExpr,
    _sym_2, _to_sympy_2, _from_sympy_2, _simplify_2, _expand_2, _factor_2,
    _solve_3, _solve_all_3, _diff_2, _diff_3, _integrate_2, _integrate_3,
    _limit_4, _series_4, _series_5, _subs_3, _free_vars_2, _sym_equal_2,
    _sym_str_2, _inf_1, _collect_3, _cancel_2, _apart_2, _apart_3,
    _together_2, _degree_2, _degree_3, _coeffs_3, _roots_3,
    _trig_simp_2, _expand_trig_2, _latex_2, _pretty_2, _mathml_2,
    _is_prime_1, _next_prime_2, _factor_int_2, _divisors_2,
    _gcd_sym_3, _lcm_sym_3, _summation_4, _product_sym_4, _binomial_3,
    _MathFunc, _SYMPY_FUNCTIONS, _ALPHA, _auto_name,
)
