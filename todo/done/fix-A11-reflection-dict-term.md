# fix(A11-F013): dict literals reify as Goal('DictTerm',…); arrow dict patterns never match

docs/reflection.md:58-60 promises "dicts appear as themselves"; the reifier
produces `Goal('DictTerm', [{'k': 5}], [])`. The arrow-pattern side compiles
the same literal to a runtime DictTerm instance, which does not unify with the
reified Goal — `reified_clause(SRC, Pt({"k": 5}) <- True)` finds nothing,
violating the matcher-parity promise (:141-144). kwargs patterns DO
interoperate; this is dict-specific.

**Fix**: reify dict literals as raw dicts (docs-conformant), and/or make the
arrow-pattern compiler and reifier agree on one representation.

**Test**: test_F013_dict_literal_pattern_matches (xfail).
