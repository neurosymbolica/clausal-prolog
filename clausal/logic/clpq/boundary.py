"""The CLP(Q) entry points' boundary code: Clausal's, not clp(q,r) 1.3.3's.

What every entry point of ``holzbaur.py`` does before the port sees a
constraint, and to an optimum on the way out.  None of it touches the
solver's store:

- an arithmetic cell becomes its operator node (:func:`_cells_as_nodes`,
  ruling R9 A1), and a relation cell of a constraint block its comparison
  node (:func:`_block_cell_as_node`);
- the units side channel (``clausal.logic.units_clp``) strips a Quantity or
  a united variable to its solver number or shadow (:func:`_units_strip`,
  :func:`_units_strip_expr`) and puts the dimension back on an optimum
  (:func:`_units_result`).

Moved here unchanged from the solver Clausal shipped before the port
(retired by operator ruling 2026-11-05).
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import present_number


# ── Cells ────────────────────────────────────────────────────────────────────


def _cells_as_nodes(l, r, context):
    """clpfd's post-boundary rewrite, STRICT (ruling R9 A1, 2026-09-27): an
    arithmetic cell becomes its operator node, which is what the normal
    form walks; an atom or a non-evaluable compound raises
    ``type_error(evaluable, F/N)``."""
    global _cells_as_nodes
    from clausal.logic.clpfd import _cells_as_nodes as impl  # noqa: PLC0415 -- clpfd imports this module lazily
    _cells_as_nodes = impl
    return impl(l, r, context)


def _cell_as_node(expr: Any, context: str) -> Any:
    """One operand's :func:`_cells_as_nodes` -- an objective or a bound."""
    return _cells_as_nodes(expr, 0, context)[0]


#: A relation cell a block holds -> the comparison node it posts as: the
#: comparisons nf.pl's {}/1 reads (``=`` is ``=:=`` there).  A relation built
#: at run time (``C = (X =< 5), clpq:rational(C)``) arrives as a cell; the
#: braces of a .clausal or seam block are compiled to the nodes.  Filled by
#: :func:`_block_cell_as_node` on first use.
_BLOCK_CELL_NODES: dict = {}


def _block_cell_as_node(term: Any) -> Any:
    """*term* as its comparison node when it is a relation cell
    (``('=<', X, 5)``), else *term* unchanged."""
    if type(term) is not tuple or len(term) != 3:
        return term
    if not _BLOCK_CELL_NODES:
        from clausal.pythonic_ast.nodes import (  # noqa: PLC0415
            ArithEq, ArithNeq, Gt, GtE, Lt, LtE)
        _BLOCK_CELL_NODES.update({
            "=<": LtE, "<": Lt, ">=": GtE, ">": Gt,
            "=:=": ArithEq, "=": ArithEq, "=\\=": ArithNeq})
    node_class = _BLOCK_CELL_NODES.get(term[0])
    if node_class is None:
        return term
    return node_class(left=term[1], right=term[2])


# ── Units ────────────────────────────────────────────────────────────────────
# The units side channel (clausal.logic.units_clp), the one CLP(FD) uses: a
# Quantity or a united variable anywhere in a post is analysed for its
# dimension first (a disagreement is ``system_error(units_mismatch)``), then
# every Quantity becomes its exact solver number and every united variable its
# bare shadow, so the solver only ever sees rationals. When the solver binds
# a shadow, the ``units_link`` hook rebinds the user's variable to a Quantity
# in the dimension's base unit -- ``5000 cent`` is 50 euro on the way in and
# comes back as euro, exactly as the ground path presents it.  Cached on
# first use.

_strip_for_solver = None
_strip_expr_for_solver = None
_reattach = None


def _ensure_units_imports() -> None:
    global _strip_for_solver, _strip_expr_for_solver, _reattach
    if _strip_for_solver is None:
        from clausal.logic import units_clp  # noqa: PLC0415
        _strip_for_solver = units_clp.strip_for_solver
        _strip_expr_for_solver = units_clp.strip_expr_for_solver
        _reattach = units_clp.reattach


def _units_strip(l, r, context, trail):
    """A comparison through the side channel: the ``(l, r)`` the solver can
    take, or the pair untouched when no units material is involved. Runs
    AFTER the cell rewrite (a Quantity leaf may sit inside a cell built at
    run time) and before the ground fast paths, which read plain numbers."""
    if _strip_for_solver is None:
        _ensure_units_imports()
    stripped = _strip_for_solver(l, r, context, trail, strict=True)
    return (l, r) if stripped is None else stripped


def _units_strip_expr(expr, context, trail):
    """An objective through the side channel: ``(expr', dims)`` -- the tree
    the solver can take and the dimension its optimum carries (``{}`` when
    no units material is involved)."""
    if _strip_expr_for_solver is None:
        _ensure_units_imports()
    stripped = _strip_expr_for_solver(expr, context, trail)
    return (expr, {}) if stripped is None else stripped


def _units_result(value, dims):
    """An optimum as the term the caller gets: a Quantity of *dims*, else the
    number as the engine presents it (an integral rational is an int)."""
    if not dims:
        return present_number(value)
    return _reattach(value, dims)
