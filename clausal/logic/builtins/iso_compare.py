"""ISO comparison, unification and arithmetic builtins under their ISO names.

Reachable from the seam (`.seam`) ONLY through the quoted canonical form —
`'=:='(A, B)` — because Python has no infix syntax for these; natively in
Clausal Prolog (`.clausal`) and `.pl`.
Spec: docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md
"""
import operator as _o
from decimal import Decimal as _Decimal
from fractions import Fraction as _Fraction

from clausal.logic.number_kinds import (
    decimal_scale as _decimal_scale_kind, numeric_kind as _numeric_kind,
)

from clausal.logic.atoms import is_atom, mint, spelling
from clausal.logic.variables import deref as _deref, is_var as _is_var
from clausal.logic.builtins._helpers import _arity as _term_arity
from clausal.logic.builtins._helpers import _cell_functor
from clausal.logic.builtins._helpers import _functor_name as _term_functor_name
from clausal.logic.builtins._helpers import _standard_order_key
from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins.inspection import _univ__2 as _iso_univ_impl
from clausal.logic.constraints import structural_eq as _structural_eq
from clausal.logic.exceptions import (
    LogicException, instantiation_error, term_functor_args,
    type_error,
)
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.variables import deref, is_var
from clausal.logic.variables import unify as _unify
from clausal.terms import ConcreteSeg, DictTerm, SegList, SetTerm, VarSeg
from clausal.terms import Quantity as _Quantity
from clausal.terms import UnitsMismatch as _UnitsMismatch


def _clpfd_leaf_culprit(exc: LogicException):
    """The offending LEAF out of a `_eval_ground` leaf error, or None.

    `_eval_ground` (clausal/logic/clpfd.py) never catches an exception
    itself. What it lets escape is either its own
    `_unknown_expr_leaf_error(leaf)` — `error(domain_error(clpz_expression,
    Leaf), _)`, prose "clpfd expression" — or an evaluable entry's ISO
    error (`evaluation_error(zero_divisor)`, `type_error(integer, X)`,
    `type_error(float, X)`, ...), each bubbled up unchanged through any
    amount of recursion. Matching the leaf error's literal shape (rather
    than translating every `LogicException`) means every other error fails
    closed: it is re-raised as-is instead of being mislabelled `evaluable`.
    """
    term = exc.term
    outer = term_functor_args(term)
    if outer is None or outer[0] != "error" or len(outer[1]) != 2:
        return None
    inner = term_functor_args(outer[1][0])
    if inner is None or inner[0] != "domain_error" or len(inner[1]) != 2:
        return None
    expected, leaf = inner[1]
    if not (is_atom(expected) and spelling(expected) == "clpz_expression"):
        return None
    # The clpfd leaf error has no culprit indicator: its second argument is
    # an unbound variable (Scryer's form) and "clpfd expression" is the
    # exception's prose, set when the exception was built.
    if not is_var(outer[1][1]) or exc.message != "clpfd expression":
        return None
    return leaf


def _evaluable_culprit(leaf):
    """*leaf* as ISO's `Name/Arity` culprit for `type_error(evaluable, …)`.

    ISO's culprit for `type_error(evaluable, …)` is a `Name/Arity` INDICATOR,
    never the offending term itself, so this maps whatever `_eval_ground`
    handed back onto that shape with the engine's own functor/arity
    accessors — the same `_helpers._functor_name` / `_helpers._arity` pair
    `functor/3` uses, so an atom, a cell, a term instance and a
    list all answer consistently. Measured directly: `_ is foo + 1` gives
    Scryer `error(type_error(evaluable,foo/0),(is)/2)`, and this yields
    `foo/0`.

    Previously this tested for the (since retired) `Compound` class, which
    was DEAD for a compound reaching here from seam source. Measured
    2026-09-09: `'=:='(1, foo(bar))` hands this function the cell tuple
    `('foo', ('bar',))`, not a class instance, so the branch never
    fired and the raw term leaked out as the culprit —
    `type_error(evaluable, foo(bar))`, which is not a legal ISO indicator at
    all.

    Matching Scryer's culprit IDENTITY for a compound is a separate,
    still-OPEN question and is deliberately not attempted here. Scryer
    evaluates arguments first, so its culprit is the innermost non-evaluable
    leaf; measured 2026-09-09, and re-checked 2026-09-30 against the clean
    reference build /workspace/scryer-prolog-clpq/target/release/scryer-prolog
    (the path tests take from tests/_oracles.py):

        1 =:= foo(bar)     error(type_error(evaluable,bar/0),(is)/2)
        1 =:= f(g(h))      error(type_error(evaluable,h/0),(is)/2)
        1 =:= foo(bar,baz) error(type_error(evaluable,bar/0),(is)/2)
        1 =:= foo(1)       error(type_error(evaluable,foo/1),(is)/2)
        1 =:= [1,2]        error(type_error(evaluable,[]/0),(is)/2)

    `clpfd._eval_ground` reports the whole offending SUBTERM as its leaf
    instead of descending, so this yields `foo/1` where Scryer yields
    `bar/0`. Reproducing Scryer's answer would mean re-deriving its
    evaluation order here from four data points, i.e. guessing; the
    divergence is PINNED instead — see
    `test_compound_evaluable_culprit_OPEN_iso_divergence` in
    tests/iso/test_iso_compare_errors.py.

    A shape with no functor/arity at all is passed through unchanged rather
    than guessed at.
    """
    arity = _term_arity(leaf)
    if arity is None:
        return leaf
    name = _term_functor_name(leaf)
    if isinstance(name, str):
        name = mint(name)
    return ("/", name, arity)


