# Task 2 report — THE INVERSION: class becomes read-through; mirrors die

Worktree: `/workspace/clausal-bug-fix/.claude/worktrees/p33-state-reloc`, branch
`feat/p33-state-reloc`. Base HEAD `5c4a8dd3` (Task 1). Commits: `9877876f`
(source + tests), plus one docs commit for these artifacts.

## Brief checkboxes

### [x] `make_predicate` gains an owner; classes are LINKED to their row

Implemented, with one deliberate divergence from the brief's spelling, argued
below.

The brief proposed an optional `db`/owner argument on `make_predicate(name,
fields)`. That does not reach the sites that matter: the overwhelming majority
of `PredicateMeta` classes in a `.clausal` load are NOT made by
`make_predicate` at all — they come from the generated
`class <functor>(metaclass=PredicateMeta)` block that
`term_rewriting._make_functor_class_ast` emits into the module body, and that
block runs during `exec` of the module, BEFORE `compile_module` has created the
`LogicModule` whose `db` would be passed. There is no db in scope at mint time
for the main path.

So the link is a metaclass method, `PredicateMeta._bind_row(db, functor,
arity)`, called at the three sites where a class actually becomes the compiled
face of a stored predicate:

| Site | File:line | Why here |
|---|---|---|
| step 4 — clauses attached | `compiler_v2.py:181` | the load-time minting site; after it `pred_cls._clauses IS db._clauses[key]` |
| step 4a — clause-less `-dynamic` | `compiler_v2.py:221` | exactly the shape whose FIRST clause arrives by runtime `assertz`, so its class must already be reading the row `assertz` appends to (A12-F005) |
| `_install` — dispatch installed | `compiler/predicate.py:2103` | covers every path that installs a dispatch without a load: bare-query compile, specialization target, runtime recompile after assertz |

`_bind_row` takes the **functor explicitly** rather than reading
`cls.__name__`. An aliased `-import_from(m, [alias(f, G)])` binds the class
under `G` while the class keeps functor `f`, and the clauses live under the
name the CLAUSE HEADS use — this is identity todo instance 2/3's exact trap, and
reading `__name__` would have walked straight into it. Pinned:
`test_bind_row_uses_the_passed_functor_not_the_class_name`.

Re-binding is legitimate and expected — a clause-free imported declaration
getting its clauses downstream (an established idiom that step 3c deliberately
does NOT refuse), a file compiled twice in one process, a name defined at two
arities. On a re-bind the old row keeps its own contents (it belongs to the
Database, not the class), but three pieces of state that were per-CLASS rather
than per-key before this task travel with the class so the relocation stays
lossless: `dynamic_arities` (UNIONED — it is a set across arities by
construction), `locked` (OR-ed — locking was one-way on the class, never undone
by a later module) and `source` (only when the target has none; step 4 re-stamps
it immediately after binding anyway). Pinned:
`test_rebinding_carries_dynamic_arities_locked_and_source`,
`test_rebinding_leaves_the_old_rows_clauses_where_they_were`.

**Detached compatibility mode.** A class minted with no Database anywhere gets a
PRIVATE `PredRow` over a private single-predicate `Database` of its own, minted
lazily on first touch of any relocated attribute (`_detached_row`). Lazy for two
reasons: `database.py` imports `predicate.py`, so eager construction in
`__init__` would need a module-level cycle; and a pure term/data class that
never touches predicate state never pays for one. Evidence below.

### [x] `PredicateMeta` state attrs become properties reading the row

All seven, get and set: `_clauses`, `_clauses_source`, `_dispatch_fn`,
`_lazy_recompile`, `_signature`, `_locked`, `_dynamic_arities`. `cls._row` is
the single slot that used to be seven, so the semantics are preserved BY
CONSTRUCTION — one slot per class, last writer wins, same `None`/`False`/`[]`
defaults — and every existing spelling keeps working verbatim:
`cls._clauses.append(...)`, `cls._clauses[:] = ...`, `cls._clauses = []` (the
reset several tests use — hence a `clauses` SETTER on `PredRow`),
`cls._dispatch_fn = fn`, `getattr(cls, "_clauses_source", None)`,
`cls._dynamic_arities = {3}`.

Note the metaclass property is a DATA descriptor, so it wins over anything left
in `cls.__dict__` — there is no way for a stale per-class attribute to shadow
the row. `_detached_row` reads `_fields` via `getattr(cls, "_fields", ()) or ()`
because a bare `class X(metaclass=PredicateMeta): pass` declares none, and
reading its `_clauses` used to be a plain attribute read that could not fail.

