# Nothing detects recursion through negation at compile time

**Written:** 2026-08-27, alongside `wfs-undefined-lost-at-query-surface.md`.
**Severity:** medium as a defect, high as a missing guardrail. Read the other one first —
it is the live wrong-answer bug; this is the reason nobody is warned before meeting it.

---

## 1. The finding

`grep -rin stratif` over `clausal/` and `docs/` returns **zero hits**. Nothing in the
engine detects, warns about, or refuses a program whose predicate dependency graph has a
cycle through negation. A non-stratified program compiles cleanly and says nothing.

What happens next depends on a runtime property of the particular query, not on any static
property of the program:

| the program | what you get |
|---|---|
| untabled, e.g. `Pu() <- (not Qu())`, `Qu() <- (not Pu())` | `RecursionError` out of the Python stack |
| tabled, e.g. `-table(Win/1)` with `Win(X) <- (Move(X,Y), not Win(Y))` | correct `Undefined` in `table_store`, and a wrong answer at every query surface — see the sibling todo |

`docs/wfs.md` already states that plain NAF on recursive negation "can loop or produce
wrong answers". That is an accurate description of a hazard the toolchain then does nothing
to help you find.

## 2. Why a `RecursionError` is not an acceptable answer

It is at least loud, which is better than the tabled case. But:

- **It names nothing.** A Python stack overflow does not tell an author which predicates
  form the cycle, or that negation is why. On a two-clause program you can guess. On a
  rulebase of the size this corpus builds, you cannot.
- **It is query-dependent.** The same program is fine until someone asks the goal that
  reaches the cycle. A test suite that never asks that goal passes, and the defect ships.
- **It can burn arbitrary work first.** The crash comes when the stack runs out, not when
  the cycle is entered, so a large program can do a lot before dying.
- **It is indistinguishable from ordinary runaway recursion**, which has entirely
  different causes and fixes.

## 3. What I would want

**A compile-time dependency analysis, reported not enforced.** Build the predicate
dependency graph, mark edges that pass through `not`, find strongly connected components
containing at least one such edge, and report them by name:

```
non-stratified: Pu/0 -> not Qu/0 -> not Pu/0
  a cycle through negation; NAF may loop or answer wrongly here.
  Add -table(...) to get well-founded semantics, or break the cycle.
```

**Report, not refuse, and this is the important part.** Non-stratified programs are not
errors — under well-founded semantics they have a perfectly good three-valued meaning, and
`-table` already delivers it. The engine should say "this program needs WFS to be
meaningful, and here is the cycle" rather than rejecting it. Refusing would make the engine
unable to express defeasible reasoning, which is a legitimate and wanted thing to express.

**Escalate when tabling is absent.** A non-stratified SCC whose predicates are **not**
tabled is the case that genuinely misbehaves — it will loop or crash, with no defined
answer available. That combination deserves a stronger diagnostic than a note, and is the
one place a hard error would be defensible.

**The information is already there at runtime.** `DelayedNegation('Win'/1, key=(2,))` in
the completed table names the cycle partner exactly. Whatever computes that could inform
the static analysis, or vice versa — they are the same relation, found at two different
times.

## 4. Acceptance

1. The two-clause untabled program in §1 produces a named diagnostic at compile time
   instead of only a `RecursionError` when queried.
2. The engine's own `tests/fixtures/wfs_win.clausal` is reported as non-stratified **and
   tabled**, i.e. flagged as fine — this is the case that must not be treated as an error,
   or every legitimate WFS program becomes noisy.
3. A stratified program using negation freely produces no diagnostic at all. Most of the
   corpus is in this category, including the composition rulebase
   (`/workspace/clausify/auto/assess/rules/eu_procurement_2014_24.clausal`), which uses
   `not` throughout and is not defeasible. False positives here would be worse than the
   current silence.

## 5. Why it is worth doing

A legal corpus is where non-stratified negation stops being exotic: "this rule applies
unless that rule disapplies it, and that rule applies unless this one does" is an ordinary
shape in law, not a pathological one. The corpus already declares **10 of 76** domains
`defeasibility: defeasible`.

An author writing one of those today gets no signal that they have crossed into territory
where the engine's plain answer is unreliable — they find out from a stack overflow, or,
worse, from the sibling todo's silent `True`. A compile-time note naming the cycle turns
the most dangerous property a rulebase can have into something visible at authoring time.

---

## RESOLVED (2026-08-27)

Implemented as `clausal/logic/stratification.py`, wired into
`compiler_v2.compile_module` step 4c (after directives + clause assert, before
compilation). Design follows §3 exactly:

- Predicate dependency graph from clause bodies (goal-position calls only —
  call ARGUMENTS are terms and record no edge, so a data constructor sharing
  a predicate's name cannot fabricate a cycle). `not` marks the edge
  negative; `if_` tests record both a positive and a negative edge (the else
  branch runs under the test's failure). Meta-called goals (`findall`,
  `call/1`) are not traced — misses are false NEGATIVES by design.
- Iterative Tarjan SCC; an SCC with an internal negative edge is
  non-stratified. **Fully `-table`d SCCs are silent** (acceptance 2 —
  `wfs_win.clausal` loads without a peep). An SCC with any untabled member
  warns (`ClausalStratificationWarning`) naming a concrete cycle
  (`Pu/0 -> not Qu/0 -> not Pu/0`), the untabled members, and the
  `-table(...)` remedy. Report, never refuse.
- §3's "escalate to a hard error when untabled" was NOT taken: a warning
  keeps the report-not-refuse principle uniform, and `-W error` turns it
  into one for whoever wants that.

Acceptance: (1) the two-clause untabled program warns by name at load;
(2) `wfs_win` is silent; (3) stratified NAF programs and positive-only
recursion are silent — `tests/test_stratification.py`. The full engine suite
(hundreds of `not`-using fixtures) runs with no new stratification noise.
The eu_procurement corpus check could not be run directly (its import chain
crosses clausify snapshots that no longer line up); the suite-wide silence
plus the term/goal-position distinction is the false-positive evidence.

Note: this analysis is per-module, like the `$naf_tabled` lowering — a
cross-module negation cycle is invisible to it
(`todo/cross-module-tabled-naf-loses-wfs-delay.md`).

Runtime note: the sibling fix (see
`todo/done/wfs-undefined-lost-at-query-surface.md`) means the §1 table's
"tabled" row now reads correctly at every query surface, and ground NAF on
never-called tabled subgoals is spawned rather than guessed.