def _iso_eval(term, context: str):
    """Evaluate an arithmetic term to a number, with ISO's errors.

    `clpfd._eval_ground` returns None for an unbound operand and raises its own
    leaf error for a non-number; ISO wants instantiation_error and
    type_error(evaluable, F/N). Scryer attributes BOTH to (is)/2 regardless of
    which comparison raised them — pin what it does, not what reads tidily.

    `_eval_ground`'s own leaf error is clpz's `domain_error(clpz_expression,
    Leaf)` (prose "clpfd expression") — a CLP(FD)-flavoured shape, not ISO's
    `type_error(evaluable, Name/Arity)` for `is/2`. Measured directly against Scryer:
    `_ is foo + 1` -> `error(type_error(evaluable,foo/0),(is)/2)`. Reconciled
    here, at the call site, rather than in `_eval_ground` itself — that
    function is shared by every other CLP(FD) caller in the engine and its
    "clpfd expression" shape is correct for THEM; only `is`/the comparisons
    need the ISO term.
    """
    # EVALUATION, not a CLP post: ``/`` is Scryer's / Python's float division
    # here (ruling Q15, 2026-09-28), where the CLP evaluator keeps it
    # rational -- so is/2 and the ISO comparisons evaluate through the
    # evaluable table's own evaluator, as eval_/2 does.
    from clausal.logic.exact_arith import evaluate
    from clausal.logic.variables import present_number
    t = deref(term)
    if is_var(t):
        raise LogicException(instantiation_error(context))
    try:
        try:
            value = evaluate(t, context)
        except _UnitsMismatch as e:
            raise _units_mismatch(context, e) from None
        if isinstance(value, _Quantity):
            # A quantity is a number with a unit (a declared constant's
            # value, folded in: ``Q is 100 * constant(one_euro)``).  One
            # whose units cancelled (``constant(max_fine) /
            # constant(one_euro)``) is a plain number, as the seam gives it.
            if not value._dims:
                return present_number(value._value)
            return value
        if not isinstance(value, (int, float, _Fraction, _Decimal)) or isinstance(value, bool):
            raise LogicException(
                type_error("evaluable", _evaluable_culprit(value), context))
        return present_number(value)
    except LogicException as e:
        leaf = _clpfd_leaf_culprit(e)
        if leaf is None:
            raise
        raise LogicException(
            type_error("evaluable", _evaluable_culprit(leaf), context)) from None
    except Exception:
        # Same culprit shape as the reconciled branch above: an ISO
        # `type_error(evaluable, …)` culprit is a Name/Arity indicator, so
        # this fallback must not hand back a raw term either.
        raise LogicException(
            type_error("evaluable", _evaluable_culprit(t), context)) from None


def _units_mismatch(context: str, e: Exception) -> LogicException:
    """A units mismatch as the seam raises it in a comparison:
    ``error(system_error(units_mismatch), _)``, catchable by ``catch/3``."""
    from clausal.logic.units_clp import _mismatch_text  # noqa: PLC0415
    return _mismatch_text(context, str(e))


def _quantity_operands(x, y, context: str):
    """The magnitudes to compare when either side is a quantity: both sides
    must carry the SAME units (Quantity._cmp_value), else units_mismatch --
    for ``=:=`` and ``=\\=`` too, which would otherwise quietly answer
    false/true for ``100 euro =:= 100``."""
    try:
        if isinstance(x, _Quantity):
            return x._cmp_value(y)
        b, a = y._cmp_value(x)
        return a, b
    except _UnitsMismatch as e:
        raise _units_mismatch(context, e) from None


def _arith_cmp(name, op):
    # `fields` is passed EXPLICITLY rather than inferred. `_registry.
    # _extract_fields_simple` computes a builtin's term fields as
    # `params[:-2]` (strip `trail, k`), so any extra parameter here — the
    # closure-capture defaults `_op=op, _name=name` this function used to
    # carry — pushes `trail`/`k` back into the field tuple and REGISTERS THE
    # TERM CLASS AT ARITY 4. Measured 2026-09-09 before the fix:
    # `_BUILTIN_FIELDS[('=:=', 2)] == ('a', 'b', 'trail', 'k')`,
    # `get_builtin_class('=:=')` -> `<Predicate =:=/4 …>`, and
    # `functor('=:='(1, 2), N, A)` gave `A = 4` (controls: `'#='` -> 2,
    # `structural_eq` -> 2). The class IS the term constructor, so the
    # translator, the seam and the reified-term tooling all saw arity 4 with
    # two junk unbound variables. `op` is captured by CLOSURE, which is
    # already correct — each `_arith_cmp` call has its own binding.
    @_builtin(name, 2, fields=("a", "b"))
    def _cmp(a, b, trail, k):
        x, y = _iso_eval(a, "is/2"), _iso_eval(b, "is/2")
        if isinstance(x, _Quantity) or isinstance(y, _Quantity):
            x, y = _quantity_operands(x, y, "is/2")
        if op(x, y):
            yield None
    _cmp.__name__ = f"_iso_cmp_{name}"
    return _cmp


_arith_cmp("=:=", _o.eq)
_arith_cmp("=\\=", _o.ne)
_arith_cmp("<", _o.lt)
_arith_cmp(">", _o.gt)
_arith_cmp("=<", _o.le)     # ISO spells it =<, never <=
_arith_cmp(">=", _o.ge)


def _cycle_unify(a, b, trail) -> bool:
    """Plain unify (what `'='`/2, `'\\='`/2 and `'is'`/2's result step run),
    made safe against a cyclic or very-deep term WITHOUT paying for it on
    the overwhelmingly common acyclic call: this tries the engine's own
    `unify` FIRST, unchanged, and only falls back to the explicit-stack
    walk (`_cycle_unify_walk`, below) on the one failure mode that means
    "this term is too deep or cyclic for a recursive walk" —
    ``RecursionError``. Every acyclic call is therefore LITERALLY a call to
    `unify` with nothing around it but a `try`/`except RecursionError`
    (and the `except` branch is never entered for an acyclic term, so its
    cost there is the `try` setup only) — not a parallel reimplementation
    that merely resembles `unify`'s behaviour, so trail effects, hook
    firing and every documented divergence are
    `unify`'s own, by construction, for every term this does not need the
    walk for.

    Safe to catch: `unify`'s depth cap (`MAX_DEPTH` in
    `clausal/logic/variables/_variables.c`) is a C-level counter checked at
    the TOP of every recursive step, before doing any further work or
    recursing deeper — not CPython's own interpreter recursion limit, and
    not an uncontrolled stack walk that might segfault before the check
    fires. Measured directly (not assumed): calling the raw `unify` on
    this exact cyclic pair, 5 times in one process, raised a clean,
    catchable `RecursionError` every time with no process death (the
    independent Ciao-sweep harness this bug was found by, `run_cases.py`,
    already relies on exactly this — it caught the same exception and kept
    running hundreds more cases afterward in the SAME process).

    `unify`'s own C wrapper (`do_unify_and_wake`) ALSO already takes a
    mark before it starts and undoes every binding it made back to that
    mark on ANY non-success return — an ordinary mismatch (0) and an error
    (-1, including this `RecursionError`) are handled by the identical
    line, `trail_undo_to(trail, mark)` — and discards its OWN per-call
    wakeup list without ever firing it when that happens. So by the time
    this function's `except RecursionError` runs, every BINDING (and
    attribute-state change) the aborted attempt made is already undone —
    nothing here needs to re-undo what `unify` already undid. A mark is
    therefore taken only in the `except` branch below, against that
    already-clean state, not before the `try` (an earlier version of this
    function took it before the `try` too, redundantly: nothing on the
    success path ever reads it, and the C wrapper's own mark/undo makes it
    unnecessary on the exception path as well — it was ~20ns of pure
    waste on the one path that matters for performance).

    One SPECIFIC case is NOT "no hook fired for the aborted attempt": a
    term whose shape has its own `__unify__` hook that re-enters `unify`
    itself — a SegList (partial list), a chars carrier's own protocol —
    calls the TOP-LEVEL `unify()` again per element from WITHIN the
    aborted attempt's own C descent, each such nested call its OWN
    `do_unify_and_wake` scope with its OWN wakeup list fired immediately
    on success (`clausal/logic/pending.py`'s own module docstring: "a
    unification nested in it — a term's `__unify__` unifying element by
    element … — only queues [goals]", not hooks). So a hook THROUGH one of
    those shapes genuinely can fire during the aborted fast attempt, and
    the OUTER `trail_undo_to` still undoes its binding/attribute-state
    effect once the RecursionError propagates out — the check function
    ran, but the trail ends up exactly as if it had not, the same
    not-fully-atomic-on-non-trail-effects property `_cycle_unify_walk`'s
    own leaf-by-leaf calls already have (see its docstring).

    `unify_with_occurs_check`/2 never reaches this function: it is a
    SEPARATE C entry point (`clausal/logic/variables/_variables.c`'s
    `occurs_check`/`unify_with_occurs_check`, imported directly by
    `clausal/logic/builtins/inspection.py::_unify_with_occurs_check__2` and
    `clausal/logic/constraints.py::_structural_unify_oc`), and neither of
    those two call sites — nor anything else in the tree — names
    `_cycle_unify` (`grep -rn _cycle_unify clausal/` turns up only this
    file's own three builtins: `'is'`, `'='`, `'\\='`).

    The SAME explicit-stack / seen-pairs pattern `==`/2's own walk already
    uses (`a480b5b8` "==/2 terminates on a cyclic term", `51f4e844` "a
    cyclic partial list walks as its cons cells") is what the FALLBACK,
    not the default path, now runs — a pair already in progress is
    skipped rather than re-descended. See `_cycle_unify_walk` for why the
    fallback needs its OWN trail mark/undo and `defer`/`run_first`
    discipline, rather than just calling that walk directly.
    """
    try:
        return bool(_unify(a, b, trail))
    except RecursionError:
        pass
    return _cycle_unify_fallback(a, b, trail)


def _cycle_unify_fallback(a, b, trail) -> bool:
    """`_cycle_unify`'s slow path, for a caller that has already tried
    `_unify` and caught its RecursionError (the builtins below inline the
    fast attempt so the common call pays no extra Python frame)."""
    # Slow path. `_unify`'s own internal mark/undo (see the docstring
    # above) already rolled back whatever the aborted fast attempt had
    # bound, so a mark taken HERE -- not before the `try`, where it would
    # sit unused on the success path -- still denotes "the state as of
    # entering this function": nothing has changed under us since.
    mark = trail.mark()
    #
    # Unlike a single `unify()` call's recursive C descent -- which
    # defers EVERY attribute hook of the WHOLE structure until that one
    # descent succeeds, firing none of them on failure -- this walk calls
    # `unify()` again per LEAF pair, so each successful leaf's hooks fire
    # as that leaf is processed, not held back for the pairs after it.
    # That is the SAME granularity a term's own `__unify__` already uses
    # when it unifies element by element by calling back into `unify()`
    # (clausal/logic/pending.py's module docstring: "a unification nested
    # in it -- a term's `__unify__` unifying element by element, a hook, a
    # woken goal -- only queues"), not a new discipline invented here, and
    # `trail.defer` is what keeps it from running a woken GOAL at the
    # wrong moment: set for the whole walk (saved and restored, the same
    # idiom `clausal/logic/_trampoline_py.py::_drive_to_root_yield` uses),
    # a nested leaf `unify()` call sees it already set and only QUEUES
    # what it wakes, same as that term-level nesting does, instead of
    # draining the queue itself mid-walk.
    #
    # What IS new here, because the engine's own wrapper does not need it
    # for a single descent: if a LATER leaf fails after an EARLIER one
    # already bound (and already fired that binding's own hooks), this
    # function's OWN mark is what undoes those earlier bindings (and any
    # attribute-state change a hook recorded on the trail) before
    # reporting failure -- trail state ends up exactly as if nothing had
    # run, even though a hook's CHECK function itself may have executed
    # once for a binding that is later rolled back. A hook whose only
    # observable effect is trail-tracked state (the normal case: dropping
    # or re-attaching a constraint) is therefore fully restored; one with
    # an effect OUTSIDE the trail (arbitrary IO) is not made atomic by
    # this, but it was never atomic on that axis elsewhere in the engine
    # either (the same per-element `__unify__` nesting above already
    # fires hooks before an enclosing failure is known).
    bare = not trail.defer
    if bare:
        trail.defer = True
    try:
        ok = _cycle_unify_walk(a, b, trail)
    finally:
        if bare:
            trail.defer = False
    if ok and bare:
        from clausal.logic.pending import run_first  # noqa: PLC0415
        ok = run_first(trail)
    if not ok:
        trail.undo(mark)
    return ok


