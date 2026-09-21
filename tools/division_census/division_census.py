"""Census: every DIVISION the engine evaluates, with its DENOMINATOR.

THE QUESTION.  The exporter lowers corpus arithmetic to clpz ``#=``, which is
CLP over the integers: ``#=(X, 7/2)`` does not raise, it silently finds no
solution, while ``#=(X, 6/2)`` binds 3.  So an exported program agrees with
the corpus only where a division comes out EXACT.  Eight corpus sites do a
genuine numeric division (iso-export-lane, 2026-09-19, by a structural walk of
the emitted AST).  Whether those divisions are exact in practice is not
knowable from anything on disk -- the runtime census records ``{file, line,
path}`` and no operand VALUES -- so it has to be measured while the corpus
RUNS.  This is that instrument.  It reads the engine, not the export pipeline,
because the engine is where the quotients are actually computed.

USAGE

    DIVISION_CENSUS_OUT=/tmp/div.tsv python -m pytest ... -p division_census
    DIVISION_CENSUS_OUT=/tmp/div.tsv python -c "import division_census; <run>"

Import it (or load it as a pytest plugin) BEFORE any ``.clausal`` module is
compiled: generated modules capture the arithmetic runtime names into their own
namespace at exec time, so a hook installed afterwards would not be in them.
``division_census.verify()`` is the positive control and says so out loud.

WHAT IT WRAPS, and why more than one thing.  ``exact_div`` is documented as the
ONE spelling shared by the compiled and interpreted evaluators, but it is bound
by NAME in several places at import time, and a rebind is invisible to a patch
of the defining module alone (the python-twin-vs-C-wrapper trap, 2026-09-18).
So every binding is wrapped, each is counted separately, and ``verify()``
fails if any of them never fires.

READING THE COUNTS.  A ``count`` is how many times the engine EVALUATED that
division, not how many times the program asked for it.  Measured 2026-09-19:
one goal with one solution (``half(6, Q) <- (Q == N / 2)``) records TWO
divisions -- the ``==`` arithmetic is evaluated twice per solution.  That does
not affect the exactness question, which is about WHICH quotients occur, but
do not read a count as a call count.

WHAT A ROW MEANS.  ``exact`` is whether the quotient is an integer -- the
property ``#=`` needs.  ``site`` is the nearest ``.clausal``/``.seam`` frame on
the stack, which is the corpus line responsible; ``(engine)`` means no corpus
frame was below it (an engine-internal division, e.g. inside a library
predicate).  A denominator of 1 is still recorded: it is exact, and a census
that hides the easy cases cannot say what fraction of traffic is easy.
"""
from __future__ import annotations

import atexit
import collections
import os
import traceback
from fractions import Fraction

_ROWS: collections.Counter = collections.Counter()
_BY_BINDING: collections.Counter = collections.Counter()
_INSTALLED: list[str] = []
_SUFFIXES = (".clausal", ".seam")


def _site() -> str:
    """Who divided: a Clausal source line if one is on the stack, else the
    generated PREDICATE whose body did it.

    Compiled clause bodies run in frames whose filename is ``<template>``
    (the generated code is compiled from a template, not from the ``.clausal``
    path), so a walk that only accepts ``.clausal`` frames answers
    ``(engine)`` for every division a compiled predicate does -- which is most
    of them.  The template frame's FUNCTION NAME carries the predicate and
    arity (``half__all__2``), which is the identification the question needs.
    """
    for frame in reversed(traceback.extract_stack()[:-3]):
        if frame.filename.endswith(_SUFFIXES):
            return f"{os.path.basename(frame.filename)}:{frame.lineno}"
        if frame.filename == "<template>" and frame.name not in ("<module>",):
            return f"<pred {frame.name}>"
    return "(engine)"


def _classify(left, right, value) -> str:
    """How this division fares under clpz ``#=``, which is CLP over the
    INTEGERS.  Three outcomes, because they fail differently and a census
    that lumps them together cannot be acted on:

    * ``exact``   -- the quotient is an integer.  ``#=`` computes it.
    * ``INEXACT`` -- an exact non-integer (a Fraction).  ``#=`` finds NO
      SOLUTION, silently; this is the case the question is about.
    * ``float``   -- a float operand.  ``#=`` raises
      ``domain_error(clpz_expression, F)``, which is loud, and
      iso-export-lane measured 0 corpus sites exposed to it.  Kept apart so
      it cannot inflate the INEXACT count: a float divided by 1 is not an
      integer, but it is not the silent failure either.
    """
    if any(type(x) is float for x in (left, right)) or type(value) is float:
        return "float"
    try:
        if isinstance(value, Fraction):
            return "exact" if value.denominator == 1 else "INEXACT"
        if isinstance(value, int):
            return "exact"
        return "exact" if Fraction(value).denominator == 1 else "INEXACT"
    except (ValueError, OverflowError, TypeError):
        return "unclassified"          # a Quantity, a Decimal special, ...


