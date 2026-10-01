"""The transition constructs' keys (operator ruling D13, 2026-09-30).

``\\+`` (the seam's ``not``), once/1, forall/2, memberchk/2, the
``findall(_, G, [])`` negation backdoor and make_quantity/3 are accepted
and COUNTED, allowed where they are, no new ones.  One key each, in this
order, in ``l3_stats["transition_constructs"]`` of BOTH front ends (the
native ``.pl`` loader, ``clausal.tools.iso_l3_directives.Uses``; the seam
loader, ``clausal.logic.compiler.terms_to_goalop``), so one consumer reads
both; ``clausal.tools.transition_census`` ratchets them.  ``if_/3`` is NOT
one: it is library(reif)'s pure conditional, the replacement target.

No imports on purpose: both front ends and the tools import this leaf.
"""

TRANSITION_KEYS: tuple[str, ...] = (
    "\\+/1", "once/1", "forall/2", "memberchk/2", "findall/3_empty",
    "make_quantity/3")
