"""Type-checking builtins: var/1, nonvar/1, is_str/1, string/1, number/1,
integer/1, float_/1, atomic/1, compound/1, callable_/1, is_list/1, ground/1,
must_be/2, can_be/2."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var
from clausal.logic.predicate import PredicateMeta, is_atom, is_term_instance, term_field_names
from clausal.terms import Compound, KWTerm, SegList, SegString, SegBytes

from clausal.logic.builtins._registry import _builtin, _db_builtin
from clausal.logic.builtins._helpers import _is_ground
from clausal.logic.runtime._seg_helpers import normalize_seg_input


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


@_builtin("is_str", 1)
def _atom__1(x, trail, k):
    """is_str(X) — succeeds if X is a Python str.

    Also succeeds for a ground ``SegString`` (its ``walk`` returns a
    plain ``str``).
    """
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, str):
        yield None
    elif isinstance(x_val, SegString) and _is_ground(x_val):
        yield None


# F081 (audit 2026-05-25): register ``string/1`` as the ISO/SWI name
# alongside the clausal-native ``is_str/1``. The ``_check_type`` table
# below has long accepted ``"string"`` as a synonym for the str check,
# so ``must_be(string, X)`` worked while ``string(X)`` raised KeyError
# — see [[F081]].
@_builtin("string", 1)
def _string__1(x, trail, k):
    """string(X) — succeeds if X is a Python str (ISO/SWI alias of ``is_str``).

    Also succeeds for a ground ``SegString``.
    """
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, str):
        yield None
    elif isinstance(x_val, SegString) and _is_ground(x_val):
        yield None


@_builtin("atom", 1)
def _is_atom__1(x, trail, k):
    """atom(X) — succeeds if X is a zero-arity PredicateMeta (a declared atom)."""
    x_val = deref(x)
    if not is_var(x_val) and is_atom(x_val):
        yield None


@_builtin("number", 1)
def _number__1(x, trail, k):
    """number(X) — succeeds if X is an int or float (not bool)."""
    x_val = deref(x)
    if (
        not is_var(x_val)
        and isinstance(x_val, (int, float))
        and not isinstance(x_val, bool)
    ):
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


@_builtin("compound", 1)
def _compound__1(x, trail, k):
    """compound(X) — succeeds if X is a compound term with arity > 0."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, Compound) and len(x_val.args) > 0:
        yield None
    elif isinstance(x_val, KWTerm) and len(x_val) > 0:
        yield None
    elif is_term_instance(x_val) and len(term_field_names(x_val)) > 0:
        yield None


# F082 (audit 2026-05-25): register ``atomic/1``, the ISO Prolog
# type-check for "any non-variable, non-compound term". Accepts
# Python ``str`` / ``int`` / ``float`` / ``bool`` / ``None`` and
# zero-arity ``PredicateMeta`` classes; rejects Var, Compound,
# KWTerm, term-instance, list, dict, and SegList / SegString — every
# Seg* shape is structurally compound. See [[F082]].
@_builtin("atomic", 1)
def _atomic__1(x, trail, k):
    """atomic(X) — succeeds if X is a non-variable, non-compound term.

    Accepts ``str``, ``int``, ``float``, ``bool``, ``None``, and
    zero-arity ``PredicateMeta`` classes. Rejects ``Var``, ``Compound``,
    ``KWTerm``, term-instances, ``list``, ``SegList``, ``SegString``.
    """
    # F029 (A09): walk a ground Seg* to its concrete form first — a ground
    # SegString walks to a str (atomic) so is_str(X) no longer contradicts
    # atomic(X). A non-ground Seg* stays a Seg* and is rejected below.
    x_val = normalize_seg_input(deref(x))
    if is_var(x_val):
        return
    # Reject compound shapes explicitly so we don't accidentally accept
    # them via the "anything else" fallthrough.
    if isinstance(x_val, (Compound, KWTerm, list, SegList, SegString, SegBytes)):
        return
    if is_term_instance(x_val):
        return
    # Atomic primitives. ``bool`` is-a ``int`` in Python — that's fine
    # for ``atomic``, but ``number/1`` continues to exclude it.
    if x_val is None or isinstance(x_val, (bool, int, float, str, bytes)):
        yield None
        return
    # Zero-arity PredicateMeta class — a declared atom.
    if is_atom(x_val):
        yield None