def _cycle_unify_walk(a, b, trail) -> bool:
    """The slow, cycle-safe fallback `_cycle_unify` reaches only after the
    fast `unify` raised ``RecursionError`` -- see its docstring for why
    that is safe to catch and why the trail is already clean by then.

    Before this existed, the Ciao `iso_tests` cases `unify_test16`
    (``'='(f(X, Y, X, 1), f(a(X), a(Y), Y, 2))``) and `not_uni_test15`
    (the same pair through `'\\='`/2) crashed the engine's C `unify` with a
    raw ``RecursionError: unify: term nesting too deep`` instead of
    producing a clean Prolog outcome. `X = a(X)` and `Y = a(Y)` each bind a
    variable into a term that contains itself — ISO 7.3.2/8.2.2 require
    plain `=`/2 (unlike `unify_with_occurs_check`/2) to allow exactly that —
    and the third argument then asks to unify X (now bound to the cyclic
    `a(X)`) against Y (bound to the cyclic `a(Y)`): a naive recursive walk
    re-enters that same pair of terms forever and hits the depth cap.
    Treating a REVISITED pair as already settled — a rational-tree
    unifier's cycle closes the proof instead of re-deriving it — lets that
    third argument through cleanly, and the FOURTH argument (`1` against
    `2`) then decides the whole unification: `fails`, the Ciao-asserted and
    ISO-correct outcome, not a crash. (`'\\='`/2 on the same pair therefore
    `not_fails`: the trial unification it runs internally fails for the
    same reason, so the negation succeeds.)

    Delegates every LEAF case — either side still an unbound variable after
    deref (a var-to-anything bind is O(1), no structural walk, so it is safe
    even when the other side is cyclic or huge) and any pair where neither
    side is a dataclass term instance, a compound CELL, or a plain `list`
    — to the engine's own `unify`, so atoms, numbers, strings, SegLists,
    DictTerms, SetTerms, bytes and Quantities keep its EXACT existing
    semantics, which this function does not touch (since 2026-10-23 those
    include refusing an int against a float,
    todo/done/iso-unify-conflates-int-and-float-2026-09-09.md). A cycle folded entirely inside one of
    those delegated shapes (e.g. a cyclic SegList reached only through a
    dict value) is a narrower, pre-existing gap this does not close — none
    of the ISO suite's current cases need it, so it is left as a known
    residual rather than papered over here.

    A compound term is, UNCONDITIONALLY since P3-2 (clausal/logic/cells.py
    module docstring, "every compound term compiles to a cell"), a plain
    `tuple` whose slot 0 is its functor name — `f(X, Y, X, 1)` is
    `('f', X, Y, X, 1)`. That tuple shape is NOT unique to compounds: the
    str/char-list carrier (`"ab"` as `('$chars', 'ab')`) and a tuple-DATA
    cell use the SAME `(str-or-tag, ...)` shape with a reserved tag in slot
    0. `_cell_functor` (`clausal/logic/builtins/_helpers.py`, the funnel's
    own single cell-shape check — the same one `functor/3`/`arity/2` use)
    is what tells them apart: it answers `(True, 'f')` for the former and
    `(False, None)` for the latter, deliberately excluding `'$chars'`/the
    `tuple`-type tag. Recursing into every plain `(str, ...)` tuple
    regardless (an EARLIER version of this function did, matching on
    `isinstance(x, tuple)` alone) broke `'='("ab", [a, b])` — a `('$chars',
    'ab')` cell paired against a plain char-list `['a', 'b']` is NOT two
    cells to recurse elementwise, it is exactly the Liskov str↔char-list
    case the engine `unify` already has its own protocol for — so this
    asks `_cell_functor` first and only recurses when BOTH sides answer a
    real compound functor.
    """
    stack = [(a, b)]
    seen: set = set()
    keep: list = []       # pins visited objects: an id is never reused
    while stack:
        x, y = stack.pop()
        x = deref(x)
        y = deref(y)
        if x is y:
            continue
        if is_var(x) or is_var(y):
            if not _unify(x, y, trail):
                return False
            continue
        if is_term_instance(x) and is_term_instance(y):
            if type(x) is not type(y):
                return False
            key = (id(x), id(y))
            if key in seen:
                continue
            seen.add(key)
            keep.append((x, y))
            stack.extend((getattr(x, f), getattr(y, f))
                         for f in term_field_names(x))
            continue
        is_cell_x, fx = _cell_functor(x)
        is_cell_y, fy = _cell_functor(y)
        if is_cell_x and is_cell_y:
            if fx != fy or len(x) != len(y):
                return False
            key = (id(x), id(y))
            if key in seen:
                continue
            seen.add(key)
            keep.append((x, y))
            stack.extend(zip(x[1:], y[1:]))
            continue
        if not is_cell_x and not is_cell_y and type(x) is list and type(y) is list:
            if len(x) != len(y):
                return False
            key = (id(x), id(y))
            if key in seen:
                continue
            seen.add(key)
            keep.append((x, y))
            stack.extend(zip(x, y))
            continue
        if not _unify(x, y, trail):
            return False
    return True