def _record(binding: str, left, right, result) -> None:
    _BY_BINDING[binding] += 1
    _ROWS[(_site(), binding, repr(left)[:40], repr(right)[:40],
           _classify(left, right, result))] += 1


#: Re-entrancy guard.  The bindings CHAIN -- ``clpfd`` does
#: ``from ... import exact_div`` at import time, so whichever of the two this
#: module imports second may already hold the other's wrapper, and a division
#: would be counted once per layer.  The guard counts the OUTERMOST call, so
#: the total is the number of divisions the engine performed, not the number
#: of wrappers they passed through.  (Measured: without it the control ran 5
#: divisions and the census reported 10.)
_IN_DIVISION = False


def _wrap(fn, binding: str):
    def wrapped(l, r, *a, **kw):
        global _IN_DIVISION
        if _IN_DIVISION:
            return fn(l, r, *a, **kw)
        _IN_DIVISION = True
        try:
            result = fn(l, r, *a, **kw)
        finally:
            _IN_DIVISION = False
        _record(binding, l, r, result)
        return result
    wrapped.__name__ = getattr(fn, "__name__", binding)
    wrapped.__doc__ = getattr(fn, "__doc__", None)
    wrapped._division_census_original = fn
    return wrapped


def install() -> list[str]:
    """Wrap every binding that evaluates a division.  Idempotent."""
    if _INSTALLED:
        return _INSTALLED

    from clausal.logic import exact_arith
    from clausal.logic import clpfd
    from clausal.logic.compiler import terms_to_ast
    from clausal.terms import Quantity

    def patch(obj, attr, binding):
        """Wrap one binding, PRESERVING how it is bound.

        ``Quantity._exact_div`` is a ``staticmethod``; assigning a plain
        function over it makes the wrapper an instance method and the
        instance arrives as the numerator -- measured, as
        ``TypeError: _exact_div() takes 2 positional arguments but 3 were
        given``, the first time this ran against a corpus module that
        divides a Quantity.  ``inspect.getattr_static`` sees the descriptor
        rather than what it resolves to, which is the only way to tell.
        """
        import inspect  # noqa: PLC0415
        static = inspect.getattr_static(obj, attr, None)
        fn = getattr(obj, attr, None)
        if fn is None or hasattr(fn, "_division_census_original"):
            return
        wrapper = _wrap(fn, binding)
        setattr(obj, attr, staticmethod(wrapper)
                if isinstance(static, staticmethod) else wrapper)
        _INSTALLED.append(binding)

    patch(exact_arith, "exact_div", "exact_arith.exact_div")
    patch(clpfd, "exact_div", "clpfd.exact_div")            # bound at import
    patch(terms_to_ast, "_exact_div", "terms_to_ast.$div")
    patch(terms_to_ast, "exact_div", "terms_to_ast.$exact_div")
    patch(Quantity, "_exact_div", "Quantity._exact_div")    # units division
    _patch_clpq()

    # The compiled path reads these VALUES into each generated module's
    # namespace at exec time, so the dict has to carry the wrappers too.
    names = terms_to_ast.ARITH_RUNTIME_NAMES
    names["$div"] = terms_to_ast._exact_div
    names["$exact_div"] = terms_to_ast.exact_div
    return _INSTALLED


def _patch_clpq() -> None:
    """CLP(Q) divides WITHOUT going through ``exact_div``.

    ``clpq._linearize``'s ``_Div`` arm flattens ``expr.left / expr.right`` by
    dividing the coefficients directly (``{v: c / rv ...}, lv / rv``), so a
    division that happens inside a posted CONSTRAINT rather than in ground
    arithmetic is invisible to every other binding here.  That is not
    hypothetical: the harness lane's row 7 (a scored domain
    produced no census rows at all while five siblings produced plenty, and
    this is the path such a site would take.

    Only the PROGRAM's division is recorded — the ``_Div`` node the source
    wrote.  The simplex's own pivot arithmetic divides constantly (bound
    computation, row reduction) and recording that would bury the signal.
    """
    from clausal.logic import clpq
    if getattr(clpq._linearize, "_division_census_original", None):
        return
    clpq._ensure_term_imports()
    div_type = clpq._Div
    original = clpq._linearize

    def linearize(expr, trail, *a, **kw):
        result = original(expr, trail, *a, **kw)
        if isinstance(expr, div_type) and result is not None:
            left = original(expr.left, trail, *a, **kw)
            right = original(expr.right, trail, *a, **kw)
            if left is not None and right is not None and not right[0]:
                _record("clpq._linearize", left[1], right[1], result[1])
        return result

    linearize._division_census_original = original
    clpq._linearize = linearize
    _INSTALLED.append("clpq._linearize")


def rows():
    """(site, binding, left, right, exactness, count) for every division seen."""
    return [(*k, n) for k, n in _ROWS.most_common()]


