# TODO: the SMT prover's front end — decided seam, and what NOT to do

**Opened 2026-07-29**, out of the `P.key` dot-attribute-access work.

## The recurring question

The prover, maintained by a downstream consumer, has its **own** front end:
`ir.py:354` does `ast.parse(text)` and builds `ProgramIR`/`ClauseIR`/`BodyGoal`;
`translate.py` then walks the raw `ast` nodes. The engine has its own, entirely
separate pipeline. So every new surface syntax has to be taught twice.

The obvious fix — "have the prover consume the engine's rewritten tree" — comes
up every time. **It has been considered and deliberately rejected.** Record of
why, so it isn't relitigated from scratch.

## The engine's rewritten term tree DOES exist

This was initially and wrongly reported as absent. It exists:

```
.clausal → ast.parse → clausal/templating/term_rewriting.py
        → clausal/pythonic_ast/  (typed node tree; transform framework in transform.py)
        → Clause(head, body=[goal terms], position)   ← clausal/logic/database.py:23
        → clausal/logic/compiler/ → Python generator
```

At the `Clause` level the sugar is already gone. For
`both(A, B) <- (mk(P), A is P.k, B is P[k])`:

```
Unify(left=AttVar(_2), right=LoadSubscript(object=AttVar(_4), index=k))
Unify(left=AttVar(_3), right=AttVar(_2))
```

`P.k` is a `LoadSubscript`; the read-once hoist has collapsed both reads to one
implicit variable. A consumer of this tree gets `P.k` — and every prior sugar —
for free. Building it is **zero work; it is already there.**

## Why the prover does not consume it

1. **It would destroy the prover's independence.** The prover deliberately
   re-implements engine behaviour (`_arrow_adjacent` at ir.py:184-198 reads
   source bytes; the trailing-comma fact detection at ir.py:294-348; comments
   marked "engine-confirmed") so that it is a genuine *second opinion*. If it
   consumed the engine's own output, an engine bug would become invisible to it
   — agreement would be guaranteed rather than evidence. That is the one thing
   the prover exists to catch.
2. **The tree only exists after executing the module.** `$define_predicate` is
   a call the *transformed source* makes, so `Clause` objects are populated at
   module-exec time. The prover today never executes what it verifies; it only
   parses text.
3. **Migration cost.** At that level variables are `AttVar` objects with
   generated names (`_2`, `_4`), while the prover keys off *spellings*
   (`ALLCAPS` / `_prefix`) for its left-to-right mode tracking. Identity-based
   is better, but it is a real rewrite of `translate.py` (828 lines).

## What was done instead

A **narrow, purely syntactic** shared desugar pass: the engine exposes an
`ast → ast` sugar normalisation (`P.key` → `P[key]`), and the prover calls it
straight after `ast.parse`. Semantic modelling stays independent and
unshared. Constraints held:

- no engine state, no module loading, no side effects;
- line/col positions preserved (`ClauseIR.line` drives counterexamples);
- the read-once hoist stays engine-only — the prover wants the inline
  `P[key]` form it already models via `axioms.subscript_read`;
- the engine is refactored to *use* the extracted function, so there is
  exactly one implementation and no drift one level down.

## Useful property to preserve

`V is P.key` currently **fails safe**: it classifies as `bind_is` (ir.py:73-103),
its `ast.Attribute` RHS misses both the `ast.Subscript` projection guard and the
`BinOp`/`UnaryOp` arithmetic guard, and it reaches `_expr`, whose last line is
`raise Unsupported(...)`. So unmodelled syntax loses proofs rather than
producing false ones. **Any future front-end change must preserve this.**

## Open idea, not started

Keep the prover independent, and use the engine's term tree to build a
**differential front-end checker**: load a domain both ways and assert the
prover's IR and the engine's `Clause` list agree on clause count, arity and goal
shape. That catches front-end drift — the actual risk — *without* the prover
inheriting engine semantics. This is the option worth building if drift bites
again.
