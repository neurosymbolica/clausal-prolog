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

from clausal.logic.atoms import is_atom as _term_is_atom, spelling as _atom_spelling
from clausal.logic.cells import chars, is_chars, chars_text  # stage 1: the chars carrier
from clausal.logic.variables import deref, walk
from clausal.terms import DictTerm, SegString

__all__ = ["to_python", "unwrap_atom"]


def to_python(val):
    """Convert a term to the plain Python value a foreign callee should see.

    Derefs, then recursively converts list, tuple, and dict elements:

    - a ``str`` is returned as itself — the overwhelmingly common case, so it
      short-circuits before the deref;
    - an **atom** becomes its spelling, a plain ``str`` — the arity-0 cell
      ``("bar",)`` unwraps to ``"bar"``;
    - a ground **SegString** walks to its ``str``; a non-ground one crosses
      raw (there is no text to hand over yet);
    - a **cell of arity >= 1** stays a tuple with converted elements.
      Tuples are preserved as tuples (not converted to lists) — library code
      that distinguishes tuple-of-ints from list-of-ints relies on this, e.g.
      ``a.at[(1, 2)]`` vs ``a.at[[1, 2]]`` in JAX have different semantics;
    - a **DictTerm** or plain dict becomes a ``dict``, KEYS converted too, so
      an atom key crosses out as a ``str`` key;
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
    ``DictTerm``, a cell as the cell, a nested atom as ``("bar",)``.  Code at
    a thunk that wants Python values all the way down calls this function by
    name (``from clausal.modules.py._helpers import to_python``); code that
    wants the engine's rendering asks for it with ``term_to_string(D, S)``
    (or ``print_term/1``) and interpolates ``S``.
    """
    # A str is a STRING (spec §5.1) whose Python form is itself, and it can
    # never be a bound Var, so it needs neither the deref nor the atom
    # branch.  It is the hot case on the thunk path (f-strings), hence the
    # short-circuit.
    if type(val) is str:
        return val
    val = deref(val)
    if is_chars(val):
        return chars_text(val)         # stage 1: a chars string crosses out as its text
    # Atom before the tuple arm, which would otherwise turn the arity-0 cell
    # ``("bar",)`` into a 1-tuple of its spelling.
    if _term_is_atom(val):
        return _atom_spelling(val)
    if isinstance(val, SegString):
        # ``deref`` follows Var bindings only; a SegString normalises under
        # ``walk``, which yields a plain str exactly when every hole is bound.
        walked = walk(val)
        if is_chars(walked):
            return chars_text(walked)  # stage 1: a ground SegString walks to the carrier
        return walked if type(walked) is str else val
    if isinstance(val, list):
        return [to_python(x) for x in val]
    if isinstance(val, tuple):
        items = tuple(to_python(x) for x in val)
        if type(val) is tuple:
            return items
        # NamedTuple — preserve subclass so attribute access survives.
        try:
            return type(val)(*items)
        except TypeError:
            return items
    if isinstance(val, DictTerm):
        return {to_python(k): to_python(v) for k, v in val.items()}
    if isinstance(val, dict):
        return {to_python(k): to_python(v) for k, v in val.items()}
    return val


def wrap_text(val):
    """The THUNK-path INBOUND conversion (stage 1 of the atoms-as-str flip,
    spec 2026-09-18): a Python ``str`` a ``++`` escape or an f-string hands
    back is TEXT, and text is the chars carrier.  Top level only, the mirror
    of :func:`unwrap_atom`'s one-level outbound rule -- a container crosses
    raw.  Stage 2 makes a bare str the ATOM and this becomes identity."""
    if type(val) is str:
        return chars(val)
    return val


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
        # the container itself still crosses raw, atoms inside stay cells)
        return [chars_text(e) if is_chars(e) else e for e in (deref(x) for x in val)]
    return _atom_spelling(val) if _term_is_atom(val) else val
