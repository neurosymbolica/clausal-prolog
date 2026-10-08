"""The outbound term → Python conversions — one deep, one top-level.

Spec: ``docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md``
§9.1.  Before this module there were four independent term↔Python crossings.
Two remain, and which one a boundary gets is a decided trade, not an
accident:

  * :func:`to_python` — the DEEP conversion, used by every ``py.*`` library
    wrapper (``clausal/modules/py/_helpers.py`` re-exports it, and keeps the
    historical name ``_deep_deref`` as an alias for the in-tree callers and
    the out-of-tree wrapper distributions).  A foreign library cannot read
    engine terms, so its arguments are converted all the way down.
  * :func:`unwrap_atom` — a TOP-LEVEL atom only, used by the ``PyThunk``
    argument path (``++`` escapes and f-strings), which the compiler lowers
    to the injected runtime name ``$unwrap_atom``
    (``clausal/logic/compiler/terms_to_ast.py``,
    ``INJECTED_RUNTIME_BUILTINS`` in ``clausal/logic/compiler/predicate.py``).
    This is §9.1's pre-stated fallback, applied 2026-09-07 on Task 14's
    measurement — see :func:`unwrap_atom` for the numbers and the trade.

It lives under ``clausal/logic/`` rather than with the wrappers precisely so
that the compiler can bind it: ``clausal.logic`` must not grow a module-level
import edge into ``clausal.modules.py``.  Its own imports (``clausal.terms``,
``clausal.logic.atoms``, ``clausal.logic.variables``) are all ones the
compiler already pulls in at module level.

Inbound is deliberately NOT symmetric (§9.1): a Python ``str`` coming back
is a *string*, not the atom that went out, so ``X = bar, Y = ++X, X == Y``
fails.  That is the loud rule (foreign text is a string, R-S3); programs that
need an atom back mint one.
"""

from __future__ import annotations

import copy

from clausal.logic.atoms import (
    crossing_value as _crossing_value,
    is_atom as _term_is_atom, spelling as _atom_spelling, atom, as_dict_key as _as_dict_key)
from clausal.logic.cells import chars, is_chars, chars_text, TUPLE_TAG  # stage 1: the chars carrier
from clausal.logic.python_terms import FROM_TERM as _FROM_TERM  # the ONE registry (no cycle: python_terms never imports this module)
from clausal.logic.variables import deref, walk
from clausal.terms import (
    DictTerm, SegBytes, SegList, SegListView, SegString, SetTerm)
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.pythonic_ast.nodes import Node as _Node

__all__ = ["to_python", "unwrap_atom", "strip_atom_tags", "has_atom_tag",
           "term_children", "map_term", "TERM_CONTAINER_TYPES"]