@_builtin("is", 2)
def _iso_is(result, expr, trail, k):
    """ISO is/2: evaluate Expr, unify with Result.

    NOT Clausal's infix `is`, which is unification (nodes.Unify) and leaves
    `X is 3 + 4` as the term Add(3, 4). Both spellings coexist: Python has no
    infix syntax for `'is'(X, E)`, so they never collide. See
    todo/is-and-eq-are-swapped-relative-to-iso-2026-09-09.md

    FIXED 2026-10-15 (Ciao `iso_tests` `is_test4`, `3 is 3.0`): ISO's
    implicit unification of Result against the evaluated expression is
    `=`/2's unification, which is type-sensitive between numeric kinds —
    `3` and `3.0` do not unify even though `3 =:= 3.0` — the same way
    `3 == 3.0` is false. When this was fixed the engine's shared `unify`
    still conflated int/float for its other callers, so this guarded ONLY
    is/2's own final step: `_numeric_types_agree` (`'=='`/2's check for the
    identical question) runs first and, when Result is already bound to a
    numeric leaf of a DIFFERENT numeric kind than the evaluated expression,
    is/2 fails before ever reaching `unify`, while an unbound Result
    (`X is 3.0`) is untouched and binds exactly as before.  Since
    2026-10-23 `unify` itself refuses the cross-kind pair (ISO 7.3, see
    `_iso_unify`), so the guard is now an early answer to the same
    question, kept because it costs nothing on the common unbound-Result
    path and documents the ruling at the site it was first applied.
    """
    value = _iso_eval(expr, "is/2")
    # The evaluated value is a number, never a cyclic term, so the engine's
    # own unify is safe here without the cyclic fallback; and an unbound
    # Result (the common `X is E`) needs no numeric-kind check.
    r = _deref(result)
    if _is_var(r):
        if _unify(r, value, trail):
            yield None
    elif _numeric_types_agree(r, value) and _unify(r, value, trail):
        yield None


@_builtin("=", 2)
def _iso_unify(a, b, trail, k):
    """ISO =/2: unification.

    Type-sensitive between numeric kinds since 2026-10-23 (operator ruling,
    ISO 7.3): `'='(1, 1.0)` fails, as Scryer answers, because the shared
    `unify` itself refuses a number against a number of another kind (see
    `variables/_variables.c::numeric_kind`;
    todo/done/iso-unify-conflates-int-and-float-2026-09-09.md).

    Cyclic-term safe since 2026-10-15 via `_cycle_unify` (see its docstring)
    — previously a term built to contain itself, e.g. through a third
    argument that equates two already-cyclic subterms, raised a raw
    ``RecursionError`` instead of failing or succeeding cleanly.
    """
    # `_cycle_unify` inlined: the fast attempt costs no extra frame.
    try:
        ok = _unify(a, b, trail)
    except RecursionError:
        ok = _cycle_unify_fallback(a, b, trail)
    if ok:
        yield None


@_builtin("\\=", 2)
def _iso_not_unifiable(a, b, trail, k):
    from clausal.logic.pending import run_first  # noqa: PLC0415
    mark = trail.mark()
    # \+ A = B: the goals the unification wakes run inside the negation.
    # _cycle_unify (not the raw engine _unify): see its docstring — the
    # same cyclic-term pair that must crash neither succeeds nor fails
    # cleanly.
    ok = _cycle_unify(a, b, trail) and run_first(trail)
    trail.undo(mark)
    if not ok:
        yield None


def _numeric_tag(x):
    """The numeric type tag of *x*, or None if *x* is not a tagged number.

    EVERY numeric type is its own kind, so `==` is an equivalence relation
    and `compare(=, X, Y) <=> X == Y` — the identity ISO guarantees — can hold
    by construction. Returns a TYPE OBJECT: nothing is wrapped, no term
    representation changes, and arithmetic never sees this.

    The ONE spelling is `clausal.logic.number_kinds.numeric_kind`, which the
    unifier (`_variables.c::numeric_kind`, since the 2026-10-23 ruling that
    `1 = 1.0` fails, ISO 7.3), `structural_eq`, tabling's variant keys and
    setof/3's dedup share, so every mechanism counts the same number of
    terms.  `Decimal`/`Fraction` used to be left untagged here to mirror
    tabling (the A01-D001 residual); measured 2026-09-09 that made `==`
    non-transitive (`1.0 == Decimal(1)` and `Decimal(1) == 1` while
    `1.0 == 1` was false), so they were tagged here first, and tabling
    followed on 2026-10-23.

    An exact-number CELL (``('decimal', M, S)``, ``('rdiv', N, D)``) is NOT
    tagged, deliberately: ``structural_eq`` already separates a cell from
    its object and two cells of different spelling, so a tag for cells would
    change no answer -- measured 2026-09-17 by mutation (disabling such a
    tag failed 0 of 11 guard tests).  The cell is handled where it IS
    observable: the order key (``_helpers._standard_order_key``) and the
    evaluator leaf (``clpfd._eval_ground``).  Spec §4a.
    """
    return _numeric_kind(x)


def _decimal_scale(x: _Decimal) -> int:
    """Decimal places of a Decimal object (``1.00`` -> 2); `number_kinds`'s."""
    return _decimal_scale_kind(x)


