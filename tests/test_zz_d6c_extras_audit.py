"""Slice D6c post-audit: assert IR-extra bucket-ref entries are absent.

The D6c cross-check (``_maybe_cross_check_bucket_refs`` in
``goal_trampoline``) tolerates an "IR ⊇ legacy" relationship on
non-flat bodies — ``terms_to_goalop`` flattens top-level ``And`` /
nested-list conjunctions, surfacing :class:`SubCall` ops the legacy
walker silently skips.  That's a latent missed-optimisation in legacy
that the IR path naturally fixes.

The tolerance is intentional, but if any IR-extra entries do appear,
D7 (which promotes the IR walk to primary) will start emitting bucket
refs that legacy never did.  We want to know about that **before**
the flip, not after.

Each ``_inject_bucket_refs_trampoline`` call records IR-extras on a
process-wide counter (``_IR_EXTRA_BUCKET_REFS``).  This file's name
sorts to the end of pytest's collection order so the audit runs after
every other test in the suite has compiled its predicates, giving the
cross-check the widest possible exposure to real bodies.

D7a flipped ``CompilationContext.use_ir_path`` default to ``True``,
so the cross-check now runs on every compile by default — the audit
no longer needs an env-var gate.  An empty counter at end of session
is the affirmative signal that no D6c-tolerated divergence occurred.
"""

from __future__ import annotations

import pytest


def test_no_ir_extra_bucket_refs_seen():
    from clausal.logic.compiler.goal_trampoline import _IR_EXTRA_BUCKET_REFS

    if _IR_EXTRA_BUCKET_REFS:
        # Format the first few extras for diagnostic clarity — the
        # full list can be very long if a regression slips in.
        sample = _IR_EXTRA_BUCKET_REFS[:5]
        pytest.fail(
            f"{len(_IR_EXTRA_BUCKET_REFS)} call(s) to "
            "_inject_bucket_refs_trampoline produced IR-extra entries "
            "(IR walker found bucket refs legacy missed). "
            "Investigate before D7 promotes the IR walk to primary; "
            "the extras would become live bucket-ref dispatches.\n"
            f"  sample (first {len(sample)}): {sample}"
        )
