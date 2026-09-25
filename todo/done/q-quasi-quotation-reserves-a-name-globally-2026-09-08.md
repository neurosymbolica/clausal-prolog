# `q()` quasi-quotation reserves `q/1` globally, in term position

Noticed 2026-09-08 while writing WFS pins: two probe programs used `q/1` as an
ordinary throwaway predicate and failed with a `BareGoalVariableError` that
named the wrong cause. Design question, parked rather than acted on.

## What is actually true (measured, not inferred)

`TermTransformer.visit_Call` (`clausal/templating/term_rewriting.py`, the
`q(expr)` branch) strips `q(<exactly one positional arg>)` to that argument,
UNCONDITIONALLY — no module flag, no check that we are inside a term-expansion
rule. So `q(X)` becomes bare `X` wherever that transformer runs.

Measured boundary:

| shape | result |
|---|---|
| `q(red),` fact | works |
| `q(X) <- r(X)` rule | works |
| `q(X)` as a plain body conjunct | works |
| `q(X)` inside `not (...)` | **`BareGoalVariableError`** |
| `--q(X)` at the seam | **`BareGoalVariableError`** |
| `q/2` (any arity but 1) | unaffected — the branch requires one arg |

So the name is not broadly poisoned: it breaks only in term-position /
reifying contexts. The diagnostic is the problem — nothing in
"a bare variable appears in goal position in predicate q/1" points at
quasi-quotation, and `q` is a very common throwaway predicate name (it appears
in ~10 test files, and `docs/style.md` + `docs/importing_prolog.md` both use
`q/1` as their generic example predicate — those examples do work).

## How much the feature is actually used

Documented in `docs/term_expansion.md` §"q() Quasi-Quotation" and listed as
done in `docs/architecture.md`. Real usage in the whole tree: 8 occurrences in
`tests/test_term_expansion.py` and one line in
`tests/fixtures/expansion_nested_var.clausal`. Nothing in the stdlib or the
corpus.

## The question for the operator

A live, documented, thinly-used feature reserves a single-letter identifier in
every module, and misuse surfaces as an unrelated error. Options, cheapest
first:

1. Leave it; add the quasi-quotation case to the `BareGoalVariableError`
   message when the offending call was `q/1` ("`q(X)` is quasi-quotation here;
   rename the predicate or use `q/2`"). Costs nothing, fixes the confusion.
2. Gate the stripping on being inside a `TermExpansion/4` rule, so `q/1` is an
   ordinary predicate everywhere else. Behaviour change, needs a pin per
   context.
3. Rename the quasi-quote to something unlikely to collide. Breaking, and the
   ISO-alignment work has opinions about reserved spellings.

(1) looks right on its own merits; (2) is what a reader would expect the
feature to already do.

## Related

- `clausal/templating/term_rewriting.py` (`visit_Call`, the `q` branch)
- `clausal/logic/compiler/terms_to_goalop.py` (raises the misleading error)
- `docs/term_expansion.md`, `docs/architecture.md`

## Resolved 2026-09-25: q() RETIRED (operator ruling)

Neither (1) nor (2): the special case in `TermTransformer.visit_Call` is
deleted and `q` is an ordinary name. Premise measured before removal: every
in-repo q() use (the doc quick/suppression/double_fact examples, the
`expansion_nested_var` fixture, q() in a TE body under `is`, in a list, around
a rule pattern -- 7 programs) lowers to a byte-identical module (positions
normalised) and gives identical answers when written without q(). No site
needed it. What it did do: strip a user's `q/1` -- `call(q(X))` was
`call(X)` (instantiation error), and `not q(X)`, `findall(X, q(X), L)`, a
body goal `q(X)` were each a `BareGoalVariableError`; all answer now.

Two tests (`test_tagged_terms` / `test_implicit_functors`, "a predicate
reference is not a cell") were green ONLY because of the strip: their
`"('q'," not in src` fails for every other name since the P2 head flip. They
now pin that `call(q(X))` answers.

An old `q(...)` in a `term_expansion/4` clause now builds `('q', ...)` cells
that match nothing, so it warns at load (`ClausalRetiredQuasiQuoteWarning`,
once per clause, only in a subtree containing `term_expansion(_,_,_,_)`).
