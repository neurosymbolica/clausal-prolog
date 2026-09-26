"""Argument-indexing and multi-strategy dispatch construction.

Functions that inspect a clause list and build a runtime dispatch
table keyed on the value at one or more argument positions.  The big
``_make_*_dispatch_*`` family emits closures that route calls to the
right subset of clauses; shallow and trampoline variants are kept
side-by-side so the future de-dup refactor is a single-file diff.

This module is heavily used by ``compile_predicate_shallow`` and
``compile_predicate_trampoline`` (in ``.predicate``).
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Any, Callable

from clausal.logic.generated_names import bare_name_of
from clausal.logic.variables import Var, is_var, deref  # noqa: F401
from clausal.logic.trampoline import DONE, StepGenerator  # noqa: F401
from clausal.terms import (
    Compound,
    Call, LoadName, LoadAttr,
    Unify,
    DictTerm, SetTerm, KWTerm, SegList,
)
from clausal.pythonic_ast.nodes import StarUnpack  # noqa: F401
from clausal.logic.predicate import (
    is_term_instance, term_field_names, resolve_predicate_row,
)
from clausal.logic.database import Clause

from ._ast_helpers import _name, _call, _assign  # noqa: F401
from .terms_to_ast import term_to_ast_expr, _dotted_name_from_loadattr  # noqa: F401
from clausal.logic.cells import TUPLE_TAG, CHARS_TAG, _cell_shape, cell_args


# ── First-argument indexing (V2-1) ────────────────────────────────────────────

_INDEX_VAR = object()  # sentinel: clause has variable/non-indexable first arg
# THE FLIP (2026-09-06-atoms-as-cells-strings §6.9): ``str`` is NOT in this
# tuple.  A string is the list of its char atoms, so a string head argument
# and a char-list head argument are the SAME term and must land in the same
# bucket -- and a list head is unindexed (``_INDEX_VAR``, a full scan), so a
# string head has to be too.  Atoms did not leave the indexable set with it:
# an atom is a cell now and keys ``(spelling, 0)`` through the cell branch.
# The perf consequence is deliberate pressure: a fact table keyed by string
# first arguments loses first-argument indexing; write atoms as atoms.
_INDEXABLE_TYPES = (int, float, bytes, bool, type(None))
_INDEX_THRESHOLD = 4  # minimum clauses before indexing kicks in
_JOINT_COVERAGE_THRESHOLD = 0.8  # min fraction of clauses needing joint key for 9b


# ── Phase 9a: key helpers ────────────────────────────────────────────────────


def _bytelist_to_bytes_or_none(seq) -> bytes | None:
    """Canonicalise a list/tuple of ints in [0, 255] to its joined bytes.

    Returns ``None`` when *seq* is empty or contains any non-int / bool /
    out-of-range element.  A head ``Foo(b"abc")`` and a caller passing
    ``[97, 98, 99]`` produce the same bucket key — the codes model (§1b) is
    kept: bytes and byte-lists still coalesce, unlike str and char-lists
    (R8 retired that half — see ``_arg_to_index_key``).
    """
    if not seq:
        return None
    for c in seq:
        if type(c) is not int or not (0 <= c <= 255):
            return None
    return bytes(seq)


def _arg_to_index_key(arg: Any, env: "dict | None" = None) -> Any:
    """Compile-time: convert a head argument to its index key.

    *env* is the compile-time namespace the reference is being compiled
    against — ``base_globals`` at every real call site (see the callers in
    ``.predicate``).  It is used ONLY by the bare-name branch below; every
    other branch is unaffected by it.

    Returns a hashable key for indexable terms:
    - Scalars (int, float, bytes, bool, None) → the value itself.  A ``str``
      is NOT a scalar here: THE FLIP made it a STRING, i.e. the list of its
      char atoms, and a list head is unindexed (§6.9).
    - A cell (a non-empty ``tuple`` whose slot 0 is a ``str`` functor or the
      ``TUPLE_TAG`` marker) → ``(functor, len(arg) - 1)`` / ``(TUPLE_TAG,
      len(arg) - 1)`` (P3-2 Task 4).  Must run BEFORE the generic
      ``(list, tuple)`` branch — a cell IS a tuple — and produces the same
      ``(name, arity)`` shape as the ``Compound`` / class-instance / ``Call``
      branches below, so a cell head and a compile-time ``Compound`` head of
      the same functor land in ONE bucket regardless of which one wrote it.
    - ``list``/``tuple`` of ints in [0, 255] → the joined ``bytes`` (the
      codes model, kept — see :func:`_bytelist_to_bytes_or_none`).  The
      str/char-list analog (F095) stays RETIRED, but for the OPPOSITE
      reason it was retired under R8 (P3-2).  R8's reasoning was that a str
      and a char list are DIFFERENT terms, so co-bucketing them was wrong.
      THE FLIP (2026-09-06-atoms-as-cells-strings §6.9) makes them the SAME
      term — and the answer is the same, from the other side: a char-list
      head is unindexed, so a string head must be unindexed too, or a
      caller passing the char-list spelling of the term would miss the
      bucket the string spelling built.  Both key ``_INDEX_VAR`` (a full
      scan is always correct).
    - Compound nodes → ``(functor, arity)`` tuple  (Phase 9a)
    - PredicateMeta instances → ``(class_name, field_count)`` tuple  (Phase 9a)
    - ``Call(LoadName(qn), args)`` (imported-compound head arg) →
      ``(qn.rsplit('.', 1)[-1], len(args))`` so the bucket matches the
      runtime ``(cls.__name__, n_fields)`` key emitted by
      :func:`_runtime_arg_key` for a real instance of that class.
      Must run BEFORE the ``is_term_instance`` branch — Call is itself a
      dataclass and would otherwise key as ``('Call', 4)``, which no
      runtime value ever matches.
    - Anything else (Var, list, DictTerm, …) → ``_INDEX_VAR``
    """
    # ``[]``/``""``/``b""`` key alike -- see the twin guard in
    # :func:`_runtime_arg_key` and :func:`_static_call_key`.
    _t = type(arg)
    if (_t is bytes or _t is str) and not arg:
        return _INDEX_VAR
    if _t is str:
        return (arg, 0)                # STAGE 2: a str is the ATOM -- name/0, the cell key's shape
    if isinstance(arg, _INDEXABLE_TYPES):
        return arg
    if type(arg) is tuple and arg:
        slot0 = arg[0]
        if slot0 == CHARS_TAG and len(arg) == 2:
            return _INDEX_VAR          # stage 1: a chars string is TEXT, equal to its char list -- unindexable
        if type(slot0) is str:
            return (slot0, len(arg) - 1)
        if slot0 is TUPLE_TAG:
            return (TUPLE_TAG, len(arg) - 1)
    if isinstance(arg, (list, tuple)):
        b = _bytelist_to_bytes_or_none(arg)
        if b is not None:
            return b
        return _INDEX_VAR
    if isinstance(arg, Compound):
        return (arg.functor, len(arg.args))
    if isinstance(arg, Call) and isinstance(arg.func, LoadName):
        basename = arg.func.name.rsplit(".", 1)[-1]
        return (basename, len(arg.args))
    # Bare/dotted name reference (``LoadName('Red')`` / ``LoadName('pkg.mod.Red')``
    # / ``LoadAttr(mod, 'Red')``) — a 0-arity reference used as a value, e.g. the
    # RHS of the ``Unify`` body goal that a keyword-atom fact ``Color(C=Red)``
    # compiles to, or a cross-module atom hoisted out of a rule head by
    # ``_normalize_structural_head_args``.
    #
    # R2 (P3-1) made an atom its own spelling — a plain ``str`` — rather than a
    # ``PredicateMeta`` class, so the compile-time key can no longer be GUESSED
    # from the reference's spelling (``(dotted.rsplit('.', 1)[-1], 0)``, the
    # pre-pivot convention): that shape only matches the runtime key
    # :func:`_runtime_arg_key` still emits for an actual ``PredicateMeta``
    # instance, never for a plain interned ``str`` (whose runtime key is the
    # string itself), a ``-hide``-mangled atom (whose runtime key is the
    # mangled ``module\x1fname`` spelling, not the bare tail), or a dotted
    # reference to a non-atom value (e.g. ``py.sympy.inf``, where keying the
    # tail ``'inf'`` would relocate the same bug).
    #
    # The fix: RESOLVE the reference against *env* (the compile-time
    # ``base_globals`` the caller threads in — the same dict
    # ``globals_env._inject_resolved_targets`` already populates with
    # ``'pkg.schema.aa' -> 'aa'`` for a cross-module atom, or the mangled
    # string for a ``-hide``-mangled one) and key the RESOLVED VALUE through
    # :func:`_runtime_arg_key` — the SAME function a real runtime argument of
    # that value goes through, so the two paths cannot disagree.
    #
    # Unresolvable (no *env*, or the name isn't in it) → ``_INDEX_VAR``: a
    # full scan is always correct, whereas guessing a key is not. Must run
    # BEFORE ``is_term_instance`` — LoadName/LoadAttr are themselves
    # dataclasses and would otherwise key as ``('LoadName', 2)``, which no
    # runtime value ever matches.
    if isinstance(arg, (LoadName, LoadAttr)):
        dotted = _dotted_name_from_loadattr(arg)
        if dotted is None:
            return _INDEX_VAR
        if env is not None and dotted in env:
            return _runtime_arg_key(env[dotted])
        return _INDEX_VAR
    if is_term_instance(arg):
        cls = type(arg)
        return (cls.__name__, len(term_field_names(arg)))
    return _INDEX_VAR


# Small, constant node budget for the deep-groundness walk below.
#
# Fix round 1 (reviewer Important-1): the walk was unbounded — measured at
# 1.42ms for a 10k-node argument, PER DISPATCH CALL. A recursive predicate
# that carries its own structure in an indexed argument calls this once per
# recursive step, so an unbounded walk goes quadratic in the structure's
# size. 64 is chosen to comfortably cover ordinary fact/rule shapes (a
# handful of fields, maybe one level of nesting — a few dozen nodes at
# most; e.g. a 4-ary compound of 4-ary compounds is 16 nodes, doubled for
# margin) while bounding the pathological case to O(64) work regardless of
# the argument's actual size.
#
# On exhaustion the walk returns False — "not proven ground within budget"
# — rather than True. This is correct BY DIRECTION: the caller (
# :func:`_runtime_arg_key`) degrades a False to ``_INDEX_VAR``, i.e. a full
# scan, never to a falsely-selected exact-match bucket. A large GROUND
# argument pays the cost of a full scan instead of an O(1) bucket lookup —
# a performance cost, not a correctness one — while a large NON-ground
# argument was always going to need the full scan anyway.
_GROUNDNESS_WALK_BUDGET = 64


def _is_deeply_ground(val: Any) -> bool:
    """True if *val* — dereferenced, recursively — contains no unbound Var.

    Guards the cell and class-instance branches of :func:`_runtime_arg_key`.
    The bucket a ``(functor, arity)`` key routes to embeds each of the
    argument's OWN elements as a plain, equality-only ``MatchValue`` pattern
    whenever the matching clause's corresponding element is a ground
    literal — ``head_to_match_pattern`` recurses into a cell/term-instance
    argument's elements with no ``== or $unify`` hybrid fallback (unlike a
    TOP-level indexed argument, which gets exactly that hybrid). An unbound
    Var anywhere inside the CALLER's value can therefore never match such a
    bucket clause, even where the un-indexed fallback's full ``unify()``
    would happily bind it. A caller like that must key ``_INDEX_VAR`` (full
    scan) rather than route into a bucket some of whose clauses it can never
    actually satisfy.

    P3-2 Task 4: found by DRIVING the raw-cell lift route the cell key
    branch below makes reachable for the first time — a caller passing a
    partially-ground cell (e.g. ``("Wrap", Var())``) against a fact whose
    matching slot is a ground atom (``Wrap(direct)``) got zero solutions
    where the fallback gives the right answer.

    Fix round 1 (reviewer Minor-3, bundled with Important-1 since the walk
    itself doesn't change shape): the walk is now BOUNDED (see
    ``_GROUNDNESS_WALK_BUDGET``) and recurses into every term shape a cell
    slot can actually hold, not just tuple/list/term-instance:

    - A nested tuple is only treated as a CELL (whose slot 0 is a functor
      tag to skip) when its own slot 0 is actually a ``str`` or
      ``TUPLE_TAG`` — matching :func:`_runtime_arg_key`'s own cell test.
      Previously ANY tuple unconditionally skipped element 0, so a nested
      var-functor tuple like ``("W", (Var(), 1))`` read as ground (the
      inner tuple's slot 0, the Var, was never even looked at).
    - ``Compound``, ``DictTerm``, ``KWTerm``, ``SetTerm`` and ``SegList``
      previously fell through to the final ``return True`` (unconditional
      ground) the moment they were reached, regardless of what Vars they
      carried — ``("W", DictTerm(...Var...))`` and
      ``("W", Compound("g", (Var(),)))`` both wrongly keyed into a bucket.
    """
    return _is_deeply_ground_walk(val, [_GROUNDNESS_WALK_BUDGET])


def _is_deeply_ground_walk(val: Any, _budget: list[int]) -> bool:
    """Budgeted recursive step for :func:`_is_deeply_ground`.

    *_budget* is a 1-element list (a mutable cell) shared across the WHOLE
    walk from one :func:`_is_deeply_ground` call, decremented once per node
    visited; hitting zero short-circuits every remaining branch to False.
    """
    if _budget[0] <= 0:
        return False
    _budget[0] -= 1
    val = deref(val)
    # Fast path: the overwhelming common case is a scalar leaf (an int,
    # str, float, bool, bytes or None field of an otherwise-structured
    # cell/instance). Checking this FIRST, before any of the isinstance
    # checks below, avoids paying for all five of them on every leaf --
    # a scalar is never a Var, so returning True here is safe without
    # even reaching the is_var check.  Measured: this fast path alone
    # brings ('point', 1, 2)'s key cost back down near its pre-completeness-
    # fix baseline (see task4-bench.txt, PART C).
    if isinstance(val, _INDEXABLE_TYPES):
        return True
    if is_var(val):
        return False
    if type(val) is tuple:
        if not val:
            return True
        slot0 = val[0]
        # Only a genuine CELL (slot 0 a str functor or the TUPLE_TAG data
        # marker — the same test _runtime_arg_key itself uses) skips slot
        # 0; any other tuple shape (e.g. a var-functor tuple, deprecated by
        # §1b but still representable) must check every element.
        start = 1 if (type(slot0) is str or slot0 is TUPLE_TAG) else 0
        for e in val[start:]:
            if not _is_deeply_ground_walk(e, _budget):
                return False
        return True
    if isinstance(val, list):
        for e in val:
            if not _is_deeply_ground_walk(e, _budget):
                return False
        return True
    if isinstance(val, Compound):
        return (
            _is_deeply_ground_walk(val.functor, _budget)
            and all(_is_deeply_ground_walk(e, _budget) for e in val.args)
        )
    if isinstance(val, DictTerm):
        # Keys must already be ground by DictTerm's own contract; only
        # values can carry a Var.
        return all(_is_deeply_ground_walk(v, _budget) for v in val.values())
    if isinstance(val, KWTerm):
        return all(_is_deeply_ground_walk(v, _budget) for v in val.values())
    if isinstance(val, SetTerm):
        # Elements must already be ground by SetTerm's own contract
        # (frozenset-backed); checked anyway, defensively and cheaply,
        # for the same reason DictTerm's values are.
        return all(_is_deeply_ground_walk(e, _budget) for e in val.elements)
    if isinstance(val, SegList):
        walked = val.__walk__()
        if isinstance(walked, SegList):
            return False  # still has an unbound VarSeg hole
        return _is_deeply_ground_walk(walked, _budget)
    if is_term_instance(val):
        return all(
            _is_deeply_ground_walk(getattr(val, name), _budget)
            for name in term_field_names(val)
        )
    return True


def _runtime_arg_key(a: Any, deep_gate: bool = True) -> Any:
    """Runtime: extract the index key from a deref'd argument value.

    Mirrors :func:`_arg_to_index_key` for the runtime dispatch path.
    All four dispatch closure factories use this so that compound-term
    buckets (Phase 9a) are reachable without special-casing.

    P3-2 Task 4: a cell (a non-empty ``tuple`` whose slot 0 is a ``str``
    functor or the ``TUPLE_TAG`` marker) keys as ``(functor, len(a) - 1)`` /
    ``(TUPLE_TAG, len(a) - 1)`` — the same shape ``Compound``/class-instance
    heads use, so a live cell argument reaches the bucket a source-written
    compound head of the same functor built.  Must run BEFORE the generic
    ``(list, tuple)`` branch, which retains only the bytes/byte-list
    coalesce (the codes model); the str/char-list half stays retired (see
    :func:`_arg_to_index_key` for why THE FLIP keeps rather than reverses
    that answer).
    """
    t = type(a)
    if t is int:
        return a
    # ``[]``, ``""`` and ``b""`` all denote the empty list and unify with each
    # other, so they must key ALIKE -- and the only key all three can share is
    # ``_INDEX_VAR`` (an empty list already keys it: ``_bytelist_to_bytes_or_
    # none([])`` answers None).  Without this guard ``b""`` keyed itself while
    # its two equal spellings keyed a full scan.
    if (t is bytes or t is str) and not a:
        return _INDEX_VAR
    if t is str:
        return (a, 0)                  # STAGE 2: a str is the ATOM
    if isinstance(a, _INDEXABLE_TYPES):
        return a
    if type(a) is tuple and a:
        slot0 = a[0]
        if slot0 == CHARS_TAG and len(a) == 2:
            return _INDEX_VAR          # stage 1: text, never a $chars bucket
        if type(slot0) is str:
            if deep_gate and not _is_deeply_ground(a):
                return _INDEX_VAR
            return (slot0, len(a) - 1)
        if slot0 is TUPLE_TAG:
            if deep_gate and not _is_deeply_ground(a):
                return _INDEX_VAR
            return (TUPLE_TAG, len(a) - 1)
    if isinstance(a, (list, tuple)):
        b = _bytelist_to_bytes_or_none(a)
        if b is not None:
            return b
        return _INDEX_VAR
    if isinstance(a, Compound):
        return (a.functor, len(a.args))
    if is_term_instance(a):
        cls = type(a)
        # P3-3 Task 4 fold-in: the same gate the cell branch above carries,
        # for the same reason and behind the same compile-time flag.  A term
        # INSTANCE with an unbound field keys into a bucket whose arms embed
        # the clause's own ground sub-values as equality-only ``MatchValue``
        # patterns, which that caller can never satisfy — while the
        # un-indexed fallback's full ``unify()`` would bind it.  Parked at
        # P3-2 fix round 1 (key side only; the flag computation in
        # ``list_dispatch._lifted_head_arg_needs_deep_gate`` already covered
        # instances) and wired here — see
        # ``todo/done/first-arg-index-partially-ground-instance-keys-into-
        # bucket-2026-09-05.md``.
        if deep_gate and not _is_deeply_ground(a):
            return _INDEX_VAR
        return (cls.__name__, len(term_field_names(a)))
    return _INDEX_VAR


def _static_call_key(arg_expr: ast.expr) -> Any | None:
    """Return the index key if *arg_expr* is statically known at compile time.

    Mirrors :func:`_runtime_arg_key` for the compile-time call-site analysis
    path.  Returns ``None`` if the argument is a variable or otherwise unknown.

    A literal list/tuple of int constants in [0, 255] canonicalises to its
    joined ``bytes`` for the same reason :func:`_runtime_arg_key` does — the
    codes model (kept).  The str/char-list coalesce (F095) is RETIRED (R8,
    P3-2): see :func:`_arg_to_index_key`.
    """
    if isinstance(arg_expr, ast.Constant):
        value = arg_expr.value
        t = type(value)
        # ``[]``, ``""`` and ``b""`` all denote the empty list and unify with
        # each other, so they must key ALIKE -- the twin guard in
        # :func:`_runtime_arg_key` and :func:`_arg_to_index_key`.  Without it
        # ``b""`` keyed ITSELF here while its two equal spellings did not, so
        # a ``b""`` call site could specialise to a bucket that a ``[]``
        # clause head is missing from.  ``_INDEX_VAR`` is never a bucket key
        # (:func:`_build_arg_index` groups only the specific keys), so every
        # consumer reads this as "no specialisation", which is the full scan.
        if (t is bytes or t is str) and not value:
            return _INDEX_VAR
        # scalar: int, float, bool, None, bytes — key is the value itself.
        # A ``str`` constant is a STRING after THE FLIP and is unindexable
        # (§6.9), so it has no static key either; answering the ``str``
        # would name a bucket no head ever built.
        if t is str:
            return (value, 0)          # STAGE 2: a str constant is the ATOM -- the bucket a head ("foo", 0) built
        return value
    if isinstance(arg_expr, ast.Tuple) and arg_expr.elts \
            and all(isinstance(e, ast.Constant) for e in arg_expr.elts) \
            and type(arg_expr.elts[0].value) is str:
        # A literal CELL — most often an atom, which after THE FLIP is the
        # arity-0 cell ``("foo",)`` and reaches a call site as
        # ``ast.Tuple([Constant("foo")])`` (``term_to_ast_expr``'s tuple
        # branch), not as the bare ``str`` Constant it used to be.  Without
        # this branch every atom-argument call site silently lost its
        # first-argument bucket specialisation at the flip.  Every element is
        # required to be a Constant so the cell is fully ground and the
        # deep-groundness gate :func:`_runtime_arg_key` applies cannot
        # disagree with the key computed here.
        if arg_expr.elts[0].value == CHARS_TAG and len(arg_expr.elts) == 2:
            return _INDEX_VAR          # stage 1: a chars string is TEXT, never a $chars bucket
        return (arg_expr.elts[0].value, len(arg_expr.elts) - 1)
    if isinstance(arg_expr, (ast.List, ast.Tuple)):
        # literal list/tuple — if every element is an int constant in
        # [0, 255], canonicalise to the joined bytes so dispatch sees the
        # same bucket as a bytes caller.  Otherwise, no static key.
        elts = []
        for e in arg_expr.elts:
            if not isinstance(e, ast.Constant):
                return None
            elts.append(e.value)
        return _bytelist_to_bytes_or_none(elts)
    if isinstance(arg_expr, ast.Call):
        # compound term constructor: Dog(_v_name, _v_age) or mod.Dog(...)
        func = arg_expr.func
        if isinstance(func, ast.Name):
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            # A runtime-table class is constructed through its ``$`` twin
            # (``$Quantity(...)``); the head side keys on ``cls.__name__``.
            return (bare_name_of(func.id), n_args)
        if isinstance(func, ast.Attribute):
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            # The ``Cls._clausal_new(...)`` call-key special case that used
            # to precede this (Phase 0 construction fast path) was retired
            # in W4b, 2026-09-23: terms_to_ast.py's emitter can no longer
            # produce that attribute shape (see solve.py's _deref_walk_py),
            # so ``func.attr`` here is never the literal "_clausal_new".
            return (func.attr, n_args)
    return None


def hint_row(
    db: Any, fname: str, arity: int, base_globals: dict | None = None,
) -> Any | None:
    """Return the callee row a call-site hint may read plans from, or ``None``.

    The four call-site hint passes (``_inject_bucket_refs_trampoline``,
    ``analyse_ir_bucket_refs``, ``call_site.analyse`` and
    ``call_site.populate_runtime_from_plan``) resolve their callee HERE
    rather than by name in ``base_globals``.  A Database row is keyed by
    ``(functor, arity)``, so a call at arity N can never be handed the plans
    compiled for the same name at arity M — which a name lookup in a module
    dict happily did, because a module dict holds one class per NAME (P1
    spec 2026-09-17 §2.3).

    ``None`` — meaning "emit no hints" — for every shape that cannot name a
    row: an unknown ``(fname, arity)`` with nothing bound under *fname* in
    ``base_globals`` either, a binding that is not a predicate class, a class
    whose own row is at ANOTHER arity, and a row that is not locked (its
    dispatch, and so its bucket functions, may still be rebuilt).  A caller
    with no Database at all (a bare globals dict, or a name-only shim without
    ``row`` such as ``_GlobalsDb``) reaches the class fallback below rather
    than stopping here.

    ROW FIRST, THEN THE CLASS BOUND AT THAT SPELLING — for ANY name (final
    review I3, ruled 2026-09-17).  Two callee shapes have no row under
    ``(fname, arity)`` in the Database this compile targets and are still
    perfectly ordinary predicates:

    * the DOTTED spelling.  ``-import_from`` rewrites every reference to an
      imported predicate into the EXPORTER's dotted spelling (``pkg.mod.p``),
      and that is a ``base_globals`` key, never a Database key — the
      importer's Database adopted the row under the LOCAL name.  Same
      reasoning as ``globals_env._maybe_cache_dispatch``, which records
      in-tree that for a dotted key the object's own row is the right one and
      a ``db.row(name, arity)`` lookup "would silently redirect the call".
    * the ROWLESS callee.  A predicate reached by a plain Python import is
      bound in ``base_globals`` under its plain name with no row adopted here
      (``test_p1_sites_rerouted.test_a_class_in_the_module_dict_without_a_
      local_row_still_resolves`` builds exactly that shape), and so is any
      callee an out-of-tree compile hands in through a globals dict.
      Restricting the fallback to dotted names silently dropped every hint
      for those — a performance loss, not a wrong answer, but a needless one.

    So the fallback is taken for any name once the row read misses, and the
    object's OWN row is used only when that row's key agrees with the call's
    ARITY.  This is THE class read the four R! sites keep (spec §3, reported
    in the handoff's class-reads-left list); it is arity-exact all the same,
    because the arity comes from the row.
    """
    row = None
    if db is not None:
        row_of = getattr(db, "row", None)
        if row_of is not None:
            row = row_of(fname, arity)
    if row is None and base_globals is not None:
        # THE class read this pass still makes, now era-agnostic (W4b-2b):
        # resolve_predicate_row replaces the raw ``isinstance(obj,
        # PredicateMeta): obj._row`` read (the "P4 can find its removal
        # site by grep" note is now moot for this site -- the migration IS
        # the removal, the same precedent ``globals_env._maybe_cache_
        # dispatch`` already made).  Deliberately NOT gated with
        # is_declared_predicate first: this docstring's own words trust
        # "the arity comes from the row" (``cand.key[1] == arity``, kept
        # exactly as before), not the class's ``_fields`` count -- a
        # class's row can in principle disagree with its current
        # ``_fields`` (a rebinding edge case), and gating on ``_fields``
        # first could reject a case the original row-key check would
        # still have accepted.  ``resolve_predicate_row``'s class arm is
        # itself arity-blind (it does not consult ``arity`` either), so
        # this is the same two-step the original code made: fetch, then
        # check the ROW's own key.
        obj = base_globals.get(fname)
        cand = resolve_predicate_row(obj, arity=arity, db=db)
        if cand is not None and cand.key[1] == arity:
            row = cand
    if row is None or not row.locked:
        return None
    return row


def _bucket_key(fname: str, pos: int, key: Any) -> str:
    """Readable globals key for a single-position bucket function.

    The returned string is used as an ``ast.Name`` id and as a
    ``base_globals`` key.  It is not a valid Python identifier (it contains
    dots, brackets, and quotes) so generated code won't re-parse, but
    ``ast.unparse()`` renders it readably and ``compile(ast_tree, ...)``
    resolves it via a plain dict lookup.
    """
    return f"{fname}.bucket(pos={pos}, {key!r})"


def _joint_bucket_key(fname: str, pos_i: int, pos_j: int,
                      ki: Any, kj: Any) -> str:
    """Readable globals key for a joint (two-position) bucket function."""
    return f"{fname}.bucket(pos=({pos_i},{pos_j}), ({ki!r},{kj!r}))"


def _drive_tro_bucket(gen, tro_state, arity, pending):
    """Yield from a signal-mode bucket generator while snapshotting a pending
    TRO tail-call signal into *pending* the instant it appears.

    A signal-mode TRO clause sets ``tro_state[0] = True`` and falls through
    (it does not yield); a LATER match arm in the same bucket may then yield a
    solution while the flag is still pending, suspending this generator.  Any
    re-entry into the same predicate during that suspension (a sibling goal, a
    nested self-call) resets the shared ``tro_state[0]`` at its own dispatch
    entry, which would silently drop the pending tail call — the enclosing
    dispatch loop would then read ``False`` and lose every remaining solution.
    See todo/tro-signal-flag-clobbered-by-later-match-arms.md.

    Capturing the signal into the per-activation *pending* list before each
    downstream ``yield`` makes the dispatch loop immune to that clobber: it
    re-dispatches from *pending*, not from the shared (re-entrant) cell.

    *pending* is a list of length ``arity + 1``: ``pending[0]`` is the
    tail-pending flag, ``pending[1:]`` the snapshotted tail-call args.  On a
    later signal the snapshot is overwritten (last-write-wins), matching the
    pre-fix semantics where the after-arms check read the final ``tro_state``.

    This is a full delegating generator (PEP-380 ``yield from`` semantics):
    it forwards ``send``/``throw``/``close`` to *gen* so the trampoline Step
    protocol — which resumes buckets via ``.send(value)`` and unwinds via
    ``.throw()`` for catch/3 — keeps working.  A plain ``for``-loop wrapper
    would swallow sent values and break it.
    """
    def _snapshot():
        if tro_state[0]:
            pending[0] = True
            for _i in range(arity):
                pending[_i + 1] = tro_state[_i + 1]

    try:
        _y = next(gen)
    except StopIteration:
        _snapshot()
        return
    while True:
        _snapshot()  # capture BEFORE yielding — before any re-entry can clobber
        try:
            _sent = yield _y
        except GeneratorExit:
            gen.close()
            raise
        except BaseException as _exc:
            try:
                _y = gen.throw(_exc)
            except StopIteration:
                _snapshot()
                return
        else:
            try:
                _y = gen.send(_sent)
            except StopIteration:
                _snapshot()
                return


def _make_call_site_bucket_trampoline(bucket_fn, dispatch_fn, done,
                                      tro_state=None, arity=0):
    """Wrap a SIGNAL-mode bucket for direct call-site use (Phase 10 /
    ``call_site`` optimisation).

    Buckets are compiled with ``emit_done=False``: they neither emit the
    terminal ``yield (fail, done)`` nor loop on TRO tail calls — the
    enclosing dispatch closure does both.  A call-site-specialised caller
    (``SubCall.direct_bucket_ref``) drives the bucket *directly* via
    ``StepGenerator``, so the function exposed through ``_index_plans`` /
    ``_index_plans_joint`` must complete the trampoline contract itself:
    emit the terminal done, and when the bucket signals a TRO tail call,
    delegate to the full *dispatch_fn* (the new args may key to a
    different bucket).  Driving a raw bucket instead raises
    ``RuntimeError: StepGenerator inner generator returned unexpectedly
    (no final yield)`` — see
    todo/call-site-imported-ground-arg-4plus-clauses-runtime-error.md.
    """
    if tro_state is None:
        def call_site_fn(*args):
            _fail = args[2]
            yield from bucket_fn(*args)
            yield (_fail, done)
    else:
        def call_site_fn(*args):
            _fail = args[2]
            tro_state[0] = False
            _pending = [False] + [None] * arity
            yield from _drive_tro_bucket(
                bucket_fn(*args), tro_state, arity, _pending)
            if _pending[0]:
                args_list = list(args)
                for _i in range(arity):
                    args_list[_i + 4] = _pending[_i + 1]
                # dispatch_fn loops on any further tail calls and emits
                # its own terminal ``(fail, done)``.
                yield from dispatch_fn(*args_list)
            else:
                yield (_fail, done)
    call_site_fn.__name__ = bucket_fn.__name__
    call_site_fn.__qualname__ = bucket_fn.__qualname__
    return call_site_fn


def _extract_arg_key(
    clause: Clause, pos: int, arity: int, env: "dict | None" = None,
) -> Any:
    """Extract the indexing key for a clause's argument at position *pos*.

    Returns a hashable key (scalar or ``(functor, arity)`` tuple) for
    indexable clauses, or ``_INDEX_VAR`` for variable/non-indexable args.

    *env* is threaded straight through to :func:`_arg_to_index_key` so a
    hoisted cross-module atom reference (``LoadName``/``LoadAttr``) can be
    resolved to its runtime value instead of guessed at from its spelling.
    """
    if arity == 0 or pos >= arity:
        return _INDEX_VAR
    head = clause.head
    # Get arg at position pos from head
    if isinstance(head, Compound):
        if len(head.args) <= pos:
            return _INDEX_VAR
        arg = head.args[pos]
    elif isinstance(head, Call) and isinstance(head.func, LoadName):
        if len(head.args) <= pos:
            return _INDEX_VAR
        arg = head.args[pos]
    elif _cell_shape(head)[0]:                      # P2: a head is a cell
        cargs = cell_args(head)
        if len(cargs) <= pos:
            return _INDEX_VAR
        arg = cargs[pos]
    elif is_term_instance(head):
        fields = term_field_names(head)
        if len(fields) <= pos:
            return _INDEX_VAR
        arg = getattr(head, fields[pos])
    else:
        return _INDEX_VAR
    # Direct ground term (scalar or compound) — Phase 9a extends to compounds.
    key = _arg_to_index_key(arg, env)
    if key is not _INDEX_VAR:
        return key
    # Var + Unify pattern (from _normalize_dataclass_fact).
    # Phase 9a: also extract compound/predicate keys from Unify targets.
    if is_var(arg):
        for goal in clause.body:
            if isinstance(goal, Unify):
                if goal.left is arg:
                    k = _arg_to_index_key(goal.right, env)
                    if k is not _INDEX_VAR:
                        return k
                elif goal.right is arg:
                    k = _arg_to_index_key(goal.left, env)
                    if k is not _INDEX_VAR:
                        return k
        return _INDEX_VAR
    return _INDEX_VAR


def _extract_first_arg_key(
    clause: Clause, arity: int, env: "dict | None" = None,
) -> Any:
    """Extract the indexing key for a clause's first argument.

    Convenience wrapper around :func:`_extract_arg_key` for position 0.
    """
    return _extract_arg_key(clause, 0, arity, env)


def _build_arg_index(
    clauses: list[Clause], arity: int, pos: int,
    threshold: int = _INDEX_THRESHOLD,
    env: "dict | None" = None,
) -> dict | None:
    """partition clauses into buckets keyed on argument *pos*.

    Returns None if indexing is not beneficial (too few clauses, all defaults,
    or arity == 0).  Otherwise returns::

        {"buckets": {key: [Clause, ...]},  # merged with defaults
         "defaults": [Clause, ...],
         "all": [Clause, ...],
         "n_distinct": int}

    Each bucket's clause list includes the default (var-headed) clauses
    interleaved in their original order, preserving Prolog clause ordering.
    """
    if arity == 0 or pos >= arity or len(clauses) < threshold:
        return None
    keys = [_extract_arg_key(c, pos, arity, env) for c in clauses]
    default_indices = [i for i, k in enumerate(keys) if k is _INDEX_VAR]
    specific_indices = [i for i, k in enumerate(keys) if k is not _INDEX_VAR]
    if not specific_indices:
        return None  # all defaults — indexing won't help
    # Group specific clauses by key
    bucket_map: dict[Any, list[int]] = defaultdict(list)
    for i in specific_indices:
        bucket_map[keys[i]].append(i)
    # Each bucket = bucket-specific + default clauses, merged in original order
    merged_buckets: dict[Any, list[Clause]] = {}
    for key, b_indices in bucket_map.items():
        merged = sorted(b_indices + default_indices)
        merged_buckets[key] = [clauses[i] for i in merged]
    return {
        "buckets": merged_buckets,
        "defaults": [clauses[i] for i in default_indices],
        "all": clauses,
        "n_distinct": len(bucket_map),
    }


def _build_first_arg_index(
    clauses: list[Clause], arity: int, threshold: int = _INDEX_THRESHOLD,
    env: "dict | None" = None,
) -> dict | None:
    """partition clauses into first-arg buckets.

    Convenience wrapper around :func:`_build_arg_index` for position 0.
    """
    return _build_arg_index(clauses, arity, 0, threshold, env)


def _analyze_index_positions(
    clauses: list[Clause], arity: int, threshold: int = _INDEX_THRESHOLD,
    env: "dict | None" = None,
) -> list[tuple[int, dict]]:
    """Find argument positions suitable for indexing, sorted by selectivity.

    Returns a list of ``(pos, index_info)`` tuples where each *index_info*
    is the dict from :func:`_build_arg_index`.  Positions are sorted by
    number of distinct keys (most distinct first = most selective).
    """
    if arity == 0 or len(clauses) < threshold:
        return []
    results = []
    for pos in range(arity):
        idx = _build_arg_index(clauses, arity, pos, threshold, env)
        if idx is not None:
            results.append((pos, idx))
    # Sort by selectivity: most distinct keys first
    results.sort(key=lambda x: -x[1]["n_distinct"])
    return results


# ── Phase 9b: joint (argI, argJ) indexing ───────────────────────────────────


def _build_joint_arg_index(
    clauses: list[Clause], arity: int, pos_i: int, pos_j: int,
    threshold: int = _INDEX_THRESHOLD,
    env: "dict | None" = None,
) -> dict | None:
    """Build a flat joint index keyed on ``(key_i, key_j)`` tuples.

    Returns ``None`` when fewer than *threshold* clauses have both args
    indexable.  Otherwise returns the same shape as :func:`_build_arg_index`
    but with tuple keys::

        {"buckets": {(ki, kj): [Clause, ...]},
         "defaults": [Clause, ...],
         "all": [Clause, ...],
         "n_distinct": int,
         "coverage": float}   # fraction of clauses with both args indexable
    """
    if arity < 2 or pos_i == pos_j or pos_i >= arity or pos_j >= arity:
        return None
    keys = []
    for c in clauses:
        ki = _extract_arg_key(c, pos_i, arity, env)
        kj = _extract_arg_key(c, pos_j, arity, env)
        if ki is not _INDEX_VAR and kj is not _INDEX_VAR:
            keys.append((ki, kj))
        else:
            keys.append(_INDEX_VAR)
    specific_indices = [i for i, k in enumerate(keys) if k is not _INDEX_VAR]
    if len(specific_indices) < threshold:
        return None
    default_indices = [i for i, k in enumerate(keys) if k is _INDEX_VAR]
    bucket_map: dict[Any, list[int]] = defaultdict(list)
    for i in specific_indices:
        bucket_map[keys[i]].append(i)
    merged_buckets: dict[Any, list[Clause]] = {}
    for key, b_indices in bucket_map.items():
        merged = sorted(b_indices + default_indices)
        merged_buckets[key] = [clauses[i] for i in merged]
    return {
        "buckets": merged_buckets,
        "defaults": [clauses[i] for i in default_indices],
        "all": clauses,
        "n_distinct": len(bucket_map),
        "coverage": len(specific_indices) / len(clauses),
    }


def _analyze_joint_index_positions(
    clauses: list[Clause], arity: int,
    single_indexes: list[tuple[int, dict]],
    min_gain: float = 1.5,
    env: "dict | None" = None,
) -> tuple[int, int, dict] | None:
    """Find the best ``(pos_i, pos_j)`` pair for joint indexing.

    Considers pairs ``(best_single_pos, k)`` for all remaining positions *k*.
    Returns ``(pos_i, pos_j, joint_index_info)`` if the joint index offers at
    least *min_gain* × more distinct keys than the best single-arg index, else
    ``None``.
    """
    if not single_indexes or arity < 2:
        return None
    best_single_pos, best_single_idx = single_indexes[0]
    best_single_distinct = best_single_idx["n_distinct"]
    best_joint: tuple[int, int, dict] | None = None
    best_joint_distinct = 0
    for pos in range(arity):
        if pos == best_single_pos:
            continue
        joint = _build_joint_arg_index(
            clauses, arity, best_single_pos, pos, env=env)
        if joint is None:
            continue
        if joint["n_distinct"] > best_joint_distinct:
            best_joint_distinct = joint["n_distinct"]
            best_joint = (best_single_pos, pos, joint)
    if best_joint is None:
        return None
    pos_i, pos_j, joint = best_joint
    if joint["n_distinct"] > best_single_distinct * min_gain:
        return pos_i, pos_j, joint
    return None


def _joint_dispatch_body(
    args, pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn,
):
    """Yield from the appropriate clause bucket given *args* at (pos_i, pos_j).

    Returns a bool indicating whether the fallback path was taken — the
    TRO variant uses this to know when the internal loop must break
    (the fallback itself owns the TRO loop).
    """
    _ai = deref(args[pos_i])
    _aj = deref(args[pos_j])
    if not is_var(_ai) and not is_var(_aj):
        _ki = _runtime_arg_key(_ai)
        _kj = _runtime_arg_key(_aj)
        # A02-F001: an uncomputable component means the joint key can't be
        # formed. Degrade to the single-position dispatch on the OTHER
        # (computable) component — which itself scans when its key is also
        # uncomputable — rather than hitting the joint default (often an
        # always-fail bucket that drops all solutions).
        if _ki is _INDEX_VAR and _kj is _INDEX_VAR:
            yield from fallback_fn(*args)
        elif _ki is _INDEX_VAR:
            yield from single_j_dispatch(*args)
        elif _kj is _INDEX_VAR:
            yield from single_i_dispatch(*args)
        else:
            _jk = (_ki, _kj)
            try:
                _bfn = joint_dict.get(_jk)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from joint_default_fn(*args)
    elif not is_var(_ai):
        yield from single_i_dispatch(*args)
    elif not is_var(_aj):
        yield from single_j_dispatch(*args)
    else:
        yield from fallback_fn(*args)


def _make_joint_dispatch_simple(
    pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn,
) -> Callable:
    """Build a flat joint-key dispatch for simple/short-stack mode.

    Decision tree (Phase 9b):
    1. Both *pos_i* and *pos_j* ground → joint dict lookup (O(1))
    2. Only *pos_i* ground → single-arg dispatch on *pos_i*
    3. Only *pos_j* ground → single-arg dispatch on *pos_j*
    4. Neither ground → *fallback_fn* (linear scan)
    """
    def dispatch(*args):
        yield from _joint_dispatch_body(
            args, pos_i, pos_j, joint_dict, joint_default_fn,
            single_i_dispatch, single_j_dispatch, fallback_fn,
        )
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_joint_dispatch_trampoline(
    pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn, done,
    tro_state=None, arity=0,
) -> Callable:
    """Build a flat joint-key dispatch for trampoline mode.  (Phase 9b)

    Same decision tree as :func:`_make_joint_dispatch_simple`, wrapped
    with the trampoline Step protocol (``(_fail, DONE)`` tail-yield)
    and, when *tro_state* is supplied, an inner TRO tail-call loop that
    restarts dispatch when a clause signals a tail call.
    """
    # Phase 2: trampoline layout is
    # (this_generator, _proceed, _fail, _catcher, arg0, ..., trail).
    # Skip four slots (this_generator + three continuations) to reach arg0.
    offset_i = pos_i + 4
    offset_j = pos_j + 4

    if tro_state is not None:
        def dispatch(*args):
            _fail = args[2]
            args_list = list(args)
            while True:
                tro_state[0] = False
                # Select the route, then drive it through _drive_tro_bucket so
                # a tail call signalled from a non-last arm survives re-entrant
                # clobbering of the shared tro_state (see _drive_tro_bucket).
                _ai = deref(args_list[offset_i])
                _aj = deref(args_list[offset_j])
                if not is_var(_ai) and not is_var(_aj):
                    _ki = _runtime_arg_key(_ai)
                    _kj = _runtime_arg_key(_aj)
                    # A02-F001: an uncomputable component means the joint
                    # key can't be formed — degrade exactly like the non-TRO
                    # body (_joint_dispatch_body): both uncomputable → full
                    # scan; one uncomputable → single-position dispatch on
                    # the OTHER (computable) component. Every route is compiled
                    # in SIGNAL mode (buckets/fallback) or owns its own TRO
                    # loop (single dispatches), so re-dispatch is uniform.
                    if _ki is _INDEX_VAR and _kj is _INDEX_VAR:
                        _bfn = fallback_fn
                    elif _ki is _INDEX_VAR:
                        _bfn = single_j_dispatch
                    elif _kj is _INDEX_VAR:
                        _bfn = single_i_dispatch
                    else:
                        _jk = (_ki, _kj)
                        try:
                            _bfn = joint_dict.get(_jk)
                        except TypeError:
                            _bfn = None
                        if _bfn is None:
                            _bfn = joint_default_fn
                elif not is_var(_ai):
                    _bfn = single_i_dispatch
                elif not is_var(_aj):
                    _bfn = single_j_dispatch
                else:
                    # A02-F001: neither arg ground — full scan (signal-mode).
                    _bfn = fallback_fn
                _pending = [False] + [None] * arity
                yield from _drive_tro_bucket(
                    _bfn(*args_list), tro_state, arity, _pending)
                if _pending[0]:
                    for _i in range(arity):
                        args_list[_i + 4] = _pending[_i + 1]
                    continue
                break
            yield (_fail, done)
    else:
        def dispatch(*args):
            _fail = args[2]
            yield from _joint_dispatch_body(
                args, offset_i, offset_j, joint_dict, joint_default_fn,
                single_i_dispatch, single_j_dispatch, fallback_fn,
            )
            yield (_fail, done)

    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


# ── Phase 9c: secondary (hierarchical) dispatch ──────────────────────────────


def _build_secondary_index(
    clauses: list[Clause], arity: int, pos_i: int, pos_j: int,
    threshold: int = _INDEX_THRESHOLD,
    secondary_threshold: int = 2,
    env: "dict | None" = None,
) -> dict | None:
    """Build a two-level hierarchical index: level-0 on *pos_i*, level-1 on *pos_j*.

    Level-0 partitions clauses by key at *pos_i* exactly as
    :func:`_build_arg_index` does.  Within each level-0 bucket a second
    :func:`_build_arg_index` on *pos_j* is attempted (using a lower threshold
    since the sub-buckets are smaller).

    Returns::

        {"level0": {ki: (level1_buckets or None, level1_default_clause_list)},
         "level0_defaults": [Clause, ...],
         "pos_i": pos_i,
         "pos_j": pos_j,
         "n_level0": int}

    or ``None`` if the primary index is not viable.
    """
    primary = _build_arg_index(clauses, arity, pos_i, threshold, env)
    if primary is None:
        return None
    level0: dict[Any, tuple] = {}
    for ki, bucket in primary["buckets"].items():
        secondary = _build_arg_index(bucket, arity, pos_j,
                                     threshold=secondary_threshold, env=env)
        if secondary is not None:
            # level-1 default: all clauses in this level-0 bucket.
            # Using bucket (= secondary["all"]) rather than secondary["defaults"]
            # ensures that unbound arg_j queries still scan every matching clause.
            level0[ki] = (secondary["buckets"], bucket)
        else:
            level0[ki] = (None, bucket)
    return {
        "level0": level0,
        "level0_defaults": primary["defaults"],
        "pos_i": pos_i,
        "pos_j": pos_j,
        "n_level0": primary["n_distinct"],
    }


def _make_secondary_dispatch_impl(
    sec_idx: dict,
    level0_compiled: dict,
    level0_default_fn: Callable,
    fallback_fn: Callable,
    *,
    arg_offset: int,
    tail_yield,
    tro_state=None,
    arity: int = 0,
) -> Callable:
    """Shared two-level hierarchical dispatch builder.

    Decision tree:
    - *pos_i* var → ``fallback_fn``
    - *pos_i* ground, key unknown → ``level0_default_fn``
    - *pos_i* ground, key found:
      - *pos_j* var or no level-1 index → level-1 default fn
      - *pos_j* ground, key found → level-1 bucket fn
      - *pos_j* ground, key unknown → level-1 default fn

    Strategy differences are the same as in ``_make_indexed_dispatch_impl``:

    - ``arg_offset``: 0 for simple, 4 for trampoline. The Phase-2 trampoline
      layout is ``(this_generator, _proceed, _fail, _catcher, arg0, …,
      trail)`` — skip four slots (this_generator + three continuations) to
      reach arg0.
    - ``tail_yield``: ``None`` for simple (early returns terminate the
      generator); ``lambda args: (args[2], done)`` for trampoline, which
      emits the ``(_fail, DONE)`` exhaustion sentinel at the end
      (``args[2]`` is the ``_fail`` continuation in the Phase-2 layout).
    - ``tro_state`` / ``arity``: when *tro_state* is supplied (trampoline
      TRO), the dispatch loops: level-0/level-1 buckets never signal
      (compiled without ``tro_indices``), but *fallback_fn* is the shared
      SIGNAL-mode ``{functor}__all`` — after each route, if
      ``tro_state[0]`` is set the args are updated from
      ``tro_state[1..arity]`` and the decision tree re-runs (the updated
      args may now key into a level-0 bucket). Without the loop a
      fallback tail call is silently dropped (0 solutions).
    """
    pos_i = sec_idx["pos_i"] + arg_offset
    pos_j = sec_idx["pos_j"] + arg_offset

    def _route(args):
        _ai = deref(args[pos_i])
        _ki = _runtime_arg_key(_ai) if not is_var(_ai) else None
        if is_var(_ai) or _ki is _INDEX_VAR:
            # A02-F001: an unbound arg OR a non-var arg with an uncomputable
            # level-0 key (partial container, Decimal, …) must scan all
            # clauses. Routing an uncomputable key to the level-0 default —
            # an always-fail bucket when no clause has a var first arg —
            # would drop every solution the arg would unify with.
            yield from fallback_fn(*args)
        else:
            try:
                _entry = level0_compiled.get(_ki)
            except TypeError:
                _entry = None
            if _entry is None:
                yield from level0_default_fn(*args)
            else:
                level1_fns, level1_default_fn = _entry
                if level1_fns is None:
                    yield from level1_default_fn(*args)
                else:
                    _aj = deref(args[pos_j])
                    if is_var(_aj):
                        yield from level1_default_fn(*args)
                    else:
                        _kj = _runtime_arg_key(_aj)
                        try:
                            _bfn = level1_fns.get(_kj)
                        except TypeError:
                            _bfn = None
                        if _bfn is not None:
                            yield from _bfn(*args)
                        else:
                            yield from level1_default_fn(*args)

    if tro_state is not None:
        def dispatch(*args):
            # The level-0/level-1 buckets are compiled without TRO, but
            # fallback_fn is the shared SIGNAL-mode `{functor}__all` — a
            # tail call signalled there must re-dispatch (the updated args
            # may now key into a level-0 bucket), not be dropped.
            args_list = None
            while True:
                tro_state[0] = False
                _current = args_list if args_list is not None else args
                _pending = [False] + [None] * arity
                yield from _drive_tro_bucket(
                    _route(_current), tro_state, arity, _pending)
                if _pending[0]:
                    if args_list is None:
                        args_list = list(args)
                    for _i in range(arity):
                        args_list[_i + arg_offset] = _pending[_i + 1]
                    continue
                break
            if tail_yield is not None:
                yield tail_yield(args)
    else:
        def dispatch(*args):
            yield from _route(args)
            if tail_yield is not None:
                yield tail_yield(args)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_secondary_dispatch_simple(
    sec_idx: dict,
    level0_compiled: dict,     # {ki: (level1_fn_dict or None, level1_default_fn)}
    level0_default_fn: Callable,
    fallback_fn: Callable,
) -> Callable:
    """Build a two-level hierarchical dispatch for simple mode.  (Phase 9c)

    See ``_make_secondary_dispatch_impl`` for the decision tree.
    """
    return _make_secondary_dispatch_impl(
        sec_idx, level0_compiled, level0_default_fn, fallback_fn,
        arg_offset=0,
        tail_yield=None,
    )


def _make_secondary_dispatch_trampoline(
    sec_idx: dict,
    level0_compiled: dict,
    level0_default_fn: Callable,
    fallback_fn: Callable,
    done: Any,
    tro_state=None,
    arity: int = 0,
) -> Callable:
    """Build a two-level hierarchical dispatch for trampoline mode.  (Phase 9c)"""
    return _make_secondary_dispatch_impl(
        sec_idx, level0_compiled, level0_default_fn, fallback_fn,
        arg_offset=4,
        tail_yield=lambda args: (args[2], done),
        tro_state=tro_state, arity=arity,
    )


def _make_indexed_dispatch_impl(all_fn, idx_dict, default_fn, *, arg_offset, tail_yield, deep_gate=False):
    """Shared indexed-dispatch builder.

    Routes on the first predicate argument (at ``args[arg_offset]``):

    - unbound Var → ``all_fn`` (covers every clause)
    - otherwise   → ``idx_dict[key]`` if known, else ``default_fn``

    The strategy differences are minimal:

    - ``arg_offset``: 0 for simple (predicate args start at position 0);
      4 for trampoline. The Phase-2 trampoline layout is
      ``(this_generator, _proceed, _fail, _catcher, arg0, …, trail)`` — skip
      four slots (this_generator + three continuations) to reach arg0.
    - ``tail_yield``: ``None`` for simple; ``lambda args: (args[2], done)``
      for trampoline, which terminates with a ``(_fail, DONE)`` tuple
      (``args[2]`` is the ``_fail`` continuation in the Phase-2 layout)
      as required by the Step protocol.
    """
    def dispatch(*args):
        _a0 = deref(args[arg_offset])
        if is_var(_a0):
            yield from all_fn(*args)
        else:
            _k = _runtime_arg_key(_a0, deep_gate)
            try:
                _bfn = idx_dict.get(_k)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from default_fn(*args)
        if tail_yield is not None:
            yield tail_yield(args)
    dispatch.__name__ = all_fn.__name__
    dispatch.__qualname__ = all_fn.__qualname__
    return dispatch


def _make_indexed_dispatch_simple(all_fn, idx_dict, default_fn, deep_gate=False):
    """Build an indexed dispatch wrapper for simple/short-stack mode.

    Legacy V2-1 wrapper — indexes only on the first argument.
    Superseded by :func:`_make_groundness_dispatch_simple` for V2-2.

    *deep_gate* (P3-2 Task 4 fix round 2): whether the runtime key
    computation runs the bounded deep-groundness walk for a cell/tuple
    argument -- see :func:`_runtime_arg_key`. Defaults to False: this
    legacy wrapper is unused by the real compiler pipeline (dead code,
    kept for the V2-1/V2-2 history), so there is no computed per-position
    risk flag to thread through it from anywhere; False matches the
    common (no lifted-literal-risk) case.
    """
    return _make_indexed_dispatch_impl(
        all_fn, idx_dict, default_fn,
        arg_offset=0,
        tail_yield=None,
        deep_gate=deep_gate,
    )


def _make_indexed_dispatch_trampoline(all_fn, idx_dict, default_fn, done, deep_gate=False):
    """Build an indexed dispatch wrapper for trampoline mode.

    Legacy V2-1 wrapper — indexes only on the first argument.
    Superseded by :func:`_make_groundness_dispatch_trampoline` for V2-2.
    See :func:`_make_indexed_dispatch_simple` for *deep_gate*.
    """
    return _make_indexed_dispatch_impl(
        all_fn, idx_dict, default_fn,
        arg_offset=4,
        tail_yield=lambda args: (args[2], done),
        deep_gate=deep_gate,
    )


# ── V2-2: Groundness-keyed dispatch ─────────────────────────────────────────


def _groundness_dispatch_body_single(args, pos, idx_dict, dflt_fn, fallback_fn,
                                     deep_gate=True):
    """Yield from the appropriate bucket for a single-position groundness plan.

    If ``args[pos]`` is an unbound Var, fall back to the all-clauses
    scan.  Otherwise look up the bucket keyed on the arg's runtime
    value; missing or TypeError key means the default fn.

    *deep_gate* (P3-2 Task 4 fix round 2): threaded straight to
    :func:`_runtime_arg_key` -- computed once, at bucket-build time, by
    ``list_dispatch._lifted_head_arg_needs_deep_gate`` over every lifted
    clause at this position (see predicate.py). Defaults to True (safe)
    for any direct caller that has not computed a real flag.
    """
    _a = deref(args[pos])
    if is_var(_a):
        yield from fallback_fn(*args)
        return
    _k = _runtime_arg_key(_a, deep_gate)
    if _k is _INDEX_VAR:
        # A02-F001: a non-var arg whose index key is uncomputable (partial
        # char/code-list, empty list, SegList, Decimal, …) must scan ALL
        # clauses — not the default bucket (var-headed only), which would
        # silently drop keyed buckets the arg would happily unify with.
        yield from fallback_fn(*args)
        return
    try:
        _bfn = idx_dict.get(_k)
    except TypeError:
        # Unhashable key (defensive) → same uncomputable-key fallback.
        yield from fallback_fn(*args)
        return
    if _bfn is not None:
        yield from _bfn(*args)
    else:
        yield from dflt_fn(*args)


def _groundness_dispatch_body_multi(args, plans, fallback_fn, arg_offset):
    """Yield from the first plan whose position has a ground argument.

    ``plans`` is a list of ``(pos, idx_dict, default_fn, deep_gate)``
    4-tuples (P3-2 Task 4 fix round 2 added the trailing ``deep_gate``
    -- see :func:`_groundness_dispatch_body_single`), sorted by
    selectivity.  Each position is checked in order; the first ground
    arg triggers its index lookup and short-circuits.  If all positions
    are unbound Vars, fall back to the all-clauses scan.

    ``arg_offset`` is added to each plan's ``pos`` — 0 for simple mode, 4 for
    trampoline. The Phase-2 trampoline layout is ``(this_generator, _proceed,
    _fail, _catcher, arg0, …, trail)`` — skip four slots (this_generator +
    three continuations) to reach arg0.
    """
    for _pos, _idx_dict, _dflt_fn, _deep_gate in plans:
        _a = deref(args[_pos + arg_offset])
        if not is_var(_a):
            _k = _runtime_arg_key(_a, _deep_gate)
            if _k is _INDEX_VAR:
                # A02-F001: uncomputable key at this plan — try the NEXT
                # plan (another position may index) before falling back.
                continue
            try:
                _bfn = _idx_dict.get(_k)
            except TypeError:
                continue
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from _dflt_fn(*args)
            return
    yield from fallback_fn(*args)


def _make_groundness_dispatch_simple(plans, fallback_fn):
    """Build a groundness-keyed dispatch selector for simple/short-stack mode.

    *plans* is a list of ``(pos, idx_dict, default_fn, deep_gate)``
    4-tuples, sorted by selectivity (most selective position first). At
    call time the selector checks each position's argument; the first
    ground argument triggers index lookup on that position.  If no
    argument is ground, *fallback_fn* (all clauses, linear scan) is used.

    A single-position plan gets a specialised fast path that skips the
    iteration.  See ``_groundness_dispatch_body_single`` /
    ``_groundness_dispatch_body_multi`` for the shared bodies.
    """
    if len(plans) == 1:
        pos, idx_dict, dflt_fn, deep_gate = plans[0]
        def dispatch(*args):
            yield from _groundness_dispatch_body_single(
                args, pos, idx_dict, dflt_fn, fallback_fn, deep_gate,
            )
    else:
        def dispatch(*args):
            yield from _groundness_dispatch_body_multi(
                args, plans, fallback_fn, arg_offset=0,
            )
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_groundness_dispatch_trampoline(plans, fallback_fn, done,
                                         tro_state=None, arity=0):
    """Build a groundness-keyed dispatch selector for trampoline mode.

    Same logic as :func:`_make_groundness_dispatch_simple` but accounts for
    the trampoline arg layout
    ``(this_generator, _proceed, _fail, _catcher, arg0, ..., trail)``
    (Phase 2 split-continuation) and emits a trailing
    ``yield (_fail, done)`` after search exhaustion.

    *plans* is a list of ``(pos, idx_dict, default_fn, deep_gate)``
    4-tuples -- see :func:`_make_groundness_dispatch_simple`.

    when *tro_state* is not None, the dispatch loops: after each bucket
    ``yield from`` completes, it checks ``tro_state[0]``.  If True, updates
    args from ``tro_state[1..N]`` and re-dispatches (potentially to a
    different bucket).
    """
    if len(plans) == 1:
        pos, idx_dict, dflt_fn, deep_gate = plans[0]
        offset = pos + 4  # skip this_generator, _proceed, _fail, _catcher
        if tro_state is not None:
            def dispatch(*args):
                _fail = args[2]
                args_list = None
                while True:
                    tro_state[0] = False
                    _current = args_list if args_list is not None else args
                    _a = deref(_current[offset])
                    # A02-F001: an unbound Var, a non-var arg with an
                    # uncomputable key (partial char/code-list, Decimal, …),
                    # or an unhashable key (defensive) must scan ALL clauses,
                    # not the default bucket — mirror the non-TRO
                    # _groundness_dispatch_body_single guard. The fallback is
                    # compiled in SIGNAL mode (emit_done=False ⇒
                    # tro_mode="signal"), exactly like the buckets, so it must
                    # fall through to the tro_state check below: a tail call
                    # signalled from its TRO clause re-dispatches (possibly
                    # into an indexed bucket) instead of being dropped.
                    if is_var(_a):
                        _bfn = fallback_fn
                    else:
                        _k = _runtime_arg_key(_a, deep_gate)
                        if _k is _INDEX_VAR:
                            _bfn = fallback_fn
                        else:
                            try:
                                _bfn = idx_dict.get(_k)
                            except TypeError:
                                _bfn = fallback_fn
                            if _bfn is None:
                                _bfn = dflt_fn
                    _pending = [False] + [None] * arity
                    yield from _drive_tro_bucket(
                        _bfn(*_current), tro_state, arity, _pending)
                    if _pending[0]:
                        if args_list is None:
                            args_list = list(args)
                        for _i in range(arity):
                            args_list[_i + 4] = _pending[_i + 1]
                        continue
                    break
                yield (_fail, done)
        else:
            def dispatch(*args):
                _fail = args[2]
                yield from _groundness_dispatch_body_single(
                    args, offset, idx_dict, dflt_fn, fallback_fn, deep_gate,
                )
                yield (_fail, done)
        dispatch.__name__ = fallback_fn.__name__
        dispatch.__qualname__ = fallback_fn.__qualname__
        return dispatch

    if tro_state is not None:
        def dispatch(*args):
            _fail = args[2]
            args_list = None
            while True:
                tro_state[0] = False
                _current = args_list if args_list is not None else args
                _bfn = None
                for _pos, _idx_dict, _dflt_fn, _deep_gate in plans:
                    _a = deref(_current[_pos + 4])
                    if not is_var(_a):
                        _k = _runtime_arg_key(_a, _deep_gate)
                        if _k is _INDEX_VAR:
                            # A02-F001: uncomputable key at this plan — try
                            # the NEXT plan (another position may index)
                            # before the full-scan fallback, mirroring the
                            # non-TRO _groundness_dispatch_body_multi.
                            continue
                        try:
                            _cand = _idx_dict.get(_k)
                        except TypeError:
                            continue
                        _bfn = _cand if _cand is not None else _dflt_fn
                        break
                if _bfn is None:
                    # A02-F001: no plan had a ground arg with a computable
                    # key — full scan. The fallback is compiled in SIGNAL
                    # mode (like the buckets), so its tail call re-dispatches.
                    _bfn = fallback_fn
                _pending = [False] + [None] * arity
                yield from _drive_tro_bucket(
                    _bfn(*_current), tro_state, arity, _pending)
                if _pending[0]:
                    if args_list is None:
                        args_list = list(args)
                    for _i in range(arity):
                        args_list[_i + 4] = _pending[_i + 1]
                    continue
                break
            yield (_fail, done)
    else:
        def dispatch(*args):
            _fail = args[2]
            yield from _groundness_dispatch_body_multi(
                args, plans, fallback_fn, arg_offset=4,
            )
            yield (_fail, done)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch
