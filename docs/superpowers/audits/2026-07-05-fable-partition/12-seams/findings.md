# Findings — A12 seams & synthesis

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.
Test refs are classes in `tests/audit_2026_07_05/test_12_seams.py`.

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A12-F001 | correctness | Tabled answer replay discards attributed-var constraints (dif AND CLP(FD) domains) | clausal/logic/tabling.py:117 (add_answer / answer normalization + replay path) | `-table(td/1)`, `td(X) <- (X is not 1)`; query twice with fresh vars | First query's answer var carries the dif/FD attr; the SECOND query replays the stored answer with the constraint GONE — `td(Y)` then `unify(Y, 1)` succeeds against the body's `Y is not 1`. Same for `in_domain/3` domains. Identical queries return semantically different answers; replay is unsound | TestF001TablingReplayDropsConstraints | investigate-A12-tabling-answer-constraints.md |
| A12-F002 | correctness | `X == <non-numeric ground term>` succeeds vacuously with an inverted-semantics FD var | == goal lowering (A03 compiler) → CLP(Z) entry (clausal/logic/clpfd.py dispatch) | `badeq(X) <- (X == myatom)`; solve, then unify probes | `==` is arithmetic equality (standing contract); a ground atom/str operand must raise a type error or fail. Actual: succeeds once, X becomes an FD var with domain ((-inf, inf),) that unifies with **42** but NOT with **myatom** itself. Cheat-sheet documents the trap ("broken FD var"), i.e. this is known-unintended | TestF002EqNonNumericOperand | fix-A12-eq-nonnumeric-operand.md |
| A12-F003 | correctness | Directive targets unvalidated: `-table` naming an undefined predicate or wrong arity is a silent no-op | import hook directive processing (clausal/import_hook.py) × tabling registration (clausal/logic/tabling.py) | `-table(zzz_no_such_pred/2)` loads clean; `-table(reach/3)` with `reach/2` defined loads clean and reach/2 runs UNtabled (diamond graph → duplicate answer 4) | A typo in a `-table` target silently loses termination/dedup guarantees — must be a load-time error (end-of-load validation; forward declaration is legitimate so the check belongs at module-load completion). Family of A10-F012 (malformed directive silent no-op) but the directive here is well-formed with a dangling target | TestF003DirectiveTargetValidation | fix-A12-directive-target-validation.md |
| A12-F004 | design | Engine helpers leak into every .clausal module namespace; same-named user predicates break at load with a cryptic error | clausal/import_hook.py module-dict setup (`walk`, `deref`, `unify`, `Var`, `Trail`, `Compound` from clausal.logic.variables / solve) | `walk("a", "b"),` in a .clausal file | Should load (or fail with a clear reserved-name error naming the clash). Actual: `TypeError: clausal.logic.variables._variables.walk() takes no keyword arguments` at the offending line; docs reserve only *Python builtins*, not engine internals. `solve` is NOT leaked (control), so the reserved set is arbitrary. Related: A10-F013 (builtin call/N shadows the clausal.call API — opposite direction of the same seam) | TestF004EngineNamespaceLeak | fix-A12-engine-namespace-leak.md |
| A12-F005 | correctness | `-dynamic(p/N)` with zero initial clauses does not mint the term class — declare-then-assertz is broken | directive processing (A10) × compiler globals_env (clausal/logic/compiler/globals_env.py:92) × assertz (A09) | `-dynamic(ghost/1)` + `seed <- assertz(ghost("x"))`; call seed | The ISO-standard dynamic workflow (declare, assert at runtime) must work with no seed fact. Actual: the module's own body raises `NameError: Predicate 'ghost/1' is not in scope as a term class` at runtime; with a seed fact the identical workflow succeeds (control test) | TestF005DynamicForwardDeclaration | fix-A12-dynamic-forward-declaration.md |
| A12-F006 | doc-drift | Cheat-sheet §8 stale-dispatch-after-assertz caveat did not reproduce | an external cheat-sheet, §8 (not in this repo — not editable by this audit) | assertz into an indexed 5-clause `-dynamic` predicate; findall + new-key + unbound queries | Cheat-sheet warns "findall over a dynamic predicate with an unbound first arg can observe stale dispatch after assertz (re-indexing is not guaranteed)". On this build all three observation channels see the new clause immediately. Either the caveat is stale or the triggering shape is narrower than described — flagged for the cheat-sheet's owning repo, pinned here as a regression guard | TestAssertzReindexSeam | — (external doc; noted for the downstream owner) |

