"""Shared helpers for the cell-representation tests.

Imported by ``tests/test_tagged_terms.py`` and by the parity corpus
(``tests/test_tagged_terms_parity.py``).  Two independent facilities live
here:

``normalize_term`` / ``normalize_answers``
    The *representation normalizer*.  A compiled module answers a query with
    CELLS -- plain tuples ``("point", x, y)``; a PYTHON-side producer
    (``clausal.reflection``, ``clausal.logic.clpb``) still builds class-term
    instances ``point(X=x, Y=y)``.  The two are structurally the same term
    in two representations, so a test cannot compare them with ``==``.
    ``normalize_term`` maps BOTH to the same canonical Python value:
    ``("point", <norm x>, <norm y>)``.

    Pre-P3-2 the two representations were the two halves of a fixture PAIR,
    one carrying the ``-tagged_terms`` flag; the flag is deleted and cells
    are unconditional, so the recorded class-era ANSWERS are what the pair
    now anchors -- this normalizer is what makes that comparison possible.

``capture_predicate_codegen``
    Deterministic capture of the Python source a predicate compiles to.
    Used by the codegen golden test and by the pattern-emission tests.
    Compilation of a predicate is lazy and memoised on the class, so the capture clears
    ``_dispatch_fn`` and re-drives ``_get_dispatch()`` through the
    predicate's own ``_lazy_recompile`` closure -- i.e. it reproduces the
    REAL compile path (same ``globals_``, same strategy, same indexing),
    not a hand-rolled approximation.
"""

from __future__ import annotations

import ast
import importlib
import re
from typing import Any

from clausal.logic.cells import is_cell, cell_args, cell_functor
from clausal.logic.compiler import predicate as _predicate_mod
from clausal.logic.predicate import (
    PredicateMeta, is_term_instance, term_field_names,
)
from clausal.logic.variables import deref, is_var


# ── Representation normalizer ────────────────────────────────────────────────


def normalize_term(value: Any) -> Any:
    """Canonicalise *value* so class terms and tagged cells compare equal.

    Mapping (applied recursively):

    ==============================  ==========================================
    input                           canonical form
    ==============================  ==========================================
    cell ``("f", a, b)``            ``("f", norm(a), norm(b))``
    class term ``f(A=a, B=b)``      ``("f", norm(a), norm(b))``
    atom ``nil``                    ``"nil"``  (P3-1 atom pivot: an atom IS
                                     the interned str; no wrapping needed --
                                     both halves already produce the same
                                     value.  See phase3-decomposition-and-
                                     p31-atom-pivot.md Task 7 work item 1.)
    unbound ``Var``                 ``("$var",)``  (identity is not comparable)
    ``list``                        ``["norm", ...]``
    plain ``tuple``                 unchanged shape, elements normalised
    ``dict``                        keys and values normalised
    anything else                   itself
    ==============================  ==========================================

    A cell and a class term of the same functor and arguments therefore
    produce the SAME canonical value, which is what the parity corpus
    compares.

    Note the deliberate collision with a plain data tuple whose slot 0 is a
    ``str``: ``("point", 1, 2)`` as ordinary tuple data normalises like the
    compound ``point(1, 2)``.  That is the representation's KNOWN AMBIGUITY
    (see ``clausal/logic/cells.py``), not a normalizer bug -- the fixtures do
    not use str-headed data tuples.
    """
    value = deref(value)
    if is_var(value):
        return ("$var",)
    # Pre-P3-1, a 0-arity predicate class used as a value WAS the atom, and
    # needed wrapping to ("name",) so it would compare equal to a cell's
    # str-headed 0-arity shape. The atom pivot (§1b) makes every atom an
    # interned str directly -- the cell half and any class half already emit
    # the identical value, so there is nothing left to normalise here. No
    # 0-arity PredicateMeta atom classes
    # are minted post-pivot (str falls through to the final `return value`
    # below); see phase3-decomposition-and-p31-atom-pivot.md Task 7.
    if is_cell(value):
        f = cell_functor(value)
        if isinstance(f, str):
            return (f, *(normalize_term(a) for a in cell_args(value)))
        # tuple-DATA cell / unresolved-functor cell: keep the shape.
        return tuple(normalize_term(e) for e in value)
    if isinstance(value, tuple):
        return tuple(normalize_term(e) for e in value)
    if is_term_instance(value):
        return (
            type(value).__name__,
            *(normalize_term(getattr(value, n)) for n in term_field_names(value)),
        )
    if isinstance(value, list):
        return [normalize_term(e) for e in value]
    if isinstance(value, dict):
        return {normalize_term(k): normalize_term(v) for k, v in value.items()}
    return value


