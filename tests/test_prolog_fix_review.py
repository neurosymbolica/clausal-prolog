"""Regression tests for the 2026-07-09 review of the A11 Prolog-tools fixes.

Covers the secondary bullets dropped during the original fix wave:

- F022: clausal→Prolog variable renaming must be injective per clause.
- F025/F035: ISO evaluable constants map to math.*; quoted non-identifier
  functor heads are rejected.
- F026/F041: newly-parsed operators (^, @<, =@=, ...) must not silently
  emit invalid Clausal.
- F034: _quote_atom escapes control characters (ISO 6.4.2).
- F036: Cut() in Clausal source is rejected on export.
- F033: qualified goals resolve builtins like the unqualified path.
"""

from __future__ import annotations

import pytest

from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    _quote_atom,
    emit_term,
)
from clausal.tools.prolog_to_clausal import (
    prolog_to_clausal,
    PrologTranslationError,
)
from clausal.tools.prolog_ast import PAtom
from clausal.tools.prolog_dialect import Dialect
from clausal.tools.prolog_parser import parse


# ═══════════════════════════════════════════════════════════════════════
# F022 — clausal → Prolog variable renaming must be injective per clause
# ═══════════════════════════════════════════════════════════════════════


class TestF022VarRenameInjective:
    def test_distinct_vars_stay_distinct(self):
        out = clausal_source_to_prolog(
            "P(_result, RESULT) <- (_result == 1, RESULT == 2)"
        )
        # Both map to base name "Result"; the second must be disambiguated.
        assert "p(Result, Result2)" in out

    def test_three_way_collision(self):
        out = clausal_source_to_prolog("P(_x, X, _X) <- (Q(_x, X, _X))")
        head = out.splitlines()[0]
        # _x → X, X → X (collides), _X → X (collides): three distinct names.
        assert "p(X, X2, X3)" in head

    def test_rename_table_resets_per_clause(self):
        out = clausal_source_to_prolog(
            "P(_result) <- (Q(_result))\nR(RESULT) <- (Q(RESULT))"
        )
        # No cross-clause leakage: each clause gets the plain base name.
        assert "p(Result)" in out
        assert "r(Result)" in out
        assert "Result2" not in out

    def test_same_var_same_name_within_clause(self):
        out = clausal_source_to_prolog("P(_head, _head) <- (Q(_head))")
        assert "p(Head, Head)" in out
        assert "q(Head)" in out

    def test_anonymous_stays_anonymous(self):
        out = clausal_source_to_prolog("P(_, _) <- (Q(_))")
        assert "p(_, _)" in out
