"""``call/1`` of a BODY term: conjunction, disjunction, negation, if-then-else
and the builtin comparison goals, built as a runtime term.

ISO 13211-1 §7.6.2 ("converting a term to a body"): ``call(G)`` runs *G* as
though it had been written as a clause body -- a variable ``V`` in a goal
position becomes ``call(V)``, and ``','``/``;``/``->`` are control constructs.
The step-1 target of the ISO ``clause/2`` plan (2026-09-25) is that the Body
``clause/2`` hands back is callable, whatever its shape.

The Clausal spellings are the ones the SAME TEXT produces in term position --
not the ISO cells ``(",", A, B)``, which the surface never builds and which
``cells.refuse_control_construct_cell`` still refuses:

====================================  ===================================
written                               term position (what ``G`` holds)
====================================  ===================================
``(A, B)``                            plain tuple ``(A', B')``, slot 0 not a str
``A and B``                           ``nodes.And``
``A or B``                            ``nodes.Or``
``not A``                             ``nodes.Not``
``if_(C, T, E)``                      ``nodes.IfExpr``
``X > Y`` ``X == Y`` ``X is Y`` ...   the comparison node (``Gt``, ``ArithEq``,
                                      ``Unify``, ``DoesNotUnify``, ``in_``, ...)
``0 < X < 9``                         ``nodes.CompareChain``
``true`` / ``fail``                   ``True`` / the atom ``'fail'``
``p(X)``                              the cell ``("p", X)``
====================================  ===================================

MECHANISM.  No second interpreter: the term is converted to the goal NODE
tree the clause-body compiler already lowers, and compiled through the query
compiler (``solve._compile_as_query``) against the calling module, whose cache
it then shares.  Two choices keep that faithful and cheap:

- Every PREDICATE-CALL leaf becomes ``call(P)`` with ``P`` bound, at run time,
  to the leaf.  So ``call((A, B))`` is exactly ``call(A), call(B)``: name
  resolution, module qualification, predicate handles, lambdas and the
  "unknown name fails" contract are ``call/1``'s own, never a second copy.
  The one exception is a leaf under ``not``/the test of ``if_`` that names a
  TABLED predicate: it is emitted as the direct call, because that is what
  makes the compiler pick WFS-sound tabled negation, as it does for the same
  text in a clause.
- Every Var and every atomic leaf in an ARGUMENT position is replaced by a
  fresh parameter Var bound to it just before the compiled body runs, so the
  compiled artifact depends only on the goal's STRUCTURE: one compile per
  shape, not per value.

ERRORS (checked against Scryer, 2026-09-25).  An unbound goal is
``instantiation_error``.  A number in a goal position reached through the
transparent constructs (conjunction, ``or``, ``if_``) is
``type_error(callable, Whole)`` naming the WHOLE term, before anything runs --
Scryer's ``call((fail, 1))``.  ``not G`` is a predicate in ISO, so its operand
is checked when the negation runs (Scryer: ``call((fail, \\+ 1))`` fails).  A
variable in a goal position is ``call(V)``: ``call((fail, _))`` fails and
``call((true, _))`` is ``instantiation_error``.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.atoms import is_mangled
from clausal.logic.cells import _cell_shape, compound_cell_shape
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.pythonic_ast import nodes


# Comparison / unification goal nodes: both operands are ARGUMENTS.
_CMP_GOALS = (
    nodes.Unify, nodes.DoesNotUnify, nodes.Evaluate,
    nodes.ArithEq, nodes.ArithNeq, nodes.Lt, nodes.LtE, nodes.Gt, nodes.GtE,
    nodes.StructuralEq, nodes.StructuralNeq, nodes.in_, nodes.NotIn,
)

# Goal-position node types a body term can be made of.
_BODY_NODES = _CMP_GOALS + (
    nodes.And, nodes.Or, nodes.Not, nodes.IfExpr, nodes.CompareChain,
    nodes.TupleLiteral,
)

# Non-callable in ISO terms: a number.  (bool is True/False -- a goal.)
_NUMBER_TYPES = (int, float, complex, Decimal, Fraction)

# Atomic leaves safe to pass as a run-time parameter instead of a baked
# literal.  A str is an atom; a MANGLED one (a predicate handle / -hide atom)
# is left to the literal lowering, which knows how to treat it.
_PARAM_ATOMIC = (int, float, str, Decimal, Fraction)


def is_conjunction_tuple(t: Any) -> bool:
    """A plain tuple whose slot 0 is not a functor: the conjunction ``(A, B)``
    as term position builds it.  (``(z, w)`` is the CELL ``z(w)`` -- the
    representation cannot tell them apart, and the cell reading wins.)

    The ``tuple`` type object in slot 0 is the RETIRED tuple-tag spelling
    ``(tuple, 1, 2)`` (the tag is the str ``"()"`` now): still data, so it
    keeps the silent failure every non-goal has
    (``test_cell_goals.test_a_tuple_tag_data_cell_goal_fails_silently``)."""
    return (type(t) is tuple and len(t) >= 2 and not _cell_shape(t)[0]
            and t[0] is not tuple)


def is_body_term(t: Any) -> bool:
    """True when *t* (dereferenced) is a body term ``call/1`` must interpret,
    rather than a predicate-call goal it resolves by name or object."""
    if t is True or t is False:
        # ``call(true)`` built as a term: ``true`` IS ``True`` in term
        # position, and before this it reached no route at all -- ``True``
        # is neither a cell, an atom nor a goal object -- and failed.
        return True
    if type(t) in _BODY_NODES:
        return True
    return is_conjunction_tuple(t)


def _is_number(t: Any) -> bool:
    return isinstance(t, _NUMBER_TYPES) and type(t) is not bool


def _culprit(term: Any) -> Any:
    """The error culprit: the term itself when it is a plain term, else its
    string form -- a raw AST node breaks catch/3 matching (see
    ``_registry._ensure_trampoline_dispatch``)."""
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    walked = _deref_walk(term)

    def has_node(x):
        if isinstance(x, nodes.Node):
            return True
        if type(x) in (tuple, list):
            return any(has_node(e) for e in x)
        return False

    return str(walked) if has_node(walked) else walked


def check_callable_body(goal: Any, context: str) -> None:
    """ISO 7.6.2: raise ``type_error(callable, Goal)`` when a goal position
    reachable through the TRANSPARENT constructs holds a number.  ``not``'s
    operand is not walked (it is checked when the negation runs)."""
    def walk(t):
        t = deref(t)
        if is_var(t):
            return False
        if _is_number(t):
            return True
        if is_conjunction_tuple(t):
            return any(walk(e) for e in t)
        if type(t) is nodes.TupleLiteral:
            return any(walk(e) for e in t.elements)
        if type(t) in (nodes.And, nodes.Or):
            return walk(t.left) or walk(t.right)
        if type(t) is nodes.IfExpr:
            return walk(t.test) or walk(t.body) or walk(t.orelse)
        return False

    if walk(goal):
        from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
        culprit = _culprit(goal)
        raise LogicException(type_error(
            "callable", culprit, f"{context}: {culprit} is not a callable body"))


class _Converter:
    """One conversion: the goal-node tree plus its run-time parameters."""

    def __init__(self, db):
        self.db = db
        self.params: list[tuple[Var, Any]] = []
        self._by_var: dict[int, Var] = {}

    def _param(self, value, raw=None):
        if raw is not None:
            pv = self._by_var.get(id(raw))
            if pv is not None:
                return pv
        pv = Var()
        self.params.append((pv, value))
        if raw is not None:
            self._by_var[id(raw)] = pv
        return pv

    # ── argument positions ──────────────────────────────────────────────
    def arg(self, raw):
        """An argument-position subterm with Vars and atomic leaves lifted
        into parameters, so the compiled body does not depend on them."""
        t = deref(raw)
        if is_var(t):
            return t                      # an unbound Var is already a slot
        if isinstance(raw, Var):          # a BOUND Var: its value, by reference
            if isinstance(t, _PARAM_ATOMIC) and type(t) is not bool \
                    and not (type(t) is str and is_mangled(t)):
                return self._param(t, raw)
            # A structured value: lift what is inside it.
            return self.arg(t)
        if isinstance(t, _PARAM_ATOMIC) and type(t) is not bool:
            if type(t) is str and is_mangled(t):
                return t
            return self._param(t)
        if type(t) is list:
            return [self.arg(e) for e in t]
        if type(t) is tuple:
            is_cell, _ = _cell_shape(t)
            if is_cell:
                if not compound_cell_shape(t)[0]:
                    return t              # TUPLE_TAG / chars carrier: data
                # Slot 0 is the functor -- structure, never a parameter.
                return (t[0],) + tuple(self.arg(e) for e in t[1:])
            return tuple(self.arg(e) for e in t)
        if isinstance(t, nodes.Node) and type(t) in _NODE_FIELDS:
            return self._rebuild(t, self.arg)
        return t

    def _rebuild(self, node, fn):
        kw = {}
        for name in _NODE_FIELDS[type(node)]:
            v = getattr(node, name)
            if type(v) is list:
                kw[name] = [fn(e) for e in v]
            else:
                kw[name] = fn(v)
        return type(node)(**kw)

    # ── goal positions ──────────────────────────────────────────────────
    def _call_leaf(self, t):
        """``call(P)``, ``P`` bound at run time to the leaf goal *t*."""
        return nodes.Call(func=nodes.LoadName(name="call"),
                          args=[self._param(t)], kwargs=[])

    def _maybe_tabled(self, raw):
        """Under ``not`` / an ``if_`` test: a cell naming a TABLED predicate
        is emitted as the direct call (WFS-sound tabled negation, as the
        compiler gives the same text in a clause); None otherwise."""
        t = deref(raw)
        is_cell, functor = compound_cell_shape(t)
        if not is_cell or self.db is None or is_mangled(functor):
            return None
        from clausal.logic.compiler.tabled_naf import _is_tabled_naf  # noqa: PLC0415
        # The probe needs only the name and the arity; the arguments are
        # lifted into parameters only for the call that is actually emitted.
        probe = nodes.Call(func=nodes.LoadName(name=functor),
                           args=list(t[1:]), kwargs=[])
        if not _is_tabled_naf(probe, self.db):
            return None
        return nodes.Call(func=nodes.LoadName(name=functor),
                          args=[self.arg(a) for a in t[1:]], kwargs=[])

    def goal(self, raw):
        t = deref(raw)
        if is_var(t):
            return self._call_leaf(t)     # ISO: a variable goal is call(V)
        if t is True or t is False:
            return t
        if type(t) is str and t in ("true",):
            return True
        if type(t) is str and t in ("fail", "false"):
            return False
        if is_conjunction_tuple(t):
            return nodes.TupleLiteral(elements=[self.goal(e) for e in t])
        tt = type(t)
        if tt is nodes.TupleLiteral:
            return nodes.TupleLiteral(elements=[self.goal(e) for e in t.elements])
        if tt is nodes.And:
            return nodes.And(left=self.goal(t.left), right=self.goal(t.right))
        if tt is nodes.Or:
            return nodes.Or(left=self.goal(t.left), right=self.goal(t.right))
        if tt is nodes.Not:
            direct = self._maybe_tabled(t.operand)
            return nodes.Not(operand=direct if direct is not None
                             else self._call_leaf(t.operand))
        if tt is nodes.IfExpr:
            test = self._maybe_tabled(t.test)
            return nodes.IfExpr(
                test=test if test is not None else self.goal(t.test),
                body=self.goal(t.body), orelse=self.goal(t.orelse))
        if tt is nodes.CompareChain:
            return nodes.CompareChain(
                comparisons=[self._rebuild(c, self.arg) for c in t.comparisons])
        if tt in _CMP_GOALS:
            return self._rebuild(t, self.arg)
        # Everything else -- a cell, an atom, a predicate class, a lambda,
        # a qualified goal -- is call/1's to resolve, exactly as it would be
        # on its own.
        return self._call_leaf(t)


# The semantic fields of each node type the converter rebuilds (``position``
# is location only and is dropped).
def _node_fields(cls):
    import dataclasses  # noqa: PLC0415
    return tuple(f.name for f in dataclasses.fields(cls) if f.name != "position")


_NODE_FIELDS: dict[type, tuple[str, ...]] = {}
for _cls in (_CMP_GOALS + (
        nodes.CompareChain,
        nodes.Add, nodes.Sub, nodes.Mult, nodes.Div, nodes.FloorDiv,
        nodes.Mod, nodes.Pow, nodes.MatMult, nodes.LShift, nodes.RShift,
        nodes.BitOr, nodes.BitXor, nodes.BitAnd,
        nodes.UnaryPlus, nodes.Negate, nodes.Invert)):
    _NODE_FIELDS[_cls] = _node_fields(_cls)
del _cls


# ── the module the body compiles against ────────────────────────────────────

_DBLESS_MODULE = None


def _module_for(db):
    """The :class:`Module` whose namespace the body compiles against.

    The loaded module when *db* has one (``$module`` in its dict).  Otherwise
    one wrapper per db, kept ON the db: the query cache keys on
    ``id(module)``, so a fresh wrapper per call would both miss the cache and
    risk a recycled id serving code compiled against another db.
    """
    global _DBLESS_MODULE
    from clausal.logic.database import Module  # noqa: PLC0415
    if db is None:
        if _DBLESS_MODULE is None:
            _DBLESS_MODULE = Module("$call_body")
        return _DBLESS_MODULE
    module_dict = getattr(db, "module_dict", None)
    if module_dict is not None:
        mod = module_dict.get("$module")
        if isinstance(mod, Module) and mod.db is db:
            return mod
    mod = getattr(db, "_call_body_module", None)
    if mod is None:
        mod = Module("$call_body", db=db, module_dict=module_dict)
        db._call_body_module = mod
    return mod


def body_goal_dispatch(db, goal_val, context: str):
    """``(dispatch, [])`` running the body term *goal_val* in *db*'s module.

    The shape ``higher_order._resolve_named_goal`` returns, so ``call/N``
    drives it like any resolved goal.
    """
    check_callable_body(goal_val, context)
    conv = _Converter(db)
    node = conv.goal(goal_val)
    if node is True:
        from clausal.logic.builtins.higher_order import _control_succeed_once  # noqa: PLC0415
        return _control_succeed_once, []
    if node is False:
        from clausal.logic.builtins.higher_order import _control_fail  # noqa: PLC0415
        return _control_fail, []
    from clausal.logic.solve import _compile_as_query  # noqa: PLC0415
    fn, param_pairs = _compile_as_query(node, _module_for(db))
    params = conv.params + list(param_pairs)

    def _call_body(this_generator, _proceed, _fail, _catcher, trail):
        for pv, value in params:
            unify(pv, value, trail)       # pv is fresh: binds, never fails
        sg = StepGenerator(fn, this_generator, this_generator, this_generator, trail)
        _st = yield (sg, None)
        while _st is not DONE:
            yield (_proceed, None)
            _st = yield (sg, None)
        yield (_fail, DONE)

    return _call_body, []


__all__ = ["is_body_term", "check_callable_body", "body_goal_dispatch"]