`_get_dispatch`'s SIGNATURE is untouched (`(cls, arity=None)`), the arity check
is untouched, and the three-step logic is the same one it always had: use the
installed dispatch; else recompile through the lazy callback and prefer whatever
`_install` stored over what the callback returned (the tabled-wrapper
invariant — pinned by
`test_get_dispatch_prefers_what_install_stored_over_the_callbacks_return`); else
raise `NotImplementedError`. Its BODY reads `row._db._dispatch` / `_lazy_recompile`
directly rather than through the properties: it is the once-per-goal-invocation
path and three property calls where there used to be two plain attribute reads
is exactly the overhead this phase must not add. That is the only place PredRow's
backing dicts are read from outside `database.py`; the same inlining was TRIED
for `_clauses` and reverted when it recovered only 4 ns of 75 (see bench §3).

### [x] database.py: the three mirror blocks and `_pred_cls_for` are DELETED

`Database.assertz` is now: `row = self.row(f, a, create=True)`;
`row.clauses.append(clause)`; `row.invalidate()` (kept behind the pre-existing
`if key in self._dispatch` guard, so the unconditional form does not start
creating `_dispatch` entries that were never there); table-abolish as today.
`asserta` and `retract` likewise.

`_pred_cls_for` is gone — `grep -rn "_pred_cls_for"` over the repo now returns
only the new tests that name it in prose. The arity-blind lookup it performed is
not fixed, it is **unrepresentable**: there is no second store to miss.
Pinned three ways (`test_assertz_no_longer_appends_onto_an_arity_mismatched_class`,
`test_retract_no_longer_reaches_into_an_arity_mismatched_class`,
`test_database_no_longer_has_pred_cls_for`), and demonstrated against the
reverted tree by `scratchpad/red_probe.py`, which prints
`p/3 class clauses after assertz of p/1: 1` before and `0` after.

### [x] compiler_v2 steps 4/5 + `_install` write through the row; ONE spelling

There is exactly one spelling for the install write, and it is the one that was
there before: `pred_cls._dispatch_fn = fn` / `pred_cls._lazy_recompile = ...` in
`_install`, and `pred_cls._clauses[:] = db_clauses` /
`pred_cls._signature = ...` in step 4. What changed is that the class property
now lands them in the row. Grep-checkable: the only assignments to those names
outside `predicate.py` are `compiler_v2.py:182/185/223/269`,
`compiler/predicate.py:2104/2106` and `builtins/_registry.py:427/428/437/438`
(the detached builtin classes), and every one of them goes through the class,
never around it. No caller pokes `row.dispatch_fn` directly.

Step 4's `pred_cls._clauses[:] = db_clauses` is a self-copy in the ordinary case
now (`clauses_for` returns a snapshot of the very list the row exposes). It is
KEPT rather than deleted: it is the write the row's contract names as the
deliberate clause-list minting site, and it is what makes the previous row's
content irrelevant when a class is re-bound.

### [x] `_predicate_functor_names` sync test — REQUIRED, added, one case each way

`_predicate_functor_names` never consulted class state (it reads the clause
NODES and the predicate-shaped directives, and says so in its docstring —
"Read at Step 3, BEFORE Step 4 attaches clauses to classes"). The class-state
consultation at the same decision is one line further on, in
`_process_declarations`: `isinstance(existing, PredicateMeta) and
existing._clauses` — which now reads the row. So the risk the brief names is
real but the divergence would be between step 3's ANSWER and the Database's
eventual TRUTH, and that is what the test pins:

- `test_predicate_functor_names_says_predicate_and_the_database_agrees` — a
  declared name WITH clauses is in the set, `db.row(name, 1)` exists with one
  clause, and the binding it produced is the class, whose `_clauses` IS
  `row.clauses`.
- `test_predicate_functor_names_says_data_and_the_database_agrees` — a declared
  functor with NO clauses is NOT in the set, `db.row(name, 2)` is `None`, no key
  of that name exists in `db._clauses` at any arity, and the binding it produced
  is the interned spelling (which is what makes its terms compile to cells).

