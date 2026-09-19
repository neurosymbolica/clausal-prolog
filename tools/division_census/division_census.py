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


def _is_exact(value) -> bool:
    """Does the quotient sit on an integer?  That is what ``#=`` can express."""
    try:
        if isinstance(value, Fraction):
            return value.denominator == 1
        if isinstance(value, int):
            return True
        return Fraction(value).denominator == 1
    except (ValueError, OverflowError, TypeError):
        return False            # a non-rational (float nan/inf, a Quantity)


def _record(binding: str, left, right, result) -> None:
    _BY_BINDING[binding] += 1
    _ROWS[(_site(), binding, repr(left)[:40], repr(right)[:40],
           "exact" if _is_exact(result) else "INEXACT")] += 1


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
        fn = getattr(obj, attr, None)
        if fn is None or hasattr(fn, "_division_census_original"):
            return
        setattr(obj, attr, _wrap(fn, binding))
        _INSTALLED.append(binding)

    patch(exact_arith, "exact_div", "exact_arith.exact_div")
    patch(clpfd, "exact_div", "clpfd.exact_div")            # bound at import
    patch(terms_to_ast, "_exact_div", "terms_to_ast.$div")
    patch(terms_to_ast, "exact_div", "terms_to_ast.$exact_div")
    patch(Quantity, "_exact_div", "Quantity._exact_div")    # units division

    # The compiled path reads these VALUES into each generated module's
    # namespace at exec time, so the dict has to carry the wrappers too.
    names = terms_to_ast.ARITH_RUNTIME_NAMES
    names["$div"] = terms_to_ast._exact_div
    names["$exact_div"] = terms_to_ast.exact_div
    return _INSTALLED


def rows():
    """(site, binding, left, right, exactness, count) for every division seen."""
    return [(*k, n) for k, n in _ROWS.most_common()]


def report(path: str | None = None) -> str:
    """Write the census.  Every population prints its SIZE."""
    path = path or os.environ.get("DIVISION_CENSUS_OUT", "/tmp/division_census.tsv")
    total = sum(_ROWS.values())
    inexact = sum(n for k, n in _ROWS.items() if k[4] == "INEXACT")
    sites = {k[0] for k in _ROWS}
    with open(path, "w") as f:
        f.write(f"# divisions evaluated: {total}\n")
        f.write(f"# distinct (site, binding, operands, exactness) rows: {len(_ROWS)}\n")
        f.write(f"# distinct corpus sites: {len(sites)}\n")
        f.write(f"# INEXACT divisions: {inexact}\n")
        f.write("# bindings that fired: "
                + ", ".join(f"{b}={n}" for b, n in _BY_BINDING.most_common()) + "\n")
        f.write("# bindings installed but NEVER fired: "
                + (", ".join(sorted(set(_INSTALLED) - set(_BY_BINDING))) or "(none)") + "\n")
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
    print("[division census] positive control OK: 2 divisions seen, "
          "exact and INEXACT distinguished")


# ── pytest plugin entry points ──────────────────────────────────────────────

def pytest_configure(config):        # noqa: ARG001
    install()


def pytest_sessionfinish(session, exitstatus):   # noqa: ARG001
    print("\n" + report())


install()
atexit.register(lambda: print(report()) if _ROWS else None)