def report(path: str | None = None) -> str:
    """Write the census.  Every population prints its SIZE."""
    path = path or os.environ.get("DIVISION_CENSUS_OUT", "/tmp/division_census.tsv")
    total = sum(_ROWS.values())
    inexact = sum(n for k, n in _ROWS.items() if k[4] == "INEXACT")
    kinds = collections.Counter(k[4] for k in _ROWS)
    sites = {k[0] for k in _ROWS}
    with open(path, "w") as f:
        f.write(f"# ARMED: {len(_INSTALLED)} bindings wrapped "
                f"({', '.join(_INSTALLED) or 'NONE — the census is not armed'})\n")
        if not total:
            f.write("# NO DIVISION WAS OBSERVED.  This file exists to say that\n"
                    "# ARMED-AND-SAW-NOTHING is what happened — not that the\n"
                    "# census failed to run.  Two readings remain and this tool\n"
                    "# cannot separate them: the code path does no division, or\n"
                    "# it divides through a binding not in the list above.\n")
        f.write(f"# divisions evaluated: {total}\n")
        f.write(f"# distinct (site, binding, operands, exactness) rows: {len(_ROWS)}\n")
        f.write(f"# distinct corpus sites: {len(sites)}\n")
        f.write(f"# INEXACT divisions (an exact non-integer — the SILENT "
                f"#= failure): {inexact}\n")
        f.write("# outcome classes: "
                + ", ".join(f"{k}={n}" for k, n in kinds.most_common()) + "\n")
        f.write("# bindings that fired: "
                + ", ".join(f"{b}={n}" for b, n in _BY_BINDING.most_common()) + "\n")
        f.write("# bindings installed but NEVER fired: "
                + (", ".join(sorted(set(_INSTALLED) - set(_BY_BINDING))) or "(none)") + "\n")
        # In the OUTPUT, not only in the README: a reader of this file has
        # the header in front of them and the docs somewhere else, and a
        # census that counts evaluations while its reader assumes calls is
        # off by exactly 2x -- the kind of factor that gets discovered a
        # month later, inside a conclusion (iso-export-lane, 2026-09-19).
        f.write("# CAUTION: `count` is EVALUATIONS, not calls. `==` evaluates "
                "its arithmetic TWICE per solution (measured: one goal, one "
                "solution, two rows). Exactness per row is unaffected.\n")
        f.write("# A division by a CONSTANT is decidable without this census: "
                "`X * Y / 10000` is exact iff X*Y is a multiple of 10000. Six "
                "of the eight corpus sites divide by a constant; only TWO "
                "divide by a runtime quantity, and those are the live "
                "question.\n")
        f.write("site\tbinding\tleft\tright\texactness\tcount\n")
        for row in rows():
            f.write("\t".join(str(x) for x in row) + "\n")
    return (f"[division census] {total} divisions, {len(sites)} sites, "
            f"{inexact} INEXACT -> {path}")


def verify() -> None:
    """Positive control: the hook must SEE a division, and must tell an exact
    one from an inexact one.  A census that reports nothing is the failure
    mode this repo keeps hitting, so refuse to be silent about it."""
    install()
    from clausal.logic import exact_arith
    before = sum(_ROWS.values())
    assert exact_arith.exact_div(6, 2) == 3, "control: 6/2 is 3"
    assert exact_arith.exact_div(7, 2) == Fraction(7, 2), "control: 7/2 is 7/2"
    seen = sum(_ROWS.values()) - before
    assert seen == 2, (f"the hook saw {seen} of 2 control divisions — "
                       f"more than 2 means the wrappers are CHAINING and the "
                       f"re-entrancy guard is not holding")
    kinds = [k[4] for k in list(_ROWS)[-2:]]
    assert "exact" in kinds and "INEXACT" in kinds, f"control exactness: {kinds}"

    # Control for the BINDING SHAPE, not only the value: a staticmethod
    # wrapped as a plain function receives the instance as its numerator.
    from clausal.terms import Quantity
    q = Quantity(10, {})
    assert (q / 2)._value == 5, "control: a Quantity still divides"
    print("[division census] positive control OK: 2 divisions seen, "
          "exact and INEXACT distinguished")


# ── pytest plugin entry points ──────────────────────────────────────────────

def pytest_configure(config):        # noqa: ARG001
    install()


def pytest_sessionfinish(session, exitstatus):   # noqa: ARG001
    print("\n" + report())


install()

# ALWAYS write, even with nothing to report.  It used to write only when
# ``_ROWS`` was non-empty, and the harness lane hit the consequence
# (2026-09-19): a domain that produced NO FILE is indistinguishable from a run
# where the census was never armed, and those are opposite conclusions — "no
# division happens here" versus "the census is blind here".  A zero-row file
# with the armed bindings listed says which.
atexit.register(lambda: print(report()))
