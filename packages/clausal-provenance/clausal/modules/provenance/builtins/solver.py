"""provenance.solve/4 and provenance.recover/3.

These wrap the engine in ``engine.py`` as ordinary Clausal predicates so
they can be called from `.clausal` source. The shape is::

    solve(+Semiring, +Facts, +Goal, -Result)

where ``Facts`` is a list of ``(GroundTerm, Tag)`` pairs and ``Result``
unifies with a list of ``(GroundTerm, Tag)`` pairs covering every ground
answer matching ``Goal`` under the chosen semiring.

The semiring argument is a Python value (e.g., ``boolean``,
``add_mult_prob``); selectable per-call.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import deref, unify
from clausal.logic.database import Module
from clausal.modules.py import ModulePredicate, simple_to_trampoline
from clausal.modules.provenance.engine import evaluate
from clausal.modules.provenance.protocol import (
    Provenance,
    AggregateProvenance,
)


def _find_calling_module() -> "Module | None":
    """Walk the Python frame stack for a ``Module`` (logic-module) instance.

    Used when ``provenance.solve/4`` is called from `.clausal` source: the
    test runner / repl / ``call(...)`` API holds a Module reference in
    its frame locals, which is otherwise lost because ``load_clausal_module``
    pops the test module from ``sys.modules`` before the test body runs.
    """
    import sys
    frame = sys._getframe(1)
    while frame is not None:
        for ns in (frame.f_locals, frame.f_globals):
            for v in ns.values():
                if isinstance(v, Module):
                    return v
        frame = frame.f_back
    return None


# ── solve/4 ──────────────────────────────────────────────────────────────


def _solve_4(semiring, facts, goal, result, trail, k):
    """provenance.solve/4 — bottom-up evaluation under a semiring.

    Modes: (+, +, +, -)
    """
    semiring = deref(semiring)
    facts = deref(facts)
    goal = deref(goal)

    if not isinstance(semiring, Provenance):
        raise TypeError(
            f"provenance.solve/4: first arg must be a Provenance instance, "
            f"got {semiring!r}"
        )
    if not isinstance(facts, list):
        raise TypeError(
            f"provenance.solve/4: facts must be a list of (term, tag) pairs, "
            f"got {facts!r}"
        )

    fact_pairs: list[tuple[Any, Any]] = []
    for f in facts:
        f = deref(f)
        # Accept tuple or list of length 2
        if isinstance(f, (list, tuple)) and len(f) == 2:
            term = deref(f[0])
            tag = deref(f[1])
            fact_pairs.append((term, tag))
        else:
            raise TypeError(
                f"provenance.solve/4: each fact must be a (term, tag) pair, "
                f"got {f!r}"
            )

    # Try to recover the calling .clausal module so the engine can resolve
    # rule-body callees during evaluation. ``_infer_module`` would normally
    # do this via ``sys.modules``, but ``load_clausal_module`` removes the
    # test module from there before the test body runs.
    module = _find_calling_module()
    answers = evaluate(semiring, fact_pairs, goal, module=module)

    # Build the result list; each entry is a 2-element tuple (term, tag).
    out_list = [(term, tag) for term, tag in answers]
    if unify(result, out_list, trail):
        yield None


# ── recover/3 ────────────────────────────────────────────────────────────


def _recover_3(semiring, internal_tag, output_tag, trail, k):
    """provenance.recover/3 — apply ``semiring.recover_fn``."""
    semiring = deref(semiring)
    internal_tag = deref(internal_tag)
    if not isinstance(semiring, Provenance):
        raise TypeError(
            f"provenance.recover/3: first arg must be a Provenance instance, "
            f"got {semiring!r}"
        )
    out = semiring.recover_fn(internal_tag)
    if unify(output_tag, out, trail):
        yield None


# ── aggregate/4 ──────────────────────────────────────────────────────────


_AGGREGATE_OPS = {"count", "sum", "argmax"}


def _aggregate_4(semiring, op, tagged_list, result, trail, k):
    """provenance.aggregate/4 — semiring-aware aggregation.

    Modes:
        aggregate(+Semiring, +Op, +Tags, -Result)         when Op ∈ {count}
        aggregate(+Semiring, +Op, +ValueTagPairs, -Result) when Op ∈ {sum, argmax}

    For ``count``: ``Tags`` is a flat list ``[t1, t2, …]``; result is the
    aggregate count tag.
    For ``sum`` / ``argmax``: ``ValueTagPairs`` is a list of ``(value,
    tag)`` pairs; result is the aggregated value (or ``(value, tag)``
    pair for argmax).
    """
    semiring = deref(semiring)
    op = deref(op)
    tagged_list = deref(tagged_list)

    if not isinstance(semiring, AggregateProvenance):
        raise TypeError(
            f"provenance.aggregate/4: semiring {semiring!r} does not "
            "implement AggregateProvenance (no count/sum/argmax)."
        )
    if not isinstance(op, str) or op not in _AGGREGATE_OPS:
        raise ValueError(
            f"provenance.aggregate/4: op must be one of "
            f"{sorted(_AGGREGATE_OPS)}, got {op!r}"
        )
    if not isinstance(tagged_list, list):
        raise TypeError(
            f"provenance.aggregate/4: 3rd arg must be a list, got {tagged_list!r}"
        )

    if op == "count":
        tags = [deref(t) for t in tagged_list]
        out = semiring.aggregate_count(tags)
    else:
        pairs = []
        for entry in tagged_list:
            entry = deref(entry)
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise TypeError(
                    f"provenance.aggregate/4: each entry must be a "
                    f"(value, tag) pair for op={op!r}, got {entry!r}"
                )
            pairs.append((deref(entry[0]), deref(entry[1])))
        if op == "sum":
            out = semiring.aggregate_sum(pairs)
        else:  # argmax
            out = semiring.aggregate_argmax(pairs)

    if unify(result, out, trail):
        yield None


# ── Predicate objects ───────────────────────────────────────────────────

solve = ModulePredicate("solve")
solve._register(4, simple_to_trampoline(_solve_4))

recover = ModulePredicate("recover")
recover._register(3, simple_to_trampoline(_recover_3))

aggregate = ModulePredicate("aggregate")
aggregate._register(4, simple_to_trampoline(_aggregate_4))


__all__ = ["solve", "recover", "aggregate"]
