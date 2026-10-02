# Findings — A04 runtime, search & tabling

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.
Test file: `tests/audit_2026_07_05/test_04_runtime_tabling.py` (24 passed,
20 xfailed on 2026-07-05 — every suspected-bug xfail actually fails, i.e.
every finding below reproduces).

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A04-F001 | correctness | **SLG completion phase cannot resume suspended-consumer continuations — answers silently lost; tabled solution sets depend on clause order and even on idiomatic programs.** When a consumer suspends before the leader has produced the answers it needs, the completion phase resumes the consumer's generator but its *parent chain is dead* (the original dispatch generator already returned DONE). The mini-trampoline intercepts `(sc._proceed, None)` and freezes `sc.args` — the consumer's *own call args*, which necessarily reproduce an already-stored answer — so the clause continuation after the recursive call **never runs** and the completion phase can never add a new answer. Consequences, all confirmed: (a) a tabled predicate with TWO recursive clauses, facts-first (fully idiomatic), loses answers: `p(X)` = `[1,2,3]` instead of `[1,2,3,4,5]`; (b) recursive-clause-first ordering loses everything derived: `[1]`; (c) mutual recursion with recursive clauses first: `ra(1,Y)` = `[2]` instead of `[2,4]`, and the inner leader `rb` is marked **complete with zero answers** (premature completion — no SCC tracking), permanently caching the wrong empty result. In-tree fixtures pass only because they use one recursive clause with base clauses first, where the live-phase consumer (iterating `entry.answers` while it grows) reaches fixpoint before suspending | `tabling.py:507-543` (completion mini-trampoline: `gen is sc._proceed`/`value is None` arm freezes `sc.args`; forwarding arm `gen.send(value)` reaches dead frames), `:489-505` (leader marks complete after own dispatch exhausts — no cross-entry SCC check) | `-table(p/1)` + `p(1), p(X)<-(p(Y),a(Y,X)), p(X)<-(p(Y),b(Y,X))` with `a(1,2), b(2,3), a(3,4), b(4,5)`; query `p(X)` | `[1,2,3,4,5]` vs `[1,2,3]` (facts-first) / `[1]` (rec-first); mutual `ra(1,Y)`: `[2,4]` vs `[2]`, `rb` complete-empty | `TestF001CompletionLosesConsumers` (4 xfail + facts-first mutual control) | `todo/audit-2026-07-05/investigate-A04-slg-completion-architecture.md` |
| A04-F002 | correctness | **`_naf_tabled` is unsound for never-called and other-variant subgoals — negation results depend on query order.** No table entry (and no same-functor variant evaluating) ⇒ "treat as no answers" ⇒ negation *succeeds* even when the positive goal is trivially derivable. `not tp(1,2)` with fact `tp(1,2)`: succeeds before any positive query, fails after — same program, opposite answers. The complete-table arm requires the **exact variant key**: a complete `tp(_,_)` table holding `(1,2)` is ignored by `not tp(1,2)` (different variant) → falls to no-entry → unsound success. Downstream: acyclic negation chains give wrong TRUE answers (`even_node(1)` succeeds and is recorded unconditional though `odd_node(2)` is derivable). Standard SLG calls the negated subgoal; this implementation never spawns it | `tabling.py:276-277` (no-entry → `return True`), `:240-252` (complete arm — exact `store_key` only), `:267-274` (any-variant check limited to same functor+arity *evaluating*, offers only delay) | `-table(tp/2)`, fact `tp(1,2)`, rule `ntp(R) <- (not tp(1,2), …)`; query `ntp` first | negation fails vs succeeds; after `tp(1,2)` query: fails (order-dependent) | `TestF002NafTabledNoEntry` (3 xfail + order control) | `todo/audit-2026-07-05/fix-A04-naf-tabled-no-entry.md` |
| A04-F003 | correctness | **WFS truth resolution is mode- and order-dependent, and wrong results are cached permanently.** Docs (`docs/wfs.md`) truth table for the asymmetric win game: a=true, b=false, c=false. Actual: `win("b")` queried FIRST yields 1 answer (stuck `undefined` — its delayed `not win("a")` targets a variant entry that is never created, so `_resolve_conditions` can never resolve it) and this wrong answer is cached `complete` forever; queried after `win("a")` it correctly yields 0. Var-mode `win(X)` yields `{a, b}` while ground-mode (docs order) yields only `a` — the solution set depends on call mode. Root causes shared with F002: negated subgoals are never spawned, and `_resolve_conditions` looks up delayed negations by exact variant key only (`tabling.py:302-306`), so cross-variant/cross-mode information is unreachable | `tabling.py:283-339` (`_resolve_conditions` — exact-key lookup, per-leader local resolution), `:254-274` (delay pathways) | fresh module: `sum(1 for _ in call("win","b"))` | 0 (docs) vs 1, sticky | `TestF003WfsModeOrderDependence` (2 xfail) + `TestTablingGuards::test_asym_win_ground_docs_order` (control) | `todo/audit-2026-07-05/investigate-A04-wfs-variant-resolution.md` |
| A04-F004 | correctness | **`query_wfs` `_truth` annotation is a stub — every result is hardcoded `True`.** `docs/wfs.md` §"The query_wfs API" promises `True` or `"undefined"`. The implementation loops `r["_truth"] = True` over all results without ever consulting `TableEntry.conditions`/`truth_value`. Symmetric win: both answers are internally `undefined` (guard test confirms the conditions machinery knows) yet `query_wfs` reports `True` for both. The in-tree test (`test_wfs.py:486-502`) only checks a non-cyclic case where `True` is correct | `solve.py:596-621` (`query_wfs`, comment even says "attach truth=True to all results by default") | `query_wfs(win(X), {"X": X}, m)` on symmetric win | `_truth == "undefined"` ×2 vs `True` ×2 | `TestF004QueryWfsStub` (xfail) + `TestTablingGuards::test_wfs_symmetric_win_internal_truth_values` (mechanism guard) | `todo/audit-2026-07-05/fix-A04-query-wfs-truth-stub.md` |
| A04-F005 | correctness | **Tabled answers containing lists, dicts, sets, or declared-functor term instances crash with `TypeError: unhashable type` — tabling only works for scalar/Compound answers.** `TableEntry.add_answer` does `answer in self.answer_set`; `freeze_args` preserves container types (list stays list; term instances are rebuilt via their class, which is unhashable). Any tabled predicate whose *arguments* contain a list at solution time crashes on the first answer — lists being the language's core data structure. Secondary gap (blocked behind the crash): `_deref_walk` (Py and C) does not walk dict/set/DictTerm/Seg* contents, so a "frozen" answer would share live sub-structure whose Vars unbind on backtracking | `tabling.py:115-122` (`add_answer`), `:184-189` (`freeze_args` → `_deref_walk`), `solve.py:49-68` (`_deref_walk_py` — no dict/set/Seg* arms), `_tabling_core.c:239-369` (same shape) | `-table(ts/1)`, `ts([1,*T]) <- (T is [2,3])`; query `ts(X)` | `[([1,2,3],)]` vs `TypeError: unhashable type: 'list'` | `TestF005UnhashableAnswers` (3 xfail: list/dict/term-instance) | `todo/audit-2026-07-05/fix-A04-tabled-answer-hashability.md` |
| A04-F006 | correctness | **Cross-type conflation in variant keys and answer dedup: tabled and untabled solution sets differ.** Keys and the answer set rely on Python `==`/`hash`, so `1 == True == 1.0 == Decimal(1)` conflate: facts `tt(1), tt(True), tt(2.0), tt(2)` tabled yield `[1, 2.0]` (True and 2 silently suppressed as "duplicates"); the untabled twin yields all four with types preserved. Subgoal variants conflate the same way (`key(1)==key(True)==key(1.0)`), so `p(True)` consumes `p(1)`'s table. C and Python implementations agree (differential ✓) — the defect is the equality relation, same family as the parked cross-type unification/index-key decisions (A01-D001, A02-D002) | `tabling.py:115-122` (`answer_set` set-of-tuples), `:149-178` (`_normalize_for_key_py`), `_tabling_core.c:58-184` (`do_normalize`) | `TYPES_SRC` fixture; `tt(X)` vs `utt(X)` | identical 4-answer sets vs `[1, 2.0]` tabled | `TestF006CrossTypeConflation` (1 xfail + 2 guards incl. key-conflation mechanism guard) | `todo/audit-2026-07-05/fix-A04-tabling-cross-type-conflation.md` (interim fix; final semantics blocked on A01-D001) |
| A04-F007 | correctness | **Abnormal leader exit (early abandonment via `once()`/loop-break, or an exception in the body) leaves the table entry `"evaluating"` forever — every later query silently returns partial answers.** The leader's `try/finally` only pops the leader context; nothing removes or completes the store entry. After `once(path(1,Y))`: entry stays `evaluating` with 1 answer; the next `path(1,Y)` takes the CONSUMER path with no live leader, yields the single cached answer + a spurious unbound answer (F008) and stops — `[2]` instead of `[2,3,4]`, no error. After a body exception (ZeroDivisionError): re-query silently returns the pre-exception partial answers instead of re-raising or recomputing. `once/1` over a tabled goal is corpus-idiomatic — this poisons real programs | `tabling.py:489-558` (leader path; `finally: pop_leader()` only — no entry cleanup on GeneratorExit/exception), `solve.py:572-593` (`once` abandons the solve generator) | `once(path(1,Y))` then `call("path",1,Y2)` | `[2,3,4]` vs `[2]` (+unbound); exception case: re-raise vs silent partial | `TestF007PoisonedEvaluatingTables` (2 xfail + poisoned-status mechanism guard) | `todo/audit-2026-07-05/fix-A04-poisoned-evaluating-tables.md` |
| A04-F008 | correctness | **A root-level `(None, _TABLING_SUSPEND)` step is misread as a solution — spurious unbound-variable answers.** All three drivers check `gen is None` and treat any value ≠ DONE as "solution found" BEFORE the tabling-suspend interception (which only handles `gen is not None`). An orphaned consumer at the root (the poisoned state of F007) suspends to `_proceed=None`, so the driver yields a "solution" whose output vars are unbound (`AttVar`). Confirmed: post-`once()` query of `path(1,Y)` yields `(2,)` then `(AttVar,)` | Py: `trampoline.py:238-241` (`_drive_until_yield` fallback), `:191-204` (`solutions`); C: `runtime/_trampoline.c:684-691` (`drive_until_yield_func`), `:536-559` (`solutions_func`) | F007 repro, inspect yielded bindings | all yielded answers ground vs one unbound AttVar answer | `TestF008RootSuspendSpuriousSolution` (xfail) | `todo/audit-2026-07-05/fix-A04-root-suspend-spurious-solution.md` |
| A04-F009 | correctness | **C `_drive_until_yield` swallows every `RuntimeError` and reports "search exhausted" — user errors from Python escapes become silent failure, and entry points disagree.** Both the initial send and the loop clear `StopIteration` **or `RuntimeError`** (`PyErr_ExceptionMatches(PyExc_RuntimeError)`) and return None. A `++user_fn()` raising `RuntimeError` therefore makes `call()`/`solve()`/`once()` silently yield nothing, while `solutions()` (C) propagates it — same program, divergent outcomes. The pure-Python fallback catches only `StopIteration` (C≠Py divergence). The RuntimeError catch presumably guards the StepGen "returned unexpectedly" protocol error / PEP-479 conversion, but it is far too broad | `runtime/_trampoline.c:663-671` (first send), `:717-724` (loop); contrast `trampoline.py:224-259` (fallback: StopIteration only) and `_trampoline.c:609-628` (`solutions_func`: propagates) | `rte(X) <- (X is 1, ++boom_rt())` with `boom_rt` raising RuntimeError; `list(call("rte", V))` | RuntimeError propagates vs `[]` silently; `solutions()` raises | `TestF009RuntimeErrorSwallowed` (xfail) + `TestCToolkitGuards::test_solutions_propagates_runtime_error` (divergence control) | `todo/audit-2026-07-05/fix-A04-drive-until-yield-runtime-error.md` |
| A04-F010 | correctness | **`when/2` disjunction: the `fired` once-flag is a plain closure cell, not trailed — after backtracking out of the branch that fired, the goal is silently skipped in the surviving branch.** Branch 1 binds X → goal fires (`fired[0]=True`), branch fails, bindings/attrs are undone but the flag survives; branch 2 binds Y → `_guarded_thunk` yields success WITHOUT running the goal → `R` stays unbound and the program "succeeds" having skipped its condition | `coroutining.py:104-121` (`_install_when_disjunction` — `fired = [False]` closure) | `w8(R) <- (when((nonvar(X) or nonvar(Y)), R is "fired"), ((X is 1, 1 == 2) or (Y is 2)))` | `R == "fired"` vs `R` unbound | `TestF010WhenDisjunctionFiredFlag` (xfail) | `todo/audit-2026-07-05/fix-A04-when-disjunction-fired-flag.md` |
| A04-F011 | design | **`freeze/2` commits to the first solution of the frozen goal — its choice points are discarded.** `_freeze_hook` drives each frozen goal to one solution and breaks; `freeze(X, in_(Y,[10,20])), X is 1` yields only `(1,10)` where SWI enumerates both. First-solution bindings stick (guarded). Not documented in `docs/coroutining.md` (which is otherwise accurate); the hook protocol is boolean (success/fail) so full backtracking needs a redesign of the attr-hook contract. Design question parked | `coroutining.py:28-46` (`_freeze_hook` — `for _ in goal_fn(): found=True; break`) | `FREEZE_SRC` fixture | 2 solutions (SWI parity) vs 1 | `TestF011FreezeFirstSolutionOnly` (1 xfail + current-behaviour guard) | `todo/audit-2026-07-05/investigate-A04-parked-design-decisions.md` (D001) |

Minor / code-read notes (no ledger row, tracked in todos where actionable):

- `_query_cache` keys on `id(module)` (`solve.py:183`) with no lifetime pinning:
  a GC'd Module whose address is reused would serve another module's compiled
  query. **unconfirmed** — could not force CPython id reuse for Module objects
  in 2k/50k-allocation attempts; noted in the parked-decisions todo as a
  hardening item, not a ledger finding.
- `assertz`/`retract` on a **non-dynamic** tabled predicate fail silently
  (0 solutions, nothing added), and `retract` *queries through the tabled
  wrapper*, minting new table entries as a side effect (observed a fresh
  `('tz',1,(99,))` complete entry). Dynamic+tabled invalidation itself works
  as documented (guard test). assertz-on-non-dynamic semantics are A09/A11
  territory — seam note below.
- Tabled predicate over a **dynamic non-tabled** predicate: assertz to the
  dependency does NOT invalidate the dependent table (doc-consistent by the
  letter of `docs/tabling.md` — invalidation is per-predicate — but a footgun;
  design question parked, D002).
- `continuation_search.py` (greenlet `Search`) has **no production callers**
  (only `tests/test_continuation_search.py`); `make_tabled_wrapper_simple` and
  `_trampoline_to_simple_adapter` are referenced only by `tests/test_wfs.py` /
  `test_tabling.py`. Dead-code candidates — noted in parked todo.
