# Construction padding audit (W4b-3 follow-up A, 2026-09-25)

Operator ruling 2026-09-25: NO implicit arity padding anywhere; a default
argument is an explicit predicate.  `BuiltinTerm.__call__` now builds the
WRITTEN-arity cell at any count no registered arity has (`between(1, 2)` ->
`('between', 1, 2)`, an existence_error as a goal; `between()` -> `'between'`)
and refuses keywords at such a count.  `build_term_cell` now refuses a slot
given both positionally and by name (it used to overwrite the keyword's value
silently).  The other construction paths were audited by probe
(`scratchpad/w4b3/pad_probe.py`, run on the A+B tree):

## Still padding -- needs a ruling

1. **Keyword-only partial construction in `build_term_cell`** fills every
   slot no keyword names with a fresh `Var`.  Reached by a predicate HANDLE's
   head from Python (`head_cell(m.q, a=1)` -> `('q', 1, _)` for `q/2`) and by
   any remaining `PredicateMeta` class call (`make_predicate` classes).
   `construction_arity_fault` allows it on purpose (ruling C / operator Q1
   2026-09-24: "keyword-only construction names the slots it fills").  The
   compile-time twin is `terms_to_ast._place_signature_slots`' `missing()`.
   Question: does "no padding anywhere" retire keyword-only partial
   construction too (refuse unless every field is named)?  BuiltinTerm
   already refuses it.

## Not padding, but found by the audit

2. **`--q(1)` for a predicate `q/2` (term position, seam) evaluates to `1`**
   -- the functor is dropped and the ARGUMENT is returned; the rewriter emits
   `$seam(1, globals())`.  Silently wrong.  `--r(1)` for `r/1`, `--between(1)`
   and `--foo(1)` (undeclared, `-implicit_functors`) build the written cell
   correctly.  Reproduce: a module `-module(m, [q(a, b)])`, `q(1, 2),`, and
   `def t(): return --q(1)`.
3. **`--q(1, 2, 3)` for a predicate `q/2` refuses (too many)** rather than
   building the written-arity cell, although ruling 4C builds predicate names
   at the written arity (the too-few side); the Python-side `head_cell(m.q, 1)`
   and `head_cell(m.q, 1, 2, 3)` refuse both ways.  Consistent with ruling C
   for heads; flagged only because the seam's term position is not a head.

## Checked, no padding

- Data functors (`-module(m, [point(x, y)])`): `--point(1)` and a clause-body
  `point(1)` refuse too few; `--point(1, 2, 3)` refuses too many.
- The seam at an undeclared or builtin name builds the written arity:
  `--between(1, 2)` -> `('between', 1, 2)`, `--between(1, 2, 3, 4)` -> the
  4-cell.
- A goal `between(1, 2)` in a clause body is `PredicateNotFoundError`
  (existence_error), never between/3.

## Rulings (operator, 2026-09-25, "let's not auto-correct arity") and what landed

1. Keyword-only partial construction is REFUSED (item 1 above) in
   `build_term_cell` and `_place_signature_slots`; so is a no-argument
   construction against a fielded signature.  The rewriter relied on the old
   padding in ONE place: an `-edcg_pred` plain clause written at its visible
   arity (`r(1),` for `r/1` with an accumulator) was emitted as
   `$head(r, arg_0=1)` and padded to r/3.  It now spells the hidden
   `_edcg_*` slots as `$Var()` explicitly (same clause as before).
   OPEN (EDCG): such a fact threads each accumulator as two INDEPENDENT free
   variables (`r(1, _, _)`), so `r(1, 0, 5)` succeeds; Van Roy's EDCG would
   make it `r(1, S, S)` (unchanged).  Not changed here.
2. `--q(1)` evaluating to `1`: NOT a construction bug.  `q(expr)` with one
   argument is QUASI-QUOTATION (`TermTransformer.visit_Call`: "q(expr) --
   produces the simple_ast node for expr"), whatever `q` is declared as; the
   audit's example happened to use the name `q`.  `--pq(1)` for a declared
   `pq/2` builds `('pq', 1)`.  The ruling "--q(1) must build ('q', 1)" would
   make a declared `q` shadow quasi-quotation -- a design change, returned to
   the operator rather than implemented.
3. Done: a predicate name written LONGER than its known arity in the seam's
   term position (and via `construction_signature_for_name`) is the compound
   at the written arity: `--pq(1, 2, 3)` -> `('pq', 1, 2, 3)`.
