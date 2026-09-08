"""ISO comparison, unification and arithmetic builtins under their ISO names.

Reachable from `.clausal` ONLY through the quoted canonical form —
`'=:='(A, B)` — because Python has no infix syntax for these; natively in
`.pl`. Spec: docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md
"""
from clausal.logic.atoms import is_atom, mint, spelling
from clausal.logic.builtins._registry import _builtin
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.logic.variables import deref, is_var
from clausal.terms import Compound


def _clpfd_leaf_culprit(exc: LogicException):
    """The offending LEAF out of a `_eval_ground` leaf error, or None.

    `_eval_ground` (clausal/logic/clpfd.py) never catches an exception
    itself, so every `LogicException` it lets escape is exactly its own
    `_unknown_expr_leaf_error(leaf)` — `error(type_error(integer, Leaf,
    "clpfd expression"), _)` — bubbled up unchanged through any amount of
    recursion. Matching that literal shape (rather than translating every
    `LogicException`) means an *unrelated* exception raised deeper in the
    tree — should `_eval_ground` ever grow one — fails closed: it is
    re-raised as-is instead of being mislabelled `evaluable`.
    """
    term = exc.term
    if not (isinstance(term, Compound) and term.functor == "error"
            and len(term.args) == 2):
        return None
    inner, context = term.args
    if not (isinstance(inner, Compound) and inner.functor == "type_error"
            and len(inner.args) == 2):
        return None
    expected, leaf = inner.args
    if not (is_atom(expected) and spelling(expected) == "integer"):
        return None
    if context != "clpfd expression":
        return None
    return leaf


def _evaluable_culprit(leaf):
    """*leaf* as ISO's `Name/Arity` culprit for `type_error(evaluable, …)`.

    An atom is arity 0 (`foo` -> `foo/0`, matching Scryer's
    `type_error(evaluable,foo/0)` for `_ is foo + 1`); a compound is its own
    functor/arity. `_eval_ground`'s leaf fallthrough only ever hands back a
    non-numeric, non-Var, non-expression-node term — atoms and compounds are
    the two shapes that occur in practice, so anything else is passed
    through unchanged rather than guessed at.
    """
    if is_atom(leaf):
        return Compound("/", (leaf, 0))
    if isinstance(leaf, Compound):
        name = leaf.functor if is_atom(leaf.functor) else mint(str(leaf.functor))
        return Compound("/", (name, len(leaf.args)))
    return leaf


def _iso_eval(term, context: str):
    """Evaluate an arithmetic term to a number, with ISO's errors.

    `clpfd._eval_ground` returns None for an unbound operand and raises its own
    leaf error for a non-number; ISO wants instantiation_error and
    type_error(evaluable, F/N). Scryer attributes BOTH to (is)/2 regardless of
    which comparison raised them — pin what it does, not what reads tidily.

    `_eval_ground`'s own leaf error is `type_error(integer, Leaf, "clpfd
    expression")` — a CLP(FD)-flavoured shape, not ISO's `type_error(evaluable,
    Name/Arity)` for `is/2`. Measured directly against Scryer (task-3-brief):
    `_ is foo + 1` -> `error(type_error(evaluable,foo/0),(is)/2)`. Reconciled
    here, at the call site, rather than in `_eval_ground` itself — that
    function is shared by every other CLP(FD) caller in the engine and its
    "clpfd expression" shape is correct for THEM; only `is`/the comparisons
    need the ISO term.
    """
    from clausal.logic.clpfd import _eval_ground
    t = deref(term)
    if is_var(t):
        raise LogicException(instantiation_error(context))
    try:
        value = _eval_ground(t)
    except LogicException as e:
        leaf = _clpfd_leaf_culprit(e)
        if leaf is None:
            raise
        raise LogicException(
            type_error("evaluable", _evaluable_culprit(leaf), context)) from None
    except Exception:
        raise LogicException(type_error("evaluable", t, context)) from None
    if value is None:
        raise LogicException(instantiation_error(context))
    return value


def _arith_cmp(name, op):
    @_builtin(name, 2)
    def _cmp(a, b, trail, k, _op=op, _name=name):
        if _op(_iso_eval(a, "is/2"), _iso_eval(b, "is/2")):
            yield None
    return _cmp


import operator as _o
_arith_cmp("=:=", _o.eq)
_arith_cmp("=\\=", _o.ne)
_arith_cmp("<", _o.lt)
_arith_cmp(">", _o.gt)
_arith_cmp("=<", _o.le)     # ISO spells it =<, never <=
_arith_cmp(">=", _o.ge)


from clausal.logic.constraints import structural_eq as _structural_eq
from clausal.logic.variables import unify as _unify


@_builtin("is", 2)
def _iso_is(result, expr, trail, k):
    """ISO is/2: evaluate Expr, unify with Result.

    NOT Clausal's infix `is`, which is unification (nodes.Unify) and leaves
    `X is 3 + 4` as the term Add(3, 4). Both spellings coexist: Python has no
    infix syntax for `'is'(X, E)`, so they never collide. See
    todo/is-and-eq-are-swapped-relative-to-iso-2026-09-09.md
    """
    if _unify(result, _iso_eval(expr, "is/2"), trail):
        yield None


@_builtin("=", 2)
def _iso_unify(a, b, trail, k):
    if _unify(a, b, trail):
        yield None


@_builtin("\\=", 2)
def _iso_not_unifiable(a, b, trail, k):
    mark = trail.mark()
    ok = _unify(a, b, trail)
    trail.undo(mark)
    if not ok:
        yield None


