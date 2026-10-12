# User term_expansion/2 and goal_expansion/2 (ISO, then Scryer)

**Requested:** operator, 2026-10-12. Prompted by a question from the Scryer side: does Clausal
have and use term and goal expansion?

## Where it stands (canonical 58f40438)

- **Built-in compile-time expansions exist, but users can't extend them.** Two examples:
  - DCG translation: `translate_dcg_rule` (`clausal/tools/iso_l3.py:1122`) for `-->`, and
    `_rewrite_dcg_body` (`clausal/templating/term_rewriting.py:5201`) for seam `>>`.
  - The `constant(Name)` fold (`iso_l3.py:322`).
- **`.clausal` (Clausal Prolog) has no user hook.** A `term_expansion/2` there is an ordinary
  predicate. This was chosen deliberately so that "no expansion can smuggle in another dialect"
  (`tests/test_dialect_gate_routes.py:484`, `test_route7e_...`).
- **Seam files have `term_expansion/4`** (Term, Expansion, StateBefore, StateAfter;
  `clausal/logic/term_expansion.py:156`).
  - It runs after the built-in rewrites, so it sees a DCG rule already translated:
    `greeting >> (['hello','world'])` reaches the hook as `greeting(S0, S) <- ...`.
  - SWI and Scryer run the hook on the `-->` term first.
- **`goal_expansion` is built-in only** (`clausal/logic/goal_expansion.py:89`: regex
  pre-compilation, and clause-pattern sugar for the reflection builtins). Neither front end
  has a user `goal_expansion/2`.

## Wanted

1. **`.clausal`: `term_expansion/2` and `goal_expansion/2` with Scryer's semantics.** Scryer is
   the reference here because ISO does not standardise either hook.
   - Which module the hook lives in, and how `user:` vs a module-local hook resolve.
   - A list result expands to several clauses.
   - The hook runs on each read term BEFORE DCG translation.
   - `goal_expansion` repeats to a fixpoint over body goals, including inside control
     constructs and meta-predicate arguments.
   - What happens when the hook fails or raises.
2. **Reconcile with the dialect gate.** route7e exists to stop an expansion bringing in another
   dialect. Decide what a user expansion may emit (only terms the native lowering accepts?) and
   what the gate checks after expansion. Do not just delete route7e.
3. **Order relative to the built-in expansions:** user `term_expansion`, then DCG translation,
   then the `constant/1` fold and the lowering. Pin each with a test against Scryer's answers.
4. **The seam's `term_expansion/4`:** keep it, or align it on the same order (the hook sees the
   grammar rule before translation). This changes behaviour for existing seam users, so it needs
   a ruling.
5. **Tests:** a `.pl` corpus of Scryer `term_expansion`/`goal_expansion` examples, run through
   both engines.

## Related

- todo/term-expansion-compile-time-predicate-synthesis.md
- todo/term-expansion-whole-item-pattern-head-representation-2026-09-19.md