def to_python(val):
    """The DEEP outbound conversion: *val* as the Python value a foreign
    callee -- or a Python caller reading an answer -- should see.

    THE PUBLIC DEEP OUT CONVERTER (dumb-seam step (a), 2026-09-26; exported
    as ``clausal.to_python``).  Derefs, then converts every engine shape all
    the way down, and rebuilds every functor the ONE registry
    (``clausal.logic.python_terms.FROM_TERM``) knows:

    - a ``str`` is returned as itself -- the overwhelmingly common case, so it
      short-circuits before the deref (an atom IS the str);
    - a **string** -- the chars carrier ``('$chars', s)``, or a ground
      ``SegString`` / all-chars ``SegList`` -- becomes its text, a plain
      ``str``; a NON-ground ``Seg*`` crosses raw (there is no text to hand
      over yet, and the caller can still unify it);
    - a **cell** ``(f, ...)`` becomes a tuple with converted elements --
      unless ``f`` is a REGISTERED functor, in which case the registered
      rebuild answers: ``('date', 2023, 6, 1)`` is a ``datetime.date``, the
      data cell ``('()', 1, 2)`` is the tuple ``(1, 2)``.  A look-alike
      whose components do not rebuild (``('date', "x", "y")``) stays a cell.
      Tuples are preserved as tuples (not converted to lists) -- library
      code that distinguishes tuple-of-ints from list-of-ints relies on
      this, e.g. ``a.at[(1, 2)]`` vs ``a.at[[1, 2]]`` in JAX;
    - a ``SetTerm`` becomes a ``frozenset`` of converted elements (a
      ``set``/``frozenset`` keeps its type); an element that converts to
      something unhashable (a dict) raises ``TypeError``, loudly;
    - a **DictTerm** or plain dict becomes a ``dict``, KEYS converted and
      NORMALISED (``atoms.as_dict_key``: nil in every spelling is ``()``).
      An atom key and the string of its spelling are ONE Python key -- the
      advisory-equality consequence the 2026-09-21 spec calls wanted; two
      engine keys that merge keep the LAST value, so a caller who needs both
      reads the ``DictTerm`` itself;
    - everything else crosses raw.

    NamedTuple subclasses are reconstructed via their own constructor so
    attribute access (``.init`` / ``.update`` on optax's
    ``GradientTransformation``, etc.) survives a round-trip.

    NOT the ``f"…"`` / ``++`` path
    ------------------------------
    The thunk argument path lowers to ``$unwrap_atom``, not to this function
    (§9.1's fallback, applied on Task 14's measurement -- see
    :func:`unwrap_atom`).  So a CONTAINER interpolated into an f-string or
    read inside a ``++`` escape crosses RAW: a ``DictTerm`` arrives as a
    ``DictTerm``, a cell as the cell.  Code at a thunk that wants Python
    values all the way down calls this function by name; code that wants the
    engine's rendering asks for it with ``term_to_string(D, S)`` (or
    ``print_term/1``) and interpolates ``S``.
    """
    # A str is an ATOM whose Python form is itself, and it can never be a
    # bound Var, so it needs neither the deref nor the atom branch.  It is
    # the hot case on the thunk path (f-strings), hence the short-circuit.
    if type(val) is str:
        return val
    val = deref(val)
    t = type(val)
    if t in _SCALAR_TYPES:
        # A number / None / bytes crosses as itself.  Exact-type dispatch
        # FIRST: the ``isinstance`` chain below is walked only by the term
        # shapes, and an int that walked all of it cost 5x (in-process A/B,
        # 2026-09-26).
        return val
    if t is tuple:
        if is_chars(val):
            return chars_text(val)     # stage 1: a chars string crosses out as its text
        items = tuple([to_python(x) for x in val])
        if items and type(items[0]) is str:
            # THE ONE REGISTRY: a registered functor rebuilds its Python
            # object from the ALREADY-CONVERTED elements -- a from_fn is
            # shallow (python_terms.from_term: one owner of recursion), so
            # nothing is converted twice; a look-alike whose components do
            # not rebuild stays a cell.  Inline, because a miss (an ordinary
            # cell) is the common case.
            rebuild = _FROM_TERM.get(items[0])
            if rebuild is not None:
                try:
                    return rebuild(items)
                except (TypeError, ValueError, OverflowError):
                    pass
        return items
    if t is list:
        return [to_python(x) for x in val]
    # A Var BOUND to an atom: the ``type(val) is str`` hot case above ran
    # before the deref, so the dereferenced str arrives here.
    if _term_is_atom(val):
        return _crossing_value(val)    # a truth atom crosses as its OBJECT (D35)
    if isinstance(val, _SEG_TYPES):
        # ``deref`` follows Var bindings only; a Seg* normalises under
        # ``walk``, which yields the ground form exactly when every hole is
        # bound: the carrier (text Seg*), a list, or bytes.  Non-ground: the
        # ORIGINAL object, unconverted (pinned by test_python_boundary).
        walked = walk(val)
        if is_chars(walked):
            return chars_text(walked)  # stage 1: a ground text Seg* walks to the carrier
        if isinstance(walked, _SEG_TYPES):
            return val
        return to_python(walked)
    if isinstance(val, tuple):
        # NamedTuple — preserve subclass so attribute access survives.
        items = tuple(to_python(x) for x in val)
        try:
            return t(*items)
        except TypeError:
            return items
    if isinstance(val, list):
        return [to_python(x) for x in val]
    if isinstance(val, (DictTerm, dict)):
        return {_as_dict_key(to_python(k)): to_python(v) for k, v in val.items()}
    if isinstance(val, SetTerm):
        return frozenset(to_python(e) for e in val)
    if isinstance(val, (set, frozenset)):
        return t(to_python(e) for e in val)
    if is_term_instance(val):
        # A dataclass term class is rebuilt with converted fields (dumb seam
        # step (c), 2026-09-26; before that it crossed unchanged, insides
        # and all).  A pythonic_ast Node crosses as itself: it is code, not
        # data, and its ``++`` values already passed through wrap_text.
        if isinstance(val, _Node):
            return val
        # Rebuild only when a field CHANGED: a dataclass whose fields all
        # convert to themselves crosses as itself.  ``t(**fields)`` needs the
        # generated ``__init__``; a dataclass with its own (an Equinox module:
        # ``Linear(in_features, out_features, key=...)``) refuses its fields,
        # so it is copied and the converted fields set on the copy.
        old = {n: getattr(val, n) for n in term_field_names(val)}
        new = {n: to_python(v) for n, v in old.items()}
        if all(new[n] is old[n] for n in old):
            return val
        try:
            return t(**new)
        except TypeError:
            rebuilt = copy.copy(val)
            for n, v in new.items():
                object.__setattr__(rebuilt, n, v)   # frozen dataclasses too
            return rebuilt
    return val


