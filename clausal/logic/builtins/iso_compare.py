"""ISO comparison, unification and arithmetic builtins under their ISO names.

Reachable from `.clausal` ONLY through the quoted canonical form —
`'=:='(A, B)` — because Python has no infix syntax for these; natively in
`.pl`. Spec: docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md
"""
import operator as _o
from decimal import Decimal as _Decimal
from fractions import Fraction as _Fraction

from clausal.logic.atoms import is_atom, mint, spelling
from clausal.logic.builtins._helpers import _arity as _term_arity
from clausal.logic.builtins._helpers import _functor_name as _term_functor_name
from clausal.logic.builtins._helpers import _standard_order_key
from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins.inspection import _univ__2 as _iso_univ_impl
from clausal.logic.constraints import structural_eq as _structural_eq
from clausal.logic.exceptions import (
    LogicException, error_context_text, instantiation_error, term_functor_args,
    type_error,
)
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.variables import deref, is_var
from clausal.logic.variables import unify as _unify
from clausal.terms import Compound, DictTerm, SetTerm, compound_as_cell


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
    outer = term_functor_args(term)
    if outer is None or outer[0] != "error" or len(outer[1]) != 2:
        return None
    inner = term_functor_args(outer[1][0])
    if inner is None or inner[0] != "type_error" or len(inner[1]) != 2:
        return None
    expected, leaf = inner[1]
    if not (is_atom(expected) and spelling(expected) == "integer"):
        return None
    if error_context_text(term) != "clpfd expression":
        return None
    return leaf


