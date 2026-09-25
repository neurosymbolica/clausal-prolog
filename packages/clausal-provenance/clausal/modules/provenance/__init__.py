"""clausal.modules.provenance — provenance-tagged bottom-up Datalog.

Public surface (Python-side and `.clausal`-side):

  - ``solve(semiring, facts, goal)`` — Python-side direct call to the engine.
  - ``query(goal, facts=, semiring=)`` — Python-side `clausal.query`-shaped
    wrapper used by neurosymbolic training loops.
  - ``provenance.solve/4`` — `.clausal`-side builtin, same shape as the
    Python helper. ``provenance.aggregate/4`` and ``recover/3`` ride
    alongside.
  - ``bottom_up_(P)`` — register a predicate for bottom-up evaluation.
  - ``pure_(P)`` — declare a predicate as pure for use from -bottom_up bodies.

Semirings shipped:

  - ``boolean`` — plain Datalog set semantics.
  - ``add_mult_prob`` — independence-assumption probability ([0, 1]).
  - ``diff_add_mult_prob`` — same algebra on PyTorch / JAX tensors.
  - ``top_k_proofs(k)`` — DNF lineage truncated to the k highest-prob proofs.
  - ``diff_top_k_proofs(k)`` — differentiable variant; autograd through I-E.

See :mod:`clausal.modules.provenance.engine` for the engine and
:mod:`clausal.modules.provenance.protocol` for the semiring protocol.
"""


from __future__ import annotations

# DISABLED 2026-09-25 (operator): the engine's PredicateMeta retirement removed
# the class-based predicate registration this package is built on, and a
# class-based design cannot map to ISO Prolog.  It needs a redesign (probably
# as a meta-interpreter).  Importing it fails loudly rather than half-working.
raise ImportError(
    "clausal-provenance is disabled pending a redesign: its class-based "
    "predicate registration does not survive the PredicateMeta retirement "
    "and cannot map to ISO Prolog (see the package README).")

# ── Engine ───────────────────────────────────────────────────────────────
from clausal.modules.provenance.engine import (
    evaluate,
    Relation,
    PurityError,
    NonGroundTupleError,
)
from clausal.modules.provenance.stratify import StratificationError
from clausal.modules.provenance.protocol import (
    Provenance,
    AggregateProvenance,
)

# ── Semirings ────────────────────────────────────────────────────────────
from clausal.modules.provenance.semirings.boolean import Boolean, boolean
from clausal.modules.provenance.semirings.add_mult_prob import (
    AddMultProb,
    add_mult_prob,
)
from clausal.modules.provenance.semirings.diff_add_mult_prob import (
    DiffAddMultProb,
    diff_add_mult_prob,
)
from clausal.modules.provenance.semirings.top_k_proofs import (
    TopKProofs,
    top_k_proofs,
)
from clausal.modules.provenance.semirings.diff_top_k_proofs import (
    DiffTopKProofs,
    diff_top_k_proofs,
)

# ── Registration goals (`.clausal`-side) ────────────────────────────────
from clausal.modules.provenance._registration import (
    bottom_up_,
    pure_,
    is_bottom_up,
    is_pure,
)

# ── Builtins (`.clausal`-side) ───────────────────────────────────────────
from clausal.modules.provenance.builtins.solver import solve, recover, aggregate


# ── Python-side convenience wrapper ─────────────────────────────────────


def query(goal, *, facts, semiring, module=None):
    """Run the bottom-up engine; return ``[(ground_term, tag), ...]``.

    Parameters
    ----------
    goal
        Goal term whose head predicate is registered ``-bottom_up``.
    facts
        Iterable of ``(ground_term, user_tag)``.
    semiring
        A ``Provenance`` instance (e.g. ``boolean``).
    module
        Optional ``clausal.Module`` for resolving foreign predicates.

    Returns
    -------
    list[(ground_term, output_tag)]
    """
    return evaluate(semiring, facts, goal, module=module)


__all__ = [
    # Engine
    "evaluate",
    "query",
    "Relation",
    # Semiring protocol
    "Provenance",
    "AggregateProvenance",
    # Semiring values
    "Boolean",
    "boolean",
    "AddMultProb",
    "add_mult_prob",
    "DiffAddMultProb",
    "diff_add_mult_prob",
    "TopKProofs",
    "top_k_proofs",
    "DiffTopKProofs",
    "diff_top_k_proofs",
    # Registration
    "bottom_up_",
    "pure_",
    "is_bottom_up",
    "is_pure",
    # In-source builtins
    "solve",
    "recover",
    "aggregate",
    # Errors
    "PurityError",
    "NonGroundTupleError",
    "StratificationError",
]
