# Compile constant-list membership `X in [c1, c2, …]` to a Python set

**Requested:** 2026-07-04. Membership tests against a **ground constant list** are common in a
downstream rulebase corpus (e.g. a compliance-screening domain's `dealing_permitted`:
`ACTION in ["acquire","dispose","amend","cancel"]`, and a safe-harbour list). Today `X in LIST` / `in_(X, LIST)` is a linear scan, and the same literal
list is often written several times in one file.

## Idea
When the right operand of `in`/`in_` is a **fully ground list literal**, the compiler can lower it to
a Python **set membership** in the emitted AST — `x in {c1, c2, c3}` — which is O(1) and builds the
frozenset once at load. Only valid when every element is ground (atoms, numbers, strings); if any
element is a var, fall back to the current relational scan (which must stay, for the enumerating
mode `member(X, L)` with X unbound).

Elements are `PredicateMeta` atoms (hashable, identity-equal), numbers, strings — all hashable, so a
frozenset works. Guard: only apply in the **check** mode (ground X against ground list); keep the
relational scan when X is unbound or the list is partial.

## Example (compliance-screening domain, dealing_permitted)
```clausal
dealing_permitted(TRADE, INFO, PERMITTED) <- (
    ...,
    ACTION in [acquire, dispose, amend, cancel],   # ground list -> compile to `ACTION in {..}`
    ...
)
```
(Corpus-side, the repeated literal is also being factored into a `regulated_action/1` fact set —
first-argument indexed, so already better than a linear list scan; the compiler optimisation would
make the inline `in [..]` form fast too, without needing the helper predicate.)

## Acceptance
`X in [ground, ground, …]` in check mode compiles to frozenset membership; enumerating mode
(`X in L`, X unbound) unchanged; a bench over a large constant list shows O(1) not O(n).

---

## DONE — 2026-07-29

Landed narrowly: the frozenset is consulted only in **check mode**, only for
lists of compile-time constants, only when the runtime left operand is a ground
term of a type whose `==` provably answers the same question as `unify()`, and
only when the list has no hash-equal duplicates. Everything else keeps the
existing scan, byte-for-byte.

### Triage first: does it pay?

Measured before touching anything, end-to-end through the trampoline with a
membership-free control clause subtracted (`benchmarks/bench_const_list_membership.py`,
which compiles both variants **in one process** via `CLAUSAL_DISABLE_OPT=const_set`
so the two numbers are not separated by a machine-state change):

| membership goal | scan | set | speedup |
|---|---|---|---|
| `in` 2 atoms, hit | 1276 ns | 302 ns | 4.2× |
| `in` 4 atoms, hit (the compliance-screening shape) | 3692 ns | 413 ns | 8.9× |
| `in` 8 atoms, hit | 7626 ns | 338 ns | 22.5× |
| `in` 16 atoms, hit | 15913 ns | 381 ns | 41.8× |
| `in` 64 atoms, hit | 66980 ns | 221 ns | 302× |
| `in` 4 atoms, miss | 4290 ns | <100 ns | >43× |
| `not in` 4 atoms, miss | 4565 ns | 140 ns | 32.6× |
| `in` 4 strings, hit | 2757 ns | 417 ns | 6.6× |
| `in` 4 atoms **with a duplicate** | 3570 ns | 2213 ns | 1.6× (declines, as it must) |

Flat at ~220–420 ns regardless of list length: O(1), which is the acceptance
criterion. The scan is ~690 ns **per element**, and the dominant term in that is
not the loop — it is that a *failing* `unify()` costs 8× a succeeding one, filed
as [`unify-failure-pays-two-attributeerrors.md`](../unify-failure-pays-two-attributeerrors.md).
Fixing that would shrink the scan to roughly 120 ns/element and leave this
optimisation a still-worthwhile ~2× at n=4 and ~30× at n=64.

### Semantics, all four verified by execution (not reasoned)

- **Order.** `X in [c, a, b]` with `X` unbound enumerates `c, a, b` — list
  order, observable in first-solution order and in `findall` results. A set
  reorders it. **This is why the fast path is check-mode only:** the runtime
  guard rejects an unbound Var and falls to the scan.
- **Duplicates.** `X in [a, a, b]` yields **three** solutions; the ground
  `a in [a, a, b]` yields **two** — membership is a choice point, so a set
  would silently drop a solution from the enclosing conjunction. Any list with
  a hash-equal pair is refused. Equality, not surface form, is the test:
  `1 in [1.0, 1]` yields two solutions today, and `{1.0, 1}` has one element.
