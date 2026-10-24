"""Negative zero is 0.0 (operator ruling 2026-10-24): the engine against the
Scryer oracle, on one ISO Prolog text run by both.

Scryer has no ``-0.0`` term: the reader reads ``-0.0`` (and ``- 0.0``, the
negative numeric literal with layout) as ``0.0``, and every float an
evaluation hands back -- ``is/2``'s result, ``number_chars/2``'s number -- is
``0.0`` where IEEE 754 would give ``-0.0`` (Ulrich's syntax table row #364,
``writeq(-0.0)`` prints ``0.0``).  It normalises the RESULT only, not each
step of an evaluation: ``atan2(-(0.0), -1)`` is ``-pi`` in Scryer, because
the inner ``-(0.0)`` keeps its sign until the outer function has used it.
The engine does the same, at the one point a number becomes the value a
binder unifies (``present_number``), at the reader's negative literal, at
number_chars/2 & co., and where CLP(R) binds a variable.  The writer prints
what it is given: a ``-0.0`` made by Python and never evaluated is not a
number the engine read or computed.

Each ROW is ``(name, goal, expected)``: the goal binds ``X``, and both
engines must print ``writeq(X)`` as *expected*.  The engine half also checks
the value itself, so a printer that hid a ``-0.0`` would not pass: a float
answer must carry a positive sign bit unless the row expects a negative
number.  ``SURFACES`` runs the rows under ``.pl`` and ``.clausal``; the seam's
rows are at the end.
"""

from __future__ import annotations

import math

import pytest

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref
from clausal.terms import term_writeq

# (name, goal binding X, what writeq(X) prints in both engines)
ROWS = [
    # reading: the negative numeric literal, with and without layout
    ("read_literal", "X = -0.0", "0.0"),
    ("read_layout", "X = - 0.0", "0.0"),
    ("read_quoted_minus", "X = '-' 0.0", "0.0"),
    ("read_in_compound", "X = f(-0.0)", "f(0.0)"),
    ("read_in_list", "X = [-0.0, 0.0]", "[0.0,0.0]"),
    ("read_exponent", "X = -0.0e10", "0.0"),
    # -(0.0) is a compound, not the literal: its argument is +0.0
    ("compound_minus_not_literal", "X = -(0.0)", "- (0.0)"),
    # is/2's result: every IEEE route to -0.0
    ("is_literal", "X is -0.0", "0.0"),
    ("is_unary_minus", "X is -(0.0)", "0.0"),
    ("is_unary_minus_variable", "Y = 0.0, X is -Y", "0.0"),
    ("is_double_minus", "X is -(-(0.0))", "0.0"),
    ("is_times_negative_int", "X is 0.0 * -1", "0.0"),
    ("is_negative_int_times", "X is -1 * 0.0", "0.0"),
    ("is_times_negative_float", "X is -1.0 * 0.0", "0.0"),
    ("is_divide_negative", "X is 0.0 / -1", "0.0"),
    ("is_underflow", "X is -1.0e-300 * 1.0e-300", "0.0"),
    ("is_exp_underflow", "X is exp(-1000) * -1", "0.0"),
    ("is_sum_of_negative_zeros", "X is -(0.0) + -(0.0)", "0.0"),
    ("is_difference", "X is -(0.0) - 0.0", "0.0"),
    ("is_power_float", "X is -(0.0) ** 3", "0.0"),
    ("is_power_caret", "X is -(0.0) ^ 3", "0.0"),
    ("is_min", "X is min(-(0.0), 0.0)", "0.0"),
    ("is_max", "X is max(-(0.0), -1)", "0.0"),
    ("is_float_of_negative_int", "X is float(-0)", "0.0"),
    ("is_float_integer_part", "X is float_integer_part(-0.5)", "0.0"),
    ("is_float_fractional_part", "X is float_fractional_part(-1.0)", "0.0"),
    ("is_sin", "X is sin(-(0.0))", "0.0"),
    ("is_tan", "X is tan(-(0.0))", "0.0"),
    ("is_asin", "X is asin(-(0.0))", "0.0"),
    ("is_atan", "X is atan(-(0.0))", "0.0"),
    ("is_sqrt", "X is sqrt(-(0.0))", "0.0"),
    ("is_atan2_of_negative_zero", "X is atan2(-(0.0), 1)", "0.0"),
    # integer results are untouched; abs and sign already give +0.0
    ("is_truncate", "X is truncate(-0.4)", "0"),
    ("is_ceiling", "X is ceiling(-0.5)", "0"),
    ("is_abs", "X is abs(-(0.0))", "0.0"),
    ("is_sign", "X is sign(-(0.0))", "0.0"),
    # the result is +0.0, so a later evaluation sees +0.0 ...
    ("sign_seen_by_atan2", "Z is 0.0 * -1, X is atan2(Z, -1)",
     "3.141592653589793"),
    ("sign_seen_by_atan2_after_read", "X is atan2(-0.0, -1)",
     "3.141592653589793"),
    ("divide_by_normalised_zero",
     "catch(_ is 1 / -0.0, error(X, _), true)",
     "evaluation_error(zero_divisor)"),
    # ... but an INNER step keeps its sign, as Scryer: only results are
    # normalised, not every intermediate value
    ("intermediate_keeps_sign", "X is atan2(-(0.0), -1)",
     "-3.141592653589793"),
    ("intermediate_product_keeps_sign", "X is atan2(0.0 * -1, -1)",
     "-3.141592653589793"),
    ("intermediate_float_integer_part",
     "X is atan2(float_integer_part(-0.5), -1)", "-3.141592653589793"),
    ("intermediate_float_fractional_part",
     "X is atan2(float_fractional_part(-1.0), -1)", "3.141592653589793"),
    # a negative result that is not zero stays negative
    ("negative_nonzero", "X is -0.5 * 1.0", "-0.5"),
    ("negative_tiny", "X is -5.0e-324 * 1.0", "-5.0e-324"),
    # number_chars/2 & co. read as the reader does
    ("number_chars", "number_chars(X, ['-', '0', '.', '0'])", "0.0"),
    ("number_chars_layout", "number_chars(X, ['-', ' ', '0', '.', '0'])",
     "0.0"),
    ("number_codes", "number_codes(X, [0'-, 0'0, 0'., 0'0])", "0.0"),
    # the comparisons were already right
    ("structural_equal", "(-0.0 == 0.0, X = yes ; X = no)", "yes"),
    ("compare", "compare(X, -0.0, 0.0)", "="),
    ("unify", "(-0.0 = 0.0, X = yes ; X = no)", "yes"),
    ("sort_dedups", "sort([-0.0, 0.0], X)", "[0.0]"),
]