def _iso_identical(a, b) -> bool:
    """ISO's `==`/2: structurally identical, WITHOUT the int/float (etc.)
    cross-type numeric conflation `structural_eq`/2 carries for its existing
    callers (dif/2, setof/2, …).

    `structural_eq` treats `1` and `1.0` as equal — a deliberately PARKED
    decision (A05-D001/A01-D001,
    todo/audit-2026-07-05/done/fix-A05-structural-eq-asymmetry-consistency.md:
    "do not change direction here, only keep it consistent with whatever
    unify does") that this function must not disturb, because `structural_eq`
    has existing callers depending on it. `'=='`/2 is a BRAND NEW predicate
    with zero existing callers, so it is free to be ISO-correct on its own:
    Scryer measures `1 == 1.0` as false (spec §3.1, "structural identity,
    `1 == 1.0` is false").

    Approach: `structural_eq` already gets everything else right — shape,
    container equivalences (str/char-list, ground SegList/list, …), and var
    identity (two distinct unbound vars are never `==`, matching the ISO
    rule; see its own docstring) — so this only ADDS a stricter requirement,
    never loosens one: given `structural_eq(a, b)` already holds, additionally
    require that fully-grounded `a` and `b` (`_deref_walk`, which also
    materializes any Seg*/String forms into plain containers so comparison
    is representation-independent) produce the same `_normalize_for_key`
    key (A04-F006's existing int/float/bool/complex type-tagging walker —
    reused rather than duplicating a second general-purpose term walker).
    Because this is a conjunction with `structural_eq`, a mismatch this
    second check finds can only turn a True into a False; it can never turn
    a False into a True, so it cannot introduce a new false positive beyond
    tightening the known numeric gap. Measured directly (see task-4-report.md):
    the var-collapsing `_normalize_for_key` does on its own (it maps every
    unbound var to one shared sentinel) never fires here, because whenever
    two terms disagree only on distinct-variable identity, `structural_eq`
    has already returned False and short-circuits the `and` below.
    """
    if not _structural_eq(a, b):
        return False
    from clausal.logic.solve import _deref_walk
    from clausal.logic.tabling import _normalize_for_key
    return _normalize_for_key(_deref_walk(a)) == _normalize_for_key(_deref_walk(b))


@_builtin("==", 2)
def _iso_structural_eq(a, b, trail, k):
    if _iso_identical(a, b):
        yield None


@_builtin("\\==", 2)
def _iso_structural_ne(a, b, trail, k):
    if not _iso_identical(a, b):
        yield None


# ---------------------------------------------------------------------------
# The CLP constraint family: '#=', '#\=', '#<', '#>', '#=<', '#>='.
#
# `==` (this module's own `_iso_structural_eq` above is a DIFFERENT builtin —
# ISO's structural `==`/2) is not what powers Clausal's infix `==`: infix
# `==` compiles to `nodes.ArithEq`, a CLP(FD) arithmetic constraint that
# BINDS and PROPAGATES rather than merely testing. A runtime measurement over
# 1933 corpus call sites (430,945 executions) found 33 sites that take TWO
# arithmetic modes — the same site BINDS on one call and TESTS on another.
# For those, no other ISO spelling works: `'=:='` raises instantiation_error
# on the binding call, and `'is'` is wrong for the testing one. `#=` is the
# only spelling valid in every mode, which is why it is in the spec at all;
# registering it under its own name just gives that existing behaviour a
# callable, ISO-recognisable spelling. The other five members of the family
# (`#\=`, `#<`, `#>`, `#=<`, `#>=`) are their natural CLP(FD) counterparts,
# named the same way for symmetry.
#
# Each target function is imported INSIDE its builtin body, not at module
# import time: `clausal/logic/clpfd.py` swaps in C-accelerated versions of
# these functions further down its own module (clpfd.py:3274+), so a
# top-level `from clausal.logic.clpfd import fd_eq` would capture the
# pure-Python definition and silently test a different function than
# production actually dispatches to.
# ---------------------------------------------------------------------------


@_builtin("#=", 2)
def _clp_eq(a, b, trail, k):
    """CLP arithmetic constraint — binds, propagates, valid in every mode.

    This is what infix `==` ALREADY does: `==` compiles to nodes.ArithEq, a
    CLP(FD) equality constraint. Registering `#=` names an existing
    behaviour rather than adding one. Required by the eq measurement: 33
    corpus sites take two arithmetic modes and `#=` is the only spelling
    correct for all of them.
    """
    from clausal.logic.clpfd import fd_eq
    if fd_eq(a, b, trail):
        yield None


@_builtin("#\\=", 2)
def _clp_ne(a, b, trail, k):
    """CLP(FD) disequality constraint — the negation of `#=`."""
    from clausal.logic.clpfd import fd_ne
    if fd_ne(a, b, trail):
        yield None


@_builtin("#<", 2)
def _clp_lt(a, b, trail, k):
    """CLP(FD)/CLP(R) strictly-less-than constraint."""
    from clausal.logic.clpfd import fd_lt
    if fd_lt(a, b, trail):
        yield None


@_builtin("#>", 2)
def _clp_gt(a, b, trail, k):
    """CLP(FD)/CLP(R) strictly-greater-than constraint."""
    from clausal.logic.clpfd import fd_gt
    if fd_gt(a, b, trail):
        yield None


@_builtin("#=<", 2)
def _clp_le(a, b, trail, k):
    """CLP(FD)/CLP(R) less-than-or-equal constraint."""
    from clausal.logic.clpfd import fd_le
    if fd_le(a, b, trail):
        yield None


@_builtin("#>=", 2)
def _clp_ge(a, b, trail, k):
    """CLP(FD)/CLP(R) greater-than-or-equal constraint."""
    from clausal.logic.clpfd import fd_ge
    if fd_ge(a, b, trail):
        yield None
