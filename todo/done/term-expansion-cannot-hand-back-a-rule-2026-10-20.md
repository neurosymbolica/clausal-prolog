# A term_expansion/4 rule cannot hand back a rule clause

**Status: FIXED 2026-10-20 (commit 2e3fa10a).** A built `(H :- B)` / seam `(H <- B)` is lowered to the rule it denotes (`term_expansion._AnswerLowering`), a head pattern matches facts only, a whole-clause pattern matches a rule (`_clause_view`, `Predicate.__unify__`), and an imported name in seam data builds its cell (`terms_to_ast._resolve_functor_binding`). Built rules' regex groups still bind nothing (the decision asked for below: kept as documented). Pinned in tests/test_term_expansion.py::TestRuleClausesHandedBack. Reworked in 71668e0a: a built `.clausal`/`.pl` clause is lowered by the front end's own `iso_l3.lower_clause` under the file's directives (no second lowering), held to the written clause by tests/test_term_expansion.py::TestWrittenAndBuiltClausesAgree.

Found 2026-10-20, while checking whether regex named-group auto-binding can
carry a clause's variable names through term expansion. Not fixed there: the
only expanded clauses with a body that reach goal expansion today are the
ones handed back unchanged, which keep their names already.

## What / Repro

1. **`.clausal`: a built `(H :- B)` becomes a `(:-)/2` fact.**

   ```prolog
   term_expansion(pd(D, Y, M), (pd2(D, Y, M) :- helper(D)), S, S).
   pd(_, _, _).
   ```

   The answer is a head term on the head-pattern retry, so
   `_validated_expansion` wraps the cell `(':-', pd2(..), helper(..))` into a
   FACT. `pd2/3` is undefined; a `(:-)/2` fact exists instead. No warning.

2. **Seam: a built `(H <- B)` does not compile.**

   ```seam
   term_expansion(pd(D, Y, M), (pd2(D, Y, M) <- helper(D)), S, S) <- True
   ```

   fails at load with `NotImplementedError: terms_to_goalop: goal shape not
   yet supported (tuple): ('helper', ...)`: the body arrives as a data cell,
   not a goal. With an imported predicate in the body
   (`-import_from(regex, [match])`, body `match(...)`) it fails earlier, in
   the expansion module, with `TypeError: 'ModulePredicate' object is not
   callable`.

3. **A head pattern drops a rule's body.**

   ```prolog
   term_expansion(pd(D, Y, M), [pd(D, Y, M)], S, S).
   pd(D, Y, M) :- D = x, Y = 1, M = 2.
   ```

   The pattern matches the rule's HEAD, the answer is wrapped as a fact, and
   `pd(A, B, C)` now succeeds with all three unbound: the body is gone.

4. **A whole-item rule pattern never matches**: `term_expansion((H :- B),
   ..., S, S)` (or `C = (H :- B)` in the rule body) matches no clause,
   because the clause node has no `__unify__` and falls back to `==`. See
   also todo/done/term-expansion-whole-item-pattern-head-representation-2026-09-19.md.

## Consequence for regex auto-binding

docs/regex.md (Term Expansion) says a clause a rule builds carries no
variable names. That stays true once 1-4 are fixed: the rule's variables
are renamed for each expansion and nothing maps them back to the names the
rule's text spells. If built rules become possible, decide whether their
regex groups should bind (it would need the rule's own clause-scope names
threaded through the solve).
