"""Core term inspection builtins: functor/3, arg/3, unpack/2, copy_term/2,
term_variables/2, numbervars/3, gensym/2, global_atom/2, module_constant/3."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.predicate import (
    is_declared_predicate_name,
    is_term_instance, term_field_names, field_names_for,
)
# ``atoms.is_atom`` is the TERM test (spec §6.1) and the one the name position
# speaks (``predicate.is_zero_field_class`` asked about a class that W4b-3
# slice 7 deleted).
from clausal.logic.cells import chars, is_chars, chars_text  # stage 1: the chars carrier
from clausal.logic.atoms import (
    char_atom,
    is_atom as _term_is_atom,
    is_char_atom,
    mint,
    spelling,
)
from clausal.terms import SegList, SegString, SegBytes, VarSeg, ConcreteSeg, DictTerm

from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins._helpers import (
    NIL_SPELLING, _functor_name, _arity, _nth_arg, _args_list, _is_empty_list,
    _check_nonneg_int_arg,
)
from clausal.logic.runtime._seg_helpers import walk_seg


# ── Python fallbacks for _copy_term / _collect_vars ───────────────────────────
# These are the reference implementations.  The C versions in _variables.c are
# used when available.  Keep these in sync with any changes to the C code.


def _copy_term_py(term: Any, var_map: dict, attvars: list | None = None) -> Any:
    """Recursively copy *term*, replacing each unbound Var with a fresh one.

    *var_map* maps original Var id -> fresh Var so that sharing is preserved.
    *attvars*, when given, receives ``(original, fresh)`` for every copied
    variable that carries attributes (copy_term/2 re-installs them; see
    ``_copy_attributes``).  Twin of ``c_copy_term``.
    """
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in var_map:
            fresh = var_map[vid] = Var()
            if attvars is not None and getattr(term, "attrs", None):
                attvars.append((term, fresh))
        return var_map[vid]
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    if field_names_for(term) == ():
        return term
    if isinstance(term, list):
        return [_copy_term_py(e, var_map, attvars) for e in term]
    if type(term) is tuple:
        # A CELL -- ``("point", X, Y)`` -- is a plain tuple, and post-P3-2
        # (THE FLIP) it is how every compound DATA term is represented, so a
        # copy that returned it unchanged would hand back a "fresh" clause
        # still sharing the original's variables.  That is not a
        # representation difference: a meta-interpreter's
        # ``copy_term(CLAUSE, [HEAD, BODY])`` then binds the PROGRAM's
        # variables on the first resolution step and every later step
        # mismatches (``clausal/examples/metainterpreters.clausal``).
        #
        # ``type(...) is tuple``, not ``isinstance``: a namedtuple or other
        # tuple subclass would lose its type through ``tuple(...)``, and
        # rebuilding one is not this function's business.  The identity
        # short-circuit keeps a GROUND tuple (the overwhelmingly common case)
        # allocation-free, so this costs nothing where nothing changed.
        copied = tuple(_copy_term_py(e, var_map, attvars) for e in term)
        if all(new is old for new, old in zip(copied, term)):
            return term
        return copied
    # F092 (audit 2026-05-25): Seg* containers must produce an
    # independent copy whose VarSegs reference FRESH Vars threaded
    # through ``var_map`` so co-references inside the container are
    # preserved.  Falling through to ``return term`` (the historical
    # behaviour) aliased the "copy" to the original — binding the
    # original's Var mutated the copy and vice versa, breaking the
    # per-call fresh-Var guarantee that ``copy_term`` is supposed to
    # provide.  Mirrors the Seg*-blind cluster fixed at the Python
    # level for [[F083]]; the C accelerator (``c_copy_term``) is
    # similarly blind and is short-circuited via the Python wrapper
    # ``_copy_term`` below.
    if isinstance(term, SegList):
        new_segments: list = []
        for seg in term.segments:
            if isinstance(seg, ConcreteSeg):
                new_segments.append(
                    ConcreteSeg([_copy_term_py(e, var_map, attvars) for e in seg.elements])
                )
            elif isinstance(seg, VarSeg):
                new_segments.append(VarSeg(_copy_term_py(seg.var, var_map, attvars)))
            else:
                # Unknown segment — be conservative and recurse.
                new_segments.append(_copy_term_py(seg, var_map, attvars))
        return SegList(new_segments)
    if isinstance(term, (SegString, SegBytes)):
        # A str / bytes literal segment is ground; a hole gets a fresh Var.
        new_segments = []
        for seg in term.segments:
            if isinstance(seg, (str, bytes)):
                new_segments.append(seg)
            elif isinstance(seg, VarSeg):
                new_segments.append(VarSeg(_copy_term_py(seg.var, var_map, attvars)))
            else:
                new_segments.append(_copy_term_py(seg, var_map, attvars))
        return type(term)(new_segments)
    # A dict term's VALUES are terms; its keys are ground by construction.
    # Kept in step with ``walk_container_kind`` in ``c_copy_term``.
    # Nothing inside changed (a ground dict): the term itself, as for cells.
    if type(term) is DictTerm or type(term) is dict:
        data = term.data if type(term) is DictTerm else term
        copied = {k: _copy_term_py(v, var_map, attvars) for k, v in data.items()}
        if all(copied[k] is v for k, v in data.items()):
            return term
        return DictTerm(copied) if type(term) is DictTerm else copied
    if is_term_instance(term):
        cls = type(term)
        # The `_clausal_new` Phase-0 fast-constructor gate that used to
        # precede this was retired in W4b, 2026-09-23 -- see the note in
        # solve.py's _deref_walk_py.
        return cls(**{
            name: _copy_term_py(getattr(term, name), var_map, attvars)
            for name in term_field_names(term)
        })
    return term


def _collect_vars_py(term: Any, result: list, _seen: set | None = None) -> None:
    """Collect all unbound Vars in *term* into *result*, left-to-right order."""
    if _seen is None:
        _seen = set()
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in _seen:
            _seen.add(vid)
            result.append(term)
        return
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return
    if field_names_for(term) == ():
        return
    if isinstance(term, list):
        for e in term:
            _collect_vars_py(e, result, _seen)
        return
    if type(term) is tuple:
        # Cells carry variables (see the matching branch in
        # ``_copy_term_py``), so ``term_variables``/``numbervars`` have to
        # see inside them.
        for e in term:
            _collect_vars_py(e, result, _seen)
        return
    # F093 (audit 2026-05-25): Seg* containers expose their VarSegs as
    # variables.  Walk every ConcreteSeg element and every VarSeg's
    # ``var`` slot so ``term_variables`` and ``numbervars`` (which
    # share this walker) see the unbound Vars hidden inside Seg*
    # containers.  Same root cause as [[F083]] / [[F092]] — the C
    # accelerator (``_collect_vars_impl``) is Seg*-blind and is
    # short-circuited by the Python wrapper below.
    if isinstance(term, SegList):
        for seg in term.segments:
            if isinstance(seg, ConcreteSeg):
                for e in seg.elements:
                    _collect_vars_py(e, result, _seen)
            elif isinstance(seg, VarSeg):
                _collect_vars_py(seg.var, result, _seen)
            else:
                _collect_vars_py(seg, result, _seen)
        return
    if isinstance(term, (SegString, SegBytes)):
        for seg in term.segments:
            if isinstance(seg, (str, bytes)):
                continue
            if isinstance(seg, VarSeg):
                _collect_vars_py(seg.var, result, _seen)
            else:
                _collect_vars_py(seg, result, _seen)
        return
    # Dict values in key order (see the matching branch in _copy_term_py).
    if type(term) is DictTerm:
        for v in term.data.values():
            _collect_vars_py(v, result, _seen)
        return
    if type(term) is dict:
        for v in term.values():
            _collect_vars_py(v, result, _seen)
        return
    if is_term_instance(term):
        for name in term_field_names(term):
            _collect_vars_py(getattr(term, name), result, _seen)


# ── C-accelerated versions (with Python fallback) ────────────────────────────

_copy_term_impl = _copy_term_py
_collect_vars_impl = _collect_vars_py
try:
    from clausal.logic.variables._variables import (
        _copy_term_impl as _c_copy_term_impl,
        _collect_vars_impl as _c_collect_vars_impl,
    )

    # The C walkers read through every shape the twins above do: cells
    # (``PyTuple_CheckExact``), and Seg* partial lists / strings / byte
    # strings and dict terms at ANY depth (``walk_container_kind`` in
    # ``_variables.c``).  The Python wrappers that used to stand here sent a
    # Seg* to the twins only at the TOP level (F092 / F093), so one nested in
    # a term reached the C walkers and was a leaf: ``term_variables(f([A|T]),
    # Vs)`` gave [] and ``copy_term(f([A|T]), C)`` shared A and T with the
    # original.  The parity corpus that keeps the two implementations honest
    # is ``tests/test_python_fallbacks.py``.
    _copy_term_impl = _c_copy_term_impl
    _collect_vars_impl = _c_collect_vars_impl
except ImportError:
    pass

# Re-export for callers that import _copy_term directly (e.g. specialization.py)
_copy_term = _copy_term_impl


def _hole_var_ids(term: Any) -> dict:
    """``{id(var): hole type}`` for the unbound variables of *term* that
    stand in a HOLE of a partial list / string / byte string -- a ``VarSeg``
    (the ``T`` of ``[A|T]``) -- at any depth; the hole type is the
    container's (``SegList``, ``SegString`` or ``SegBytes``; the first one
    met wins).

    Such a variable may only ever be bound to a list (a string, a byte
    string): the engine has no representation for a list with any other
    tail (``[a|b]``), so binding one to a marker cell -- numbervars/3's
    ``'$VAR'(N)``, bagof/3's variant markers -- leaves a term that every
    later walk refuses (``PartialTermError``: writeq, answer snapshots).
    Callers that substitute markers for variables ask this first.  Empty for
    a term with no partial list in it.
    """
    out: dict = {}

    def walk(t: Any) -> None:
        t = deref(t)
        if is_var(t) or isinstance(t, (bool, int, float, str, bytes)) or t is None:
            return
        if isinstance(t, list) or type(t) is tuple:
            for e in t:
                walk(e)
        elif isinstance(t, (SegList, SegString, SegBytes)):
            for seg in t.segments:
                if isinstance(seg, VarSeg):
                    v = deref(seg.var)
                    if is_var(v):
                        out.setdefault(id(v), type(t))
                    else:
                        walk(v)
                elif isinstance(seg, ConcreteSeg):
                    for e in seg.elements:
                        walk(e)
        elif type(t) is DictTerm:
            for v in t.data.values():
                walk(v)
        elif type(t) is dict:
            for v in t.values():
                walk(v)
        elif is_term_instance(t):
            for name in term_field_names(t):
                walk(getattr(t, name))

    walk(term)
    return out


def _segments_of(tail):
    """*tail* (a ``SegList`` or ``SegString``) as SegList-shaped segments.

    ``SegString`` holds plain ``str`` segments alternating with ``VarSeg``
    holes (``terms.py``'s ``SegString.__init__`` rejects anything else), while
    ``SegList`` holds ``ConcreteSeg``/``VarSeg``.  A string segment is the
    char list it denotes, which is how ``SegString`` already unifies against a
    ``SegList`` (``SegString.__unify__``'s list arm).
    """
    if isinstance(tail, SegString):
        return [
            ConcreteSeg([char_atom(c) for c in seg]) if isinstance(seg, str) else seg
            for seg in tail.segments
        ]
    return list(tail.segments)


def _cons(head, tail, who: str):
    """``[Head | Tail]`` in the engine's list shapes: list, str, or a partial
    ``SegList`` — never a ``(".", H, T)`` cell.

    Spec §5.4: ``'.'/2`` is how a list *looks* through ``functor/3`` and
    ``=..``, never how one is *stored*.  So the name position's ``'.'``/2 case
    builds the shape the runtime actually holds, and a term built this way is
    a real list that unifies with one written longhand.  Consing a char atom
    onto a ``str`` keeps it a ``str``; consing anything else onto one expands
    the string to the char list it denotes, which is the only shape that can
    hold the foreign head.
    """
    tail = deref(tail)
    if isinstance(tail, list):
        return [head] + tail
    if isinstance(tail, str):
        h = deref(head)
        if is_char_atom(h):
            return spelling(h) + tail
        return [head] + [char_atom(c) for c in tail]
    if is_chars(tail):
        # STAGE 1: consing a char atom onto the chars carrier keeps it a
        # carrier; anything else expands it to the char list it denotes.
        text = chars_text(tail)
        h = deref(head)
        if is_char_atom(h):
            return chars(spelling(h) + text)
        return [head] + [char_atom(c) for c in text]
    if is_var(tail):
        return SegList([ConcreteSeg([head]), VarSeg(tail)])
    if isinstance(tail, (SegList, SegString)):
        return SegList([ConcreteSeg([head]), *_segments_of(tail)])
    from clausal.logic.exceptions import LogicException, type_error
    raise LogicException(type_error("list", tail, who))


def _construct_named(name_val, args, who: str):
    """Build a term with functor *name_val* over *args*, for ``functor/3``/``unpack/2``.

    A ``PredicateMeta`` handed in as the name used to be reduced to
    ``name_val.__name__`` and rebuilt as a generic compound (the since-retired
    ``Compound`` class), throwing away the very class the caller supplied.  Since that never unified
    with a declared term-class instance of the same name and arity, that made
    decompose-then-reconstruct fail for every declared with-fields term, and
    the two rendered identically so the mismatch was invisible.  Downstream
    documentation had recorded the symptom as settled behaviour rather than
    a defect.  See
    ``todo/done/functor-3-names-an-atom-as-a-class-but-a-compound-as-a-string.md``.

    Only the class arm resolves.  An ATOM name is deliberately *not* resolved
    back to a class: which module's ``cite`` a bare name means is ambiguous
    under module-local atom identity, and downstream callers depend on the
    name arm behaving exactly as it does.

    ``field_names_for`` answering is NOT by itself "this is a class": its
    arm 3 (final fix wave, CRITICAL 2, 2026-09-23) also answers for a NAME
    -- a mangled atom string resolves through its owner module's registry
    and gets real field names back, with no class in sight.  So the class
    arms below are gated on ``isinstance(name_val, type)`` as well as the
    fields being known; a name that only resolves through arm 3 falls
    through to the generic shape, same as any other atom.

    An arity that disagrees with the class's field count is not that term, so
    it falls through to the generic shape rather than raising — which keeps a
    downstream ``functor/3`` probe over an arity-0 schema atom working.

    Spec §6.4 (2026-09-06-atoms-as-cells-strings): the generic shape is a
    CELL, ``(spelling, *args)`` — cells are how the
    engine represents a compound data term post-P3-2, so a term built here now
    unifies with the same term written longhand.  §5.4 carves out ``'.'``/2,
    which builds the engine's list shape instead (see :func:`_cons`).
    """
    # arity is already in hand (IMPORTANT 2, 2026-09-23): pass it so arm 3's
    # exact-arity read (``signature_for``, which chains ``_signatures``
    # before ``_declared``) is used instead of the lossier no-arity
    # by-name read.  Harmless for a plain (un-mangled) atom name, which
    # still answers None here with no db/namespace supplied.
    _ctor_fields = field_names_for(name_val, arity=len(args))
    if isinstance(name_val, type) and _ctor_fields is not None:
        # ``field_names_for`` is the field list whatever minted the class —
        # ``make_predicate`` or a declared ``@dataclass`` functor.  (The
        # rewriter's ``class <functor>(metaclass=PredicateMeta)`` block, the
        # route for an in-file predicate, went at W4b-3 slice 5: a module
        # binds its predicate's handle, not a class.)  ``PredicateMeta.__call__`` fills missing
        # trailing fields with fresh Vars and rejects only *overflow*, so it
        # is this exact-match gate, not the constructor, that makes
        # ``name_val(*args)`` bind every field positionally with nothing
        # left over.
        if len(_ctor_fields) == len(args):
            return name_val(*args)
        # Arity disagrees → not this class; fall through as the bare name.
        name_val = mint(name_val.__name__)
    if _is_empty_list(name_val):
        # Fix round 1, item 2: the name is the reserved atom ``'[]'``, which
        # IS the empty list.  At arity 0 the term is that list; above arity 0
        # it is an ordinary compound whose functor spells ``[]`` — Scryer
        # answers ``T =.. [[], a]`` with ``[](a)``.
        if not args:
            return []
        return (NIL_SPELLING, *args)
    if _term_is_atom(name_val):
        # §5.4: ``'.'``/2 in the name position builds the engine's list shape.
        # This is checked BEFORE the generic cell arm because a
        # ``(".", H, T)`` cell is not a list, does not unify with one, and no
        # runtime path may construct it.
        if len(args) == 2 and spelling(name_val) == ".":
            return _cons(args[0], args[1], who)
        return (spelling(name_val), *args)
    # A09-F027: the functor of a compound must be atom-shaped (ISO:
    # type_error(atom, Name)), else unpack(T, [3, 1, 2]) built
    # a compound named "3" and functor/3 built a bogus functor "f(1)".
    from clausal.logic.exceptions import LogicException, type_error
    raise LogicException(type_error("atom", name_val, who))


@_builtin("functor", 3)
def _functor__3(term, name, arity, trail, k):
    """functor(Term, Name, Arity) — decompose or compose a term.

    If Term is bound: unify Name with its functor name and Arity with its arity.
    If Term is unbound: Name and Arity must be bound; construct a cell.
    """
    term_val = deref(term)

    if is_var(term_val):
        # Construction mode
        name_val = deref(name)
        arity_val = deref(arity)
        # ISO 8.5.1.3 a, b, d, f (Scryer-verified): an unbound Name or Arity
        # is an instantiation error, a non-integer Arity a type error and a
        # negative one a domain error.  All four used to FAIL silently.
        # A09-F015 / A01-D001(c): a bool arity is not an integer (True is
        # not 1).
        if is_var(name_val) or is_var(arity_val):
            from clausal.logic.exceptions import (  # noqa: PLC0415
                LogicException, instantiation_error)
            raise LogicException(instantiation_error("functor/3"))
        _check_nonneg_int_arg(arity_val, "functor/3")
        # Spec §6.4 / ISO 8.5.1.3 e: the name of a term built here must be
        # ATOMIC.  A list, a dict, a set, a cell or any other compound shape
        # is not, and used to be handed straight back as ``T`` at arity 0 —
        # ``functor(T, [1, 2], 0)`` "succeeded" with a list as the name.
        # A declared predicate reference stays in: a declared functor class
        # (or, era-agnostic per F2b, the mangled atom it becomes at the
        # later flip) is an atom value (arity-0 declared atoms are the
        # corpus's schema atoms) and ``_construct_named`` resolves it for
        # itself.  ``is_declared_predicate_name`` never widens past that --
        # a bare ``@dataclass`` class still answers False here, so
        # ``functor(T, SomeDataclass, 0)`` keeps raising below.
        # Fix round 1, item 2: the EMPTY LIST is the reserved atom ``'[]'``,
        # so it is an atomic name — ``functor(T, [], 0)`` gives ``T = []``
        # (Scryer-verified).  ``b""``/``""`` are the same term.  A non-empty
        # ``bytes`` is a code LIST and stays out (it is a compound).
        if not (
            _term_is_atom(name_val)
            or _is_empty_list(name_val)
            or is_declared_predicate_name(name_val)
            or isinstance(name_val, (int, float, bool, bytes))
            or name_val is None
        ):
            from clausal.logic.exceptions import LogicException, type_error
            raise LogicException(type_error("atomic", name_val, "functor/3"))
        if arity_val == 0:
            constructed = name_val
        else:
            args = tuple(Var() for _ in range(arity_val))
            constructed = _construct_named(name_val, args, "functor/3")
        mark = trail.mark()
        if unify(term, constructed, trail):
            yield None
        trail.undo(mark)
    else:
        # Inspection mode. SegList/SegString never appear at the
        # Clausal surface — walk to ground form first per user
        # decision 2026-06-13 (audit follow-up). Non-ground Seg*
        # surfaces here as a still-Seg* shape; ``_functor_name``
        # returns None for that and we fall through to silent
        # failure, matching the existing "unknown shape" convention.
        term_val = walk_seg(term_val)
        f_val = _functor_name(term_val)
        a_val = _arity(term_val)
        if f_val is None or a_val is None:
            return
        # §6.4: the name position hands back an ATOM.  The funnel answers a
        # bare slot-0 spelling; ``mint`` is what turns that into the atom.
        if type(f_val) is str:
            f_val = mint(f_val)
        mark = trail.mark()
        if unify(name, f_val, trail):
            mark2 = trail.mark()
            if unify(arity, a_val, trail):
                yield None
            trail.undo(mark2)
        trail.undo(mark)


@_builtin("arg", 3)
def _arg__3(n, term, arg_out, trail, k):
    """arg(N, Term, arg) — unify arg with the N-th argument of Term (1-based)."""
    n_val = deref(n)
    term_val = deref(term)
    # ISO 8.5.2.3 (Scryer-verified): an unbound Term is an instantiation
    # error, an atomic one a type_error(compound), and a bound N that is not
    # a non-negative integer a type or domain error.  All used to FAIL
    # silently.  (An unbound N enumerates -- a deliberate extension.)
    if is_var(term_val):
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, instantiation_error)
        raise LogicException(instantiation_error("arg/3"))
    _check_nonneg_int_arg(n_val, "arg/3")
    from clausal.logic.builtins.type_checks import _is_atomic_term  # noqa: PLC0415
    if _is_atomic_term(walk_seg(term_val)):
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, type_error)
        raise LogicException(type_error("compound", term_val, "arg/3"))
    if is_var(n_val):
        # Output mode: enumerate (N, Arg) pairs, SWI-style relational arg/3.
        # This used to FAIL SILENTLY — the exact ground-vs-var blind spot of
        # todo/audit-tests-input-output-mode-coverage.md.  Same _nth_arg
        # semantics as the ground mode, so a list enumerates its cons view
        # (1 → head, 2 → tail) and arity-0 terms yield nothing.
        term_norm = walk_seg(term_val)
        index = 1
        while True:
            try:
                arg_val = _nth_arg(term_norm, index)
            except IndexError:
                return
            mark = trail.mark()
            if unify(n_val, index, trail) and unify(arg_out, arg_val, trail):
                yield None
            trail.undo(mark)
            index += 1
    # SegList/SegString never appear at the Clausal surface — walk
    # to ground form first (user decision 2026-06-13).
    term_val = walk_seg(term_val)
    try:
        arg_val = _nth_arg(term_val, n_val)
    except IndexError:
        return
    mark = trail.mark()
    if unify(arg_out, arg_val, trail):
        yield None
    trail.undo(mark)


@_builtin("unpack", 2)
def _univ__2(term, lst, trail, k):
    """univ(Term, List) — ``=..`` in Prolog.

    If Term is bound: List unifies with [functor | args].
    If Term is unbound: List must be [FunctorName | Args]; Term is constructed.

    TODO (post-audit 2026-06-13): rename ``unpack/2`` to a less
    procedural-sounding Clausal name. This is the Python-callable
    form of ISO ``=..`` (univ). Candidates: ``univ/2``,
    ``decompose/2``, ``as_list/2``, ``to_list/2``, ``structure/2``.
    User to decide.
    """
    term_val = deref(term)

    if not is_var(term_val):
        # Decomposition. SegList/SegString never appear at the
        # Clausal surface — walk to ground form first (user decision
        # 2026-06-13).
        term_val = walk_seg(term_val)
        f_val = _functor_name(term_val)
        if f_val is None:
            return
        # §6.4: the head of the univ list is an ATOM, not a bare spelling.
        if type(f_val) is str:
            f_val = mint(f_val)
        decomposed = [f_val] + _args_list(term_val)
        mark = trail.mark()
        if unify(lst, decomposed, trail):
            yield None
        trail.undo(mark)
    else:
        # Construction
        # ISO 8.5.3.3 (Scryer-verified): an unbound or partial List, or an
        # unbound head, is an instantiation error; a non-list List is
        # type_error(list, L); the empty list is
        # domain_error(non_empty_list, []).  All used to FAIL silently.
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, domain_error, instantiation_error, type_error)
        from clausal.logic.builtins.lists import _as_items  # noqa: PLC0415
        lst_val = deref(lst)
        items = _as_items(lst_val)
        if items is None:
            if is_var(lst_val) or isinstance(lst_val, (SegList, SegString)):
                if isinstance(lst_val, SegList):
                    walked = lst_val._walk_raw()
                    if isinstance(walked, list):
                        items = walked
                if items is None:
                    raise LogicException(instantiation_error("=../2"))
            else:
                raise LogicException(type_error("list", lst_val, "=../2"))
        lst_val = list(items)
        if len(lst_val) == 0:
            raise LogicException(domain_error("non_empty_list", [], "=../2"))
        f_val = deref(lst_val[0])
        if is_var(f_val):
            raise LogicException(instantiation_error("=../2"))
        args_vals = [deref(a) for a in lst_val[1:]]
        if len(args_vals) == 0:
            # ``T =.. [N]`` — N must be ATOMIC (spec §6.4 / ISO 8.5.3.3 e);
            # a one-element list holding a list or any other compound shape
            # is not a term description.  Same admissions as ``functor/3``.
            # Fix round 1, item 2: the EMPTY LIST is the reserved atom
            # ``'[]'``, so ``T =.. [[]]`` gives ``T = []`` (Scryer-verified),
            # where it used to be ``type_error(atomic, [])``.
            if not (
                _term_is_atom(f_val)
                or _is_empty_list(f_val)
                or is_declared_predicate_name(f_val)
                or isinstance(f_val, (int, float, bool, bytes))
                or f_val is None
            ):
                raise LogicException(type_error("atomic", f_val, "=../2"))
            constructed: Any = f_val  # atom
        else:
            constructed = _construct_named(f_val, args_vals, "=../2")
        mark = trail.mark()
        if unify(term, constructed, trail):
            yield None
        trail.undo(mark)


# ── V2-13 Term inspection ──────────────────────────────────────────────────────


def _copy_dif(value, var_map, attvars, seen, trail) -> bool:
    """Re-post each ``dif/2`` pair of *value* (the ``"dif"`` attribute: a
    list of ``(X, Y)`` pairs) on its copy.  A pair is shared by the
    attributes of all its variables, so *seen* makes it posted once."""
    from clausal.logic.constraints import dif  # noqa: PLC0415
    for pair in value:
        if id(pair) in seen:
            continue
        seen.add(id(pair))
        x, y = pair
        if not dif(_copy_term_impl(x, var_map, attvars),
                   _copy_term_impl(y, var_map, attvars), trail):
            return False
    return True


#: Attribute key -> how copy_term/2 re-installs that attribute on a copy:
#: ``fn(value, var_map, attvars, seen, trail) -> bool`` (False: the copied
#: constraint is already violated).  It copies the attribute's terms with
#: the SAME *var_map* (so a variable shared with the copied term is the
#: copy's variable, and any other is copied fresh, as Scryer copies an
#: attribute term) and appends any further attributed variable it meets to
#: *attvars*.  An attribute whose key has no copier is not copied: its value
#: is a Python object (a freeze/2 goal closure, a CLP propagator network)
#: that cannot be renamed apart -- see CHANGELOG / the todo on copying them.
_ATTRIBUTE_COPIERS = {"dif": _copy_dif}


def _copy_attributes(attvars, var_map, trail) -> bool:
    """Install on each fresh copy the attributes of its original, for every
    ``(original, fresh)`` in *attvars* -- a worklist: copying an attribute's
    terms can reach more attributed variables, which are appended to it."""
    seen: set = set()
    i = 0
    while i < len(attvars):
        orig, _fresh = attvars[i]
        i += 1
        for key, value in list((orig.attrs or {}).items()):
            copier = _ATTRIBUTE_COPIERS.get(key)
            if copier is not None and not copier(value, var_map, attvars, seen, trail):
                return False
    return True


@_builtin("copy_term", 2)
def _copy_term__2(original, copy, trail, k):
    """copy_term(Original, Copy) — unify Copy with a deep copy of Original with fresh Vars.

    Attributes are copied too, as Scryer (and SICStus/SWI) copy them: a
    ``dif/2`` constraint on a variable of Original holds on its copy
    (``dif(A, a), copy_term(A, B), B = a`` fails).  See
    ``_ATTRIBUTE_COPIERS`` for which attributes can be copied.
    """
    orig_val = deref(original)
    var_map: dict = {}
    attvars: list = []
    copied = _copy_term_impl(orig_val, var_map, attvars)
    mark = trail.mark()
    if (not attvars or _copy_attributes(attvars, var_map, trail)) \
            and unify(copy, copied, trail):
        yield None
    trail.undo(mark)


@_builtin("term_variables", 2)
def _term_variables__2(term, vars_out, trail, k):
    """term_variables(Term, Vars) — unify Vars with list of unbound variables in Term."""
    term_val = deref(term)
    result: list = []
    _collect_vars_impl(term_val, result)
    mark = trail.mark()
    if unify(vars_out, result, trail):
        yield None
    trail.undo(mark)


@_builtin("numbervars", 3)
def _number_vars__3(term, start, end, trail, k):
    """number_vars(Term, Start, End) — bind unbound Vars in Term to '$VAR'(N) atoms.

    Variables are numbered left-to-right starting at Start.  End is unified
    with the next available number after all variables are numbered.
    """
    start_val = deref(start)
    if is_var(start_val) or not isinstance(start_val, int):
        return
    term_val = deref(term)
    vars_list: list = []
    _collect_vars_impl(term_val, vars_list)
    # A variable in the hole of a partial list / string (the T of [A|T]) can
    # only be bound to a list: ``[A|'$VAR'(1)]`` has no representation, and
    # every later walk of the term -- writeq, the answer snapshot -- would
    # raise PartialTermError.  It stays unbound and is not counted, at any
    # depth.  (ISO numbers it: Scryer gives N = 3 for f([A|T], B).  This
    # follows the [a|b] representation gap, not a choice about numbervars.)
    if vars_list:
        holes = _hole_var_ids(term_val)
        if holes:
            vars_list = [v for v in vars_list if id(v) not in holes]
    # Bind each unbound var to the cell '$VAR'(N)
    marks = []
    for i, v in enumerate(vars_list):
        m = trail.mark()
        atom = ("$VAR", start_val + i)
        if not unify(v, atom, trail):
            for mk in reversed(marks):
                trail.undo(mk)
            return
        marks.append(m)
    end_val = start_val + len(vars_list)
    mark = trail.mark()
    if unify(end, end_val, trail):
        yield None
    trail.undo(mark)
    for mk in reversed(marks):
        trail.undo(mk)


# ── gensym/2 ──────────────────────────────────────────────────────────────────

import threading

_gensym_counters: dict[str, int] = {}
_gensym_lock = threading.Lock()


@_builtin("gensym", 2)
def _gensym__2(prefix, atom, trail, k):
    """gensym(Prefix, Atom) — generate a unique atom by appending a counter.

    Counter is global and monotonically increasing. NOT trailed — survives
    backtracking. This is intentional and matches Prolog's gensym/2 semantics.
    """
    prefix_d = deref(prefix)
    if is_var(prefix_d) or not _term_is_atom(prefix_d):
        return
    # §6.4: the prefix is an ATOM read by spelling, and the counter dict is
    # keyed by that spelling so the two atom shapes share one counter.
    prefix_spelling = spelling(prefix_d)
    with _gensym_lock:
        count = _gensym_counters.get(prefix_spelling, 0) + 1
        _gensym_counters[prefix_spelling] = count
    result = mint(f"{prefix_spelling}_{count}")
    if unify(atom, result, trail):
        yield None


# ── global_atom/2 ─────────────────────────────────────────────────────────────


@_builtin("global_atom", 2)
def _global_atom__2(name, atom, trail, k):
    """global_atom(Name, Atom) — reflect on the process-wide global atom dict.

    Exposes ``clausal.import_hook.predicate_builtins``, the dict that seeds
    every fresh predicate module's globals.  Modes:

      (+Name, -Atom): mint-on-demand.  Name is an ATOM read by spelling
        (spec §6.4).  Look that spelling up in the global dict; if absent,
        install ``mint(spelling)``.  Unify Atom with it.
      (+Name, +Atom): guard.  Succeed iff ``predicate_builtins[Name] ==
        Atom`` — EQUALITY, never identity (spec §2/§5.2): an atom is a value,
        and two atoms of the same spelling are the same atom whether or not
        they are the same object.
      (-Name, +Atom): reverse lookup.  Succeed iff Atom resolves back to
        Name in the dict (i.e. Atom is genuinely the registered global, not
        a module-local namesake); unify Name with the ATOM of that name.
        Atom is ordinarily the cell itself; a 0-arity ``PredicateMeta``
        (what the retired ``make_predicate(name, [])`` built; W4b-3 slice 6)
        is still accepted for anything that manually installs one.
      (-Name, -Atom): enumerate.  Yield one solution per registered atom —
        a cell whose spelling is its key, or a legacy 0-arity
        PredicateMeta.  Order not guaranteed.

    P3-1 Task 7 sweep: pre-pivot this builtin minted a fresh
    ``make_predicate(Name, [])`` class per name (a function retired since,
    at W4b-3 slice 6) — the last live,
    user-reachable atom-class-construction path (every other one is
    compile-time and was flipped in Task 2/3).  It is one of the five
    documented legitimate ways to reach an undeclared atom under
    ``-strict_atoms`` (see ``compiler_v2._build_strict_atoms_diagnostic``),
    so it had to be fixed to match, not deleted.
    """
    # Lazy import: clausal.import_hook depends transitively on this package,
    # so a top-level import here would create a cycle at package load time.
    from clausal.import_hook import predicate_builtins

    name_val = deref(name)
    atom_val = deref(atom)
    name_bound = not is_var(name_val)
    atom_bound = not is_var(atom_val)

    if name_bound:
        if not _term_is_atom(name_val):
            # A bound Name that is not an atom is a TYPE error, not a
            # failure.  Under ``-double_quotes(chars)`` the old spelling
            # ``global_atom("date", A)`` hands over a CHAR LIST, and a silent
            # failure there took a whole clause -- and five suites -- down
            # with it before anyone saw why (corpus, 2026-09-08).  Write the
            # atom quoted (``global_atom('date', A)``, or simply ``'date'``),
            # or come from text through ``atom_chars/2``.
            from clausal.logic.exceptions import LogicException, type_error
            raise LogicException(type_error("atom", name_val, "global_atom/2"))
        key = spelling(name_val)
        if atom_bound:
            # Guard mode: succeed iff atom_val EQUALS the registered global.
            if predicate_builtins.get(key) == atom_val:
                yield None
            return
        # Mint-on-demand mode: install the atom for the spelling (no class).
        val = predicate_builtins.setdefault(key, mint(key))
        mark = trail.mark()
        if unify(atom, val, trail):
            yield None
        trail.undo(mark)
        return

    # name is unbound.
    if atom_bound:
        # Reverse-lookup mode.  Atom must resolve back to Name in the
        # global dict — either the interned str itself, or (backward
        # compatibility) a 0-arity PredicateMeta's __name__.
        if _term_is_atom(atom_val):
            cls_name = spelling(atom_val)
        else:
            return
        # Equality, never identity (spec §2/§5.2).
        if predicate_builtins.get(cls_name) != atom_val:
            return
        mark = trail.mark()
        # The NAME position answers an ATOM (spec §6.4), not the spelling.
        if unify(name, mint(cls_name), trail):
            yield None
        trail.undo(mark)
        return

    # Both unbound — enumerate registered atoms: an interned str
    # (self-mapped, key == value — the P3-1 shape) or a legacy 0-arity
    # PredicateMeta.  Snapshot keys so concurrent minting elsewhere can't
    # perturb iteration.
    for key, val in list(predicate_builtins.items()):
        # THE FLIP: a registered global atom is the CELL ``(key,)``; the
        # legacy 0-arity PredicateMeta is still accepted.  A pool entry that
        # is neither (or whose spelling disagrees with its key) is not this
        # predicate's business and is skipped, as before.
        if _term_is_atom(val):
            if spelling(val) != key:
                continue
        else:
            continue
        mark = trail.mark()
        if unify(name, mint(key), trail) and unify(atom, val, trail):
            yield None
        trail.undo(mark)


# ── module_constant/3 ──────────────────────────────────────────────────────────


def _module_constants_dict(py_module):
    """The ``-constants`` registry a loaded ``.clausal`` module owns, or
    ``None`` if *py_module* isn't a compiled Clausal module.

    ``__clausal_module__`` is set at the end of ``import_hook``'s module-exec
    pipeline (both the V1 and V2 pipelines) to the ``clausal.logic.database.
    Module`` instance — see ``docs/import.md``'s "two module objects" table.
    Its ``.constants`` dict is populated by ``register_module_constant``
    (``clausal/logic/constants.py``), called from the lowered ``-constants``
    directive itself — so only a module's OWN declarations appear here, never
    a constant it merely imported (see docs/import.md).
    """
    logic_module = getattr(py_module, "__clausal_module__", None)
    if logic_module is None:
        return None
    return logic_module.constants


@_builtin("constant_value", 2)
def _constant_value__2(name, value, trail, k):
    """constant_value(Name, Value) — the constant *Name* names.

    ``Name`` is an ATOM (the NAME POSITION speaks atoms in and atoms out,
    spec §6.4); ``Value`` is its frozen ground value.

    This is Markus Triska's name for the cross-implementation convention
    (2026-09-10), so the spelling and arity are not ours to vary: an
    exported `.pl` and any expansion prelude must use exactly this.

    **Scope, and the one compromise.** In a Prolog system there is one
    program, so ``constant_value/2`` is a fact about it. Clausal has
    modules, and the module-implicit reading would need the CALLING
    module -- which a builtin does not get: the registry hands dispatch
    functions their arguments and a trail, and nothing else. So this
    enumerates every loaded Clausal module's own declarations, exactly as
    ``module_constant(-Module, +Name, ?Value)`` does. Two modules that
    declare the same constant name both answer, in load order. Use
    ``module_constant/3`` when the module matters.

    Modes:

      (+Name, ?Value): the value(s) declared under that name.
      (-Name, ?Value): enumerate every declared constant.
    """
    m = Var()
    yield from _module_constant__3(m, name, value, trail, k)


@_builtin("constant_number_units", 3)
def _constant_number_units__3(name, number, units, trail, k):
    """constant_number_units(Name, Number, Units) — as DECLARED.

    ``Name`` is an atom, ``Number`` and ``Units`` are the pair the
    ``-constant_number_units`` declaration wrote. Named for what it can hold:
    only NUMBERS carry units (operator, 2026-09-11), which is why this is not
    ``constant_value_units/3``.

    **It reports the DECLARATION, not the stored value** (operator's ruling,
    2026-09-11). Those differ whenever the declared unit is not the base of
    its own dimension, because the units library rescales to that base:
    ``-constant_number_units(standstill, 30, day)`` stores
    ``Quantity(2592000, second)``, and both the 30 and the ``day`` are
    unrecoverable from it. Reporting the normalised pair would make this a
    lossy view of ``constant_value/2`` rather than a second source of
    information — and it would make it impossible to check that a parameter's
    declared unit matches the unit its NAME claims, since every duration
    comes back as ``second`` regardless of what was written.

    ``constant_value/2`` remains the VALUE view and yields the Quantity. The
    two therefore disagree about the number on purpose: for ``30 day``, /2
    gives 2592000 seconds and /3 gives 30 day. Both are true of the same
    constant.

    A constant declared without units has no solution here.

    Modes:

      (+Name, ?Number, ?Units): the declared magnitude and units.
      (-Name, ?Number, ?Units): enumerate every united constant.
    """
    from clausal.logic.constants import loaded_clausal_py_modules  # noqa: PLC0415
    name_val = deref(name)
    want = spelling(name_val) if _term_is_atom(name_val) else None
    if want is None and not is_var(name_val):
        return                       # a non-atom names no constant
    for py_module in loaded_clausal_py_modules():
        logic_module = getattr(py_module, "__clausal_module__", None)
        declared = getattr(logic_module, "constant_units", None)
        if not declared:
            continue
        for cname, pair in list(declared.items()):
            if want is not None and cname != want:
                continue
            cnumber, cunits = pair
            if cnumber is None:
                continue             # no literal magnitude was declared
            mark = trail.mark()
            if (unify(name, mint(cname), trail)
                    and unify(number, cnumber, trail)
                    and unify(units, cunits, trail)):
                yield None
            trail.undo(mark)


def _module_constant_units_dict(module):
    """A module's ``constant_units`` registry, or ``None``.

    Accepts EITHER module object, because the two callers hold different
    ones: a hand-written ``module_constant_units(m, ...)`` passes the PYTHON
    module that ``-import_module`` binds (as ``module_constant/3`` does),
    while the compile-time insertion for ``constant_number_units/3`` passes
    the LOGIC module, which is what ``$module`` holds where the transformer
    emits it. See docs/import.md's "two module objects" table -- requiring
    one of them would make the same relation unwritable from one of its two
    call paths.
    """
    own = getattr(module, "constant_units", None)
    if own is not None:
        return own                      # already the logic Module
    logic_module = getattr(module, "__clausal_module__", None)
    if logic_module is None:
        return None
    return getattr(logic_module, "constant_units", None)


@_builtin("module_constant_units", 4)
def _module_constant_units__4(m, name, number, units, trail, k):
    """module_constant_units(Module, Name, Number, Units) — the DECLARED pair,
    scoped to one module.

    The module-scoped sibling of ``constant_number_units/3``, standing to it
    exactly as ``module_constant/3`` stands to ``constant_value/2``.

    It exists because a builtin never receives the CALLING module -- the
    registry hands dispatch functions their arguments and a trail, and
    nothing else -- so ``constant_number_units/3`` answers for every loaded
    module that declares the name, in load order. Where the module matters,
    it has to be an ARGUMENT, and the caller that always knows it is the
    COMPILER: the transformer inserts ``$module`` here, the same way it
    already hands ``$module`` to ``$register_constant_units`` when the
    declaration is lowered. Reading works the way writing already does.

    Reports the DECLARATION, not the stored value, for the reasons set out at
    ``constant_number_units/3``: a rescaling unit makes the stored Quantity
    unable to yield either half back.

    A module that does not declare *Name* simply FAILS. This is a lookup, not
    an assertion -- the raise for a name nothing declares belongs at the
    ``constant_number_units/3`` call site, where the compiler can see the name
    was written as a literal and can refuse it before anything runs.
    """
    registry = _module_constant_units_dict(deref(m))
    if registry is None:
        return
    name_val = deref(name)
    if is_chars(name_val):
        # STAGE 1: the compiler's name thunk hands its spelling back through
        # the inbound text rule ($text_in), so the SPELLING arrives as the
        # carrier -- read it as the registry key it is.
        name_key = chars_text(name_val)
    elif isinstance(name_val, str):
        # The compile-time insertion passes the SPELLING directly (see
        # term_rewriting's constant_number_units branch): in the importing
        # module the name re-resolves to the imported value, so the compiler
        # sends the registry key rather than something that looks it up.
        name_key = name_val
    else:
        name_key = spelling(name_val) if _term_is_atom(name_val) else None
    if not is_var(name_val):
        if name_key is None or name_key not in registry:
            return
        number_val, units_val = registry[name_key]
        mark = trail.mark()
        if unify(number, number_val, trail) and unify(units, units_val, trail):
            yield None
        trail.undo(mark)
        return
    for n, (number_val, units_val) in list(registry.items()):
        mark = trail.mark()
        if (unify(name, mint(n), trail)
                and unify(number, number_val, trail)
                and unify(units, units_val, trail)):
            yield None
        trail.undo(mark)


@_builtin("module_constant", 3)
def _module_constant__3(m, name, value, trail, k):
    """module_constant(Module, Name, Value) — reflect on a module's own
    ``-constants`` declarations.

    ``Module`` is the Python module object a ``-import_module(...)``
    directive binds (the same object a qualified reference like
    ``other_module._PI_`` resolves against); ``Name`` is the ATOM of the
    constant's full declaration spelling (``'_PI_'``, underscores included,
    not ``'PI'``) -- the NAME POSITION speaks atoms in and atoms out (spec
    §6.4), and the registry itself stays keyed by the spelling; ``Value`` is
    the constant's frozen value (see
    ``clausal.logic.constants._freeze``) — the identical object the module's
    own clause bodies embed.

    Modes:

      (+Module, +Name, ?Value): look up.  Fails if ``Module`` declares no
        constant named ``Name``; otherwise checks/binds ``Value``.
      (+Module, -Name, ?Value): enumerate ``Module``'s constants.
      (-Module, +Name, ?Value): enumerate every LOADED Clausal module
        (``sys.modules``, snapshotted) that declares a constant named
        ``Name``.
      (-Module, -Name, ?Value): enumerate every ``(Module, Name, Value)``
        triple across every loaded Clausal module.

    Only constants a module DECLARES (via its own ``-constants``
    directive(s)) are reflected here — an imported constant is not
    re-registered on the importer, so it is reachable only through the
    module that actually declared it. See docs/import.md.
    """
    m_val = deref(m)
    name_val = deref(name)
    m_bound = not is_var(m_val)
    name_bound = not is_var(name_val)
    # THE FLIP (spec §6.4): the Name argument is an ATOM read by spelling; a
    # STRING there names no constant.
    name_key = spelling(name_val) if _term_is_atom(name_val) else None

    if m_bound:
        cdict = _module_constants_dict(m_val)
        if cdict is None:
            return
        if name_bound:
            if name_key is None or name_key not in cdict:
                return
            mark = trail.mark()
            if unify(value, cdict[name_key], trail):
                yield None
            trail.undo(mark)
            return
        for n, v in list(cdict.items()):
            mark = trail.mark()
            if unify(name, mint(n), trail) and unify(value, v, trail):
                yield None
            trail.undo(mark)
        return

    # Module unbound: enumerate every loaded Clausal module.
    # Snapshot values() so a module load triggered mid-iteration (e.g. by a
    # lazy import somewhere downstream) can't perturb this iteration.
    # ``sys.modules`` plus the modules a test run loads outside it (see
    # ``clausal.logic.constants.register_detached_module``).
    from clausal.logic.constants import loaded_clausal_py_modules  # noqa: PLC0415
    for py_module in loaded_clausal_py_modules():
        cdict = _module_constants_dict(py_module)
        if not cdict:
            continue
        if name_bound:
            if name_key is None or name_key not in cdict:
                continue
            mark = trail.mark()
            if unify(m, py_module, trail) and unify(value, cdict[name_key], trail):
                yield None
            trail.undo(mark)
            continue
        for n, v in list(cdict.items()):
            mark = trail.mark()
            if (unify(m, py_module, trail) and unify(name, mint(n), trail)
                    and unify(value, v, trail)):
                yield None
            trail.undo(mark)


# ── unify_with_occurs_check/2, subsumes_term/2, acyclic_term/1 (ISO) ─────────
#
# ISO core builtins that did not exist (existence_error(procedure, ...)).
# Answers are Scryer's (measured 2026-09-30).


@_builtin("unify_with_occurs_check", 2)
def _unify_with_occurs_check__2(a, b, trail, k):
    """unify_with_occurs_check(X, Y) -- ISO 8.2.2: unification that fails
    rather than build a cyclic term (``unify_with_occurs_check(X, f(X))``
    fails)."""
    from clausal.logic.constraints import _structural_unify_oc  # noqa: PLC0415
    mark = trail.mark()
    if _structural_unify_oc(a, b, trail):
        yield None
    trail.undo(mark)


@_builtin("subsumes_term", 2)
def _subsumes_term__2(general, specific, trail, k):
    """subsumes_term(General, Specific) -- ISO 8.2.4: some substitution of
    General's variables makes it identical to Specific, binding none of
    Specific's.  Leaves no bindings.

    The ISO reference definition, step for step::

        \\+ \\+ (term_variables(S, V1), unify_with_occurs_check(G, S),
               term_variables(V1, V2), V1 == V2)
    """
    from clausal.logic.constraints import _structural_unify_oc  # noqa: PLC0415
    v1: list = []
    _collect_vars_impl(deref(specific), v1)
    mark = trail.mark()
    ok = _structural_unify_oc(general, specific, trail)
    if ok:
        v2: list = []
        _collect_vars_impl(list(v1), v2)
        ok = len(v1) == len(v2) and all(
            deref(x) is deref(y) for x, y in zip(v1, v2))
    trail.undo(mark)
    if ok:
        yield None


def _acyclic_children(t):
    """The immediate subterms of a (dereferenced) compound *t*, or ()."""
    if type(t) in (tuple, list):
        return t
    if isinstance(t, SegList):
        raw = t._walk_raw()
        if isinstance(raw, list):
            return raw
        out = []
        for seg in raw.segments:
            if isinstance(seg, VarSeg):
                out.append(seg.var)
            else:
                out.extend(seg.elements)
        return out
    if is_term_instance(t):
        return [getattr(t, f) for f in term_field_names(t)]
    import dataclasses  # noqa: PLC0415
    if dataclasses.is_dataclass(t) and not isinstance(t, type):
        # an operator node (``Add``/``Div``/...): its operands
        return [getattr(t, f.name) for f in dataclasses.fields(t)
                if f.name != "position"]
    return ()


def _is_acyclic(term) -> bool:
    """False when *term*, followed through its variable bindings, reaches
    itself.  Iterative depth-first search with three colours: a compound on
    the current path (grey) reached again is a cycle; one fully explored
    (black) is not revisited, so a shared subterm costs one visit and a deep
    term no Python recursion."""
    grey, black = set(), set()
    stack = [(deref(term), False)]
    while stack:
        t, leaving = stack.pop()
        key = id(t)
        if leaving:
            grey.discard(key)
            black.add(key)
            continue
        children = _acyclic_children(t)
        if not children:
            continue
        if key in grey:
            return False
        if key in black:
            continue
        grey.add(key)
        stack.append((t, True))
        for c in children:
            c = deref(c)
            if id(c) in grey and _acyclic_children(c):
                return False
            stack.append((c, False))
    return True


@_builtin("acyclic_term", 1)
def _acyclic_term__1(term, trail, k):
    """acyclic_term(T) -- ISO 8.3.11 (Cor.2): T is a finite (acyclic) term.
    ``X = f(X), acyclic_term(X)`` fails."""
    if _is_acyclic(term):
        yield None