Both drive a REAL `.clausal` load through `import_hook._load_module` with a spy
around `_predicate_functor_names`, and both assert the spy fired ("the anchor
moved" otherwise) rather than silently passing on a renamed function.

### [x] `$disp_` bake-in still fires for locked predicates

Unchanged this task, as the brief requires: `globals_env._maybe_cache_dispatch`
still reads `getattr(obj, "_locked", False)` and `obj._dispatch_fn`, now
properties. The existing locked-predicate compile test the brief asked me to
find already covers it and passes:
`tests/test_compiler_optimizations.py::TestLockedDispatchCaching::
test_disp_key_in_globals_for_locked_callee` asserts `"$disp_Bar_1" in
fn.__globals__`, and its two siblings assert the bytecode references
`$disp_Bar_1` and contains neither `get_dispatch` nor `$dispatch_at`. All four
tests in that class pass. Worth noting WHY they are a real test of the new code
path and not a vacuous one: `_make_locked_callee` builds `Bar` with a bare
`make_predicate` and never binds it to a db, so the capture is reading a
DETACHED row — the compatibility mode — end to end.

### [x] deep_gate 4-tuple plans untouched

`arg_index.py` and `list_dispatch.py` are not in the diff; the bucket-compile
path in `compiler/predicate.py` builds its functions with
`functiondef_to_function` and never reaches `_install`, so the binding added
there cannot touch a driven bucket. The P3-2 driven-bucket tests are green
inside the empty full-suite diff.

### [x] Spot A/B — see `task2-bench.txt`; one-liner below

### [x] Full suite: diff == ledger (empty) — see Gate below

## The `_dynamic_arities` choice: row-LOCAL field, not derived

**Chosen: a new row-local `PredRow.dynamic_arities: set[int] | None = None`
field.** The brief allows this explicitly ("if derivation can't preserve
None-vs-empty-set distinctions, keep a row-local field for it rather than
forcing a lossy mapping — state your choice"); here is why derivation cannot
work, checked against all three consumer sites.

`row.dynamic` is a per-`(functor, arity)` BOOLEAN — "is this key declared
dynamic". `_dynamic_arities` is a per-NAME SET, stamped onto the class for every
declared arity of the name whatever the class's own arity, and its consumers
turn on distinctions a single key's boolean cannot carry:

1. **`compiler_v2.py:206-208` (write)** — `if stamped._dynamic_arities is None:
   stamped._dynamic_arities = set()` then `.add(arity)`, run once per
   `-dynamic(f/N)` spec. `-dynamic(f/0)` and `-dynamic(f/3)` in one module stamp
   ONE class with `{0, 3}`. A per-key boolean cannot represent two arities on one
   class.
2. **`predicate.py::_declared_arity` (read)** — declines on `None` ("nothing was
   declared"), declines on `len(declared) != 1` ("guessing which of two to blame
   would be wrong half the time"), declines when `calling in declared`, and
   otherwise REPORTS the single element. So it needs: None vs a set, size 1 vs
   larger, and the element's value. Only the third survives a boolean.
3. **`compiler/terms_to_ast.py:226`** — a comment, no read. No constraint.

Tests pin both distinctions the derivation would have lost:
`test_dynamic_arities_is_row_local_and_independent_of_row_dynamic` sets
`db.mark_dynamic("p", 1)` (so `row.dynamic is True`) and asserts
`cls._dynamic_arities is None` — declared-at is not the same question as
is-dynamic — then pins `set()` as distinct from `None`. The pre-existing
`tests/test_predicate_arity_mismatch_diagnostic.py` block (`{3}`, `{2, 3}`,
`{2}`, `is None`) exercises all four shapes through the property and is green.

## The `locked` / `source` migration

Both were inert placeholders on `PredRow` after Task 1; this task makes them the
one true storage.

- `_locked` → `row.locked`. `PredicateMeta._lock()`/`_unlock()` are unchanged
  (`cls._locked = True/False`), and every enforcement point still reads
  `cls._locked`: `_assertz`/`_asserta`/`_retract` and the `assertz/1`-family
  builtins' `permission_error`. Verified live on a real load — after
  `compiler_v2` step 7 locks a compiled predicate,
  `db.row("pfn_greeting", 1).locked is True`.
- `_clauses_source` → `row.source`. `record_clause_source` is unchanged; step
  3c's ownership check reads the identical tuple back off the identical class.
  Verified live: `row.source == ('tests_pfn_sync',
  '/tmp/.../pfn_sync.clausal')`.

Both are or-ed / carried on a re-bind (above) because they were per-CLASS slots
before, not per-key.

## Detached-mode evidence

`test_bare_make_predicate_is_a_working_predicate_with_no_database` is the duck
type pin the brief asked for: a bare `make_predicate("Detached", ["x"])`, no
Database constructed anywhere in the test, asserting all seven attributes read
their old defaults, then that `_clauses.append(...)` works, that
`_dispatch_fn = fn` followed by `_get_dispatch()` and `_get_dispatch(1)` both
return `fn`, and that `_lock()`/`_unlock()` round-trip.
`test_predicate_meta_mutators_work_detached_and_respect_the_lock` does the same
for `_assertz`/`_asserta`/`_retract` including all three `RuntimeError`s.
`test_detached_classes_of_the_same_name_and_arity_do_not_share_state` pins that
each class gets its OWN private row — this is why the detached store is a
per-class private `Database` rather than one process-wide one: the builtin
registry mints several same-named classes (one per arity) in a single process,
and a shared store would collide them on `(functor, arity)`.
`test_detached_row_is_private_and_lazy` pins `cls._row is None` until first
touch.

Three of the new tests pass on the REVERTED tree as well as after — deliberately:
they are the compatibility-mode pins, and they assert behavior that must NOT have
changed. The other 20 fail at base (18 with `AttributeError: type object 'p' has
no attribute '_bind_row'`, one with `AttributeError: ... '_row'`, one with
`assert not True` on `hasattr(Database, "_pred_cls_for")`).

The in-tree consumers of the compatibility mode are exercised by the suite
throughout: `clausal/reflection.py` (9 classes), `clausal/logic/clpb.py` (2),
`builtins/_registry.py` (every builtin class, all `_locked = True` with a
`_dispatch_fn`), `term_expansion.py` (3), `specialization.py` (3 sites),
`compiler_v2.py:748`.

## Spot A/B

Full detail and raw transcripts in `task2-bench.txt` (marker line at the top).
Headline: **the dispatch path gains 24 ns and exactly one dict lookup per goal
invocation — 17 microseconds of a 2.1-second `bench_struct_tabling` run.**

The mandated interleaved wall-clock A/B on `bench_struct_tabling(1500, 3)`
against branch base `1f86daf4` gave a median of **+1.10%** on the final code
(10 pairs, alternating order). It is reported with a caveat rather than as a
verdict: four runs of the identical driver over the task, two of them on
byte-identical code, gave medians of +2.13%, +2.05%, +4.57% and +1.10%. The
estimate moves 3.5 points while the code does not — this machine's own noise
(base stdev 4-7%) is larger than the effect being resolved.

So the ≤3% question is answered by counting work instead, which does not drift:

- cProfile call counts, query half (`Nats(700, _)`): base 98 078 calls, task2
  98 779 — **+701**, of which `{method 'get' of 'dict'}` is 2105 → 2806,
  **+701**. 700 subgoals, one extra `dict.get` each. Nothing else on the query
  path changed.
- cProfile call counts, load half (10 module loads): 320 825 → 321 165, **+34
  calls per load**.
- Microbench: `_get_dispatch()` 53.2 → 76.8 ns; `_get_dispatch(arity)` 74.2 →
  100.5 ns; `_clauses` 20.0 → 94.6 ns (a compile/assert-path read, not per-goal;
  ~50 ns of it is the metaclass descriptor call itself). `bench_fib(25)`, the
  dispatch-densest macro in the workload set, is flat.
- Corroborating: the full suite ran 108-116 s with the change (three runs
  over the task) vs 130 s for a same-session base re-run of the identical
  suite.

Every bench process asserts `clausal.__file__` starts with the tree it was told
to measure before importing any workload. That assertion earned its keep: a
probe script run from outside the tree silently imported the venv's installed
`clausal` once during this task and was caught by it, not shipped. The C lever
is **not** needed and was not reached for.

## Gate evidence

Command (foreground, from worktree root):

```
/workspace/clausal/venv/bin/python -m pytest tests/ \
    --continue-on-collection-errors --tb=no -q -rf
```

```
144 failed, 12107 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error
in 108.27s (0:01:48)
```

Run executed — timed, non-zero duration, summary line present; full output at
`task-2-full.txt`, failure names at `task-2-failed-names.txt`.

Failure-NAME-set diff against `baseline-failed-names.txt` (both normalized by
stripping the `FAILED ` prefix and the ` - <reason>` tail, then `sort -u`):
**EMPTY, `diff` exit 0**, both sets 144 names.

Passed count reconciles exactly: an intermediate full run of the source change
alone (before the new tests) gave `144 failed, 12084 passed`; 12 084 + 23 new
tests = **12 107**. `tests/test_predrow.py` is 26 Task-1 tests + 23 new = 49,
all passing.

A same-session re-run of the suite at BASE (the five files reverted) gave `145
failed, 12083 passed` — one name MORE than the recorded baseline:
`tests/audit_2026_05_25/test_class_C17_perf_memory.py::
test_F026_multi_star_splits_bounded_for_moderate_input`, the C17-perf flake the
project memory already documents as pre-existing. It did not fire in the graded
run. Worth stating plainly: the recorded baseline is the reference the gate is
measured against, and the change matches it exactly.

Funnel lint: **no re-pin was needed**, contrary to the brief's expectation of a
third. Net line movement in `database.py` around `head_key` was −2 (the mirror
deletions roughly cancelled the `PredRow` additions), leaving its pre-existing
`atom_bypass` pattern at line 715, still inside Task 1's `(691, 723)`
`AllowEntry` range. `tests/test_funnel_lint.py` passes 9/9 including its
ALLOWLIST self-check, and it was run explicitly as well as inside the full
suite.

Inversion ledger: `task-2-inversions.md` — **no rows**, with each of the three
predicted inversion families accounted for and each behavior change evidenced by
a before/after probe against the reverted tree.

## Deliberate semantic changes (no test inverted; stated for review)

1. **`retract/1` builtin invalidates the ROW, not just the class.** The deleted
   identity-match loop in `builtins/database_ops.py` also did
   `pred_cls._dispatch_fn = None`, and the recompile below it is SKIPPED when
   the last clause goes — so without a replacement the predicate would keep
   dispatching to the function compiled from the clause it just lost. It is now
   `row.invalidate()`. Two differences from the old loop, both deliberate: it
   fires unconditionally after a successful removal (the old loop's identity
   match was the normal case anyway, since `db.assertz` appended the SAME
   object to both stores), and it clears `db._dispatch[key]` as well as the
   class's view, which the old code did not — so `db.get_dispatch` and
   `pred_cls._get_dispatch` can no longer disagree about a retracted predicate.

2. **The low-level `Database.assertz`/`asserta`/`retract` no longer skip LOCKED
   predicates when reaching the class — and this is ANSWER-CHANGING.**
   *(Framing corrected in fix round 1: the original text here claimed "the
   Database's view was already winning", which is false for the path that
   matters. `solve()` dispatches through the CLASS, and the class was reading
   its own private list, so a low-level `db.assertz` against a locked
   predicate did NOT change any answer. Demonstrated: a static
   `f3_static(1)` answers `[1]` before and `[1, 2]` after.)*

   `_pred_cls_for` returned `None` for a locked class, so the static lock was
   a PARTIAL bypass guard at this door — accidentally, as a side effect of the
   dual store, not by design. With the class reading the row, `db.assertz` is
   now a COMPLETE static-lock bypass.

   Every lock ENFORCEMENT point is unchanged — `PredicateMeta._assertz/
   _asserta/_retract` raise `RuntimeError` and the `assertz/1`-family builtins
   raise `permission_error`, both BEFORE touching anything — and
   `Database.assertz` itself never had a lock check of its own; it is the
   low-level door. But "the guard that was there by accident is gone" is a
   real widening, so it is now PINNED
   (`test_low_level_db_assertz_now_bypasses_the_static_lock_completely`) and
   CARRIED FORWARD: Task 3's mutation gate (`Database.mutate` — "checks
   lock/permission once, stamps provenance per-write") is where this door gets
   closed, and that test is the one to flip when it does. See
   `task-2-inversions.md`, "Fix round 1 — carry-forward for Task 3".

3. **`_get_dispatch` can now lazy-recompile where it used to raise.** If a
   bound class has no dispatch but its ROW has a `lazy_recompile` installed by
   some other path, `_get_dispatch` recompiles instead of raising
   `NotImplementedError`. Previously the class's own `_lazy_recompile` slot had
   to be set. This is the unification the task is for, and nothing pinned the
   old behavior.

## Self-review

Things I checked that could have gone wrong, and how:

- **Metaclass property vs. class `__dict__` shadowing.** A `property` on the
  metaclass is a DATA descriptor, so `type.__getattribute__` gives it priority
  over anything in `cls.__dict__`. Confirmed there is no leftover per-class
  attribute of any of the seven names (the `__init__` assignments are deleted),
  so no shadow is even possible.
- **Subclassing.** `PredicateMeta.__init__` sets `cls._row = None` in every
  class's OWN `__dict__`, so a subclass can never inherit a parent's row.
- **A class with no `_fields`.** `getattr(cls, "_fields", ()) or ()` in
  `_detached_row`; verified `class X(metaclass=PredicateMeta): pass` still
  answers `X._clauses == []` and `X._locked is False`.
- **Multi-arity same functor in one module.** `module_dict[functor]` holds ONE
  class, and step 4 / step 5 iterate `pending` in the same insertion order, so
  the class ends bound to the same row the old code's last write would have
  targeted. `_install` re-binding per compile makes each arity's dispatch land
  on its own row on the way through, which the old code did not manage.
- **The wholesale-dict-wipe pattern** (`tests/test_search.py:472-474`) — Task
  1's self-heal property still holds, and `test_search.py` is green.
- **Import cycle.** `_detached_row`'s `from clausal.logic.database import
  Database` is function-local and lazy, so nothing is imported at
  `predicate.py` module scope.
- **`PredRow` gained `slots=True`** while I was measuring. It is kept: tests
  pass, the object shrinks, and nothing sets ad-hoc attributes on a row.

## Concerns / notes for later tasks

- **`_find_pred_cls` in `builtins/database_ops.py` is still arity-blind.** It is
  the OTHER `module_dict.get(functor)` the identity todo complains about, and it
  is what supplies `pred_cls` to the `assertz/1`-family lock check and to the
  recompile. Deleting `_pred_cls_for` removed the mirror half of the problem,
  not the lookup half. Because `_install` now re-binds, a runtime `assertz` on
  `p/1` that finds a `p/3` class will MOVE that class onto `p/1`'s row (the old
  code instead wrote `p/1`'s dispatch into the `p/3` class's slot — differently
  wrong, and the mirror also corrupted `p/3`'s clause list). Out of scope here;
  it is the resolver the identity todo proposes, and Task 3's mutation gate is
  the natural home for it.
- **Two classes bound to the same row share `locked`.** Reachable only if two
  distinct classes are bound to the same `(db, functor, arity)`, which
  `module_dict` holding one class per name makes unlikely; flagged rather than
  defended against.
- **`record_clause_source`'s docstring** still says "the two deferred paths in
  `clausal.import_hook`". Those callers no longer exist (`grep` shows
  `compiler_v2.py:183` as the only call site). Pre-existing staleness, not
  touched.
- **`_clauses` costs 95 ns where it cost 20 ns**, ~50 ns of which is the
  metaclass descriptor call and cannot be removed while it is a property. It is
  off the per-goal path, and inlining the row's dict recovered only 4 ns, but if
  a later task finds a compile-time hot spot here, caching the row in a local
  across a compile is the lever.
- **Task 3 note:** the `dispatch_fn` setter is open this task by design and is
  what `_install` writes through. Gating it will need `_install`'s
  `pred_cls._dispatch_fn = fn` re-pointed at the mutation gate, not just
  `Database.mutate` — the class property is now a second door onto the same
  state.
- **Task 4 note:** the `$disp_` bake-in still reads `obj._dispatch_fn`; moving
  it to a row read is a one-line change in `globals_env._maybe_cache_dispatch`
  once `_bind_row` guarantees the row (it does not, for a detached builtin
  class — those have private rows, so the read must stay class-side or go
  through `cls._row`).

---

# Fix round 1

Four Important findings, two carrying controller rulings. All four addressed.
One commit on top of `9877876f`.

## F1 (RULING) — restore the instance face

**The finding is correct and my "byte-identical duck type" claim was false as
written.** Moving the seven names to METACLASS properties served `cls.x` and
silently broke `instance.x`: a metaclass descriptor is never consulted for
instance attribute lookup, and `namespace["__slots__"] = fields` leaves
instances no `__dict__` to fall back on, so all seven raised `AttributeError`
where they had returned the plain class attribute. Out-of-tree code reading
`instance._locked` was unguarded against it, and nothing in the suite noticed.

**Fix, per the ruling.** Every predicate class now also carries a plain
class-level `property` for each of the seven, delegating to the class (and so
to the row). Both faces coexist: `type.__getattribute__` finds the METACLASS
property first for `cls.x`; ordinary instance lookup finds the injected one for
`instance.x`.

Implementation points worth review:

- **Injected into `namespace` in `__new__`, not assigned after class
  creation.** `cls.__dict__` is a read-only mappingproxy, and a post-hoc
  `setattr(cls, "_locked", prop)` would be intercepted by the metaclass
  property of the same name and written to the ROW as a value. The namespace
  is the only door.
- **Skipped when the name is also a FIELD.** `__slots__` has already claimed
  that slot descriptor and declaring both is a `ValueError` at class creation
  — the same rule the existing `_clausal_new` / `_registered_at` guards
  follow. Pinned by `test_a_field_named_like_a_relocated_attribute_stays_a_field`
  (`make_predicate("FieldClash", ["_signature"])`: the instance reads the
  field, the class still reads the row).
- **Read-only.** `instance._locked = True` raised `AttributeError` before this
  task as well (not in `__slots__`, no instance `__dict__`), so a setter would
  be a NEW capability rather than a restored one. Pinned by
  `test_instance_writes_to_the_relocated_names_still_refuse`.
- **Zero per-class cost.** One shared `property` object per name at module
  scope (`_INSTANCE_STATE_PROPERTIES`); a property takes its instance at call
  time, so the same seven descriptors serve every predicate class.

Tests: `test_instances_still_resolve_all_seven_relocated_attributes` (all seven
defaults), `test_instance_reads_of_all_seven_are_live_through_the_class`
(mutate through the class and through the Database, read through an instance —
all seven, plus `inst._clauses is db._clauses[key]`, plus a second instance
made after the writes). Verified to bite: with the injection removed, both fail
with `AttributeError: 'InstFace' object has no attribute '_clauses'`.

## F2 (RULING) — confine vivification

**Also correct.** Task 1 accepted read-vivification because only `PredRow` read
the property; Task 2 then routed every `PredicateMeta._clauses` read through
it, which multiplied the minting sites without my noticing — `__repr__`,
`_clause_arity`, `_declared_arity` and the compiler's own inspections all
became mints, and a bound clause-less `-dynamic` class reported itself defined
merely for having been looked at. That contradicts Task 1's contract that
compile-install is the deliberate minting site.

**Fix, per the ruling.**

- `PredRow.clauses` getter loses the `setdefault`: it returns
  `self._db._clauses[key]` when that entry exists, else a per-row cached list
  held in a new `_unminted_clauses` field (created once, on first such read).
- New `PredRow.ensure_clauses()` — the single promotion point. Idempotent, and
  **identity-preserving**: it promotes that same cached object into the dict
  rather than a fresh one, so a caller that read the list, appended to it, and
  only then triggered a mint does not lose the append. It clears
  `_unminted_clauses` on the way out, so a later wholesale wipe leaves the row
  handing back a FRESH empty list rather than a stale populated one — which is
  what keeps Task 1's self-heal semantics (`row.clauses == []` after a wipe)
  exactly as they were.
- The `clauses` SETTER still mints (an explicit assignment is an explicit
  statement that the predicate has a clause list) and clears
  `_unminted_clauses` for the same identity reason.
- Callers, all of which MUTATE and therefore promote first:
  `Database.assertz` / `Database.asserta` (`row.ensure_clauses().append/insert`);
  `PredicateMeta._assertz` / `_asserta` via a new class-side
  `cls._ensure_clauses()`; `compiler_v2` step 4's clause install
  (`pred_cls._ensure_clauses()[:] = db_clauses`).
- `LogicModule.define_predicate` needs no call of its own: it delegates to
  `self.db.assertz`. Pinned by `test_define_predicate_mints_through_db_assertz`
  so a refactor that stops delegating is noticed.
- NOT called from `compiler/predicate._install`: that installs a DISPATCH, not
  clauses, and minting there would just move the flip the finding is about — a
  compiled clause-less `-dynamic` predicate must stay `is_defined() is False`,
  as it is at base.
- `retract` paths need no promotion: `Database.retract` returns early when the
  key is absent, and an unminted list can only be non-empty if something
  appended to it, which goes through `_assertz` and mints.

Tests: `test_reading_a_bound_clauseless_class_leaves_is_defined_false` (the
finding's exact probe, driving `__repr__`, `_clause_arity` and
`_declared_arity` through the row and asserting the key never appears),
`test_the_first_assertz_onto_a_bound_class_mints_and_aliases`,
`test_appending_to_an_unminted_read_is_invisible_until_promotion`,
`test_ensure_clauses_is_idempotent_and_keeps_the_existing_entry`. Four existing
tests adapted or inverted — all mine, all ledgered in `task-2-inversions.md`
under "Fix round 1 — inversions".

## F3 — the locked-class bypass is answer-changing; pinned, and the report amended

Correct, and my report's framing was wrong. I wrote that "the Database's view
was already winning" because the recompile path reads `db.clauses_for`. It was
NOT winning for the path that matters: `solve()` dispatches through the CLASS,
and the class read its own private list, so a low-level `db.assertz` against a
locked predicate changed no answer. It changes them now — reviewer-demonstrated
and independently reproduced here: a static `f3_static(1)` answers `[1]` before
and `[1, 2]` after.

Semantic change #2 in the section above is rewritten to say so plainly (the old
claim is retracted in place), and the change is now pinned by
`test_low_level_db_assertz_now_bypasses_the_static_lock_completely`, whose
docstring states that `Database.assertz` is a COMPLETE static-lock bypass (it
was a PARTIAL one, and only by accident of the dual store) and names Task 3's
`Database.mutate` gate as where the door closes. The test also asserts the
enforcement doors are still shut (`cls._assertz` still raises `RuntimeError`).
Carried forward in `task-2-inversions.md`.

## F4 — regression test for `retract/1`'s new logic, and the guard aligned

Correct on both counts.

- **Test added:** `test_retract_builtin_of_the_last_clause_leaves_no_answers`
  drives the real `retract/1` BUILTIN over a loaded `-dynamic` module —
  retract the only clause, assert `[]` answers, then re-assert and assert `[9]`.
  **Verified to bite:** with the `row.invalidate()` temporarily removed, the
  predicate still answers `[7]` after its only clause is retracted.
- **Guard aligned:** the invalidate is now behind
  `if (functor, arity) in db._dispatch`, matching the care
  `Database.assertz`/`asserta`/`retract` document. The unconditional form wrote
  `_dispatch[key] = None` for a never-compiled predicate, which flips
  `db.row(..., create=False)` from `None` to a row for a key nothing had
  touched. Pinned by
  `test_retract_builtin_does_not_create_a_dispatch_entry_it_did_not_find`.

## Trivial — the corroborating suite time

The report said 108 s and `task2-bench.txt` said 114 s; both were real numbers
from different runs of the same suite, quoted as if there were one. Both now
say 108-116 s (three runs: 114 s, 108 s, 116 s) against the 130 s base re-run.

## Covering tests and commands

```
/workspace/clausal/venv/bin/python -m pytest tests/test_predrow.py -q --tb=short
    61 passed
```
(49 before this round + 12 new; four of the 49 adapted or inverted.)

```
/workspace/clausal/venv/bin/python -m pytest tests/test_funnel_lint.py -q
    9 passed
```

Bite checks (each reverted immediately after):

```
# F1 — instance-face injection removed from PredicateMeta.__new__
  2 failed  AttributeError: 'InstFace' object has no attribute '_clauses'
            AttributeError: 'InstLive' object has no attribute '_clauses'
# F4 — row.invalidate() removed from the retract/1 builtin
  f4 before: [7] / retract solutions: 1 / f4 after retract: [7]   <-- stale
  (with the fix:                        f4 after retract: [])
```

## Full suite (REQUIRED re-run — F2 changes read semantics broadly)

```
/workspace/clausal/venv/bin/python -m pytest tests/ \
    --continue-on-collection-errors --tb=no -q -rf
```

```
144 failed, 12119 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error
in 115.60s (0:01:55)
```

Full output `task-2-fix1-full.txt`, names `task-2-fix1-failed-names.txt`.
Failure-NAME-set diff against `baseline-failed-names.txt`: **EMPTY, `diff` exit
0**, both sets 144 names. Passed reconciles: 12 107 + 12 new = **12 119**.

**Funnel-lint re-pin, at last.** The first pass needed none; F1's and F2's
additions to `database.py` moved `head_key`'s pre-existing `atom_bypass`
pattern out of Task 1's `(691, 723)` range, and the first fix-round suite run
caught it as one extra failure (`145 failed`) before the re-pin. Confirmed the
mechanical cause rather than assuming it: the lint named
`clausal/logic/database.py:766`, `def head_key` is now at line 742, and
`head_key` itself is byte-identical across all four shifts. `AllowEntry`
re-pinned to `(742, 774)` with a comment continuing the existing chain of shift
annotations. The suite run quoted above is the one AFTER the re-pin.

## Self-review of the fix round

- **Does the instance face create a new write path onto row state?** No — the
  injected properties have no setter, so `instance._locked = True` raises
  exactly as it did at base. Checked all seven.
- **Can the injected property shadow something?** It lives in `cls.__dict__`,
  which loses to the metaclass data descriptor for class-level access, so
  `cls._clauses` still reaches the row. Both directions pinned in the same
  test (`test_a_field_named_like_a_relocated_attribute_stays_a_field` covers
  the one case where they genuinely diverge).
- **Is `ensure_clauses` reachable from every mutation?** I walked the mutation
  sites rather than assuming: `db.assertz`/`asserta` (yes), `_assertz`/
  `_asserta` (yes), the `clauses` setter (mints directly), compiler_v2 step 4
  (yes), `db.retract`/`_retract`/`retract/1` (no promotion needed — argued
  above). Every remaining `row.clauses` use in the tree is a read.
- **Does the unminted list leak stale clauses across a wipe?**
  `ensure_clauses` clears `_unminted_clauses` on promotion, so after a wipe the
  next read builds a fresh empty one. That is exactly the assertion Task 1's
  wipe test makes (`row.clauses == []`), and it still passes.
- **Did I re-check the perf story?** The F2 getter replaces one `setdefault`
  with one `get` plus a `None` test on the hit path — no new call. The F1
  properties are reached only from instance access, which nothing on the
  dispatch path does. No re-measurement was warranted, and the suite time is
  unchanged (115.6 s, inside the 108-116 s band).
