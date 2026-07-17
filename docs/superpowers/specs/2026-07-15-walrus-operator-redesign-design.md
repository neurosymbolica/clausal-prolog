# Retire `:=`, add `eval_/2`, document `is`-chains

**Date:** 2026-07-15 (revised same day; supersedes the walrus-reintroduction design)
**Status:** Approved (design)
**Source todo:** `todo/fix_walrus_operator.md`

## Problem

Clausal overloaded Python's `:=` (walrus) to mean Prolog-style arithmetic
evaluate-and-bind. The spelling misleads LLMs (they reach for `:=` when they
want `is`, `==`, or `++(...)`, and it "kind of works"), and the original plan
was to migrate arithmetic `:=` to `==` and reintroduce `:=` as inline naming.

Empirical probing during Phase 1 invalidated both halves of that plan:

1. **`==` is not a faithful replacement.** `:=` was *eager* (Python-semantics
   evaluate-and-bind via `ArithEval`); `==` posts a *deferred* CLP(ℤ)/CLP(ℝ)
   constraint. Three subsystems depend on eagerness:
   - **TRO**: `N1 == N - 1` breaks tail-call optimization — `MyNthOf` allocates
     51 StepGenerators instead of 1 (groundness dispatch can't see the deferred
     binding).
   - **Units**: CLP can't divide `Quantity` objects — `V == D / T` raises
     `OverflowError` in `clpq.py` (`Fraction(domain_min(...))` on an unbounded
     FD domain).
   - **Exceptions**: `==` division doesn't raise a catchable
     `ZeroDivisionError`; `catch`-based fixtures need eager evaluation.

   The `is ++(...)` escape is eager but **untranslatable to Prolog**
   (`N1 = ???` in golden output) and opaque to the compiler.

2. **Inline naming already exists.** Python chained comparisons give Clausal
   unification chains: `VALUE is [1, X] is D["k"]` compiles via `CompareChain`
   expansion (`terms_to_goalop.py:146`) with the shared middle operand as the
   same Var by identity — single-evaluation, top-level naming. All probes pass
   today with zero new code, including the todo's motivating case (naming a
   compound while unifying it with a dict accessor). Within-term reuse of a
   named subexpression remains unsupported (YAGNI — two goals cover it).

## Decisions

1. **Add `eval_(EXPR, RESULT)`** — a reserved goal-position builtin compiling to
   the existing `Evaluate` node → `ArithEval` IR. Eager Python-semantics
   arithmetic: preserves TRO, units, catchable exceptions. Translates to/from
   Prolog `is/2` (`eval_(E, R)` ↔ `R is E`). Output-last argument order matches
   house style (`plus/3`, `succ/2`, `abs_/2`). Follows the established
   reserved-functor pattern (`throw`, `once`, `findall` at
   `terms_to_goalop.py:294+`); the name is unclaimed.
2. **Remove `:=`** after the deprecation period: `visit_NamedExpr` raises
   `SyntaxError` with a migration hint (`==` / `eval_/2` / `is` / `is ++(...)`).
   The misuse-prone spelling must stop "kind of working". **Keep**
   `Evaluate`/`ArithEval` — they are `eval_/2`'s backend now (the original
   "prune the dead path" phase is cancelled).
3. **Drop the walrus-as-inline-naming reintroduction.** Document `is`-chains in
   the syntax/arithmetic docs instead.
4. **Idiom rule** (docs + deprecation message): `==` for relational arithmetic
   constraints; `eval_/2` for eager Python-semantics arithmetic (units,
   exceptions, performance-sensitive recursion); `is` for unification
   (including chains for naming); `++()` for arbitrary Python expressions.

## Migration rules (revised)

| Cluster | Target |
|---|---|
| Plain declarative arithmetic (clausal_modules, iso_arithmetic, fibonacci, clpfd/meta fixtures, lambda bodies, EDCG accumulators) | `==` (done, green) |
| TRO-sensitive predicates (`deep_index`, `tro_predicates`) | `eval_/2` (re-migrate from interim `is ++(...)`) |
| Catch-division (`catch_test`) | `eval_/2` (re-migrate from interim `is ++(...)`) |
| Units fixtures (~125 sites, `n(Unit)` sugar preserved) | `eval_/2` — mechanical `X := E` → `eval_(E, X)`, same IR, zero semantic risk |
| Term/lambda naming (`builtins_call`) | `is` (done) |
| Shipped examples, module docstrings, embedded clausal in `tests/*.py`, docs | per the same rules; Python-level `X := Var()` walrus in `.py` files is untouched |
| Prolog bridge | `prolog_to_clausal`: `is/2` → `eval_(E, R)` call (replacing the `is`→`:=` infix map); `clausal_to_prolog`: `eval_/2` → `is/2`; regenerate all goldens |

## Phases (revised)

- **Phase 1 (in progress):** deprecation warning on `:=` (done; message gains a
  pointer to `eval_/2` once it lands) + implement `eval_/2` + full in-repo
  migration + goldens + docs (`eval_/2` section, `is`-chain naming section).
  Full suite green, `-W error::DeprecationWarning` sweep clean. Review
  checkpoint.
- **Phase 2:** `visit_NamedExpr` → `SyntaxError` + hint; remove the
  `NamedExpr` handling in `clausal_to_prolog`; delete/rewrite deprecated-path
  tests (walrus-parse tests, `:=` goldens). `Evaluate`/`ArithEval` stay.

## Parked

- Fresh-variable assign optimization (`X is T` with first-occurrence `X` →
  plain assignment, skip general unify): `todo/optimize_fresh_var_unify_assign.md`.

## Evidence log

- TRO breakage: `test_mynthof_tro_allocations` — 51 SGs under `==`, 1 under
  eager eval; `is ++(N - 1)` also 1.
- Units: `V == D / T` → `OverflowError` (clpq.py:894); `V is ++(D / T)` fails
  on `==`-bound (AttVar) operands; only full-Python construction worked under
  `is ++`. `eval_/2` sidesteps all of it by reusing `ArithEval`.
- Prolog: `is ++(...)` exports as `N1 = ???` + warning.
- Chains: plain, dict-accessor, three-way, and negative probes all pass on
  current main + Phase-1 WIP.