def normalize_answers(answers) -> list:
    """Normalise an iterable of solution dicts (or bare values).

    Each element may be a ``dict`` (the usual ``solve`` binding map) or any
    term; both are routed through :func:`normalize_term`.
    """
    out = []
    for a in answers:
        if isinstance(a, dict):
            out.append({k: normalize_term(v) for k, v in a.items()})
        else:
            out.append(normalize_term(a))
    return out


# ── Deterministic codegen capture ────────────────────────────────────────────


# Generated local names carry counters that are process-global, not
# per-compilation: ``_vN`` is derived from ``Var._id`` (assigned when the
# module was loaded, so it depends on how many Vars any earlier import made),
# ``_mN`` from a monotonic trail-mark counter, ``_pyt_N`` / ``$headlit_N``
# from ``id()``.  None of that is part of the emitted program's MEANING, so a
# golden that pinned the raw numbers would be a flake generator.
#
# ``_stabilise`` renumbers every such name per prefix in order of first
# appearance across the whole capture.  Aliasing is preserved exactly -- two
# occurrences of the same original name still map to the same canonical name,
# and two different originals still differ -- so a genuine codegen change
# (an extra mark, a reordered capture, a dropped guard) still shows up.
# Anchored at an identifier boundary, and the whole matched identifier must be
# compiler-generated -- it starts with ``_`` or ``$`` and may carry a generated
# stem (``_fa_m246``, the fallback function's marks).  Without the anchor a
# USER identifier that merely ends in one of these shapes (``foo_v12`` -- a
# predicate or field a fixture happens to name that way) would have its tail
# renumbered, rewriting source the golden is supposed to pin verbatim.
_UNSTABLE_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_$])"                                   # identifier start
    r"((?:_[A-Za-z0-9]+)*)"                                 # generated stem
    r"(_pyt_|\$headlit_|_v|_m|_gen|_st|_ncap|_acap|_dcap|_scap|_xcap)"
    r"(\d+)"
)


def _stabilise(src: str) -> str:
    mapping: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {}

    def _sub(match: re.Match) -> str:
        stem, prefix, number = match.group(1), match.group(2), match.group(3)
        key = (prefix, number)
        canonical = mapping.get(key)
        if canonical is None:
            n = counters.get(prefix, 0)
            counters[prefix] = n + 1
            canonical = f"{prefix}{n}"
            mapping[key] = canonical
        return stem + canonical

    return _UNSTABLE_NAME_RE.sub(_sub, src)


def module_predicate_names(module) -> list[str]:
    """Every rule/fact predicate a ``.clausal`` module defines, name-sorted.

    Data functors and atoms (no clauses) are skipped -- they compile no
    dispatch function.  Names imported from another module are skipped too
    (``__module__`` gate), so a golden captured for module A does not shift
    when an unrelated module B it imports changes.
    """
    names = []
    for name, obj in vars(module).items():
        if not isinstance(obj, PredicateMeta):
            continue
        if not getattr(obj, "_clauses", None):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        names.append(name)
    return sorted(names)


def capture_predicate_codegen(module_name: str, pred_names=None) -> str:
    """Return the generated Python source for *pred_names* of *module_name*.

    *pred_names* defaults to every predicate the module itself defines
    (:func:`module_predicate_names`).

    Every ``FunctionDef`` the compiler hands to ``functiondef_to_function``
    is captured -- the main predicate function AND every index-bucket /
    default / fallback sub-function -- so the golden covers the indexed
    dispatch codegen too, not just the top-level arm layout.

    The module is imported normally (so the ``.clausal`` import hook, the
    directive handling and the module namespace are all the real ones), then
    each named predicate's memoised dispatch is dropped and recompiled.
    """
    module = importlib.import_module(module_name)
    if pred_names is None:
        pred_names = module_predicate_names(module)
    captured: list[str] = []
    original = _predicate_mod.functiondef_to_function

    def _spy(func_def, globals_=None, **kwargs):
        captured.append(ast.unparse(func_def))
        return original(func_def, globals_=globals_, **kwargs)

    _predicate_mod.functiondef_to_function = _spy
    try:
        for name in pred_names:
            pred = getattr(module, name)
            pred._dispatch_fn = None
            pred._get_dispatch()
    finally:
        _predicate_mod.functiondef_to_function = original

    header = f"# module: {module_name}  predicates: {', '.join(pred_names)}\n"
    return _stabilise(header + "\n\n# ----\n\n".join(captured) + "\n")