def _numeric_types_agree(a, b) -> bool:
    """False ONLY when *a* and *b* have CORRESPONDING numeric leaves whose
    types differ; True for everything else.

    That one-way property is the whole design. This runs as a second
    conjunct after `structural_eq` has already said "equal", so its only job
    is to answer the cross-type NUMERIC question ISO cares about (`1 == 1.0`
    is false) — and it must never answer "different" for a difference of
    REPRESENTATION that `structural_eq` deliberately blesses.

    The previous implementation (`_normalize_for_key(_deref_walk(a)) ==
    _normalize_for_key(_deref_walk(b))`) was a whole-term key comparison, so
    every representational difference read as "different" too. Measured
    2026-09-09 under `-double_quotes(chars)`, that made

        '=='("ab", [a, b])    ->  no      (Scryer: YES; spec §3.3: true)
        '\\=='("ab", [a, b])  ->  yes     (Scryer: no)

    while `'='("ab", [a, b])` stayed yes — `'='` and `'=='` disagreeing on a
    GROUND pair, which ISO does not permit. `_deref_walk` does not
    materialize a `str` into its char list, so the keys compared were `'ab'`
    against `[('a',), ('b',)]`.

    Descent therefore happens ONLY through shapes that line up on both sides
    (same Python type, same length/functor/fields). Any mismatch — a `str`
    against a list of char atoms, a `SegList` against a plain list, an
    unrecognised shape — stops with True, i.e. "no numeric objection", which
    falls back exactly onto `structural_eq`'s own answer. Being incomplete is
    therefore SAFE by construction: it can only ever fail to tighten, never
    wrongly reject.
    """
    # An explicit stack, not recursion: a cons chain ``[1,2,...|foo]`` nests
    # one tuple per element, and a few hundred cells overflowed Python's
    # stack (RecursionError) once ``structural_eq`` had said "equal".  The
    # answer is a pure conjunction over the pairs, so the visiting order is
    # free.  A pair already visited is skipped: the answer for a pair is a
    # pure function of the two objects, and a CYCLIC term (``X = f(X)``)
    # would otherwise be walked forever.  Children are pushed reversed, so
    # they are visited left to right, as the recursive version did (an error
    # from a leaf surfaces in the same order).
    stack = [(a, b)]
    seen: set = set()
    keep: list = []     # strong references: a seen id is never reused
    while stack:
        a, b = stack.pop()
        a = deref(a)
        b = deref(b)
        if a is b:
            continue            # one object: its numeric leaves are its own
        ta = _numeric_tag(a)
        tb = _numeric_tag(b)
        if ta is not None or tb is not None:
            # Only a PAIR of tagged numbers raises the cross-type question. A
            # tagged number against an UNTAGGED one -- `Decimal`/`Fraction`,
            # which `_normalize_for_key` also leaves untagged, so
            # `Decimal('1')` and `1` already read as identical today -- is
            # not this check's business and gets no objection.
            if ta is None or tb is None:
                continue
            if ta is not tb:
                return False
            # RULED 2026-09-17 Q2: two decimals of equal VALUE and different
            # SCALE are distinct terms (``1.0`` vs ``1.00``, the analogue of
            # ISO's ``1`` vs ``1.0``).  Python's ``Decimal.__eq__`` ignores
            # scale, so the objection has to be raised here, where the order
            # key raises it too (``_helpers._number_key``) -- that agreement
            # is what keeps ``compare(=, X, Y) <=> X == Y`` true by
            # construction.
            if ta is _Decimal and _decimal_scale(a) != _decimal_scale(b):
                return False
            continue
        # The pair is keyed BEFORE a SegList is read: the walk below makes
        # fresh objects, and a cyclic partial list (``X = [a|X]``) walks to
        # a cons cell whose tail is the SegList itself, so only the term's
        # own objects can close the loop.  ``keep`` pins them.
        key = (id(a), id(b))
        if key in seen:
            continue
        seen.add(key)
        keep.append((a, b))
        if isinstance(a, SegList) or isinstance(b, SegList):
            # A hole-built list is read as the term it denotes, so it lines
            # up with the literal: ``X = [a|T], T = 1`` against ``[a|1.0]``
            # (cons cells), ``T = [1]`` against ``[a, 1.0]`` (a list), and
            # a partial list against a partial list (round 4 of the
            # improper-tail fix; before, a SegList against anything but a
            # SegList stopped here with "no objection", so ``==`` said yes).
            a = _seg_term(a)
            b = _seg_term(b)
            keep.append((a, b))
        if type(a) is not type(b):
            continue
        if isinstance(a, (list, tuple)):
            if len(a) == len(b):
                stack.extend(reversed(list(zip(a, b))))
        elif isinstance(a, DictTerm):
            if not _dict_numeric_types_agree(a.data, b.data):
                return False
        elif isinstance(a, dict):
            if not _dict_numeric_types_agree(a, b):
                return False
        elif isinstance(a, SetTerm):
            if not _set_numeric_types_agree(a.elements, b.elements):
                return False
        elif isinstance(a, (set, frozenset)):
            if not _set_numeric_types_agree(a, b):
                return False
        elif is_term_instance(a):
            fields = term_field_names(a)
            if fields == term_field_names(b):
                stack.extend(reversed([(getattr(a, f), getattr(b, f))
                                       for f in fields]))
    return True


_PARTIAL = "$partial"      # marks a partial list's items, so only two line up


def _seg_term(x):
    """A SegList as the term `_numeric_types_agree` can pair up: its element
    list when ground, its cons cells when it is an improper (or cyclic)
    list, or, when it is still partial, the tuple ``($partial, item, ...)``
    of its elements with each open hole as that hole's variable -- so two
    partial lists of one shape pair element by element and a hole pairs
    with a hole.  Anything else, and a SegList the walk cannot read, is
    returned as is (the type check then stops the descent: no objection)."""
    if not isinstance(x, SegList):
        return x
    w = x._walk_once()
    if w is None:
        return x
    if isinstance(w, SegList):
        items = [_PARTIAL]
        for seg in w._segments:
            if isinstance(seg, VarSeg):
                items.append(seg.var)
            elif isinstance(seg, ConcreteSeg):
                items.extend(seg.elements)
            else:
                return x
        return tuple(items)
    return w


def _dict_numeric_types_agree(a, b) -> bool:
    """Values under matching keys; a key set that does not line up is not a
    numeric objection."""
    if len(a) != len(b):
        return True
    for key, value in a.items():
        if key not in b:
            return True
        if not _numeric_types_agree(value, b[key]):
            return False
    return True


def _set_numeric_types_agree(a, b) -> bool:
    """Set elements cannot be paired up positionally, so compare the MULTISET
    of numeric element types — enough to separate `{1}` from `{1.0}` without
    inventing a pairing."""
    def tags(elements):
        return sorted(t.__name__ for t in map(_numeric_tag, elements)
                      if t is not None)
    return tags(a) == tags(b)


