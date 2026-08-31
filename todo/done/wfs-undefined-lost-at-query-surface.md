# WFS: the third truth value is computed correctly and then thrown away

**Written:** 2026-08-27, from the law-formalization side, while measuring whether Clausal
could carry cross-instrument defeasibility.
**Severity:** high. The engine computes the right answer and every public query path
reports a wrong one. There is no error, no warning, and no way for a caller to tell.

---

## 1. Minimal reproduction

Uses the engine's own fixture, `tests/fixtures/wfs_win.clausal` — the symmetric 2-cycle
`Win(X) <- (Move(X, Y), not Win(Y))` over `Move(1,2), Move(2,1)`. Both atoms are unfounded;
the correct WFS answer for each is **Undefined**.

```python
import sys; sys.path.insert(0, 'tests')
from test_wfs import _load, _module
from clausal.logic.solve import query_wfs
from clausal.logic.variables import Var, Trail, unify
from clausal.terms import Call as TermCall, LoadName

m = _load("wfs_win"); lm = _module(m)
X = Var()
print(query_wfs(TermCall(func=LoadName(name="Win"), args=[X], kwargs=[]), {"X": X}, lm, Trail()))
for v in (1, 2):
    Y = Var(); t = Trail(); unify(Y, v, t)
    print(v, query_wfs(TermCall(func=LoadName(name="Win"), args=[Y], kwargs=[]), {}, lm, t))
for key, e in lm.db.table_store.items():
    for i, a in enumerate(e.answers):
        print(a, e.truth_value(i), e.conditions[i])
```

Measured output:

```
UNBOUND  ->  [{'X': 1, '_truth': True}, {'X': 2, '_truth': True}]
GROUND 1 ->  []
GROUND 2 ->  [{'_truth': True}]

table_store:
  (1,)  Undefined  frozenset({DelayedNegation('Win'/1, key=(2,))})
  (2,)  Undefined  frozenset({DelayedNegation('Win'/1, key=(1,))})
  (2,)  True       frozenset()
```

## 2. What is wrong, in order of severity

**2a. The same atom reads true, or false, depending only on how it is asked.**
`Win(1)` comes back `True` from the unbound query and `[]` — which every caller reads as
false — from the ground query. One atom, two contradictory answers, neither of them the
correct `Undefined`.

**2b. A symmetric program gets asymmetric answers.** `Win(1)` and `Win(2)` are
interchangeable under the program's own symmetry. Ground-queried, `Win(1)` is false and
`Win(2)` is true. Whatever is happening is order-dependent, and order-dependence on a
symmetric input is a much stronger signal of a real defect than the lost annotation is.

**2c. The correct value exists and is discarded.** `table_store` holds `Undefined` for
both, with a `DelayedNegation` condition that **names the other cycle member**. Everything
a caller would need to report "here is a pair I cannot order, and here is the pair" is
computed, then dropped at the surface.

**2d. There is a third, unconditional `True` answer for `(2,)`.** Note the table has three
answers for a two-atom cycle: `(2,)` appears twice, once `Undefined` with a delayed
negation and once `True` with an empty condition set. I have not diagnosed this and am not
going to guess at it, but an unconditionally-true answer for an atom that is unfounded
looks wrong on its face, and it is the most likely explanation for 2a and 2b — a ground
query would find the unconditional answer for `(2,)` and nothing usable for `(1,)`.
**Start here.** If this answer should not exist, fixing it may resolve the surface
behaviour without touching the annotation path at all.

## 3. Mechanism for the lost annotation

`clausal/logic/solve.py:685-715`. `query_wfs` asks `_tabled_entry_for_goal(goal, module,
trail)` for the tabled entry, and when it gets `None`:

```python
    entry, goal_args = _tabled_entry_for_goal(goal, module, trail)
    if entry is None:
        for r in results:
            r["_truth"] = True
        return results
```

`_tabled_entry_for_goal` returns `(None, None)` for a `TermCall` goal — it handles
`is_term_instance` and `Compound` — and a `TermCall` is the goal shape the engine's **own
test** builds (`tests/test_wfs.py:486-500`). So the documented remedy for undefined
answers does not work through the shape its own test suite uses.

The code says as much in its comments: *"Non-tabled goals stay True (documented)"* and
*"Composite/conjunctive goals are not decomposed here and keep True (a min-truth semantics
over tabled conjuncts is future work)."* Both are honest, and both mean that in practice
`_truth` is `True` for nearly everything a real caller asks.

**Why the existing test does not catch it:** `test_query_wfs_returns_list` runs
`tabled_fib` — a negation-free program where every answer really is `True`, so the
hardcoded value is accidentally correct. The annotation path is untested for `Undefined`
at the query surface, which is the only place it matters.

## 4. What "fixed" should mean

1. **`Undefined` reaches the caller, or the call fails loudly.** Silently substituting
   `True` for `Undefined` is the worst available behaviour: it converts "no determinate
   answer" into "yes".