- `_naf_tabled` complete-table arm unifies on a **scratch Trail** and iterates
  the whole `table_store` in the any-variant fallback (O(store) per NAF call) —
  perf note only.
- C cross-cutting citations (not re-reported): `_trampoline.c` /
  `_tabling_core.c` / `_list_unify.c` use `m_size = -1` (cross_cutting #5);
  lazily-initialized statics `g_LogicException`/`g_TABLING_SUSPEND`
  (`_trampoline.c:34-63`) lack FT atomics (cross_cutting #4) — FT impact
  `unconfirmed — needs 3.14t`; `unwind_logic_exception` uses the deprecated
  `PyErr_Fetch`/`PyErr_Restore` pair (works on 3.13; maintenance).
- `Database._table_store` is a plain dict shared across threads;
  `_leader_ctx` is thread-local but the store is not — FT race
  `unconfirmed — needs 3.14t`.

## Coverage map

Files: `solve.py`, `trampoline.py`, `continuation_search.py`, `coroutining.py`,
`tabling.py`, `runtime/{list_unify,body_star_unify,tramp_call,_seg_helpers}.py`,
C: `runtime/_trampoline.c`, `_tabling_core.c`, `runtime/_list_unify.c`.

Dimensions: **IN** = input/ground mode, **OUT** = output/var mode,
**PART** = partial instantiation, **E/S** = empty & singleton & edge values,
**BT** = backtracking + trail restoration, **ERR** = error paths,
**ABANDON** = early abandonment (once / break mid-iteration),
**C≡Py** = C vs pure-Python parity (differential oracle).
Legend: `✓` probed clean, `F###` finding, `cr` code-read only, `pa` prior art,
`doc` documented divergence, `unc` unconfirmed (needs 3.14t / not reproducible).

### Query API (`solve.py`)

| Surface | IN | OUT | PART | E/S | BT | ERR | ABANDON | C≡Py |
|---|---|---|---|---|---|---|---|---|
| `solve` — pred-instance goals | ✓ | ✓ | ✓ | ✓ | ✓ | F009 | F007 (tabled) | ✓ |
| `solve` — Compound goals | ✓ | ✓ | ✓ | — | ✓ | — | — | — |
| `solve` — `True`/`False` fast paths | ✓ | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `solve` — module inference / `_coerce_module` | ✓ | ✓ | — | — | n/a | cr (TypeError msg) | n/a | n/a |
| `call` — string vs class functor; builtin fallback | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ KeyError | F007 | ✓ |
| `once` | ✓ | ✓ | — | ✓ fail→None | ✓ | F009 | F007 | — |
| `query` (deprecated) / `_deref_walk` structures | ✓ | ✓ | — | — | — | — | — | ✓ (P52 grid) |
| `query_wfs` | F004 | F004 | — | — | — | — | n/a | n/a |
| `_query_cache` structural key (aliased vars, values, unhashable skip) | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | n/a | n/a |
| `_query_cache` `id(module)` lifetime | cr/unc (note) | | | | | | | |
| `_templatize_query_goal` | ✓ (via solve matrix) | ✓ | — | — | — | — | n/a | n/a |

### Trampoline (`trampoline.py`, `runtime/_trampoline.c`, `runtime/tramp_call.py`)

| Surface | IN | OUT | PART | E/S | BT | ERR | ABANDON | C≡Py |
|---|---|---|---|---|---|---|---|---|
| `StepGenerator` send/close protocol | ✓ | ✓ | — | ✓ | ✓ | ✓ | — | cr (same spec) |
| `trampoline()` LogicException unwinding | ✓ (via A03 catch fixtures + P38) | — | — | — | ✓ | ✓ | — | cr |
| `solutions()` (+suspend interception, snapshot) | ✓ | ✓ | — | — | — | ✓ propagates RTE | — | cr; FINAL cold (no producer emits) |
| `_drive_until_yield` | ✓ | ✓ | — | ✓ | ✓ | F009 (RuntimeError swallow) / F008 (root suspend) | F007 trigger | F009 divergence |
| deep recursion | ✓ 30k tail, 2k output-list | ✓ | — | — | ✓ | — | — | — |
| `_tramp_call` bridge | pa (A03 once/NAF probes) | | | | | | | |

### Tabling (`tabling.py`, `_tabling_core.c`)

| Surface | IN | OUT | PART | E/S | BT | ERR | ABANDON | C≡Py |
|---|---|---|---|---|---|---|---|---|
| variant keys: scalars/lists/compounds/instances | ✓ | ✓ | ✓ | ✓ | n/a | ✓ 60k-depth graceful | n/a | ✓ (P52) |
| variant keys: cross-type (1/True/1.0/Decimal) | F006 | F006 | — | — | — | — | — | ✓ (conflation identical) |
| answer freezing: dict/set/Seg*/instances | F005 | F005 | — | — | F005 (sharing, blocked by crash) | F005 TypeError | — | ✓ |
| answer dedup | F006 | F006 | — | ✓ | — | — | — | — |
| leader: drive, incremental yield | ✓ | ✓ | ✓ | ✓ | ✓ | F007 | F007 | — |
| leader: completion fixpoint | F001 | F001 | — | ✓ (no consumers) | F001 | — | — | — |
| consumer: live phase (answers grow under iteration) | ✓ | ✓ | — | ✓ | ✓ | — | — | — |
| consumer: suspend/resume rounds | F001 | F001 | — | — | F001 | — | F008 orphan | — |
| complete path cache hit | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — |
| left recursion, 1 rec clause, facts first | ✓ | ✓ | — | — | ✓ | — | — | — |
| ≥2 rec clauses / rec-first ordering | F001 | F001 | — | — | — | — | — | — |
| mutual recursion | F001 (rec-first) / ✓ (facts-first control) | F001 | — | — | — | — | — | — |
| exception during leader | — | — | — | — | — | F007 | — | — |
| abandonment (`once`/break) | — | — | — | — | — | — | F007 | — |
| assertz/retract invalidation (dynamic+tabled) | ✓ | ✓ | — | — | — | ✓ | — | — |
| assertz/retract on non-dynamic tabled | note (seam A09/A11) | | | | | | | |
| `abolish_table`/`abolish_all_tables` (db API + builtins exist) | ✓ | — | — | — | — | — | — | — |
| WFS `_naf_tabled`: complete / evaluating / no-entry / other-variant | ✓ / ✓ (delays) / F002 / F002 | F003 | — | — | ✓ scratch trail | — | — | — |
| WFS `_resolve_conditions`: same-leader / cross-variant / order | ✓ (sym win undefined) | F003 | — | — | — | — | — | — |
| simple wrapper + adapter | cr — no production callers (note) | | | | | | | |
| FT: table_store races, C static caches | unc — needs 3.14t | | | | | | | |

### Coroutining (`coroutining.py`)

| Surface | IN | OUT | PART | E/S | BT | ERR | C≡Py |
|---|---|---|---|---|---|---|---|
| freeze bound-now / deferred / failure rejects / multiple | pa (in-tree 51 tests) + ✓ | ✓ | — | ✓ | pa (attr undone) | — | n/a |
| freeze: nondet frozen goal | F011 | F011 | — | — | F011 | — | n/a |
| when nonvar/ground/conj | pa + A03 compile-side ✓ | — | ✓ re-install | — | — | ✓ ValueError unknown cond (cr) | n/a |
| when disjunction across backtracking | F010 | F010 | — | — | F010 | — | n/a |

### List/star unification runtime (`list_unify.py`, `body_star_unify.py`, `_list_unify.c`, `_seg_helpers.py`)

| Surface | IN | OUT | PART | E/S | BT | ERR | C≡Py |
|---|---|---|---|---|---|---|---|
| `_head_list_unify_input/output` × {var,list,str,bytes,Seg* ground/open,int,short,empty} × 5 shapes × prebind | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ 0 mismatches (220-cell grid) |
| mid-pattern failure trail restoration (or-arm) | ✓ | ✓ | — | — | ✓ | — | — |
| `_body_star_unify` / builders | ✓ (via P7 + pa C3 audit F031-F043 guards) | ✓ | ✓ | ✓ | ✓ | — | pa |
| `_segstring_align`/`_segbytes_align` | pa (C3 audit territory; empty-witness semantics documented in code) | | | | | | |
| `_in_iter` pair mode | cr | | | | | | |

### C toolkit

| Surface | Result |
|---|---|
| refcount/alloc: complete-table solve loop ×1500 | ✓ stable (growth ≤ 0) |
| refcount/alloc: fill+abolish loop ×1500 | ✓ stable |
| `_tabling_core` deep C recursion: 40k survive, 60k graceful RecursionError (walk + key), Compound nesting 49k survive | ✓ (MAX_DEPTH=50000 guard effective; no segfault) |
| `_trampoline` error classes vs Py fallback | F009 |
| cross_cutting_issues items | cited above, not re-reported |

### Dry-pass log

Six probe passes (`/tmp/a04/probe1..6*`). Pass 1 (10 probes): F004 (query_wfs
stub), F007 (once-abandon, +AttVar symptom), F007 (exception poison), F006
(cross-type), F005 (dict crash), F009 (RuntimeError swallow + solutions
divergence), F010 (when-disj flag), F011 (freeze semidet), F001 (mutual-rec
rec-first, rb complete-empty); trail-restoration probe clean. Pass 2: F002
(NAF no-entry order dependence), F002/F003 (acyclic chain wrong TRUE),
dynamic-dependency staleness note; assertz-on-non-dynamic anomaly flagged;
id-reuse attempt failed (unconfirmed); aliased-var cache keys clean. Pass 3:
F001 single-predicate two-rec-clause (rec-first `[1]`), F005 list-answer
crash, assertz deep-dive (non-dynamic fails silently; retract mints table
entries), C-stack walk 49k clean, refcount loops clean, mode matrix clean.
Pass 4: dynamic+tabled invalidation CLEAN (docs honored), F002 var-variant
isolation, C-stack graceful guards incl. key mode + Compounds, C≡Py
list-unify differential 0 mismatches, LogicException surfacing clean,
abolish builtins present. Pass 5: F003 asym var-mode `{a,b}`, F001
facts-first `[1,2,3]` (the idiomatic-program repro), F009 also via
solve/once, C≡Py deref-walk/key differential clean (dict/set identity
passthrough noted), F005 term-instance crash. Pass 6: F003 ground-order
(`win('b')` first → sticky undefined) — confirmed prediction, nothing else
new → findings stable across passes 5–6 (new evidence only deepened known
findings); stopped per budget with map covered.

### Seam notes for A12

- **assertz/retract on non-dynamic tabled predicates** fail silently and
  retract queries *through* the tabled wrapper (mints table entries).
  Database-ops semantics are A09/A11; the table-store side effect is A04's.
- **`findall([X,Y], Path(X,Y), L)` stale-dispatch note** in
  `tests/fixtures/tabled_left_rec.seam` (V2-2/V2-4b interaction) — prior
  art, intersects A03 findall + A04 tabling; not re-probed.
- **F009 divergence** means `python -m clausal.testing` (solutions-driven)
  and Python-embedding entry points (`solve`/`call`) disagree on error
  surfacing — affects every subsystem's error-path tests.
- **`_naf_tabled` is emitted by the compiler** (A03's `tabled_naf.py`); the
  fix for F002 may need a compiler-side "call before negate" transform —
  coordinate with A03 owners.
- Cross-type conflation (F006) is the tabling face of A01-D001/A02-D002 —
  whatever unification semantics is decided must be applied to variant keys,
  answer sets, AND index buckets together.
- `solve.py:83` DeprecationWarning seam noted by A03 — with the C extension
  active no warning was observed in A04 runs; likely fallback-path-only.