#: Every type the engine treats as a TERM CONTAINER -- the shapes to_python
#: converts, map_term rebuilds and term_children walks.  One list, so the
#: three cannot drift (tests/test_leak_doors.py pins each entry against all
#: three); a dataclass term class is the open-ended member, recognised by
#: ``is_term_instance``.  Seg* are containers too but hold str/VarSeg
#: segments, not arbitrary terms: map_term leaves them alone, to_python walks
#: them to their ground form.
TERM_CONTAINER_TYPES = (tuple, list, dict, DictTerm, SetTerm, set, frozenset)


def term_children(val):
    """The direct children of a term container, or ``()`` for a leaf.  A
    dict-like container yields keys and values; a NamedTuple its fields."""
    if isinstance(val, (tuple, list)):
        return val
    if isinstance(val, (dict, DictTerm)):
        out = []
        for k, v in val.items():
            out.append(k); out.append(v)
        return out
    if isinstance(val, (SetTerm, set, frozenset)):
        return list(val)
    if is_term_instance(val):
        return [getattr(val, n) for n in term_field_names(val)]
    return ()


def map_term(val, fn):
    """*val* rebuilt with *fn* applied to each direct child, for every
    container in TERM_CONTAINER_TYPES; the SAME OBJECT when no child
    changed (identity is the "unchanged" signal, so callers allocate
    nothing on the common path).  A leaf is returned as it is.  A dict or
    list SUBCLASS is rebuilt as its own type when its constructor takes
    the rebuilt contents, and a NamedTuple through its own constructor;
    when that raises TypeError the plain type is the documented fallback."""
    t = type(val)
    if t is tuple or t is list:
        out = [fn(v) for v in val]
        if all(a is b for a, b in zip(out, val)):
            return val
        return tuple(out) if t is tuple else out
    if isinstance(val, tuple):                         # NamedTuple
        out = [fn(v) for v in val]
        if all(a is b for a, b in zip(out, val)):
            return val
        try:
            return t(*out)
        except TypeError:
            return tuple(out)
    if isinstance(val, list):                          # a list subclass
        out = [fn(v) for v in val]
        if all(a is b for a, b in zip(out, val)):
            return val
        # a shallow copy keeps the instance's own state; list's slot
        # assignment bypasses a subclass constructor or __setitem__ whose
        # one-argument form means something else (roborev 257)
        new = copy.copy(val)
        list.__setitem__(new, slice(None), out)
        return new
    if isinstance(val, DictTerm):
        items = list(val.items())
        out = [(fn(k), fn(v)) for k, v in items]
        if all(k1 is k2 and v1 is v2 for (k1, v1), (k2, v2) in zip(out, items)):
            return val
        return DictTerm(dict(out), _position=val._position)
    if isinstance(val, dict):                          # dict and its subclasses
        items = list(val.items())
        out = [(fn(k), fn(v)) for k, v in items]
        if all(k1 is k2 and v1 is v2 for (k1, v1), (k2, v2) in zip(out, items)):
            return val
        if t is dict:
            return dict(out)
        # a shallow copy keeps default_factory and any other instance state;
        # dict's own update bypasses a subclass whose constructor reads a
        # pair list differently (Counter counts the pairs; roborev 257)
        new = copy.copy(val)
        dict.clear(new)
        dict.update(new, out)
        return new
    if isinstance(val, SetTerm):
        elems = [fn(e) for e in val]
        if all(a is b for a, b in zip(elems, val)):
            return val
        return SetTerm(elems, _position=val._position)
    if isinstance(val, (set, frozenset)):
        elems = [fn(e) for e in val]
        return val if all(a is b for a, b in zip(elems, val)) else t(elems)
    if is_term_instance(val):
        names = term_field_names(val)
        fields = {n: fn(getattr(val, n)) for n in names}
        if all(fields[n] is getattr(val, n) for n in names):
            return val
        return t(**fields)
    return val


