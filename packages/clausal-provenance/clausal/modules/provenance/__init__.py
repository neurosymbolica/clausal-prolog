"""clausal.modules.provenance — provenance-tagged bottom-up Datalog.

Public surface (Python-side and `.clausal`-side):

  - ``solve(semiring, facts, goal)`` — Python-side direct call to the engine.
  - ``provenance.solve/4`` — `.clausal`-side builtin, same shape as the
    Python helper.
  - ``bottom_up_(P)`` — register a predicate for bottom-up evaluation.
  - ``pure_(P)`` — declare a predicate as pure for use from -bottom_up bodies.
  - ``boolean`` — boolean semiring (B, ∨, ∧, ⊥, ⊤).

Phase P-1 ships only the boolean semiring. Probabilistic and
differentiable semirings (``add_mult_prob``, ``diff_add_mult_prob``,
``top_k_proofs``, …) land in P-2 and later.

See :mod:`clausal.modules.provenance.engine` for the engine and
:mod:`clausal.modules.provenance.protocol` for the semiring protocol.
"""

from __future__ import annotations

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
