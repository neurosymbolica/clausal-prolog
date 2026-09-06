"""The ONE outbound term → Python conversion.

Spec: ``docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md``
§9.1.  Before this module there were four independent term↔Python crossings;
``to_python`` is the single outbound one, shared by

  * every ``py.*`` library wrapper (``clausal/modules/py/_helpers.py``
    re-exports it, and keeps the historical name ``_deep_deref`` as an alias
    for the in-tree callers and the out-of-tree wrapper distributions), and
  * the ``PyThunk`` argument path — ``++`` escapes and f-strings — which the
    compiler lowers to the injected runtime name ``$to_python``
    (``clausal/logic/compiler/terms_to_ast.py``,
    ``INJECTED_RUNTIME_BUILTINS`` in ``clausal/logic/compiler/predicate.py``).

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
from clausal.logic.variables import deref, walk
from clausal.terms import DictTerm, SegString

__all__ = ["to_python"]


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

    What this changes for ``f"…"`` and ``++`` (Task 8 carry-forward)
    ----------------------------------------------------------------
    The thunk argument path lowers to ``$to_python`` (see the module
    docstring), so a CONTAINER interpolated into an f-string or read inside a
    ``++`` escape crosses as the plain Python container -- a ``DictTerm``
    arrives as a ``dict``, a ``SegList``/``SegString`` as the ``list``/``str``
    it walks to, a cell as a ``tuple`` -- and is therefore rendered by
    PYTHON's ``repr``/``format``, not by the engine's ``term_str``.  Concretely
    ``f"{D}"`` on ``D = {a: 1}`` renders ``{'a': 1}`` (Python dict syntax,
    the atom key as its spelling) rather than the engine's ``{a: 1}``.  That
    is the whole point of the single outbound conversion -- a foreign callee
    sees Python values, never engine term objects -- but it is a visible
    change in interpolated TEXT, so it is spelled out here.  Code that wants
    the engine's rendering asks for it: ``term_to_string(D, S)`` (or
    ``print_term/1``), then interpolate ``S``.
    """
    # A str is an atom AND its own spelling AND can never be a bound Var, so
    # it needs neither the deref nor the atom branch.  It is the hot case on
    # the thunk path (f-strings), hence the short-circuit.
    if type(val) is str:
        return val
    val = deref(val)
    # Atom before the tuple arm, which would otherwise turn the arity-0 cell
    # ``("bar",)`` into a 1-tuple of its spelling.
    if _term_is_atom(val):
        return _atom_spelling(val)
    if isinstance(val, SegString):
        # ``deref`` follows Var bindings only; a SegString normalises under
        # ``walk``, which yields a plain str exactly when every hole is bound.
        walked = walk(val)
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