2. **The same atom gets the same answer whichever way it is asked** — unbound, ground,
   `Compound`, `TermCall`. 2a and 2b are the acceptance test.
3. **`[]` must not be how an undefined atom is reported.** An empty result is
   indistinguishable from false, and false is the opposite of the truth here.
4. **The delayed-negation condition should be reachable.** It names the cycle partner. A
   caller that can see it can report *which* pair is unresolved instead of only that
   something is. This is a feature request rather than a bug, but it is cheap given the
   data already exists, and it is the difference between "undetermined" and "undetermined
   between these two".
5. **Regression tests on a negation-bearing program.** The current suite proves the API
   returns a list; it does not prove the annotation is right, because it never runs a
   program that can be undefined.

## 5. Why this matters beyond the engine

A design was under evaluation in which cross-instrument legal defeasibility — law A
applies, law B disapplies A, and the pair may be unorderable — would be expressed directly
in Clausal and read back through `query_wfs`. The literature answer for such a cycle is
that it has no determinate truth value, and the honest system behaviour is to report
exactly that to a lawyer.

On the measurement above that design was rejected, and the interaction layer is being kept
out of the engine as data instead. The reason is 2a: a legal finding that reads "this
instrument applies" when the correct answer is "I cannot determine whether it applies" is
precisely the class of overclaim that whole system exists to refuse. The engine's WFS core
is right; only the surface is wrong. **Fixing this reopens a design that is currently
closed.**

## 6. Related

- `docs/wfs.md`, §"What to Do with Undefined Answers", documents that `query()`/`call()`
  yield undefined answers alongside true ones and points at `query_wfs` as the remedy. On
  this measurement the remedy does not work for the goal shapes callers use.
- `todo/truth-value-alias-open-questions.md` in this directory is adjacent and may share a
  root cause; worth reading together.
- `/workspace/portal-design/applicability/01-cycle-semantics.md` — the fuller measurement
  this came from, including the untabled case (§1c: `RecursionError`) and the
  no-stratification finding, which has its own todo beside this one.

---

## RESOLVED (2026-08-27)

All four numbered wrongs fixed, plus the underlying core defect they exposed:

- **2a/2b (ask-shape and order consistency):** `_tabled_entry_for_goal` now
  resolves reified `Call(LoadName, args)` goals — the shape this todo's repro
  and the engine's own test build — and checks `Compound` BEFORE
  `is_term_instance` (which also matches Compound and mangled its functor to
  `"Compound"`, making that branch dead). The same atom now reports the same
  truth however it is asked: unbound, ground, `Compound`, `TermCall` — and in
  any query order (regression: `tests/test_wfs.py::TestQueryWfsUndefinedSurface`).
- **2c (`Undefined` reaches the caller):** the symmetric cycle reports
  `_truth is Undefined` at the surface, and `[]` is no longer how an
  undefined atom comes back — the conditional answer is yielded and annotated.
- **2d (the unconditional `True` answer):** root-caused to `_naf_tabled`
  treating a CONDITIONAL answer in a complete table as a definite positive:
  ground `Win(1)` failed against the complete unbound table's conditional
  `(2,)` (subsumption branch), leaving an empty `(1,)` table that ground
  `Win(2)`'s `not Win(1)` then read as definite false → unconditional true.
  `not Undefined` now delays (is `Undefined`) instead of failing.
- **§4 item 4 (conditions reachable):** every `query_wfs` result carries
  `_delays`: a frozenset of `DelayedNegation` naming exactly the unresolved
  cycle partner(s). Documented in docs/wfs.md.
- **§4 item 5 (regression tests):** `TestNafTabledConditionalMatch`,
  `TestQueryWfsUndefinedSurface`, `TestWfsDisjunctiveDerivations` in
  tests/test_wfs.py, plus the un-xfailed F002/F003 tests in
  tests/audit_2026_07_05/test_04_runtime_tabling.py.

Fixing 2d honestly forced the parked A04-F003 design (the docs-order guard
test is only satisfiable with it): answer conditions are now a DISJUNCTION of
per-derivation delay sets, ground negated subgoals with no table are SPAWNED
(`$naf_db` seam), and resolution runs globally at root exit. See
`todo/audit-2026-07-05/investigate-A04-wfs-variant-resolution.md`
§IMPLEMENTED for the full design. Net: `wfs_win_asym` and fact-in-cycle
programs now compute their true/false values exactly (docs/wfs.md truth
tables reproduce in any order and mode) — the design this todo said was
closed can reopen.

The sibling `todo/no-stratification-analysis.md` was implemented alongside
(compile-time negation-cycle warning). `todo/cross-module-tabled-naf-loses-wfs-delay.md`
remains open and unchanged: the `$naf_db` seam, like `_is_tabled_naf`, reads
the CALLER's module db, so cross-module cycles still compile to plain NAF.
