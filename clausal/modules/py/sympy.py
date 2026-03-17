"""clausal.modules.py.sympy — SymPy predicates under the ``py.sympy`` name.

Re-exports everything from :mod:`clausal.modules.sympy_module` so that
``.clausal`` files can use the familiar name::

    -import_from(py.sympy, [Simplify, Solve, Diff, sin, cos, inf])
"""

from clausal.modules.sympy_module import (  # noqa: F401
    # Predicates
    Sym,
    ToSympy,
    FromSympy,
    Simplify,
    Expand,
    Factor,
    Solve,
    SolveAll,
    Diff,
    Integrate,
    Limit,
    Series,
    Subs,
    FreeVars,
    SymEqual,
    SymStr,
    Inf,
    # Algebra
    Collect,
    Cancel,
    Apart,
    Together,
    Degree,
    Coeffs,
    Roots,
    # Trig
    TrigSimp,
    ExpandTrig,
    # Printing
    Latex,
    Pretty,
    MathML,
    # Number theory
    IsPrime,
    NextPrime,
    FactorInt,
    Divisors,
    Gcd,
    Lcm,
    # Special
    Sum,
    Product,
    Binomial,
    # Math functions
    sin,
    cos,
    tan,
    asin,
    acos,
    atan,
    exp,
    log,
    ln,
    sqrt,
    factorial,
    Abs,
    # Constants
    inf,
    pi,
    e,
)