_NEGATIVE = {"intermediate_keeps_sign", "intermediate_product_keeps_sign",
             "intermediate_float_integer_part",
             "negative_nonzero", "negative_tiny"}

CLAUSAL_SUFFIX = CLAUSAL_PROLOG_SUFFIXES[0]
SURFACES = [PROLOG_SUFFIX, CLAUSAL_SUFFIX]


def _floats(t):
    t = deref(t)
    if type(t) is float:
        yield t
    elif isinstance(t, (tuple, list)):
        for a in t:
            yield from _floats(a)


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """``run(goal, suffix)``: X's first answer, from ``t(X) :- Goal.`` loaded
    as a module of the given surface."""
    d = tmp_path_factory.mktemp("negative_zero")
    counter = [0]

    def run(goal: str, suffix: str, prelude: str = ""):
        counter[0] += 1
        name = f"nz{counter[0]}"
        path = d / f"{name}{suffix}"
        text = f"{prelude}t(X) :- {goal}.\n"
        if suffix == CLAUSAL_SUFFIX:
            text = f":- module({name}, [t/1]).\n{text}:- end_module({name}).\n"
        path.write_text(text)
        mod = _load_module(name, str(path))
        x = Var()
        for _ in solve(("t", x), mod, Trail()):
            return deref(x)
        raise AssertionError(f"no answer: {goal}")
    return run


@pytest.mark.parametrize("suffix", SURFACES)
@pytest.mark.parametrize("name, goal, expected", ROWS, ids=[r[0] for r in ROWS])
def test_engine(engine, suffix, name, goal, expected):
    x = engine(goal, suffix)
    assert term_writeq(x) == expected, (name, goal)
    for f in _floats(x):
        sign = math.copysign(1.0, f)
        assert sign == (-1.0 if name in _NEGATIVE else 1.0), (name, goal, f)


@pytest.mark.parametrize("name, goal, expected", ROWS, ids=[r[0] for r in ROWS])
def test_oracle(scryer, name, goal, expected):
    got = scryer(f"({goal}), writeq(X), nl, halt.")
    assert got == expected, (name, goal, got)


# -- the seam: its own spellings of the same values ------------------------

SEAM_PROGRAM = """\
-module(nz_seam, [lit(X), neg(X), prod(X), iso_is(X), escape(X), fact(X)])
fact(-0.0),
lit(X) <- (X == -0.0)
neg(X) <- (Y is 0.0, X == -Y)
prod(X) <- (X == 0.0 * -1)
iso_is(X) <- ('is'(X, 0.0 * -1))
escape(X) <- (X == ++(-0.0))
"""


@pytest.mark.parametrize("pred", ["fact", "lit", "neg", "prod", "iso_is",
                                  "escape"])
def test_seam(tmp_path, monkeypatch, pred):
    from tests._suffix import SEAM
    (tmp_path / f"nz_seam{SEAM}").write_text(SEAM_PROGRAM)
    mod = _load_module("nz_seam", str(tmp_path / f"nz_seam{SEAM}"))
    x = Var()
    for _ in solve((pred, x), mod, Trail()):
        v = deref(x)
        assert type(v) is float and v == 0.0, (pred, v)
        assert math.copysign(1.0, v) == 1.0, (pred, v)
        assert term_writeq(v) == "0.0"
        return
    raise AssertionError(f"no answer: {pred}")



# -- CLP(R): a real variable bound to a point (engine only: Scryer's clpz
# has no reals) ----------------------------------------------------------

CLPR_ROWS = [
    ("ground_product", "X #= 0.0 * -1.0"),
    ("ground_negation", "X #= -(0.0)"),
    ("point_interval_product", "in_real(Z, 0.0, 0.0), X #= Z * -1.0"),
    ("bound_later", "in_real(Z), Z #= 0.0, X #= -1.0 * Z"),
]


@pytest.mark.parametrize("suffix", SURFACES)
@pytest.mark.parametrize("name, goal", CLPR_ROWS, ids=[r[0] for r in CLPR_ROWS])
def test_clpr(engine, suffix, name, goal):
    x = engine(goal, suffix, ":- use_module(library(clpz)).\n")
    assert type(x) is float and x == 0.0, (name, x)
    assert math.copysign(1.0, x) == 1.0, (name, x)
