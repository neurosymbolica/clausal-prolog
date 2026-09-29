"""clpz's predicates under Scryer's names, as engine builtins (ruling D9(a)):
``in/2``, ``ins/2``, ``labeling/2`` and the reified connectives ``#<==>/2``,
``#==>/2``, ``#<==/2``, ``#\\//2``, ``#/\\/2``, ``#\\/1`` and ``#\\/2``.

Usable from every front end and from ``query()``; from the seam in quoted
form (``'in'(X, '..'(1, 3))``, ``'#<==>'(B, '#='(X, 1))``).  The
``#=`` family (``#=``, ``#\\=``, ``#<``, ``#>``, ``#=<``, ``#>=``) is
registered in :mod:`clausal.logic.builtins.iso_compare`.  ``label/1`` keeps
the engine's first-fail meaning; Scryer's (leftmost) ``label/1`` is
``labeling([], Vs)``, which a ``.pl`` file importing library(clpz) gets
under the name ``label`` (``clausal.stdlib.clpz``).  The implementation is
:mod:`clausal.logic.clpz_surface`, over :mod:`clausal.logic.clpfd`.
"""
from __future__ import annotations

from clausal.logic.builtins._registry import _builtin


@_builtin("in", 2, fields=("var", "domain"))
def _clpz_in(x, dom, trail, k):
    """X in Dom -- X is an element of the clpz domain Dom (``1..3``,
    ``inf..sup``, ``1..3 \\/ 5..7``, an integer)."""
    from clausal.logic.clpz_surface import clpz_in  # noqa: PLC0415
    if clpz_in(x, dom, trail):
        yield None


@_builtin("ins", 2, fields=("vars", "domain"))
def _clpz_ins(xs, dom, trail, k):
    """Xs ins Dom -- every element of the list Xs is in Dom."""
    from clausal.logic.clpz_surface import clpz_ins  # noqa: PLC0415
    if clpz_ins(xs, dom, trail):
        yield None


@_builtin("labeling", 2, fields=("options", "vars"))
def _clpz_labeling(options, xs, trail, k):
    """labeling(Options, Vars) -- Scryer's clpz labeling search."""
    from clausal.logic.clpz_surface import labeling  # noqa: PLC0415
    yield from labeling(options, xs, trail)


def _connective(name: str, arity: int):
    fields = ("p",) if arity == 1 else ("p", "q")

    def run(*args):
        from clausal.logic.clpz_surface import post_connective  # noqa: PLC0415
        trail = args[arity]
        if post_connective(name, args[:arity], trail):
            yield None
    run.__name__ = f"_clpz_{arity}_{name}"
    run.__doc__ = f"{name}/{arity} -- clpz's reified connective."
    return _builtin(name, arity, fields=fields)(run)


for _n in ("#<==>", "#==>", "#<==", "#\\/", "#/\\", "#\\"):
    _connective(_n, 2)
_connective("#\\", 1)
del _n
