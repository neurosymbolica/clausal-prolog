"""Core term inspection builtins: functor/3, arg/3, unpack/2, copy_term/2,
term_variables/2, numbervars/3, gensym/2, global_atom/2, module_constant/3."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.predicate import PredicateMeta, is_atom, is_term_instance, term_field_names
from clausal.terms import Compound, KWTerm, SegList, SegString, VarSeg, ConcreteSeg

from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins._helpers import _functor_name, _arity, _nth_arg, _args_list
from clausal.logic.runtime._seg_helpers import normalize_seg_input


# ── Python fallbacks for _copy_term / _collect_vars ───────────────────────────
# These are the reference implementations.  The C versions in _variables.c are
# used when available.  Keep these in sync with any changes to the C code.


def _copy_term_py(term: Any, var_map: dict) -> Any:
    """Recursively copy *term*, replacing each unbound Var with a fresh one.

    *var_map* maps original Var id -> fresh Var so that sharing is preserved.
    """
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in var_map:
            var_map[vid] = Var()
        return var_map[vid]
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
        return term
    if isinstance(term, list):
        return [_copy_term_py(e, var_map) for e in term]
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_copy_term_py(a, var_map) for a in term.args))
    if isinstance(term, KWTerm):
        return KWTerm(term.functor, **{k: _copy_term_py(v, var_map) for k, v in term.items()})
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
                    ConcreteSeg([_copy_term_py(e, var_map) for e in seg.elements])
                )
            elif isinstance(seg, VarSeg):
                new_segments.append(VarSeg(_copy_term_py(seg.var, var_map)))
            else:
                # Unknown segment — be conservative and recurse.
                new_segments.append(_copy_term_py(seg, var_map))
        return SegList(new_segments)
    if isinstance(term, SegString):
        new_segments = []
        for seg in term.segments:
            if isinstance(seg, str):
                new_segments.append(seg)
            elif isinstance(seg, VarSeg):
                new_segments.append(VarSeg(_copy_term_py(seg.var, var_map)))
            else:
                new_segments.append(_copy_term_py(seg, var_map))
        return SegString(new_segments)
    if is_term_instance(term):
        cls = type(term)
        fast = vars(cls).get("_clausal_new")
        if isinstance(fast, classmethod):
            return cls._clausal_new(*(
                _copy_term_py(getattr(term, name), var_map)
                for name in term_field_names(term)
            ))
        return cls(**{
            name: _copy_term_py(getattr(term, name), var_map)
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
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
        return
    if isinstance(term, list):
        for e in term:
            _collect_vars_py(e, result, _seen)
        return
    if isinstance(term, Compound):
        for a in term.args:
            _collect_vars_py(a, result, _seen)
        return
    if isinstance(term, KWTerm):
        for v in term.values():
            _collect_vars_py(v, result, _seen)
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
    if isinstance(term, SegString):
        for seg in term.segments:
            if isinstance(seg, str):
                continue
            if isinstance(seg, VarSeg):
                _collect_vars_py(seg.var, result, _seen)
            else:
                _collect_vars_py(seg, result, _seen)
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

    # F092 / F093 (audit 2026-05-25): the C accelerators do not know
    # about ``SegList`` / ``SegString`` — they fall through to "return
    # as-is" for ``copy_term`` (aliasing the original) and "leaf" for
    # ``term_variables`` (missing VarSegs).  Both types are absent
    # from ``_register_term_types`` (which only knows ``Compound`` and
    # ``KWTerm``).  Short-circuit Seg* shapes in Python (same pattern
    # used by ``_is_ground`` for [[F083]]) and delegate every other
    # shape to the C fast path.  Within the Python branch we still
    # recurse via ``_copy_term_py`` / ``_collect_vars_py`` so any
    # nested Seg* container is handled too.
    def _copy_term_impl(term: Any, var_map: dict) -> Any:
        t = deref(term)
        if isinstance(t, (SegList, SegString)):
            return _copy_term_py(t, var_map)
        return _c_copy_term_impl(t, var_map)

    def _collect_vars_impl(term: Any, result: list) -> None:
        t = deref(term)
        if isinstance(t, (SegList, SegString)):
            _collect_vars_py(t, result)
            return
        _c_collect_vars_impl(t, result)
except ImportError:
    pass

# Re-export for callers that import _copy_term directly (e.g. specialization.py)
_copy_term = _copy_term_impl


def _construct_named(name_val, args, who: str):
    """Build a term with functor *name_val* over *args*, for ``functor/3``/``unpack/2``.

    A ``PredicateMeta`` handed in as the name used to be reduced to
    ``name_val.__name__`` and rebuilt as a generic :class:`Compound`, throwing
    away the very class the caller supplied.  Since a Compound never unifies
    with a declared term-class instance of the same name and arity, that made
    decompose-then-reconstruct fail for every declared with-fields term, and
    the two rendered identically so the mismatch was invisible.  Downstream
    documentation had recorded the symptom as settled behaviour rather than
    a defect.  See
    ``todo/done/functor-3-names-an-atom-as-a-class-but-a-compound-as-a-string.md``.

    Only the class arm resolves.  A ``str`` name still builds a Compound and is
    deliberately *not* resolved back to a class: which module's ``cite`` a bare
    string names is ambiguous under module-local atom identity, and downstream
    callers depend on the string arm behaving exactly as it does.

    An arity that disagrees with the class's field count is not that term, so
    it falls through to the Compound rather than raising — which keeps a
    downstream ``functor/3`` probe over an arity-0 schema atom working.
    """
    if isinstance(name_val, PredicateMeta):
        # ``_fields`` is the field list whatever minted the class — a generated
        # ``class <functor>(metaclass=PredicateMeta)`` block (the usual route
        # for an in-file predicate, see ``_make_functor_class_ast``) or
        # ``make_predicate``.  ``PredicateMeta.__call__`` fills missing trailing
        # fields with fresh Vars and rejects only *overflow*, so it is this
        # exact-match gate, not the constructor, that makes ``name_val(*args)``
        # bind every field positionally with nothing left over.
        if len(name_val._fields) == len(args):
            return name_val(*args)
        # Arity disagrees → not this class; fall through to a generic Compound.
        functor_str = name_val.__name__
    elif isinstance(name_val, str):
        functor_str = name_val
    else:
        # A09-F027: the functor of a compound must be atom-shaped (ISO:
        # type_error(atom, Name)), else unpack(T, [3, 1, 2]) built
        # Compound("3", (1, 2)) and functor/3 built a bogus functor "f(1)".
        from clausal.logic.exceptions import LogicException, type_error
        raise LogicException(type_error("atom", name_val, who))
    return Compound(functor_str, tuple(args))


@_builtin("functor", 3)
def _functor__3(term, name, arity, trail, k):
    """functor(Term, Name, Arity) — decompose or compose a term.

    If Term is bound: unify Name with its functor name and Arity with its arity.
    If Term is unbound: Name and Arity must be bound; construct a Compound.
    """
    term_val = deref(term)

    if is_var(term_val):
        # Construction mode
        name_val = deref(name)
        arity_val = deref(arity)
        if is_var(name_val) or is_var(arity_val):
            return
        # A09-F015 / A01-D001(c): a bool arity is rejected (True is not 1).
        if not isinstance(arity_val, int) or isinstance(arity_val, bool) or arity_val < 0:
            return
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
        term_val = normalize_seg_input(term_val)
        f_val = _functor_name(term_val)
        a_val = _arity(term_val)
        if f_val is None or a_val is None:
            return
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
    if is_var(term_val):
        return
    if is_var(n_val):
        # Output mode: enumerate (N, Arg) pairs, SWI-style relational arg/3.
        # This used to FAIL SILENTLY — the exact ground-vs-var blind spot of
        # todo/audit-tests-input-output-mode-coverage.md.  Same _nth_arg
        # semantics as the ground mode, so a list enumerates its cons view
        # (1 → head, 2 → tail) and arity-0 terms yield nothing.
        term_norm = normalize_seg_input(term_val)
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
    # A09-F015 / A01-D001(c): a bool index is rejected (True is not 1).
    if not isinstance(n_val, int) or isinstance(n_val, bool):
        return
    # SegList/SegString never appear at the Clausal surface — walk
    # to ground form first (user decision 2026-06-13).
    term_val = normalize_seg_input(term_val)
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
        term_val = normalize_seg_input(term_val)
        f_val = _functor_name(term_val)
        if f_val is None:
            return
        decomposed = [f_val] + _args_list(term_val)
        mark = trail.mark()
        if unify(lst, decomposed, trail):
            yield None
        trail.undo(mark)
    else:
        # Construction
        lst_val = deref(lst)
        if is_var(lst_val) or not isinstance(lst_val, list) or len(lst_val) == 0:
            return
        f_val = deref(lst_val[0])
        if is_var(f_val):
            return
        args_vals = [deref(a) for a in lst_val[1:]]
        if len(args_vals) == 0:
            constructed: Any = f_val  # atom
        else:
            constructed = _construct_named(f_val, args_vals, "unpack/2")
        mark = trail.mark()
        if unify(term, constructed, trail):
            yield None
        trail.undo(mark)


# ── V2-13 Term inspection ──────────────────────────────────────────────────────


@_builtin("copy_term", 2)
def _copy_term__2(original, copy, trail, k):
    """copy_term(Original, Copy) — unify Copy with a deep copy of Original with fresh Vars."""
    orig_val = deref(original)
    copied = _copy_term_impl(orig_val, {})
    mark = trail.mark()
    if unify(copy, copied, trail):
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
    # Bind each unbound var to Compound("$VAR", (N,))
    marks = []
    for i, v in enumerate(vars_list):
        m = trail.mark()
        atom = Compound("$VAR", (start_val + i,))
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
    if is_var(prefix_d) or not isinstance(prefix_d, str):
        return
    with _gensym_lock:
        count = _gensym_counters.get(prefix_d, 0) + 1
        _gensym_counters[prefix_d] = count
    result = f"{prefix_d}_{count}"
    if unify(atom, result, trail):
        yield None


# ── global_atom/2 ─────────────────────────────────────────────────────────────


@_builtin("global_atom", 2)
def _global_atom__2(name, atom, trail, k):
    """global_atom(Name, Atom) — reflect on the process-wide global atom dict.

    Exposes ``clausal.import_hook.predicate_builtins``, the dict that seeds
    every fresh predicate module's globals.  Modes:

      (+Name, -Atom): mint-on-demand.  Look Name up in the global dict; if
        absent, install the interned SPELLING itself (§1b/R2's atom pivot —
        an atom IS the str, no class is minted).  Unify Atom with it.
      (+Name, +Atom): guard.  Succeed iff ``predicate_builtins[Name] is Atom``.
      (-Name, +Atom): reverse lookup.  Succeed iff Atom resolves back to
        Name in the dict (i.e. Atom is genuinely the registered global, not
        a module-local namesake); unify Name with that name.  Atom is
        ordinarily the interned str itself; a 0-arity ``PredicateMeta``
        (``make_atom``'s pre-pivot shape) is still accepted for anything
        that manually installs one.
      (-Name, -Atom): enumerate.  Yield one solution per registered atom —
        an interned str (key == value, the P3-1 shape) or a legacy 0-arity
        PredicateMeta.  Order not guaranteed.

    P3-1 Task 7 sweep: pre-pivot this builtin minted a fresh
    ``make_predicate(Name, [])`` class per name — the last live,
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
        if not isinstance(name_val, str):
            return
        if atom_bound:
            # Guard mode: succeed iff atom_val IS the registered global.
            if predicate_builtins.get(name_val) is atom_val:
                yield None
            return
        # Mint-on-demand mode: install the spelling itself (no class).
        val = predicate_builtins.setdefault(name_val, name_val)
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
        if isinstance(atom_val, str):
            cls_name = atom_val
        elif is_atom(atom_val):
            cls_name = atom_val.__name__
        else:
            return
        if predicate_builtins.get(cls_name) is not atom_val:
            return
        mark = trail.mark()
        if unify(name, cls_name, trail):
            yield None
        trail.undo(mark)
        return

    # Both unbound — enumerate registered atoms: an interned str
    # (self-mapped, key == value — the P3-1 shape) or a legacy 0-arity
    # PredicateMeta.  Snapshot keys so concurrent minting elsewhere can't
    # perturb iteration.
    for key, val in list(predicate_builtins.items()):
        if isinstance(val, str):
            if val != key:
                continue
        elif not is_atom(val):
            continue
        mark = trail.mark()
        if unify(name, key, trail) and unify(atom, val, trail):
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


@_builtin("module_constant", 3)
def _module_constant__3(m, name, value, trail, k):
    """module_constant(Module, Name, Value) — reflect on a module's own
    ``-constants`` declarations.

    ``Module`` is the Python module object a ``-import_module(...)``
    directive binds (the same object a qualified reference like
    ``other_module._PI_`` resolves against); ``Name`` is the constant's full
    declaration spelling as a string (``"_PI_"``, underscores included, not
    ``"PI"``); ``Value`` is the constant's frozen value (see
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

    if m_bound:
        cdict = _module_constants_dict(m_val)
        if cdict is None:
            return
        if name_bound:
            if not isinstance(name_val, str) or name_val not in cdict:
                return
            mark = trail.mark()
            if unify(value, cdict[name_val], trail):
                yield None
            trail.undo(mark)
            return
        for n, v in list(cdict.items()):
            mark = trail.mark()
            if unify(name, n, trail) and unify(value, v, trail):
                yield None
            trail.undo(mark)
        return

    # Module unbound: enumerate every loaded Clausal module.
    # Snapshot values() so a module load triggered mid-iteration (e.g. by a
    # lazy import somewhere downstream) can't perturb this iteration.
    import sys as _sys  # noqa: PLC0415
    for py_module in list(_sys.modules.values()):
        cdict = _module_constants_dict(py_module)
        if not cdict:
            continue
        if name_bound:
            if not isinstance(name_val, str) or name_val not in cdict:
                continue
            mark = trail.mark()
            if unify(m, py_module, trail) and unify(value, cdict[name_val], trail):
                yield None
            trail.undo(mark)
            continue
        for n, v in list(cdict.items()):
            mark = trail.mark()
            if (unify(m, py_module, trail) and unify(name, n, trail)
                    and unify(value, v, trail)):
                yield None
            trail.undo(mark)
