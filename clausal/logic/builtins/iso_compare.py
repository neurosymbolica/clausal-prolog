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


@_builtin("==", 2)
def _iso_structural_eq(a, b, trail, k):
    if _structural_eq(a, b):
        yield None


@_builtin("\\==", 2)
def _iso_structural_ne(a, b, trail, k):
    if not _structural_eq(a, b):
        yield None