- **Hashability.** `hash(Decimal('nan'))` *raises*, so `Decimal` is off the
  whitelist wholesale rather than case by case. Unhashable elements (compound
  terms, nested lists) and unhashable left operands fall back rather than
  raising `TypeError` — the latter needs the runtime type guard, since the
  frozenset for that callsite already exists.
- **Unification vs equality.** `unify()` on two ground non-container terms
  bottoms out in `PyObject_RichCompareBool(…, Py_EQ)`, so `unify` *is* `==`
  there — probed over a full pairwise matrix of `int`/`float`/`bool`/`complex`/
  `Decimal`/`Fraction`/`str`/`bytes`/`None`/`tuple` with zero disagreements.
  `unify(1, 1.0)` succeeds and `1 in {1.0}` is True, so the numeric tower
  agrees in both directions (Python guarantees `x == y ⇒ hash(x) == hash(y)`
  across it). Atoms are `PredicateMeta` classes: `==` and `hash` are `type`'s
  identity ones, and atom unification is identity, so they coincide.
  `Quantity` is excluded — it carries a `__unify__` hook and may contain a Var,
  so its unification is not its `==`.

### Shape of the change

`_const_set_prologue` in `_lower_goalop_shared.py` emits a one-slot memo cell
into the predicate's `base_globals`; `$const_set` fills it on **first
execution** and returns `False` to pin the callsite to the scan forever if the
list is ineligible. Building at first execution rather than at compile time is
deliberate: the list expression and the set are then evaluated in the same
namespace, so an atom can never be captured as a different object than the
fallback scan would see, and hashability/duplicate/whitelist validation happens
once per callsite instead of once per call.

For `in`, the fast path swaps the loop's *iterable* for a one- or zero-element
tuple rather than branching around the loop, so the continuation is emitted
once — branching would double the code size of every membership goal and square
it for nested ones. For `not in`, which already tests its flag outside the
loop, the fast path sets the flag directly.

`const_set` is a registered entry in `_ALL_OPTIMISATIONS`, so
`CLAUSAL_DISABLE_OPT=const_set` gives a full-suite A/B; the suite is green both
ways. `tests/test_const_list_membership.py` (48 tests) runs every semantics
case against **both** builds, so it asserts that the fast path agrees with the
scan it replaces rather than merely that it answers something plausible. Three
mutants confirmed the tests are load-bearing: dropping the duplicate check
(4 failures), dropping the left-operand type guard (5 failures, including all
three order tests), dropping the element whitelist (2 failures).

Corpus: the investment-screening domain ALL GREEN (46+27+32+18 = 123 tests, 4/4 negative controls
load-bearing), the tax-credit domain 41/41.

Files: `clausal/logic/runtime/const_set.py` (new),
`clausal/logic/compiler/_lower_goalop_shared.py`,
`clausal/logic/compiler/{predicate,compile_ctx}.py`,
`benchmarks/bench_const_list_membership.py` (new),
`tests/test_const_list_membership.py` (new), `tests/test_optimisations_toggle.py`.

### Open question, for whoever picks up the corpus side

**How much of the corpus should be rewritten to use the inline form?** A survey
of the corpus found only **11** inline constant-list memberships, and both
gold suites run for this change (the investment-screening and tax-credit domains) contain
**zero** — every membership there is `X in LIST` against a runtime list variable, which
correctly declines. The compliance-screening domain's `dealing_permitted` has already been hand-factored
into a first-argument-indexed `regulated_action/1` fact set, exactly as this
todo anticipated. So the optimisation currently fires on a handful of sites.

Options:

1. **Leave the corpus alone.** The value is that the natural inline idiom is no
   longer a trap, so future authors need not hand-factor. Costs nothing.
2. **Un-factor the helper predicates** that exist only to dodge the linear
   scan (`regulated_action/1` and kin) back to inline `in [...]`. Fewer
   predicates, closer to the statutory text — but it churns gold transcripts
   and loses the helper's own documentation value.
3. **Lint for it** — flag `X in LIST` where `LIST` is bound to a ground
   constant list one goal earlier, since that shape declines today and is easy
   to write by accident.

Recommendation: **(1) now, (3) later.** (2) trades readable, citable helper
predicates for a speedup on goals that are not hot; the measurement above is
per-goal, and no profile yet shows membership dominating any corpus query.
A second open question, smaller: the fast path currently needs the left operand
to be a Var *already in `var_context`*, so `[H|_] = L, H in [a, b]` qualifies
but a body-only Var does not. Widening that would mean hoisting the walrus
that `term_to_ast_expr` emits for body-only Vars into a temporary; worth doing
only if a profile ever asks for it.
