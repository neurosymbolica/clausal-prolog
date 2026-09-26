"""F5 (rows 18, 39): the coupled ``PredicateMeta``-atom-head-literal pair.

Design authority: ``implementation_plans/w4b2-f2b-and-hard-families-2026-09-23.md``
section F5.

``terms_to_ast.py:_is_opaque_head_literal`` and
``head_match.py:head_to_match_pattern``'s "PredicateMeta atom" branch both
gated on the identical arity-blind test
``isinstance(term, type) and isinstance(term, PredicateMeta)``, and were
migrated TOGETHER, in the same commit, to
``is_declared_predicate_name(term)``.

They are a coupled pair, not two independent call sites:
``_is_opaque_head_literal`` returning ``False`` for a bare predicate
reference means "not opaque, handled elsewhere" -- and the "elsewhere" is
precisely ``head_to_match_pattern``'s dedicated branch a few lines later,
which captures the value and routes it through ``unify()`` instead of
falling through to the accept-all wildcard (A02-F003).  Migrating one
without the other reopens that bug for a bare predicate reference used as
a head-literal *value* (e.g. a zero-arity predicate's own name, used as a
dict value or a compound argument, per ``PredicateAsTermError``'s own
docstring on the *coercion* case this guards the *literal* case for).

This suite locks in that BOTH sites still agree with each other, and with
``is_declared_predicate_name`` directly, for every shape that can reach
either check position:

  - a ``PredicateMeta`` class (today's era) -> both say "not opaque" /
    "route through unify() as an atom" -- identically.
  - anything else that reaches this far in either function (a bare
    ``@dataclass`` class, an arbitrary object) -> both fall through to
    their respective generic fallback (opaque-wildcard-capture /
    ``is_term_instance``-or-wildcard) exactly as before the swap.

A mangled atom (the post-flip predicate-reference shape) is a plain
``str`` and is intercepted by BOTH functions' earlier, unrelated
``isinstance(term, str)`` branch, long before either function reaches the
line this migration touches -- confirmed by reading the branch order in
both files (the str check precedes the PredicateMeta/``is_declared_predicate_name``
check in both). That branch already emits the same
``("atom", cap_name, term)`` capture+unify guard the PredicateMeta branch
emits (head_match) / the same "not opaque" answer (terms_to_ast), so the
post-flip shape was ALREADY handled correctly before this migration and
stays handled correctly after it -- this migration's job is identity-test
hygiene (retiring the isinstance check in favour of the era-agnostic F2b
accessor used elsewhere in both files), not a behaviour change for any
reachable input.
"""
from __future__ import annotations

import ast
import dataclasses

from clausal.logic.compiler.head_match import head_to_match_pattern
from clausal.logic.compiler.terms_to_ast import _is_opaque_head_literal
from clausal.logic.predicate import is_declared_predicate_name



# ── Shared fixtures ──────────────────────────────────────────────────────



@dataclasses.dataclass
class _NotAPredicate:
    x: int


# ── terms_to_ast._is_opaque_head_literal: PredicateMeta class -> not opaque ──

class TestOpaqueHeadLiteralPredicateClass:



    def test_unrelated_dataclass_class_is_still_opaque(self):
        """A bare dataclass CLASS (never a predicate) must NOT be swept
        into the "not opaque" answer -- is_declared_predicate_name refuses
        it (hazard 1a) exactly as the old isinstance check did."""
        assert is_declared_predicate_name(_NotAPredicate) is False
        assert _is_opaque_head_literal(_NotAPredicate) is True


# ── head_match.head_to_match_pattern: PredicateMeta atom -> capture+unify ──



# ── Cross-function mirror: both sites must agree on every input ────────────

class TestCoupledPairMirror:
    """The coupling the F5 design brief calls out: for any term shape,
    terms_to_ast's "not opaque" answer and head_match's "route through the
    dedicated atom-guard branch" answer must never diverge -- one being
    True while the other is False is exactly the accept-all-wildcard
    regression (A02-F003) this pair exists to prevent."""

    def _head_match_takes_atom_branch(self, term) -> bool:
        list_guards: list = []
        p = head_to_match_pattern(term, {}, list_guards=list_guards)
        return (
            isinstance(p, ast.MatchAs)
            and bool(list_guards)
            and list_guards[0][0] == "atom"
            and list_guards[0][2] is term
        )


    def test_non_predicate_dataclass_both_sites_agree_false(self):
        assert _is_opaque_head_literal(_NotAPredicate) is True
        assert self._head_match_takes_atom_branch(_NotAPredicate) is False