#: Exact types that cross as themselves (bool before int matters not: both
#: are here).  ``str`` is handled first, above, as the thunk-path hot case.
_SCALAR_TYPES = frozenset((int, float, bool, type(None), bytes, complex))
_SEG_TYPES = (SegString, SegList, SegBytes)


def wrap_text(val):
    """The THUNK-path INBOUND conversion (stage 1 of the atoms-as-str flip,
    spec 2026-09-18): a Python ``str`` a ``++`` escape or an f-string hands
    back is TEXT, and text is the chars carrier.  Top level only, the mirror
    of :func:`unwrap_atom`'s one-level outbound rule -- a container crosses
    raw.  Stage 2 makes a bare str the ATOM and this becomes identity for a
    plain ``str``.

    THE LEAK RULE (boundary spec 2026-09-21): an ``atom`` INSTANCE handed back
    here is normalised to a plain ``str``.  ``atom`` is a boundary type — it
    exists so ``--`` can tell Python which it has — and ``is_atom`` is
    ``type(term) is str``, so an instance that reached term space would be
    INVISIBLE to it.  ``--`` now hands atoms out tagged, so an author who feeds
    one straight back through ``++`` is the ordinary round trip, not a misuse:
    this is where it becomes a term again.

    What a plain ``str`` MEANS here is unchanged and is step 4's question."""
    if type(val) is atom:
        return str.__str__(val)        # the LEAK RULE: a boundary tag never enters a term
    return val                         # STAGE 2: a str a thunk hands back IS the atom (identity)


def has_atom_tag(val) -> bool:
    """True iff an ``atom`` INSTANCE is reachable from *val* through the term
    containers.  ITERATIVE (a cons-like goal thousands of levels deep must
    not raise RecursionError at solve()), read-only: the cheap scan every
    Python entry runs before deciding whether the rebuild is needed at all.

    CYCLE-SAFE: a container is entered once, by id, and a reference to it
    is kept for the scan so a computed child (a property that returns a
    fresh container) cannot die and hand its id to a later one.  A cyclic
    term -- the engine builds one on purpose in unify without the occurs
    check, and the adversarial tests hand such goals to solve() -- otherwise
    grew the walk's stack without bound until the OOM killer took the
    process (the gate died twice at the same test, 2026-09-26).  A
    pythonic_ast Node (a rewriter-built goal) is a leaf: it is code, and its
    ``++`` values already passed through wrap_text, so a goal-position seam
    pays one type test here, not a walk of its tree."""
    stack = [val]
    seen: dict = {}          # id -> the container: a reference is KEPT, so no id can be reused mid-scan
    while stack:
        v = stack.pop()
        if type(v) is atom:
            return True
        if isinstance(v, _Node):
            continue         # a rewriter goal is code, not data; its ++ values passed wrap_text
        children = term_children(v)
        if children:
            key = id(v)
            if key in seen:
                continue
            seen[key] = v
            stack.extend(children)
    return False


def strip_atom_tags(val):
    """*val* with every ``atom`` INSTANCE -- at any depth of any term
    container (TERM_CONTAINER_TYPES, via map_term) -- replaced by the plain
    ``str`` it tags.  THE LEAK RULE, deep.

    ``wrap_text`` applies the rule to a ``++`` value, one level.  The doors
    it never sees are a seam's bare-name lookup (``seam.build``) and a Python
    caller's goal/arguments at ``solve``/``call`` (and so ``once``, ``query``,
    ``each``); both call this (dumb seam step (d), 2026-09-26).  Returns the
    SAME OBJECT when nothing needed changing; callers on a hot path run
    :func:`has_atom_tag` first, so the rebuild only ever runs on a value
    that holds a tag.

    ONLY A SUBTREE THAT HOLDS A TAG IS REBUILT (roborev 257): one linear,
    cycle-safe pass (:func:`_tag_reachability`) marks every container from
    which a tag is reachable; every other subtree -- an unrelated cyclic
    answer beside a tag, a big untagged list -- is handed back by identity
    without being entered.  A CYCLE that itself holds a tag cannot be
    rebuilt (an immutable cycle has no first element to build) and is
    refused with a ``TypeError``."""
    if type(val) is atom:
        return str.__str__(val)
    reach = _tag_reachability(val)
    if not reach:
        return val
    return _strip(val, reach, set(), {})