def _str_is_identifier(s: str) -> bool:
    """Return True if *s* could plausibly be a predicate name.

    Conservative: non-empty + Python ``str.isidentifier`` rule. Predicate
    names in clausal use the same lexical class as Python identifiers
    (head-of-word: letter/underscore; body: alphanumeric/underscore).
    """
    return bool(s) and s.isidentifier()


# F084 (audit 2026-05-25): tighten ``callable_/1`` so it no longer
# accepts arbitrary Python strs. A str now has to (a) be a non-empty
# valid identifier *and* (b) name a predicate that is registered in
# the current module's database — either as user-defined clauses or
# as a builtin / stdlib entry. Compound, KWTerm, term-instance, and
# zero-arity PredicateMeta classes continue to succeed unchanged.
# See [[F084]] for the full rationale.
@_db_builtin("callable_", 1, fields=("x",))
def _callable__1_factory(db):
    """Factory for ``callable_/1`` — captures *db* for predicate-name lookups."""
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS

    def _str_is_callable(name: str) -> bool:
        if not _str_is_identifier(name):
            return False
        # Any registered arity counts: scan user clauses, dispatch table,
        # and the builtin / db-builtin registries for at least one match.
        try:
            iter_clauses = db._clauses  # internal — same shape used elsewhere
        except AttributeError:
            iter_clauses = {}
        for (fn, _arity) in iter_clauses:
            if fn == name:
                return True
        try:
            iter_dispatch = db._dispatch
        except AttributeError:
            iter_dispatch = {}
        for (fn, _arity) in iter_dispatch:
            if fn == name:
                return True
        for (fn, _arity) in _BUILTINS:
            if fn == name:
                return True
        for (fn, _arity) in _DB_BUILTINS:
            if fn == name:
                return True
        # Module-globals fallback: a PredicateMeta class registered
        # under this name in the importing module.
        module_dict = getattr(db, "module_dict", None)
        if module_dict is not None:
            obj = module_dict.get(name)
            if obj is not None and hasattr(obj, "_get_dispatch"):
                return True
        return False

    def callable___1(x, trail, k):
        x_val = deref(x)
        if is_var(x_val):
            return
        if isinstance(x_val, (Compound, KWTerm)):
            yield None
            return
        if is_term_instance(x_val):
            yield None
            return
        if isinstance(x_val, type) and isinstance(x_val, PredicateMeta):
            yield None
            return
        if isinstance(x_val, str):
            if _str_is_callable(x_val):
                yield None
            return
        # Any other shape (int, float, list, SegList, …) — not callable.

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
    if isinstance(x_val, (list, str, bytes)):
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
    if isinstance(normalize_seg_input(deref(x)), (list, str)):
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
    "integer", "int", "float", "number", "atom", "string", "str", "list",
    "boolean", "bool", "callable", "dict", "compound",
})


def _check_type(type_name: str, term) -> bool:
    """Return True if *term* satisfies *type_name* (assumes a known type)."""
    if type_name in ("integer", "int"):
        return isinstance(term, int) and not isinstance(term, bool)
    elif type_name == "float":
        return isinstance(term, float)
    elif type_name == "number":
        return isinstance(term, (int, float)) and not isinstance(term, bool)
    elif type_name in ("atom", "string", "str"):
        if isinstance(term, str):
            return True
        if is_atom(term):
            return True
        return False
    elif type_name == "list":
        # F016 (A09): align with is_list/1 — under strings-as-lists a str is
        # a char list and a bytes is a code list, and a ground Seg* walks to
        # one. Rejecting them here contradicted is_list("abc") succeeding.
        if isinstance(term, (list, str, bytes)):
            return True
        return isinstance(term, (SegList, SegString, SegBytes)) and _is_ground(term)
    elif type_name in ("boolean", "bool"):
        return isinstance(term, bool)
    elif type_name == "callable":
        return (
            isinstance(term, (str, Compound, KWTerm))
            or is_term_instance(term)
            or (isinstance(term, type) and hasattr(term, '_get_dispatch'))
            or hasattr(term, '_get_dispatch')
        )
    elif type_name == "dict":
        from clausal.terms import DictTerm
        return isinstance(term, DictTerm)
    elif type_name == "compound":
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
    if not isinstance(type_val, str):
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
    if not isinstance(type_val, str):
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
