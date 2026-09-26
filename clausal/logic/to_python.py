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

from clausal.logic.atoms import (
    is_atom as _term_is_atom, spelling as _atom_spelling, atom, as_dict_key as _as_dict_key)
from clausal.logic.cells import chars, is_chars, chars_text, CHARS_TAG, TUPLE_TAG  # stage 1: the chars carrier
from clausal.logic.python_terms import FROM_TERM as _FROM_TERM  # the ONE registry (no cycle: python_terms never imports this module)
from clausal.logic.variables import deref, walk
from clausal.terms import (
    Compound, DictTerm, KWTerm, SegBytes, SegList, SegString, SetTerm, compound_as_cell)

__all__ = ["to_python", "unwrap_atom"]


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
    - a ``Compound`` with a cell equivalent (atom functor, arity >= 1;
      ruling 2026-09-26: it IS that cell) converts as the cell; one without
      (arity 0, or a Var functor) keeps its shape with converted arguments;
    - a ``KWTerm`` keeps its shape with converted field values -- Python has
      no keyword-term type to become;
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
        if len(val) == 2 and val[0] == _CHARS_TAG and type(val[1]) is str:
            return val[1]              # stage 1: a chars string crosses out as its text
        items = tuple([to_python(x) for x in val])
        if items and type(items[0]) is str:
            # THE ONE REGISTRY: a registered functor rebuilds its Python
            # object from the already-converted elements; a look-alike whose
            # components do not rebuild stays a cell.  Inline, because a
            # miss (an ordinary cell) is the common case.
            rebuild = _FROM_TERM.get(items[0])
            if rebuild is not None:
                try:
                    return rebuild(items)
                except (TypeError, ValueError, OverflowError):
                    pass
        return items
    if t is list:
        return [to_python(x) for x in val]
    # Atom before the generic tuple arm, which would otherwise turn the
    # arity-0 cell ``("bar",)`` into a 1-tuple of its spelling.
    if _term_is_atom(val):
        return _atom_spelling(val)
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
    if isinstance(val, Compound):
        cell = compound_as_cell(val)
        if cell is not None:
            return to_python(cell)
        return Compound(deref(val.functor), tuple(to_python(a) for a in val.args),
                        _position=val._position)
    if isinstance(val, KWTerm):
        return KWTerm(val.functor, _position=val._position,
                      **{k: to_python(v) for k, v in val.items()})
    if isinstance(val, (DictTerm, dict)):
        return {_as_dict_key(to_python(k)): to_python(v) for k, v in val.items()}
    if isinstance(val, SetTerm):
        return frozenset(to_python(e) for e in val)
    if isinstance(val, (set, frozenset)):
        return t(to_python(e) for e in val)
    return val


#: Exact types that cross as themselves (bool before int matters not: both
#: are here).  ``str`` is handled first, above, as the thunk-path hot case.
_SCALAR_TYPES = frozenset((int, float, bool, type(None), bytes, complex))
_SEG_TYPES = (SegString, SegList, SegBytes)
_CHARS_TAG = CHARS_TAG


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
    if type(val) is list:
        # one level down too: a list of chars strings is what ", ".join(W)
        # and every other str-consuming call over a list expects (stage 1;
        # atoms inside stay cells).  The container crosses by IDENTITY when
        # nothing inside is a carrier -- the documented "nothing deeper"
        # contract -- and as a fresh list only when a carrier had to be read.
        if any(is_chars(deref(x)) for x in val):
            return [chars_text(e) if is_chars(e) else e for e in (deref(x) for x in val)]
        return val
    return _atom_spelling(val) if _term_is_atom(val) else val