def _tag_reachability(root) -> dict:
    """``{id(container): container}`` for every container reachable from
    *root* from which an ``atom`` instance is reachable.  Linear: one
    iterative DFS records containers, their parent links and which hold a
    tag directly; one reverse BFS from those propagates "holds a tag" to
    every ancestor.  Cycle-safe by construction (ids, references kept)."""
    nodes: dict = {}          # id -> container (kept alive for the pass)
    parents: dict = {}        # id -> [parent ids]
    direct: list = []         # ids of containers with a tag as a direct child
    stack = [(root, None)]
    while stack:
        v, parent = stack.pop()
        if type(v) is atom:
            if parent is not None:
                direct.append(parent)
            continue
        if isinstance(v, _Node):
            continue
        children = term_children(v)
        if not children:
            continue
        key = id(v)
        if parent is not None:
            parents.setdefault(key, []).append(parent)
        if key in nodes:
            continue
        nodes[key] = v
        for c in children:
            stack.append((c, key))
    reach: dict = {}
    todo = list(direct)
    while todo:
        key = todo.pop()
        if key in reach:
            continue
        reach[key] = nodes[key]
        todo.extend(parents.get(key, ()))
    return reach


def _strip(val, reach: dict, active: set, done: dict):
    """Rebuild *val* with its tags stripped.  *done* memoises by id for the
    one call, so a tagged subterm SHARED by several paths is rebuilt once
    and the result keeps the sharing (roborev on 3ee9c7d6: without it a
    tagged DAG with nested sharing took exponential time).  *reach* keeps
    every container alive for the call, so an id cannot be reused."""
    if type(val) is atom:
        return str.__str__(val)
    key = id(val)
    if key not in reach:
        return val                    # no tag below: by identity, not entered
    if key in done:
        return done[key]
    if key in active:
        raise TypeError(
            "the goal holds a boundary `atom` inside a CYCLIC term; a cyclic "
            "term cannot be rebuilt -- build it from plain str atoms (the atom "
            "IS the str) or break the cycle")
    active.add(key)
    try:
        out = map_term(val, lambda v: _strip(v, reach, active, done))
    finally:
        active.discard(key)
    done[key] = out
    return out


def unwrap_atom(val):
    """The THUNK-path outbound conversion: a TOP-LEVEL atom only.

    Spec §9.1's stated fallback, **applied 2026-09-07** after Task 14's
    interleaved A/B put ``bench_thunk_atoms`` at B/A = 1.074 against the
    3 % bar — the one item §9.1 predicted would register.  Rebinding the
    thunk argument path from :func:`to_python` to this function recovered
    8.2 % of that benchmark and landed within 0.9 % of the pre-flip
    single-level ``$deref`` lowering.

    So ``++`` escapes and f-strings unwrap an atom ARGUMENT to its spelling
    -- the case the flip actually broke, where the old ``$deref`` handed a
    ``str`` method a 1-tuple -- and hand everything else over exactly as the
    old lowering did.  A CONTAINER therefore crosses raw: a nested atom
    inside a list, tuple or dict argument arrives as the cell ``("bar",)``,
    not as ``"bar"``, and a ``DictTerm``/``SegList`` arrives as itself.  Code
    that wants the deep conversion asks for it by name -- ``to_python`` is
    exported from ``clausal.modules.py._helpers`` (also as ``_deep_deref``)
    and is what every ``py.*`` wrapper still uses.

    The asymmetry is deliberate and is the whole content of the fallback: a
    ``py.*`` call crosses a bounded argument list into a foreign library that
    cannot read engine terms, and pays for the walk once; a ``++`` escape is
    inline in a clause body, runs in the inner loop, and is written by
    someone who can see exactly what they are passing.
    """
    val = deref(val)
    if is_chars(val):
        return chars_text(val)         # stage 1: a TOP-LEVEL chars string crosses out as its text
    if type(val) is SegListView:
        val = val.elements()           # the view of a list crosses as the list it is (a copy)
    if type(val) is list:
        # one level down too: a list of chars strings is what ", ".join(W)
        # and every other str-consuming call over a list expects (stage 1;
        # atoms inside stay cells).  The container crosses by IDENTITY when
        # nothing inside is a carrier -- the documented "nothing deeper"
        # contract -- and as a fresh list only when a carrier had to be read.
        if any(is_chars(deref(x)) for x in val):
            return [chars_text(e) if is_chars(e) else e for e in (deref(x) for x in val)]
        return val
    return _crossing_value(val) if _term_is_atom(val) else val   # a truth atom crosses as its OBJECT (D35)