def _iso_identical(a, b) -> bool:
    """ISO's `==`/2: structurally identical, WITHOUT the int/float (etc.)
    cross-type numeric conflation `structural_eq`/2 carries for its existing
    callers (dif/2, setof/2, …).

    `structural_eq` treats `1` and `1.0` as equal — a deliberately PARKED
    decision (A05-D001/A01-D001,
    todo/done/fix-A05-structural-eq-asymmetry-consistency.md:
    "do not change direction here, only keep it consistent with whatever
    unify does") that this function must not disturb, because `structural_eq`
    has existing callers depending on it. `'=='`/2 is a BRAND NEW predicate
    with zero existing callers, so it is free to be ISO-correct on its own:
    Scryer measures `1 == 1.0` as false (spec §3.1, "structural identity,
    `1 == 1.0` is false").

    `structural_eq` already gets everything else right — shape, the container
    equivalences (str↔char-list, ground SegList↔list, DictTerm↔dict,
    SetTerm↔set) and var identity — so the only thing added on top is the
    cross-type NUMERIC objection of `_numeric_types_agree`, which by
    construction can only tighten and never reject a difference of mere
    representation. Measured 2026-09-09 under `-double_quotes(chars)`, all
    three of Clausal `'='`, Scryer `==` and spec §3.3 agree that
    `'=='("ab", [a, b])` is TRUE, and this conjunction keeps it true while
    still answering no to `'=='(1, 1.0)`.
    """
    a = deref(a)
    b = deref(b)
    if type(a) is SegList and type(b) is SegList:
        # Two hole-built lists (the common case of a list built through its
        # open tail): read each ONCE.  ``structural_eq`` on the SegLists
        # walks both, and ``_numeric_types_agree`` would walk both again
        # (``_seg_term``) and then visit every element pair in Python --
        # measured as ~1.85x on ``==`` over two equal 100-element lists.
        pa = _seg_list_parts(a)
        pb = _seg_list_parts(b)
        if pa is not None and pb is not None:
            ea, ta = pa
            eb, tb = pb
            # ``[E1..En|T1] == [F1..Fm|T2]``: one tail variable (or both
            # proper), equal lengths, and the elements pairwise identical.
            # That is exactly what ``structural_eq`` (unify with no
            # bindings) answers for this shape, read off the walked parts.
            if ta is not tb or len(ea) != len(eb):
                return False
            if not _structural_eq(ea, eb):
                return False
            if _int_or_atom_leaves(ea) and _int_or_atom_leaves(eb):
                # No float/Decimal/... leaf on either side: every pair of
                # tagged leaves is int against int, so the numeric
                # objection cannot arise.
                return True
            return _numeric_types_agree(ea, eb)
    if not _structural_eq(a, b):
        return False
    return _numeric_types_agree(a, b)


# Element types that hold no tagged number other than int: an atom, an int,
# a truth atom.  Deliberately NOT a variable (an element may be a bound one)
# nor any compound (it may hold a float).
_INT_OR_ATOM = frozenset({int, str, bool})


def _int_or_atom_leaves(elements) -> bool:
    return _INT_OR_ATOM.issuperset(map(type, elements))


def _seg_list_parts(x):
    """The SegList *x* read once as ``(elements, tail)``: *tail* the open
    tail's unbound variable, or None for a proper list.  None when *x* is
    any other shape -- an improper or cyclic list, a hole that is not the
    tail, a SegList out of contract -- which the general path answers."""
    w = x._walk_once()
    if isinstance(w, list):
        return w, None
    if type(w) is not SegList:
        return None
    segs = w._segments
    if not segs or type(segs[-1]) is not VarSeg:
        return None
    elements = []
    for seg in segs[:-1]:
        if type(seg) is not ConcreteSeg:
            return None
        elements.extend(seg.elements)
    tail = deref(segs[-1].var)
    if not is_var(tail):
        return None
    return elements, tail


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
# 1933 downstream call sites (430,945 executions) found 33 sites that take TWO
# arithmetic modes — the same site BINDS on one call and TESTS on another.
# For those, no other ISO spelling works: `'=:='` raises instantiation_error
# on the binding call, and `'is'` is wrong for the testing one. `#=` is the
# only spelling valid in every mode, which is why it is in the spec at all;
# registering it under its own name just gives that existing behaviour a
# callable, ISO-recognisable spelling. The other five members of the family
# (`#\=`, `#<`, `#>`, `#=<`, `#>=`) are their natural CLP(FD) counterparts,
# named the same way for symmetry.
#
# Their error surface is clpz's, NOT infix `==`'s (ruled 2026-09-30).
# Measured 2026-09-09 with a non-numeric ground operand the family had three
# behaviours -- `'#='(1, foo)` failed silently, `'#\='(1, foo)` succeeded,
# `'#<'(1, foo)` raised type_error(orderable, foo) -- where Scryer's clpz
# answers `error(domain_error(clpz_expression,foo),_)` for every one.  Each
# builtin now hands both operands to `clpfd.clpz_refuse_non_numeric` first,
# which raises that formal (context: the builtin's own indicator) for an
# atom, a Python bool, a string, a list or a non-evaluable compound
# anywhere in the operand.  Infix `==` is untouched.
#
# Another difference from infix `==` (2026-09-30): under clpz `/` is exact
# integer division, so each builtin first hands its operands to
# `clpfd.clpz_operands`, which posts `A / B` as an integer Z with
# `Z * B #= A, B #\= 0` (Scryer: `X #= 7/2` fails, `X #= 8/2` is 4).  Infix
# `==` keeps `/` rational (ruling Q15).
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
    from clausal.logic.clpfd import (  # noqa: PLC0415
        clpz_operands, clpz_refuse_non_numeric, fd_eq)
    clpz_refuse_non_numeric(a, "#=/2")
    clpz_refuse_non_numeric(b, "#=/2")
    ops = clpz_operands(a, b, trail)
    if ops is not None and fd_eq(*ops, trail):
        yield None


@_builtin("#\\=", 2)
def _clp_ne(a, b, trail, k):
    """CLP(FD) disequality constraint — the negation of `#=`."""
    from clausal.logic.clpfd import (  # noqa: PLC0415
        clpz_operands, clpz_refuse_non_numeric, fd_ne)
    clpz_refuse_non_numeric(a, "#\\=/2")
    clpz_refuse_non_numeric(b, "#\\=/2")
    ops = clpz_operands(a, b, trail)
    if ops is not None and fd_ne(*ops, trail):
        yield None