## Seams probed and found CORRECT (regression-pinned)

| Seam | What was probed | Test ref |
|------|-----------------|----------|
| dif (A05) × CLP(FD) (A06) | FD narrowing/binding wakes the dif hook on every path probed: singleton `in_domain` bind, `fd_eq` narrow-to-bound, labeling enumeration | TestDifClpfdComposition |
| dispatch (A02) × attr hooks (A05/A06) | Indexed first-arg dispatch with FD- and dif-constrained query vars filters solutions through the hooks correctly | TestDispatchWithConstrainedVars |
| once/not (A03) × constraint trail (A05) | dif posted inside `once/1` survives; dif posted inside a failed NAF goal is fully unwound (no attr leak) | TestControlConstraintScoping |
| tabling replay (A04) × caller constraints (A05/A06) | Stored answers unify through the CALLER's dif/FD hooks on replay (the converse of F001, which is about constraints in the STORED answer) | TestTablingReplayRespectsCallerConstraints |
| compiler recursion shapes (A03) × tabling (A04) | Tail-position (TRO-eligible) and left-recursive tabled predicates over a diamond graph both dedup multi-derivation answers and terminate; deterministic tail recursion under `-table` correct | TestCompilerRuntimeTablingSeam |
| strings-as-lists (A01) × dispatch (A02) | str vs equivalent char-list take the same path through guard-form and head-pattern dispatch incl. empty cases; tabled str query against list-head fact works | TestStringsAsListsDispatchParity |
| assertz (A09) × indexing (A02) × findall (A03) | New clause visible to findall, new-key lookup and unbound enumeration immediately | TestAssertzReindexSeam |

## Known-family confirmations (cited, not re-owned)

- catch/3 (A03) cannot catch element/3's raw `ValueError` — executed confirmation of the A06-F005 error path escaping through the A09-D002/A11-D001 raw-exception family (TestKnownFamilySeams, xfail).
- A tabled predicate whose answer contains a list crashes `unhashable type: 'list'` in `add_answer` — seam consequence of A04-F005 reached via the Liskov char-list route (TestKnownFamilySeams, xfail).

## Coverage map

Boundaries × dimensions (probes ran against the /workspace/clausal-bug-fix clone, pyenv 3.13.3):

| Seam (prompt-mandated) | in-mode | out-mode/unbound | constrained var | backtracking/trail | error path | replay/2nd query |
|---|---|---|---|---|---|---|
| compiler-emits (A03) ↔ runtime-consumes (A04) | ✓ cnt | ✓ reach diamond | — | ✓ (dedup) | ✓ F003 directives | ✓ tabled 2nd query |
| terms.py dunders (A01) ↔ C unifier ↔ head matcher (A02) | ✓ str/list parity | ✓ guard+head forms | ✓ FD/dif dispatch | ✓ (t.undo probes) | ✓ F004 name clash | n/a |
| tabling (A04) ↔ dif (A05) ↔ CLP(FD) (A06) | ✓ ground facts | ✓ F001 answers | ✓ caller-constrained replay | ✓ NAF unwind | ✓ F002 ==-atom | ✓ F001 (unsound) |
| import hook (A10) ↔ compiler (A02/A03) ↔ runtime (A04) | ✓ loads | ✓ F005 fwd-decl | — | — | ✓ F003/F004/F005 | ✓ assertz reindex |

Handed-off boundary ambiguities from the 11 ledgers (searched for "seam"/boundary): all either (a) already carry their own design question in DESIGN-DECISIONS.md (A01-D001 cascade, A04-D001 hook protocol, A08-D002/D003 solver sync, A09-D002/A11-D001 error protocol, A10-D003/A10-F004 import clobber, A10-F008/A01-D004 pattern identity), or (b) were executed here (constraint×tabling composition → F001; ==-lowering → F002; catch×raw-error → cited). CLP(Q/R)/Z3-side composition with tabling was NOT probed (A08's solvers have no attr hooks at all — A08-F013 — so there is nothing for the table to preserve yet; blocked on A08-D002).

Dry-pass status: two consecutive probe passes (stages 6–7) surfaced only refinements of already-logged findings — stopped per protocol.
