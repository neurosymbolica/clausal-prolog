"""Micro-benchmark for the constant-list membership frozenset fast path.

``X in [c1, c2, …]`` lowers to a scan that ``unify()``s X against every
element, bracketed by ``trail.mark()``/``trail.undo()``.  Where the list
is a run of compile-time constants and X derefs to a ground whitelisted
term, the compiler now consults a memoised frozenset instead — see
:mod:`clausal.logic.runtime.const_set`.

The two variants are compiled **in the same process**, the baseline by
disabling the ``const_set`` optimisation for that compile, so the numbers
are not separated by a machine-state change.  Each measurement subtracts
a membership-free control clause of the same shape, so what is reported
is the cost of the membership goal itself, not the trampoline around it.

Usage (from project root):
    python benchmarks/bench_const_list_membership.py
"""

from __future__ import annotations

import os
import tempfile
import timeit

from clausal.import_hook import _load_module
from clausal.logic.compiler.compile_ctx import _ALL_OPTIMISATIONS
from clausal.logic.solve import call


_ATOMS = [f"a{i}" for i in range(64)]


def _source() -> str:
    def lst(n):
        return ", ".join(_ATOMS[:n])
    return f"""\
-private([{", ".join(_ATOMS)}])

control(_),
scan2(A) <- (A in [{lst(2)}])
scan4(A) <- (A in [{lst(4)}])
scan8(A) <- (A in [{lst(8)}])
scan16(A) <- (A in [{lst(16)}])
scan64(A) <- (A in [{lst(64)}])
notin4(A) <- (A not in [{lst(4)}])
strings4(A) <- (A in ["acquire", "dispose", "amend", "cancel"])
dup4(A) <- (A in [a0, a0, a1, a2])
"""


def _load(name: str, const_set: bool):
    """Load the bench module, optionally with the fast path suppressed."""
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(_source())
        path = f.name
    prev = os.environ.get("CLAUSAL_DISABLE_OPT")
    if not const_set:
        os.environ["CLAUSAL_DISABLE_OPT"] = "const_set"
    else:
        os.environ.pop("CLAUSAL_DISABLE_OPT", None)
    try:
        pymod = _load_module(name, path)
        return pymod, pymod.__dict__["$module"]
    finally:
        if prev is None:
            os.environ.pop("CLAUSAL_DISABLE_OPT", None)
        else:
            os.environ["CLAUSAL_DISABLE_OPT"] = prev
        os.unlink(path)


_slow_py, _slow = _load("bench_cset_scan", const_set=False)
_fast_py, _fast = _load("bench_cset_set", const_set=True)

N = 30_000


def _drain(functor: str, arg, mod) -> int:
    return sum(1 for _ in call(functor, arg, module=mod))


def _ns(functor: str, arg, mod) -> float:
    """ns per call for *functor*, net of the membership-free control.

    Best-of-5 on both terms: the set path is fast enough that the control
    subtraction is the dominant source of noise, and a single timing run
    of it swamps the signal.
    """
    total = min(timeit.repeat(lambda: _drain(functor, arg, mod), number=N, repeat=5))
    floor = min(timeit.repeat(lambda: _drain("control", arg, mod), number=N, repeat=5))
    return (total - floor) / N * 1e9


# (label, functor, argument, expected solution count)
PROBES = [
    ("in 2 atoms, hit",      "scan2",    "a0",     1),
    ("in 4 atoms, hit",      "scan4",    "a0",     1),
    ("in 8 atoms, hit",      "scan8",    "a0",     1),
    ("in 16 atoms, hit",     "scan16",   "a0",     1),
    ("in 64 atoms, hit",     "scan64",   "a0",     1),
    ("in 4 atoms, miss",     "scan4",    "a63",    0),
    ("not in 4 atoms, miss", "notin4",   "a63",    1),
    ("in 4 strings, hit",    "strings4", "cancel", 1),
    ("in 4 atoms w/ dup",    "dup4",     "a0",     2),
]


def _arg(spec, pymod):
    """Resolve an atom name against the loaded module, or pass a str through.

    The two builds are separate modules, so each has its own atom objects —
    an atom from one will not unify with the same-named atom in the other.
    """
    return getattr(pymod, spec) if spec in _ATOMS else spec


if __name__ == "__main__":
    assert "const_set" in _ALL_OPTIMISATIONS
    # Both builds must agree on every solution count, or the numbers below
    # are comparing two different programs.
    for label, functor, spec, want in PROBES:
        for pymod, mod in ((_slow_py, _slow), (_fast_py, _fast)):
            got = _drain(functor, _arg(spec, pymod), mod)
            assert got == want, f"{label}: {got} solutions, expected {want}"

    print(f"\n{'membership goal':<24}  {'scan ns':>10}  {'set ns':>10}  {'speedup':>9}")
    print("-" * 60)
    for label, functor, spec, _want in PROBES:
        slow = _ns(functor, _arg(spec, _slow_py), _slow)
        fast = _ns(functor, _arg(spec, _fast_py), _fast)
        # Below ~100 ns the control subtraction is the same size as the
        # signal, so report a bound rather than a fake precision.
        if fast < 100:
            print(f"{label:<24}  {slow:>10.0f}  {'<100':>10}  {'>' + f'{slow / 100:.0f}':>8}x")
        else:
            print(f"{label:<24}  {slow:>10.0f}  {fast:>10.0f}  {slow / fast:>8.1f}x")
    print("\n(the duplicate-list row must NOT speed up: a set would collapse")
    print(" [a0, a0, a1, a2] to one solution where the scan yields two)\n")