@_builtin("#<", 2)
def _clp_lt(a, b, trail, k):
    """CLP(FD)/CLP(R) strictly-less-than constraint (an all-integer ``/`` is
    clpz's exact integer division, see clpfd.clpz_operands)."""
    from clausal.logic.clpfd import (  # noqa: PLC0415
        clpz_operands, clpz_refuse_non_numeric, fd_lt)
    clpz_refuse_non_numeric(a, "#</2")
    clpz_refuse_non_numeric(b, "#</2")
    ops = clpz_operands(a, b, trail)
    if ops is not None and fd_lt(*ops, trail):
        yield None


@_builtin("#>", 2)
def _clp_gt(a, b, trail, k):
    """CLP(FD)/CLP(R) strictly-greater-than constraint (an all-integer ``/`` is
    clpz's exact integer division, see clpfd.clpz_operands)."""
    from clausal.logic.clpfd import (  # noqa: PLC0415
        clpz_operands, clpz_refuse_non_numeric, fd_gt)
    clpz_refuse_non_numeric(a, "#>/2")
    clpz_refuse_non_numeric(b, "#>/2")
    ops = clpz_operands(a, b, trail)
    if ops is not None and fd_gt(*ops, trail):
        yield None


@_builtin("#=<", 2)
def _clp_le(a, b, trail, k):
    """CLP(FD)/CLP(R) less-than-or-equal constraint (an all-integer ``/`` is
    clpz's exact integer division, see clpfd.clpz_operands)."""
    from clausal.logic.clpfd import (  # noqa: PLC0415
        clpz_operands, clpz_refuse_non_numeric, fd_le)
    clpz_refuse_non_numeric(a, "#=</2")
    clpz_refuse_non_numeric(b, "#=</2")
    ops = clpz_operands(a, b, trail)
    if ops is not None and fd_le(*ops, trail):
        yield None


@_builtin("#>=", 2)
def _clp_ge(a, b, trail, k):
    """CLP(FD)/CLP(R) greater-than-or-equal constraint (an all-integer ``/`` is
    clpz's exact integer division, see clpfd.clpz_operands)."""
    from clausal.logic.clpfd import (  # noqa: PLC0415
        clpz_operands, clpz_refuse_non_numeric, fd_ge)
    clpz_refuse_non_numeric(a, "#>=/2")
    clpz_refuse_non_numeric(b, "#>=/2")
    ops = clpz_operands(a, b, trail)
    if ops is not None and fd_ge(*ops, trail):
        yield None


# ── standard order of terms (spec 2026-09-09) ────────────────────────────────
#
# `_standard_order_key` already implemented the order and drove sort/2; these
# only expose it. The order is TOTAL by construction, so none of these raises:
# ISO requires the standard order to be defined for every pair of terms.

# Minted once. `mint` interns permanently, so it is for bounded producers —
# three atoms for the life of the process, not one per comparison.
_ORD_LT = mint("<")
_ORD_EQ = mint("=")
_ORD_GT = mint(">")


def _order_atom(a, b):
    """`<`, `=` or `>` for *a* against *b*, as a bare str."""
    ka = _standard_order_key(a)
    kb = _standard_order_key(b)
    if ka < kb:
        return "<"
    if kb < ka:
        return ">"
    return "="


def _register_order_cmp(name, accept):
    """Register one standard-order comparison.

    `accept` is closed over, NOT passed as a default argument. A default would
    sit in `params` after `a, b` and push `(trail, k)` past
    `_registry._extract_fields_simple`'s `params[:-2]`, registering a /4 term
    class with two junk variables — which is exactly what happened to the six
    arithmetic comparisons on the predecessor branch and reached final review.
    """
    def _cmp(a, b, trail, k):
        if _order_atom(a, b) in accept:
            yield None

    _cmp.__name__ = f"_iso_order_{name}"
    return _builtin(name, 2, fields=("a", "b"))(_cmp)


_register_order_cmp("@<", ("<",))
_register_order_cmp("@>", (">",))
_register_order_cmp("@=<", ("<", "="))
_register_order_cmp("@>=", (">", "="))


def _compare_order_error(o):
    """ISO 8.4.2.3: an Order that is neither a variable nor an atom is
    type_error(atom, Order); an atom other than <, = and > is
    domain_error(order, Order).  compare(foo, a, b) used to fail silently."""
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, domain_error, type_error)
    from clausal.logic.atoms import is_nil  # noqa: PLC0415
    if not (is_atom(o) or is_nil(o)):  # [] is an atom (Scryer)
        raise LogicException(type_error("atom", o, "compare/3"))
    raise LogicException(domain_error("order", o, "compare/3"))


@_builtin("compare", 3, fields=("order", "a", "b"))
def _iso_compare(order, a, b, trail, k):
    """ISO compare/3: unify Order with the atom `<`, `=` or `>`.

    `compare(=, X, Y)` holds exactly when `'=='(X, Y)` — an identity ISO
    guarantees. It holds here by construction rather than by coincidence:
    the number-band ranks in `_standard_order_key` are derived from the same
    numeric kinds `_numeric_tag` uses, so two terms share a key exactly when
    `_iso_identical` calls them identical.
    """
    o = _deref(order)
    if not _is_var(o) and not (type(o) is str and o in ("<", "=", ">")):
        _compare_order_error(o)
    got = _order_atom(a, b)
    atom = _ORD_LT if got == "<" else (_ORD_EQ if got == "=" else _ORD_GT)
    if _unify(order, atom, trail):
        yield None


# ── '=..' (univ) ─────────────────────────────────────────────────────────────
#
# The canonical ISO spelling of the existing `unpack/2`. Registered as the
# SAME function object rather than a wrapper that forwards to it: there is no
# second implementation, so the two spellings cannot drift apart, and no call
# layer to pay for. §6.4 already applies unchanged — the head of the univ list
# is an ATOM, not a bare spelling.
_builtin("=..", 2, fields=("term", "lst"))(_iso_univ_impl)
