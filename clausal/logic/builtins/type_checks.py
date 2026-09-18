"""Type-checking builtins: var/1, nonvar/1, is_str/1, string/1, number/1,
integer/1, float_/1, atomic/1, compound/1, callable_/1, is_list/1, ground/1,
must_be/2, can_be/2."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var
from clausal.logic.predicate import (
    PredicateMeta, is_zero_field_class, is_atom_value, is_term_instance,
    term_field_names,
)
from clausal.logic.atoms import (
    is_atom as _term_is_atom, is_char_atom as _is_char_atom,
    spelling as _spelling,
)
from clausal.terms import (
    Compound, KWTerm, Quantity, SegList, SegString, SegBytes)

from clausal.logic.builtins._registry import _builtin, _db_builtin
from clausal.logic.builtins._helpers import (
    NIL_SPELLING, _arity, _is_compound, _is_empty_list, _is_ground,
    _is_non_empty_list,
)
from clausal.logic.runtime._seg_helpers import walk_seg
from clausal.logic.cells import is_chars


@_builtin("var", 1)
def _var__1(x, trail, k):
    """var(X) — succeeds if X is an unbound logic variable."""
    if is_var(deref(x)):
        yield None


@_builtin("nonvar", 1)
def _nonvar__1(x, trail, k):
    """nonvar(X) — succeeds if X is bound (not an unbound Var)."""
    if not is_var(deref(x)):
        yield None


def _is_string_term(x) -> bool:
    """True iff *x* is the term a ``"…"`` literal denotes — a STRING.

    Task 14b (spec §6.3's ``""``/``[]`` column): the check answers for the
    TERM, never for the storage.  ``""`` and ``[]`` are one term and so are
    ``"ab"`` and ``['a', 'b']``, so a proper list whose every element is a
    char atom is a string exactly as the equal ``str`` is; the empty list is
    the empty string.  A list with a NON-char element (``[1, 2]``,
    ``['ab']``) is not, and neither is an atom, a cell or a number.

    A ground ``Seg*`` is walked first, so a ground ``SegString`` (which
    walks to a ``str``) and a ground ``SegList`` of char atoms both answer
    true, while a non-ground one stays a ``Seg*`` and answers false.

    The one implementation behind ``is_str/1``, ``string/1`` and
    ``_check_type``'s ``string``/``str`` row, so the three cannot drift.
    """
    x_val = deref(x)
    from clausal.logic.cells import is_chars  # noqa: PLC0415
    if type(x_val) is str:
        return False                   # STAGE 2: a str is an ATOM, not a string
    if is_chars(x_val):
        return True
    x_val = walk_seg(x_val)
    if is_chars(x_val):
        return True                    # a ground SegString walked to its text
    if type(x_val) is list:
        return all(_is_char_atom(deref(e)) for e in x_val)
    return False


@_builtin("is_str", 1)
def _atom__1(x, trail, k):
    """is_str(X) — succeeds if X is a STRING (spec §6.3).

    That is a Python ``str``, a ground ``SegString``, ``[]``, or a proper
    list of char atoms — every spelling of the same term.  See
    :func:`_is_string_term`, which ``string/1`` shares.
    """
    if _is_string_term(x):
        yield None


# F081 (audit 2026-05-25): register ``string/1`` as the ISO/SWI name
# alongside the clausal-native ``is_str/1``. The ``_check_type`` table
# below has long accepted ``"string"`` as a synonym for the str check,
# so ``must_be(string, X)`` worked while ``string(X)`` raised KeyError
# — see [[F081]].
@_builtin("string", 1)
def _string__1(x, trail, k):
    """string(X) — the ISO/SWI alias of ``is_str/1``, one implementation.

    Succeeds for a STRING: a ``str``, a ground ``SegString``, ``[]``, or a
    proper list of char atoms (spec §6.3).
    """
    if _is_string_term(x):
        yield None


def _is_atom_term(x) -> bool:
    """The one ``atom/1`` definition: an arity-0 cell, a declared-atom class,
    or the empty list (the atom ``'[]'``).

    Shared with ``_check_type``'s ``atom`` row so ``must_be(atom, X)`` and
    ``atom(X)`` cannot drift apart.
    """
    return is_atom_value(x) or _is_empty_list(x)


@_builtin("atom", 1)
def _is_atom__1(x, trail, k):
    """atom(X) — succeeds if X is the arity-0 cell ``("bar",)``, a
    zero-arity PredicateMeta (a declared atom), or the empty list.

    THE FLIP (2026-09-06-atoms-as-cells-strings §6.3): a plain ``str`` is a
    STRING — the list of its char atoms — so ``atom("bar")`` is FALSE and
    ``string("bar")``/``is_list("bar")`` are true.  The two questions that
    were co-extensional under the pivot are now disjoint.

    Task 15 item 2 (spec §14.1/§14.12, RULED 2026-09-07): ``[]`` is the
    reserved atom ``'[]'``, so ``atom([])``, ``atom("")`` and ``atom(b"")``
    hold — the ISO/Scryer answer.
    """
    x_val = deref(x)
    from clausal.logic.cells import is_chars  # noqa: PLC0415
    from clausal.terms import SegList, SegString, SegBytes  # noqa: PLC0415
    if is_chars(x_val) or isinstance(x_val, (SegList, SegString, SegBytes)):
        # STAGE 2: a STRING (or a Seg*) is not an atom -- except that nil in
        # any spelling is the atom '[]'
        if _is_empty_list(walk_seg(x_val)):
            yield None
        return
    if not is_var(x_val) and _is_atom_term(x_val):
        yield None


@_builtin("number", 1)
def _number__1(x, trail, k):
    """number(X) — X is numeric-valued: an int, a float, or a QUANTITY.

    A ``Quantity`` is a number carrying a unit, and a guard that silently
    dropped one was the most dangerous defect this vocabulary produced. A
    rulebase summing money behind ``number(V)`` — the documented shape in
    ``eu/peppol_einvoicing``'s ``sum_field/3``, "a member whose KEY is absent
    or non-numeric contributes nothing... empty list -> 0" — would, on
    attaching units, total ZERO for every field, compare 0 against 0 in every
    consistency rule, and turn a legal conformance surface vacuously true with
    a green suite (corpus-lane, 2026-09-11, who found it by building the
    migration rather than reading it).

    Accepting inverts the failure mode rather than merely widening the test.
    Code that guards and then does BARE arithmetic (``number(V), V > 0``) now
    raises ``UnitsMismatch`` — loudly, at the site — where before it summed
    zero in silence.

    **Deviates from ISO**, which says number/1 is true of integers and floats
    only. Mitigated by the fact that a ``Quantity`` cannot occur in an ISO
    ``.pl`` program at all, so no conforming program can observe the
    difference. ``integer/1`` and ``float_/1`` stay STRICT: they name a
    specific representation, and a Quantity is neither — widening those would
    make ``integer(V)``, which is how a rulebase asserts minor-unit scale,
    silently true for an amount in any scale.
    """
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, Quantity):
        yield None
        return
    if isinstance(x_val, (int, float)) and not isinstance(x_val, bool):
        yield None


@_builtin("integer", 1)
def _integer__1(x, trail, k):
    """integer(X) — succeeds if X is an int (not bool)."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, int) and not isinstance(x_val, bool):
        yield None


@_builtin("float_", 1)
def _float__1(x, trail, k):
    """float_(X) — succeeds if X is a Python float."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, float):
        yield None


@_builtin("quantity", 1)
def _quantity__1(x, trail, k):
    """quantity(X) — X is a number carrying a UNIT.

    The affirmative test, for saying explicitly what ``number/1`` now also
    admits: a currency amount, a physical measurement, a dimensionless
    quantity. A bare int or float is NOT a quantity — it carries no unit —
    which is the distinction ``compatible_units/2`` asserts at a boundary.
    """
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, Quantity):
        yield None


@_builtin("compound", 1)
def _compound__1(x, trail, k):
    """compound(X) — succeeds if X is a compound term with arity > 0.

    Task 15 item 2 (spec §14.12, RULED 2026-09-07): a non-empty LIST is the
    ``'.'/2`` compound, so ``compound([1, 2])``, ``compound("abc")`` and
    ``compound(b"ab")`` hold — the ISO/Scryer answer, and the one that makes
    ``functor("hello", '.', 2)`` (§6.4, already true) coherent.  The empty
    list is the atom ``'[]'`` and stays non-compound.
    """
    x_val = walk_seg(deref(x))
    if is_var(x_val):
        return
    if _is_non_empty_list(x_val):
        yield None
        return
    if isinstance(x_val, Compound) and len(x_val.args) > 0:
        yield None
    elif isinstance(x_val, KWTerm) and len(x_val) > 0:
        yield None
    elif is_term_instance(x_val) and len(term_field_names(x_val)) > 0:
        yield None
    elif _is_compound(x_val) and (_arity(x_val) or 0) > 0:
        # P3-2 Task 2 (THE FLIP): a CELL is a compound term, and this was the
        # one type check in the file that did not go through the funnel and so
        # answered FALSE for one -- ``compound(pt(1, 2))`` failed while
        # ``functor/3``, ``arg/3``, ``=../2`` and ``callable/1`` all answered
        # for the same term.  The funnel's ``_is_compound``/``_arity`` pair is
        # the shared definition (``builtins/_helpers.py``); the branches above
        # stay first so the common shapes keep their direct test.
        yield None


# F082 (audit 2026-05-25): register ``atomic/1``, the ISO Prolog
# type-check for "any non-variable, non-compound term".  STAGE 2: accepts
# an atom (a ``str``), ``int`` / ``float`` / ``bool`` / ``None`` and the
# empty list; rejects Var, Compound, KWTerm, term-instance, list, dict, a
# non-empty STRING (the carrier), every class, and SegList / SegString —
# every Seg* shape is structurally compound. See [[F082]].
def _is_atomic_term(x) -> bool:
    """The one ``atomic/1`` definition, shared with ``_check_type``'s
    ``atomic`` row (fix round 1, item 6) so ``must_be(atomic, X)`` and
    ``atomic(X)`` cannot drift apart — the pattern the ``atom`` and
    ``string`` rows already follow.

    True for an atom (STAGE 2: a ``str``), the empty list in any spelling,
    ``int``, ``float``, ``bool`` and ``None``.  False for ``Var``,
    ``Compound``, ``KWTerm``, term-instances, ``list``, ``SegList``,
    ``SegString``, a non-empty STRING (the chars carrier: it is the LIST of
    its char atoms, spec §6.3, so no more atomic than that list) — and any
    class (STAGE 2, spec §4: no class is an atom).

    Task 15 item 2 (spec §14.1/§14.12, RULED 2026-09-07): ``""``/``[]``/
    ``b""`` ARE atomic — they are the atom ``'[]'`` — and a non-empty
    ``bytes`` is NOT: a code list is a list (spec §5.4), so it is the
    ``'.'/2`` compound that ``compound/1`` now answers for, and a term
    cannot be both atomic and compound.

    *x* is expected already dereffed and Seg*-walked by the caller.
    """
    if is_var(x):
        return False
    # The empty list is the ATOM ``'[]'`` whichever way it is spelled, so it
    # is decided BEFORE the compound-shape rejection below catches ``[]``.
    if _is_empty_list(x):
        return True
    if is_chars(x):
        return False                   # a non-empty string is the '.'/2 compound
    # Reject compound shapes explicitly so we don't accidentally accept
    # them via the "anything else" fallthrough.
    if isinstance(x, (Compound, KWTerm, list, bytes,
                      SegList, SegString, SegBytes)):
        return False
    if is_term_instance(x):
        return False
    # THE FLIP (2026-09-06-atoms-as-cells-strings): the arity-0 cell atom
    # ("foo",) is the atomic term here — checked via the public atom API so
    # a plain data tuple like (1, 2) still falls off the end below
    # unrecognized.
    if _term_is_atom(x):
        return True
    # Atomic primitives. ``bool`` is-a ``int`` in Python — that's fine
    # for ``atomic``, but ``number/1`` continues to exclude it.  ``str`` and
    # ``bytes`` are deliberately ABSENT: a string is a list of char atoms and
    # a code list is a list of numbers (both rejected above).
    if x is None or isinstance(x, (bool, int, float)):
        return True
    # Zero-arity PredicateMeta class — a declared atom.
    return False                       # STAGE 2: no class is an atom


@_builtin("atomic", 1)
def _atomic__1(x, trail, k):
    """atomic(X) — succeeds if X is a non-variable, non-compound term.

    See :func:`_is_atomic_term`, which ``must_be(atomic, X)`` shares.
    """
    # F029 (A09): walk a ground Seg* to its concrete form first — a ground
    # SegString walks to the chars carrier (a STRING, the '.'/2 compound), so
    # string(X) and atomic(X) stay coherent: both see the same term.  A
    # non-ground Seg* stays a Seg* and is rejected below.
    if _is_atomic_term(walk_seg(deref(x))):
        yield None


# F084 (audit 2026-05-25) tightened ``callable_/1`` so it no longer accepted
# arbitrary Python strs: a str had to be a valid identifier naming a
# registered predicate.  THE FLIP (2026-09-06-atoms-as-cells-strings §6.3)
# retires that check entirely — a ``str`` is a STRING, and no string is
# callable, whatever it spells.  Compound, KWTerm, term-instance, cell and
# zero-arity PredicateMeta classes continue to succeed unchanged.
@_db_builtin("callable_", 1, fields=("x",))
def _callable__1_factory(db):
    """Factory for ``callable_/1`` — *db* is kept for the registry shape."""

    def callable___1(x, trail, k):
        x_val = walk_seg(deref(x))
        if is_var(x_val):
            return
        # Task 15 item 2 (spec §14.12, RULED 2026-09-07): callable = atom or
        # compound (ISO 3.24).  A list is one or the other whichever way it
        # is spelled — ``[]`` is the atom ``'[]'`` and ``[1, 2]``/``"abc"``/
        # ``b"ab"`` are the ``'.'/2`` compound — so ``callable("foo")`` is
        # TRUE, as Scryer answers.  That is why calling one is an
        # existence_error for ``'.'/2`` and not a ``type_error(callable, …)``
        # (item 3): the term IS callable, the procedure does not exist.
        if _is_empty_list(x_val) or _is_non_empty_list(x_val):
            yield None
            return
        if _is_atom_term(x_val):           # STAGE 2: an atom (a str) is callable -- ISO 3.24
            yield None
            return
        if isinstance(x_val, (Compound, KWTerm)):
            yield None
            return
        if is_term_instance(x_val):
            yield None
            return
        if _is_compound(x_val):
            # P3-2 Task 2 (THE FLIP): a CELL is a compound term, so it is
            # callable for exactly the reason a Compound is.  This was the
            # second type check in this file found blind to cells (after
            # ``compound/1``), and the review probe that missed it did so
            # because it called the predicate ``callable`` — the ISO name —
            # while it is REGISTERED as ``callable_``, so both halves of the
            # comparison raised the same KeyError and compared equal.
            #
            # No arity gate here, deliberately: the ``Compound``/``KWTerm``
            # branch above yields for a 0-arity Compound too, and this branch
            # mirrors the branch it is the cell twin OF, not ``compound/1``'s
            # (which does gate, because its Compound branch does).
            #
            # ``_is_compound`` is the funnel's shared definition, so a
            # ``(tuple, ...)`` tuple-DATA cell is NOT compound and does not
            # reach here — matching a plain Python tuple, which is what
            # tuple-data IS and which is likewise not callable.
            yield None
            return
        if isinstance(x_val, type) and isinstance(x_val, PredicateMeta):
            yield None
            return
        # THE FLIP (spec §6.3/§6.4) deleted the old ``str`` branch (and its
        # ``_str_is_callable`` predicate-name lookup) with the representation
        # that motivated it: a ``str`` is a STRING, so it is callable as the
        # LIST it is (the branch at the top), never as the predicate its
        # characters spell.  A program that means the atom writes ``foo`` or
        # mints one.
        # Any other shape (int, float, dict, non-ground SegList, …) — not
        # callable.

    return callable___1


@_builtin("is_list", 1)
def _is_list__1(x, trail, k):
    """is_list(X) — succeeds if X is a Python list or a Python str.

    F080 (audit 2026-05-25): under the strings-as-lists contract a
    ``str`` *is* a (character) list, so ``is_list("abc")`` must agree
    with ``in_/2``, ``length/2``, ``append/3``, ``msort/2``,
    ``reverse/2``, and ``maplist/N`` — all of which accept a ``str``
    as a list of chars. A ground ``SegList`` / ``SegString`` (one
    whose ``walk`` collapses to a plain list / str) also succeeds.
    See [[F080]] for the full design discussion and the lock-in
    update in ``tests/test_string_list_builtins.py``.
    """
    x_val = deref(x)
    from clausal.logic.cells import is_chars  # noqa: PLC0415
    if isinstance(x_val, (list, bytes)) or is_chars(x_val):   # STAGE 2: a str is an ATOM; the carrier is the list
        yield None
    elif isinstance(x_val, (SegList, SegString, SegBytes)) and _is_ground(x_val):
        yield None


@_builtin("is_chars", 1)
def _is_chars__1(x, trail, k):
    """is_chars(X) — succeeds if X is a list or a string (a character sequence).

    A ``bytes`` is a *code* sequence, not a *char* sequence, so it is rejected
    here — use ``is_codes/1``.

    F029 (A09): a ground ``SegString`` / ``SegList`` walks to a str / list
    and succeeds (coherent with ``is_str`` / ``is_list``); a ground
    ``SegBytes`` walks to bytes and is rejected (codes model).
    """
    x_val = walk_seg(deref(x))
    if isinstance(x_val, list) or is_chars(x_val):
        yield None


@_builtin("is_codes", 1)
def _is_codes__1(x, trail, k):
    """is_codes(X) — succeeds if X is a *code* sequence: a ``bytes`` value, or a
    list of ints in ``[0, 255]`` (the bytes-as-lists codes model — the codes
    analog of ``is_chars/1``). A ground ``SegBytes`` also succeeds.

    A ``str`` / char-list is the *chars* model and is rejected here (use
    ``is_chars/1``)."""
    x_val = deref(x)
    if isinstance(x_val, bytes):
        yield None
    elif isinstance(x_val, list):
        if all(
            isinstance(e, int) and not isinstance(e, bool) and 0 <= e <= 255
            for e in x_val
        ):
            yield None
    elif isinstance(x_val, SegBytes) and _is_ground(x_val):
        yield None


@_builtin("ground", 1)
def _ground__1(x, trail, k):
    """ground(X) — succeeds if X contains no unbound Vars."""
    if _is_ground(deref(x)):
        yield None


# ── Type checking map for must_be/can_be ─────────────────────────────────

# A09-F028: the set of type names must_be/can_be recognise. An unknown name
# is a domain_error(type, Name) — the TYPE is wrong, not the term.
_KNOWN_TYPES = frozenset({
    "integer", "int", "float", "number", "atom", "atomic", "string", "str",
    "list", "boolean", "bool", "callable", "dict", "compound",
})


def _check_type(type_name: str, term) -> bool:
    """Return True if *term* satisfies *type_name* (assumes a known type)."""
    if type_name in ("integer", "int"):
        return isinstance(term, int) and not isinstance(term, bool)
    elif type_name == "float":
        return isinstance(term, float)
    elif type_name == "number":
        return isinstance(term, (int, float)) and not isinstance(term, bool)
    elif type_name == "atom":
        # THE FLIP: an atom is the arity-0 cell (or a declared-atom class)
        # and NOT a str; Task 15 item 2 adds the empty list, the atom
        # ``'[]'``.  The same call the atom/1 builtin makes, so
        # ``must_be(atom, "x")`` and ``atom("x")`` cannot drift apart.
        return _is_atom_term(walk_seg(term))
    elif type_name == "atomic":
        # Fix round 1, item 6: the row the table was missing, so
        # ``must_be(atomic, [])`` raised ``domain_error(type, atomic)`` while
        # ``atomic([])`` succeeded.  The same call the atomic/1 builtin
        # makes, so the two cannot drift apart.
        return _is_atomic_term(walk_seg(term))
    elif type_name in ("string", "str"):
        # Task 14b: the same call the string/1 builtin makes, so
        # ``must_be(string, ['a','b'])`` and ``string(['a','b'])`` cannot
        # drift apart (the pattern the ``atom`` row above already follows).
        return _is_string_term(term)
    elif type_name == "list":
        # F016 (A09): align with is_list/1 — under strings-as-lists a str is
        # a char list and a bytes is a code list, and a ground Seg* walks to
        # one. Rejecting them here contradicted is_list("abc") succeeding.
        if isinstance(term, (list, bytes)) or is_chars(term):   # STAGE 2: a str is an ATOM; the carrier is the list
            return True
        return isinstance(term, (SegList, SegString, SegBytes)) and _is_ground(term)
    elif type_name in ("boolean", "bool"):
        return isinstance(term, bool)
    elif type_name == "callable":
        # Task 15 item 2: callable = atom or compound (ISO 3.24), so a list
        # — ``[]``, ``[1, 2]``, ``chars("abc")``, ``b"ab"`` — is callable, matching
        # callable_/1.
        walked = walk_seg(term)
        return (
            _is_empty_list(walked)
            or _is_non_empty_list(walked)
            or _is_atom_term(walked)       # STAGE 2: the same atom arm callable_/1 has (review round 1)
            or isinstance(term, (Compound, KWTerm))
            or is_term_instance(term)
            or (isinstance(term, type) and hasattr(term, '_get_dispatch'))
            or hasattr(term, '_get_dispatch')
            # Stage A: a cell is compound (any arity, incl. 0) exactly as
            # the callable_/1 builtin's own _is_compound branch treats it.
            or _is_compound(term)
        )
    elif type_name == "dict":
        from clausal.terms import DictTerm
        return isinstance(term, DictTerm)
    elif type_name == "compound":
        # Task 15 item 2: a non-empty list is the ``'.'/2`` compound,
        # matching the compound/1 builtin.
        if _is_non_empty_list(walk_seg(term)):
            return True
        # Stage A: the funnel's shared definition — a cell counts as
        # compound only above arity 0, matching the compound/1 builtin's
        # own cell branch (P3-2 Task 2, THE FLIP).
        if _is_compound(term) and (_arity(term) or 0) > 0:
            return True
        if isinstance(term, Compound) and len(term.args) > 0:
            return True
        if isinstance(term, KWTerm) and len(term) > 0:
            return True
        if is_term_instance(term) and len(term_field_names(term)) > 0:
            return True
        return False
    return False


@_builtin("must_be", 2)
def _must_be__2(type_name, term, trail, k):
    """must_be(Type, Term) — assert that Term is of the given type.

    Succeeds silently if Term matches Type.
    Throws instantiation_error if Term is unbound.
    Throws type_error if Term is ground but wrong type.
    """
    from clausal.logic.exceptions import LogicException, type_error, instantiation_error

    from clausal.logic.exceptions import domain_error

    type_val = deref(type_name)
    # A09-F028: must_be raises on violation — an unbound or non-atom Type is a
    # usage error, not a silent failure; an unknown type name is a
    # domain_error(type, Type) (the TYPE is wrong, not the term).
    if is_var(type_val):
        raise LogicException(instantiation_error("must_be/2"))
    if _term_is_atom(type_val):
        # The Type argument is an ATOM (it arrives as ("atom",) from source);
        # read it through its spelling.  THE FLIP deleted the plain-``str``
        # arm that used to sit here: a string Type is a type_error(atom).
        type_val = _spelling(type_val)
    else:
        raise LogicException(type_error("atom", type_val, "must_be/2"))
    if type_val not in _KNOWN_TYPES:
        raise LogicException(domain_error("type", type_val, "must_be/2"))
    term_val = deref(term)
    if is_var(term_val):
        raise LogicException(instantiation_error("must_be/2"))
    if _check_type(type_val, term_val):
        yield None
    else:
        raise LogicException(type_error(type_val, term_val, "must_be/2"))


@_builtin("can_be", 2)
def _can_be__2(type_name, term, trail, k):
    """can_be(Type, Term) — assert that Term could possibly be of the given type.

    Succeeds if Term is unbound (could become anything) or already matches.
    Throws type_error if Term is ground and definitely not the type.
    """
    from clausal.logic.exceptions import (
        LogicException, type_error, domain_error, instantiation_error)

    type_val = deref(type_name)
    # A09-F028: same Type-validation as must_be/2.
    if is_var(type_val):
        raise LogicException(instantiation_error("can_be/2"))
    if _term_is_atom(type_val):
        # Same Type-spelling rule as must_be/2 above.
        type_val = _spelling(type_val)
    else:
        raise LogicException(type_error("atom", type_val, "can_be/2"))
    if type_val not in _KNOWN_TYPES:
        raise LogicException(domain_error("type", type_val, "can_be/2"))
    term_val = deref(term)
    if is_var(term_val):
        # Unbound — could become anything
        yield None
    elif _check_type(type_val, term_val):
        yield None
    else:
        raise LogicException(type_error(type_val, term_val, "can_be/2"))