def _evaluable_culprit(leaf):
    """*leaf* as ISO's `Name/Arity` culprit for `type_error(evaluable, …)`.

    ISO's culprit for `type_error(evaluable, …)` is a `Name/Arity` INDICATOR,
    never the offending term itself, so this maps whatever `_eval_ground`
    handed back onto that shape with the engine's own functor/arity
    accessors — the same `_helpers._functor_name` / `_helpers._arity` pair
    `functor/3` uses, so an atom, a cell, a `Compound`, a term instance and a
    list all answer consistently. Measured directly: `_ is foo + 1` gives
    Scryer `error(type_error(evaluable,foo/0),(is)/2)`, and this yields
    `foo/0`.

    Previously this tested `isinstance(leaf, Compound)`, which is DEAD for a
    compound reaching here from `.clausal` source. Measured 2026-09-09:
    `'=:='(1, foo(bar))` hands this function the cell tuple
    `('foo', ('bar',))`, NOT a `clausal.terms.Compound`, so the branch never
    fired and the raw term leaked out as the culprit —
    `type_error(evaluable, foo(bar))`, which is not a legal ISO indicator at
    all.

    Matching Scryer's culprit IDENTITY for a compound is a separate,
    still-OPEN question and is deliberately not attempted here. Scryer
    evaluates arguments first, so its culprit is the innermost non-evaluable
    leaf; measured 2026-09-09 against
    /workspace/scryer-prolog/target/release/scryer-prolog:

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

    `_eval_ground`'s own leaf error is `type_error(integer, Leaf, "clpfd
    expression")` — a CLP(FD)-flavoured shape, not ISO's `type_error(evaluable,
    Name/Arity)` for `is/2`. Measured directly against Scryer:
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
        # Same culprit shape as the reconciled branch above: an ISO
        # `type_error(evaluable, …)` culprit is a Name/Arity indicator, so
        # this fallback must not hand back a raw term either.
        raise LogicException(
            type_error("evaluable", _evaluable_culprit(t), context)) from None
    if value is None:
        raise LogicException(instantiation_error(context))
    return value


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
        if op(_iso_eval(a, "is/2"), _iso_eval(b, "is/2")):
            yield None
    _cmp.__name__ = f"_iso_cmp_{name}"
    return _cmp


_arith_cmp("=:=", _o.eq)
_arith_cmp("=\\=", _o.ne)
_arith_cmp("<", _o.lt)
_arith_cmp(">", _o.gt)
_arith_cmp("=<", _o.le)     # ISO spells it =<, never <=
_arith_cmp(">=", _o.ge)


@_builtin("is", 2)
def _iso_is(result, expr, trail, k):
    """ISO is/2: evaluate Expr, unify with Result.

    NOT Clausal's infix `is`, which is unification (nodes.Unify) and leaves
    `X is 3 + 4` as the term Add(3, 4). Both spellings coexist: Python has no
    infix syntax for `'is'(X, E)`, so they never collide. See
    todo/is-and-eq-are-swapped-relative-to-iso-2026-09-09.md

    The unification at the end is the engine's `unify`, which conflates int
    and float, so `'is'(7.0, 3 + 4)` SUCCEEDS here where Scryer says no.
    That is an OPEN, deliberately deferred divergence shared with `'='`/2 —
    see todo/iso-unify-conflates-int-and-float-2026-09-09.md and the two
    `*_OPEN_iso_divergence` pins in tests/iso/test_iso_compare_scryer.py.
    """
    if _unify(result, _iso_eval(expr, "is/2"), trail):
        yield None


@_builtin("=", 2)
def _iso_unify(a, b, trail, k):
    """ISO =/2: unification.

    Clausal's `unify` conflates int and float, so `'='(1, 1.0)` succeeds
    where Scryer says no — OPEN and deferred, see
    todo/iso-unify-conflates-int-and-float-2026-09-09.md.
    """
    if _unify(a, b, trail):
        yield None


@_builtin("\\=", 2)
def _iso_not_unifiable(a, b, trail, k):
    mark = trail.mark()
    ok = _unify(a, b, trail)
    trail.undo(mark)
    if not ok:
        yield None


def _numeric_tag(x):
    """The numeric type tag of *x*, or None if *x* is not a tagged number.

    EVERY numeric type is its own kind, so `==` is an equivalence relation
    and `compare(=, X, Y) <=> X == Y` — the identity ISO guarantees — can hold
    by construction. Returns a TYPE OBJECT: nothing is wrapped, no term
    representation changes, and arithmetic never sees this.

    `Decimal`/`Fraction` used to be left untagged to mirror
    `clausal/logic/tabling.py::_normalize_for_key_py` (the A01-D001 residual).
    That was harmless while `1.0 == 1` was also true, but once that correctly
    became false the relation stopped being transitive: measured 2026-09-09,
    `1.0 == Decimal(1)` and `Decimal(1) == 1` were both true while
    `1.0 == 1` was false.

    This is the COMPARISON site ONLY. `_normalize_for_key_py` and its C twin
    `do_normalize` keep the residual deliberately — a C rebuild and P52
    lock-step do not belong here — so tabled answer dedup still collapses
    `Decimal(1)` with `1` while this says they differ. Filed as
    todo/a01-d001-tabling-half-2026-09-09.md. Spec §4a.
    """
    if type(x) is int:
        return int
    if isinstance(x, (bool, float, complex, _Decimal, _Fraction)):
        return type(x)
    # An exact-number CELL (``('decimal', M, S)``, ``('rdiv', N, D)``) is NOT
    # tagged here, deliberately: ``structural_eq`` already separates a cell
    # from its object and two cells of different spelling, so a tag for cells
    # would change no answer -- measured 2026-09-17 by mutation (disabling
    # such a tag failed 0 of 11 guard tests).  The cell is handled where it
    # IS observable: the order key (``_helpers._standard_order_key``) and the
    # evaluator leaf (``clpfd._eval_ground``).
    return None


def _decimal_scale(x: _Decimal) -> int:
    """Decimal places of a Decimal object (``1.00`` -> 2)."""
    return -x.as_tuple().exponent


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
    a = deref(a)
    b = deref(b)
    # Ruling 2026-09-26: an atom-functor Compound of arity >= 1 IS its cell,
    # so descend into it as that cell -- otherwise `f(1) == f(1.0)` across
    # the two spellings would stop at the type mismatch with no objection.
    if type(a) is not type(b):
        if isinstance(a, Compound):
            a = compound_as_cell(a) or a
        if isinstance(b, Compound):
            b = compound_as_cell(b) or b
    ta = _numeric_tag(a)
    tb = _numeric_tag(b)
    if ta is not None or tb is not None:
        # Only a PAIR of tagged numbers raises the cross-type question. A
        # tagged number against an UNTAGGED one — `Decimal`/`Fraction`, which
        # `_normalize_for_key` also leaves untagged, so `Decimal('1')` and `1`
        # already read as identical today — is not this check's business and
        # gets no objection.
        if ta is None or tb is None or ta is not tb:
            return ta is None or tb is None
        # RULED 2026-09-17 Q2: two decimals of equal VALUE and different SCALE
        # are distinct terms (``1.0`` vs ``1.00``, the analogue of ISO's ``1``
        # vs ``1.0``).  Python's ``Decimal.__eq__`` ignores scale, so the
        # objection has to be raised here, where the order key raises it too
        # (``_helpers._number_key``) -- that agreement is what keeps
        # ``compare(=, X, Y) <=> X == Y`` true by construction.
        if ta is _Decimal:
            return _decimal_scale(a) == _decimal_scale(b)
        return True
    if type(a) is not type(b):
        return True
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return True
        return all(_numeric_types_agree(x, y) for x, y in zip(a, b))
    if isinstance(a, Compound):
        if a.functor != b.functor or len(a.args) != len(b.args):
            return True
        return all(_numeric_types_agree(x, y) for x, y in zip(a.args, b.args))
    if isinstance(a, DictTerm):
        return _dict_numeric_types_agree(a.data, b.data)
    if isinstance(a, dict):
        return _dict_numeric_types_agree(a, b)
    if isinstance(a, SetTerm):
        return _set_numeric_types_agree(a.elements, b.elements)
    if isinstance(a, (set, frozenset)):
        return _set_numeric_types_agree(a, b)
    if is_term_instance(a):
        fields = term_field_names(a)
        if fields != term_field_names(b):
            return True
        return all(_numeric_types_agree(getattr(a, f), getattr(b, f))
                   for f in fields)
    return True


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
    todo/audit-2026-07-05/done/fix-A05-structural-eq-asymmetry-consistency.md:
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
    if not _structural_eq(a, b):
        return False
    return _numeric_types_agree(a, b)


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
# BECAUSE these name an EXISTING behaviour, they inherit its error surface
# unchanged, and that surface is neither uniform nor Scryer's. Measured
# 2026-09-09 with a non-numeric ground operand, against Scryer's clpz, which
# answers `error(domain_error(clpz_expression,foo),unknown(foo)-1)` for
# every one of these four goals:
#
#     '#='(1, foo)    fails silently
#     '#\='(1, foo)   succeeds
#     '#<'(1, foo)    type_error(orderable, foo)   context '(<)/2'
#     '#='(X, foo)    type_error(evaluable, foo)   context '(==)/2'
#
# Three behaviours across one family, and the last one names `(==)/2` in a
# `'#='` call. All four are PINNED, not changed, in
# tests/iso/test_iso_compare_errors.py — changing them would change infix
# `==`, which this plan may not do.
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


@_builtin("compare", 3, fields=("order", "a", "b"))
def _iso_compare(order, a, b, trail, k):
    """ISO compare/3: unify Order with the atom `<`, `=` or `>`.

    `compare(=, X, Y)` holds exactly when `'=='(X, Y)` — an identity ISO
    guarantees. It holds here by construction rather than by coincidence:
    the number-band ranks in `_standard_order_key` are derived from the same
    numeric kinds `_numeric_tag` uses, so two terms share a key exactly when
    `_iso_identical` calls them identical.
    """
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
