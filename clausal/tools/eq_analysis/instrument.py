"""Record which SEMANTICS each ``==`` site actually executes.

Clausal's ``==`` is ``nodes.ArithEq``, and at run time it dispatches three
different things depending on the MODE of its operands:

    X == 3 + 4     X unbound      binds X            -> ISO ``is/2``
    1 + 1 == 2     both ground    tests              -> ISO ``=:=``
    X == Y + 1     both unbound   posts a constraint -> CLP ``#=``
    A == lo        ground, non-numeric   structural  -> ISO ``==``
    X == X + 1     var, no effect        NO mode shown -> FAILED

Which one a site means therefore cannot be read off its source shape -- it is
a property of the mode, and the mode is only visible when the site RUNS. This
installs a wrapper around the ``$fd_eq`` runtime entry that records, per
execution, the source site and the path taken. Running the suites under it
turns a static guess into evidence, and the sites nothing exercises become an
explicit list rather than a silent default.

Output is one JSON object per EXECUTION -- duplicates are meaningful, because
a site that binds on one call and tests on another has no single correct
respelling and must become ``#=``:

    {"file": "<abs .clausal path>", "line": 42, "path": "BIND"}

ORDERING IS A CONTRACT: :func:`install` must run BEFORE the modules under
analysis are imported. The compiler captures ``$fd_eq`` into each predicate's
globals at compile time, so a wrapper installed afterwards is never seen and
the run produces an empty record set -- which is indistinguishable from "this
code contains no ``==``". :func:`install` therefore refuses to run twice
silently, and callers should treat an empty result as suspect rather than
clean (the companion runner exits non-zero on it).
"""
from __future__ import annotations

import json
import os
import sys

#: One dict per execution, in execution order. Duplicates are kept.
_RECORDS: list[dict] = []
_ORIGINAL = None
_ARITH_NODES: tuple = ()

BIND = "BIND"
TEST = "TEST"
CONSTRAINT = "CONSTRAINT"
STRUCTURAL = "STRUCTURAL"
FAILED = "FAILED"


def _arith_node_types() -> tuple:
    """The arithmetic expression-tree types, imported lazily.

    An operand is numeric if it is a number OR an unevaluated arithmetic tree:
    ``1 + 1 == 2`` arrives with its left side an ``Add``, not an ``int``, so a
    bare ``isinstance(x, (int, float))`` calls the most basic arithmetic site
    STRUCTURAL. That was a real bug in the first draft of this classifier.
    """
    global _ARITH_NODES
    if not _ARITH_NODES:
        from clausal.terms import Add, Mult, Negate, Sub
        _ARITH_NODES = (Add, Sub, Mult, Negate)
    return _ARITH_NODES


def _is_numeric(x) -> bool:
    from clausal.logic.variables import deref
    x = deref(x)
    return isinstance(x, (int, float)) and not isinstance(x, bool) \
        or isinstance(x, _arith_node_types())


def _site():
    """``(file, line)`` of the clause frame that called ``$fd_eq``.

    The generated clause code object reports ``co_filename == "<template>"``,
    but the frame's globals carry the module's real ``__file__``, and
    ``f_lineno`` is the true ``.clausal`` line. (Reading ``co_filename`` and
    concluding the file was unavailable cost a design detour; the file is
    there, one attribute over.)
    """
    f = sys._getframe(2)          # 0 = here, 1 = the wrapper, 2 = the clause
    path = f.f_globals.get("__file__")
    return (os.path.abspath(path) if path else None), f.f_lineno


def _classify(l, r, was_var_l, was_var_r, trail_grew, result) -> str:
    from clausal.logic.variables import is_var, deref
    now_var_l, now_var_r = is_var(deref(l)), is_var(deref(r))
    if (was_var_l and not now_var_l) or (was_var_r and not now_var_r):
        return BIND
    if not was_var_l and not was_var_r:
        return TEST if (_is_numeric(l) and _is_numeric(r)) else STRUCTURAL
    if trail_grew:
        return CONSTRAINT
    # A var operand that neither bound nor posted has demonstrated NO mode:
    # nothing was evaluated, nothing was constrained. Recording it as TEST
    # would let the verdict table report ``=:=`` MEASURED off a run in which
    # the site never did arithmetic at all -- a confidence the data did not
    # earn, baked into the records where no later fix could recover it. It is
    # nearer NOT_EXERCISED than TEST, with one useful difference for whoever
    # migrates: a test DOES reach this site, so the remedy is a BETTER test,
    # not a new one. FAILED is ABSORBING downstream: dropped before the
    # verdict is computed, so it never decides and never forces.
    return FAILED


def install() -> None:
    """Wrap the ``$fd_eq`` runtime entry. Call BEFORE importing targets."""
    global _ORIGINAL
    if _ORIGINAL is not None:
        raise RuntimeError(
            "eq_analysis.instrument.install() called twice; a second wrap "
            "would double-count every execution")
    import clausal.logic.compiler.predicate as predicate
    from clausal.logic.variables import deref, is_var
    _ORIGINAL = predicate._fd_eq_fn

    def _instrumented(l, r, trail, _orig=_ORIGINAL):
        was_var_l, was_var_r = is_var(deref(l)), is_var(deref(r))
        before = len(trail)
        result = _orig(l, r, trail)      # exceptions propagate unrecorded
        path = _classify(l, r, was_var_l, was_var_r, len(trail) > before, result)
        file, line = _site()
        _RECORDS.append({"file": file, "line": line, "path": path})
        return result

    predicate._fd_eq_fn = _instrumented


def uninstall() -> None:
    """Restore the original entry. Records are kept; use :func:`reset`."""
    global _ORIGINAL
    if _ORIGINAL is None:
        return
    import clausal.logic.compiler.predicate as predicate
    predicate._fd_eq_fn = _ORIGINAL
    _ORIGINAL = None


def reset() -> None:
    _RECORDS.clear()


def records() -> list[dict]:
    """Every execution recorded so far, in order, duplicates preserved."""
    return list(_RECORDS)


def write_jsonl(path) -> int:
    """Write :func:`records` as JSON Lines. Returns the count written."""
    rows = records()
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return len(rows)
