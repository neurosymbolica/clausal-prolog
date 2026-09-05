# HAND-OFF: plan and execute Phase 4 — dict/set pair tagging + atom/string audit

**For the next Claude instance.** You are continuing the tagged-tuple program. Read
this file, then `implementation_plans/phase3-decomposition-and-p31-atom-pivot.md`
(the decomposition; every P3-x section now carries a DONE pointer), then
`implementation_plans/tagged-tuple-term-representation.md` §1/§1a/§1b/§3/§4/§6
before doing anything. Your job: write the full Phase 4 implementation plan (same
No-Placeholders discipline as the P3-1/P3-2/P3-3 plans — they are your template),
get the user's go-ahead on any new rulings, then execute via subagent-driven
development. CLONE ONLY (`/workspace/clausal-bug-fix`); never touch
`/workspace/clausal`.

## Where the program stands (2026-09-06)

- **Phases 0–2**: done (fast path, funnel, the `-tagged_terms` bridge; cells beat
  fast-pathed classes 1.8×).
- **toklex L0 + PrologReader L1/L2**: done (spec §1c STATUS block tells that story).
  The Phase 3 compiler work consumes that reader; it never builds a second one.
- **P3-1 atom pivot**: MERGED to clone main. Atoms are interned global `str`s; the
  identity machinery, `$atom`, shadowing warnings and `-overwrites` are deleted;
  `-hide` ships with the R1-revised separator US (0x1F).
- **P3-2 cell default flip**: MERGED to clone main. Cells are the unconditional
  compiled representation in every module; `-tagged_terms` is deleted; slot-0
  first-arg indexing is live behind a compile-time deep gate; one authorized C
  change (`_variables.c` tuple branches).
- **P3-3 state relocation + qualified goals**: implemented on branch
  `feat/p33-state-reloc`, 26 commits `d3cfe27a..022208ba` off base `1f86daf4`,
  plus the close-out doc commits. Full-suite failure-NAME diff EMPTY (reproduced
  twice); perf gate PASSED. Merge status at the time this file was written: the
  whole-branch final review and the merge are the P3-3 controller's last two
  steps — **check `git log --oneline -5` on clone main before assuming either
  happened.**
- Memory files (`tagged-tuple-term-design-parked`, `toklex-formalism-status`,
  `phase3-parser-user-owned`, `iso-prolog-compatibility-goal`) carry the same
  status — trust them.

**User rulings in force:** R1-revised (`⟨SEP⟩` = US 0x1F); R2 (`atom(X)` true for
every `str`); R3 (Phase 3 runs on the existing Python-syntax pipeline; the
reader-surface migration is a later, user-owned phase); R4/R10-REVISED (qualified
goals); R5–R9 (P3-2); R11 (cell-head assert for declared-dynamic only). C changes
are allowed where they make sense (standing since 2026-09-05). The user's stated
driver is **ISO Prolog compatibility** — weigh new semantics against it.

---

## P3-3's crown jewels (VERBATIM from the code at `022208ba`; re-verify line numbers, the structure is current)

These are the interfaces Phase 4 will read, write through, or extend. Every
signature below was grepped out of the tree at close-out.

### The authoritative store — `clausal/logic/database.py`

```python
WriteStamp = namedtuple("WriteStamp", "author kind detail")            # :66
DEFAULT_BACKEND = "python"                                             # :73

@dataclasses.dataclass(slots=True)
class PredRow:                                                         # :81
    _db: "Database"                                                    # :105
    _key: "tuple[str, int]"                                            # :106
    backend: str = DEFAULT_BACKEND                                     # :112
    locked: bool = False                                               # :113
    source: "tuple[str, str] | None" = None                            # :114
    writes: list = dataclasses.field(default_factory=list)             # :115
    dynamic_arities: "set[int] | None" = None                          # :124
    _unminted_clauses: "list | None" = ...                             # :130
    _txn: int = ...                                                    # :138
    detached: bool = False                                             # :144
```

`clauses` (:157 getter / :195 setter), `dispatch_fn` (:229/:233),
`lazy_recompile` (:265/:269), `signature` (:273/:277) and `dynamic` (:281/:285)
are **live properties over the Database's own containers**, not a second store —
a row self-heals across a wholesale `db._clauses.clear()`. Plus:

```python
def ensure_clauses(self) -> list:                                      # :209
def invalidate(self) -> None:                                          # :291
def record_write(self, author: str, kind: str, detail: Any = None) -> None:   # :303
def mutate(self, author: str, kind: str, detail: Any = None, through: Any = None):  # :316
```

Two rules Phase 4 must not break:
- **Reading `row.clauses` mints nothing.** `ensure_clauses()` is the ONE
  sanctioned promotion point and is identity-preserving; a plain read must never
  flip `is_defined()` False→True.
- **`invalidate()` is THE one invalidation point** — including for a backend's
  own derived caches.

### The mutation gate — same file

```python
WRITE_LOAD_CLAUSES  = "load-clauses"                                   # :352
WRITE_LOAD_DISPATCH = "load-dispatch"                                  # :353
WRITE_ASSERT        = "assert"                                         # :354
WRITE_RETRACT       = "retract"                                        # :355
WRITE_RECOMPILE     = "recompile"                                      # :356

def write_refusal(row: "PredRow", author: str, kind: str) -> "str | None":     # :367
def refusal_error(functor: str, arity: int, author: str, kind: str,
                  reason: str, channel: "str | None" = None) -> LogicException:  # :419

class Database:
    def row(self, functor: str, arity: int, create: bool = False) -> "PredRow | None":  # :468
    def load_author(self) -> str:                                      # :626
    def runtime_author(self) -> str:                                   # :634
    def refusal_for(self, functor: str, arity: int, *, author: str, kind: str,
                    detail: Any = None, through: Any = None) -> "LogicException | None":  # :660
    @contextlib.contextmanager
    def mutate(self, functor: str, arity: int, *, author: str, kind: str,
               detail: Any = None, through: Any = None):               # :687
```

Three facts about the policy that took a whole task and two fix rounds to get
right, and that a Phase 4 planner should not re-derive:

1. **An author is a canonical SOURCE PATH**, never a module name — one file
   legitimately compiles under two names in one process, and keying ownership on
   the name made a file refuse to load beside itself.
2. **`through=<PredicateMeta>` widens the blast radius.** An `-import_from`
   SHARES the exporter's class, so a write "here" can land on the exporter's
   predicate; the class's CURRENT row is therefore asked the same question. This
   is also how an ALIASED import is caught, where `module_dict.get(functor)`
   finds nothing.
3. **`refusal_for` is a pure dry run**, so a load asks about every predicate it
   will write BEFORE writing any of them — without it, a refusal partway through
   the write loop leaves the module it was protecting half-written.

`WRITE_RECOMPILE` is never refused. Transactions nest, and a nested `mutate`
inherits the outer transaction's authorization and stamp.

### The backend seam (what stencil-v2 consumes) — same file

```python
_BACKEND_CHOOSER: "Callable[[PredRow], str] | None" = None             # :445

class Database:
    @classmethod
    def set_backend_chooser(cls, fn: "Callable[[PredRow], str] | None"):    # :503
    @classmethod
    def backend_chooser(cls) -> "Callable[[PredRow], str] | None":          # :554
    @classmethod
    def register_backend(cls, name: str, installer: Callable) -> None:      # :560
    def backend_dispatch(self, functor: str, arity: int, fn: Callable) -> Callable:  # :574
```

Consumed at the compiler's ONE install choke point,
`clausal/logic/compiler/predicate.py::_install` (:2042; the call is
`fn = db.backend_dispatch(functor, arity, fn)` at :2088).

**What stencil-v2 consumes from this seam** (the scoping memo
`implementation_plans/stencil-v2-scoping-memo.md` calls its own integration seam
the one piece of the parked ~67.5k-line branch that cannot be revived by
re-extraction — it must be rewritten against exactly this):

- `set_backend_chooser(fn)` — the single hook, replacing the parked branch's
  ~1,196 LOC of ad-hoc backend selection inside `compiler/predicate.py`.
- `fn(row) -> str`, called **once per dispatch install** with the `PredRow`
  about to receive it, so the decision can read the predicate's clauses,
  signature, tabled-ness and `row.db`. The answer is recorded on `row.backend`
  (descriptive, not a request — setting it by hand installs nothing).
- `register_backend(name, installer)` with
  `installer(row, python_fn) -> Callable | None`: a backend **PRODUCES, it does
  not install**. `None` means "not mine" and falls back to the Python dispatch
  with `row.backend` left `"python"`. `"python"` cannot be re-registered; an
  unregistered chosen name raises `existence_error(backend, Name)` through the
  engine's error family.
- The returned callable goes through **the same transaction, the same tabling
  wrapper and the same provenance stamp** the Python dispatch would have.
- The chooser is process-wide because the decision is per ROW and a row names
  its own `db`; per-module policy reads `row.db`.
- With no chooser installed, `backend_dispatch` returns `fn` without so much as
  a row lookup — the default path costs one global read.

**Do not add a second invalidation channel or a second install site in Phase 4.**
That shape is exactly what the gate exists to make impossible.

### Class ↔ row linking — `clausal/logic/predicate.py`

```python
cls._row = None                                                        # :740 (per-class slot)
def _detached_row(cls):                                                # :765
def _bind_row(cls, db, functor: str, arity: int,
              authorized: bool = False) -> None:                       # :799
```

- `_detached_row()` is the **compatibility mode** for the ~22 out-of-tree
  `_get_dispatch` implementors and every `make_predicate` caller: a
  `PredicateMeta` minted outside a `.clausal` load gets a `PredRow` over a
  private single-predicate `Database` nobody else can reach, so all seven legacy
  attributes keep their old semantics with no `Database` in the caller's world.
  It is lazy (`database.py` imports `predicate.py`, so eager construction would
  be a cycle) and marked `detached=True`.
- `_bind_row` is a **policed write**: a class already reading another Database's
  real row is left where it is unless the caller passes `authorized`, which
  exactly two callers do — `compiler_v2` step 4's clause install and
  `specialization._install_specialized` — each from inside a write the gate has
  just cleared. *functor* is passed rather than read off `cls.__name__` because
  an aliased `-import_from` binds a class under a name that is not its own.

### The `$disp_` direct-read — `clausal/logic/compiler/globals_env.py`

`_disp_key(fname, arity)` :436; `_maybe_cache_dispatch(obj, name, arity)` :514,
whose two decisive lines are

```python
row = obj._row                                                         # :545
if row is None or not row.locked: return
```

The row read is the **CLASS's own** (`obj._row`), NOT `db.row(name, arity)` of
the compiling module: the call site this key serves resolves to THIS class, and
baking a same-named predicate from the compiling module's own Database would
silently redirect the call. **Only a LOCKED row is ever baked** — that is the
entire staleness argument, and it is why `invalidate()` on an unlocked row can
never orphan a baked reference.

---

## The cell-goal surfaces map (every function that learned cells)

| Surface | Location | What it learned |
|---|---|---|
| `cells.compound_cell_shape(x) -> (bool, functor)` | `clausal/logic/cells.py:266` | THE one spelling of the cell-shape check (`_cell_shape` with `TUPLE_TAG` excluded). Six former call sites consolidated onto it. |
| `cells.CELL_GOAL_CONTROL_FUNCTORS` | `cells.py:300` | `frozenset({",", ";", "->", "*->", "\\+"})` |
| `cells.refuse_control_construct_cell(cell, functor, context)` | `cells.py:319` | raises `type_error(callable_control_construct_unsupported, Cell)` |
| `cells.QUALIFIED_GOAL_FUNCTOR` | `cells.py:363` | `":"` |
| `cells.resolve_qualified_goal_cell(cell, context, calling_module=None) -> (module, G)` | `cells.py:372` | R10 resolution for `(":", M, G)`; peels nesting itself |
| `solve._term_to_goal(term)` | `clausal/logic/solve.py:180` | cell branch (:222) → qualified resolution, then the control-construct refusal |
| `solve._structural_key(term, var_index)` | `solve.py:248` | cell branch (:292) inside the `(list, tuple)` arm, so scalars pay nothing |
| `solve._goal_cache_key(goal, module)` | `solve.py:305` | admits cell goals (:320); tag `"cell"` |
| `solve._templatize_query_goal(goal)` | `solve.py:336` | cell + `":"` form (:419-440) |
| `solve._compile_as_query(goal, module)` | `solve.py:458` | **where the module switch lives** — every live qualified-goal entry funnels through this one strip |
| `solve.resolve_module(designator, calling_module=None, context="")` | `solve.py:578` | THE R10 chain |
| `solve._module_for_moduleless_solve(goal) -> (goal, module)` | `solve.py:658` | `solve(goal)` with no `module=`: a qualified cell names its own module; any other cell raises `existence_error(module, <cell>)` |
| `solve._strip_module_qualification(goal, module)` | `solve.py:731` | strips the top-level qualification |
| `solve._infer_module(goal)` | `solve.py:756` | RETIRED for cells (legacy class-walk kept for class terms) |
| `solve.solve(goal, module=None, trail=None)` | `solve.py:887` | `module=` resolves through `resolve_module` |
| `solve.query_wfs(...)` | `solve.py:993` | qualified goals (:1106-1120); the truth-annotation consumer still holds the pre-Task-6 module contract |
| `solve._tabled_entry_for_goal(goal, module, trail)` | `solve.py:1079` | treats every plain tuple goal as a cell; swallows `LogicException` from resolution. **The legacy dotted-`Call` walk here is deliberately untouched** — convergence todo filed |
| `higher_order._resolve_named_goal(db, goal_val, extra_args, context)` | `clausal/logic/builtins/higher_order.py:30` | cells AND bare atoms as goals; folds `call(M:G, Extra…)` (`>= 2` slots) and recurses once |
| `higher_order._calling_module(db)` | `higher_order.py:127` | |
| `higher_order._namespace_dispatch(db, functor, arity)` | `higher_order.py:142` | the second lookup: db dispatch table first, then the module NAMESPACE (via `_find_pred_cls`/`_home_db`) |
| `higher_order._make_call_goal_factory(extra_n)` | `higher_order.py:179` | `call_goal/1..8` + `call/1..8` moved from `_BUILTINS` to `_DB_BUILTINS` as native-trampoline factories — **this is what makes `call/N` resolve against the CALLING module** |
| `_registry._stateless_dispatch(functor, arity)` | `clausal/logic/builtins/_registry.py:55` | the one db-less route for the three registry paths; honours a `_db_optional` flag on the factory |
| `database_ops._build_clause(term_val, context, db, module_dict)` | `clausal/logic/builtins/database_ops.py:53` | cell heads for `assertz`/`asserta` (R11) |
| `database_ops._freeze_asserted_head_args(head)` | `database_ops.py:87` | assert path only; `retract` keeps sharing |
| `database_ops._declared_here_at_arity(module_dict, functor, ...)` | `database_ops.py:214` | reads `__clausal_functor_signatures__` via `functor_signature_for` |
| `database_ops._find_pred_cls(functor, arity, ...)` / `_home_db(db, pred_cls)` | `database_ops.py:246` / `:288` | spelling→class resolution + the owner's db |
| `database.head_key(head)` / `_stored_head_key(head, channel)` | `clausal/logic/database.py:1224` / `:1267` | cell branch `("f", a, b) → ("f", 2)`; the low-level door REFUSES a cell head with `type_error(callable, Cell)` |

**Where the R10 resolution chain lives:** `solve.resolve_module` (`solve.py:578`)
is the single answer to "which module does this designator mean?". Its three
consumers are `cells.resolve_qualified_goal_cell` (`cells.py:372`, for the
`(":", M, G)` cell), `solve(goal, module=...)` (`solve.py:887`), and `call/N`
(`higher_order.py:101`). The module SWITCH itself is in `_compile_as_query`
(`solve.py:458`), which is the condition the Task 6 review verified: every live
qualified-goal entry funnels through that one strip.

### Known gaps in the cell-goal surface (live, filed)

- A cell goal NESTED in `And`/`Or`/`Not` or written in a CLAUSE BODY is still
  not lowered (`terms_to_goalop._convert_inner` has no cell branch).
- `call/N` resolves a cell and an atom by NAME but not a runtime-built CLASS
  term (`_get_dispatch` is on the metaclass, so only the class answers `hasattr`).
- `control.py`'s goal builtins (`time_goal`, `count_all`, `setup_call_cleanup`,
  `call_cleanup`, `freeze`, `when`) do not recognise cells at all.
- A bare body goal `k` for a `/0` predicate does not compile (local and imported
  alike).

---

## Deferred / parked from P3-3 (read before scoping Phase 4)

**Carried to the whole-branch final review** (fix-wave candidates, not defects
that ship): `Database.retract` lacks the `_stored_head_key` treatment its
`assertz` twin got; a duplicate table-abolish outside the gate in
`compiler/predicate.py` with a stale justification comment; `_install` opens two
transactions/two stamps per install; the lazy-recompile direct write in
`database.py` is an uncommented twin of the one in `predicate.py`;
`_belongs_elsewhere` (`compiler_v2.py`) is a hand-copy of `_bind_row`'s police
predicate — two copies of one policy; `_local_functor_arities` duplicates
`_predicate_functor_names`' declaration walk (`compiler_v2.py:1539`); the
`row.backend` write sits outside `mutate` and takes no stamp;
`backend_dispatch` mints a row per install once any chooser is set;
`register_backend` silently overwrites and has no `unregister`;
`clausal/reflection.py:1019`'s `_SKIPPED_ITEMS` is a DENYLIST (future worklist
items leak by default); source-positioning of the `-specialize` clobber refusal;
`BuiltinPredicate._dispatch_fn` (`_registry.py:300,310,314`) is a rowless
instance attribute sharing a name with the gated metaclass property and wants
one clarifying comment; `clausal/import_diagnostics.py:510` still credits via
`_clauses_source` (nothing reads `row.writes` yet).

**Todos filed on this branch** (by filename, under `todo/`):

- `a-cell-goal-nested-in-a-control-node-is-not-lowered-2026-09-06.md`
- `assert-stores-live-vars-for-class-term-and-cell-spellings-2026-09-06.md`
- `call-n-does-not-resolve-a-runtime-built-class-term-goal-2026-09-06.md`
- `bare-zero-arity-predicate-body-goal-does-not-compile-2026-09-06.md`
- `imported-atom-shadows-local-arity-n-predicate-at-call-site-2026-09-06.md`
  (the Task 5b source todo — closed by Task 5b; moved to `todo/done/` at close-out)
- `importer-without-dynamic-locks-shared-dynamic-predicate-for-its-owner-2026-09-05.md`
- `listing-of-a-bare-atom-lists-only-arity-0-2026-09-06.md` (names
  `predicate_rows(module)` as its future consumer — that helper is still unbuilt,
  deliberately, for want of a second consumer)
- `mixed-apply-and-read-of-imported-dual-declared-atom-gets-the-class-2026-09-06.md`
- `query-cache-keys-on-id-of-a-possibly-transient-module-2026-09-06.md`
- `table-times-specialize-refusal-may-be-over-broad-2026-09-06.md`
- `tabled-entry-dotted-walk-should-converge-on-resolve-module-2026-09-06.md`
- Two head-arg indexing todos rode in from the mid-phase hotfix:
  `dotted-loadattr-value-head-args-not-indexed-2026-09-05.md` and
  `imported-non-atom-constant-head-args-unreachable-2026-09-05.md`

**Closed by P3-3** (in `todo/done/`):
`a-shared-predicate-has-no-single-mutation-gate.md`,
`predicate-identity-is-keyed-on-spelling-not-on-the-class.md`,
`first-arg-index-partially-ground-instance-keys-into-bucket-2026-09-05.md`,
`atom-declared-name-applied-as-functor-is-silent-2026-09-05.md`,
`registration-asserting-probes-for-inspection-builtins-2026-09-05.md`.

---

## Phase 4 scope (from the spec + decomposition — this is the phase you plan)

Two workstreams, from the decomposition's phase list ("pair migration + semantic
audit", estimated 1–2 weeks, *grew* because the audit is user-visible semantics):

### 1. dict/set pair tagging

Spec §6 hazard 2, RE-AFFIRMED as Phase 4 at P3-2 close-out and again here: dict
and set pairs are **plain 2-tuples today** and become `(tuple, k, v)` —
`TUPLE_TAG`-tagged, like every other tuple DATA occurrence since P3-2.
**Migrate, don't exempt.**

Recon anchors:

- `clausal/logic/builtins/dict_set.py` — `_pair_key(pair)` :69 and
  `_pair_value(pair)` :77 are the two chokepoints; both currently accept
  `isinstance(pair, (list, tuple)) and len(pair) == 2` and raise `TypeError`
  otherwise. Everything else in that file reads pairs through them or through
  `_dict_input(v)` (:83), which accepts a plain Python `dict` wherever a
  `DictTerm` is accepted — a deliberate softness with its own closed todo, and a
  trap for a migration that assumes `DictTerm`.
- `clausal/terms.py` — `class DictTerm` :1648, `class SetTerm` :1729.
- `clausal/logic/cells.py` — `TUPLE_TAG = tuple` :131; the tag domain is
  `{str} ∪ {TUPLE_TAG}` and §1b says it **contracts, never extends**. A tagged
  pair is `(tuple, k, v)`, i.e. length 3 — every `len(pair) == 2` test in the
  tree is a migration site.
- The spec names **19 `.clausal` stdlib/corpus files to audit for
  destructuring**; re-derive that set with a grep for pair patterns rather than
  trusting the number.
- Interaction with P3-2's slot-0 first-arg indexing: a `(tuple, k, v)` pair keys
  on `TUPLE_TAG` at slot 0, where a bare 2-tuple fell to `_INDEX_VAR`. Check
  `clausal/logic/compiler/arg_index.py`'s `_arg_to_index_key` (:64) /
  `_runtime_arg_key` (:303) and the deep gate before assuming the change is
  invisible to dispatch (`_INDEX_VAR` sentinel at :38).

### 2. atom/string collapse audit

R2 made `atom(X)` true for every `str`, which means `atom/1` and `string/1` are
now **co-extensional**. The spec scheduled the consequences here:

- `clausal/logic/builtins/type_checks.py` — `string/1` at :53 is retained as a
  compatibility alias; its deprecation and its relationship to `atomic` were
  explicitly deferred to Phase 4. `:335` and `:348` carry the type-name tables
  that already fold `atom`/`string`/`str` together.
- `clausal/logic/builtins/chars.py` — `atom_chars/2` already emitted plain
  `str`s for its chars→atom direction BEFORE the pivot, so the pre-P3-1
  semantics were internally inconsistent; the collapse fixes an existing blur
  rather than creating one. Audit the whole `atom_*`/`number_*`/`sub_atom`
  family for the same shape.
- **`docs/dicts_sets.md:154` is now WRONG**: it teaches that "an atom key and
  the same-spelled string key are **distinct**". Post-P3-1 they are the same
  `str`. Every doc, golden output and test that relies on atom-vs-string dict-key
  distinctness or on atom ORDERING is an audit site (spec §6 hazard 5).
- Tabling / standard order / indexing collapse onto slot 0 (the decomposition's
  own words) — the ordering half of the audit.
- Weigh every ruling here against the **ISO compatibility driver**; `string/1`
  is not ISO, and "co-extensional alias" vs "deprecate" is a user ruling, not an
  implementer's call.

### Explicitly NOT Phase 4

Class REMOVAL for predicates and the `packages/` migration (Phase 5, per
`implementation_plans/python-seam-classes-as-functors.md`, which supersedes §5a's
TermProxy design); the reader-surface migration (user-owned, R3); stencil-v2
itself (its own plan, consuming the seam above, user-timed).

---

## Canonical-sync note

P3-3 is clone-side work. The next sync of this work to canonical repeats the
coordination protocol used for P3-1 and P3-2 — it is not optional, and each leg
of it has caught something real at least once:

1. **Hold and announce.** Announce the intended sync to the peer sessions working
   downstream of this engine BEFORE pushing, and hold until they answer. They run
   their own acceptance work against the engine and a landing that surprises them
   costs more than the wait. Their reply is also where a "we need this sooner"
   request surfaces, which can turn a phase-end sync into a main-line hotfix.
2. **Pre-sync barrier scan of the WHOLE crossing range** — not just your own
   commits. The clone's main carries other sessions' commits, so the range that
   crosses to canonical is wider than the range you wrote. Scan it for
   downstream-project references, peer project names, their battery sizes and
   their corpus domain names, and genericize before the crossing (precedent:
   commit `be08ba4f`). Historical mentions already in canonical history are
   clues, not code — do NOT propose history rewrites over them.
3. **The peers' own acceptance batteries and pins are the bar** — theirs, run by
   them, on top of this repo's own green suite. A phase that changes lowering or
   resolution (this one changes both) must also show their previously-red domains
   green on their corpus gate before it lands.
4. **Check whether a fast-forward is even possible first.** Canonical has been
   AHEAD of the clone before (7 commits, 2026-09-01), in which case the answer is
   cherry-pick, not merge.

Deliberately generic here: the peer project names, their battery sizes and their
corpus domain names live in the git-ignored SDD ledger and the controller's
memory, not in a committed file.

---

## Process discipline (carried forward, plus what P3-3 learned)

- **SDD**: worktree per plan (`git worktree add .claude/worktrees/<name>
  -b feat/<name>` from clone HEAD — NOT origin), `EnterWorktree(path)`,
  `build_ext --inplace`, fresh baseline capture (full suite, failure-NAME set,
  `--continue-on-collection-errors`, `/workspace/clausal/venv/bin/python` FROM
  the worktree), ledger in the sdd-workspace, task briefs, per-task review + fix
  loops, whole-branch final review (top-tier model), merge only after an EMPTY
  (or fully reconciled + ledgered) name-diff.
- **NEVER `git add -A`** — the clone is shared with other instances; `-A` sweeps
  their in-progress todos and WIP into your commit. Stage explicit paths. **NEVER
  `git stash`** — the stash is a single shared stack across worktrees/sessions;
  use a throwaway branch or a diff-and-revert-in-place for TDD-red checks.
- **The sandbox refuses compound shell commands that chain git.** Run git
  commands one per invocation; do not build `cd X && git …` pipelines.
- **FOREGROUND ONLY for subagent test runs, and do not block on agent output.**
  Implementer subagents have repeatedly run the full suite with
  `run_in_background` and then stalled waiting for a notification that never
  comes. If a subagent goes quiet with uncommitted work, message it a finish
  instruction — state is recoverable from `git status` plus the scratchpad files.
  An implementer can also become **non-resumable after context compaction**
  (P3-3 Task 3 fix round 2): when that happens, dispatch a FRESH implementer at
  the same tier with a self-contained brief and ledger the fact that the skill's
  resume rule could not be honoured.
- **Survey the brief's file attributions before dispatching it.** P3-3 corrected
  a plan anchor at Task 0 (`add_clause` was really `Database.define_predicate`)
  and a whole file attribution at Task 8 (the plan said `compiler_v2.py (listing)`;
  `listing/1` actually lives in `clausal/logic/builtins/io.py`). Both were caught
  by a pre-dispatch grep that cost minutes; either would have cost a task.
- **Say "Task N", not "TN"** — in chat, in the ledger, in commits and in
  dispatches (user preference, 2026-09-05).
- **Reviews: instruct reviewers to PROBE, not trust.** P3-3's reviews caught,
  among others, a load-break introduced by a "cheap pass" fix, a false refusal
  driven by declaration ORDER, an owner's answers silently changing under an
  importer's globals, and a doc example that raised. Spot-check inversion ledgers
  adversarially, and treat "the report says RED" as unverified until the literal
  output is in the report.
- **`_db_optional` must be set on the STORED factory.** The `_db_builtin`
  decorator returns the UNWRAPPED function, so setting the flag on the decorated
  name sets it on the wrong object and the builtin silently loses its dispatch
  (`clausal/logic/builtins/io.py:359` is the correct spelling:
  `_DB_BUILTINS[("listing", 1)]._db_optional = True`).
- **`/` in `.clausal` source is arithmetic `Div`, not the ISO indicator.** A
  doc example written as `listing(fib/2)` compiles to a `Div` operator node; the
  current surface has no other spelling, which is why `listing/1` now accepts
  that node. Any future ISO-indicator surface work has to reckon with this.
- **Perf gate**: interleaved, alternating-order A/B vs the branch base on
  `bench_struct_tabling` and `bench_fib`; **median of the per-pair head/base
  ratios**; >3% fails. Every bench process must assert the branch name is in
  `clausal.__file__` BEFORE running any workload — a P3-2 bench script silently
  imported canonical `/workspace/clausal` once and produced a reproducible
  70×-wrong first result.
- **Bench method — copy BOTH A/B trees onto the same filesystem before
  measuring.** `bench_struct_tabling` reloads its `.clausal` fixture INSIDE the
  timed region, so an A/B with base on an overlay mount and head on virtiofs
  charges the filesystem difference to head; P3-3 Tasks 2 and 4 did exactly that
  (their numbers still passed, so nothing needs re-litigating). P3-3 Task 9's
  report §3 is the worked method and the numbers: three runs of one driver on
  byte-identical code landed at +2.54% / +1.94% / +1.41%, a 1.1-point spread
  against a base-side stdev of 1–1.5%. The alternative is to gate on the query
  half (98% of the macro) instead of the macro.
- **Perf headroom is thin, and this is a standing constraint on Phase 4.**
  P3-3's macro sits at a consistent **+1.4–2.5% head/base residue** under the 3%
  bar, accepted under the plan's declared carried risk (Task 2's read-through
  property on the dispatch hot path, +1 `dict.get` per goal ≈ 23 ns; the C lever
  is available by ruling and was not reached for). The residue is *unexplained by
  call counts* — the query half moves +0.10% and the counts move +701 on a 2.07 s
  run. **Any future change that adds hot-path cost must instrument first**
  (cProfile call counts; query-half vs load-half split) rather than trust the
  macro, because the macro alone can no longer distinguish 1% of real work from
  its own noise. Quote `task-9-report.md` §3 (copied to
  `implementation_plans/p33-execution-record/task-9-report.md`) for the numbers.
- **Information barrier**: keep downstream/peer project information out of NEW
  commits — project names, their battery sizes, their corpus domain names. Write
  them in the git-ignored ledger; genericize in anything committed. Scan before
  merging or syncing.
- `eval_harness` is GATE_CORE — off limits (editing it requires syncing two
  out-of-tree forks). The `_get_dispatch` signature is frozen (~22 out-of-tree
  implementors); P3-3 preserved it through `_detached_row`, and Phase 4 must too.
- C changes are allowed where they make sense (user ruling, standing since
  2026-09-05) — but the C twins (`_variables.c`, `_tabling_core.c`,
  `_constraints_dif.c`, `_clpfd_core.c`) move in LOCK-STEP with the Python
  walkers, and drift is silent corruption rather than errors (spec §6 hazard 3).
  A pair-shape change is exactly the kind of thing that reaches them.

## After Phase 4

Phase 5 — the Python seam
(`implementation_plans/python-seam-classes-as-functors.md`, which supersedes
§5a's TermProxy design), the `packages/` migration, docs including the
strict-atoms migration note, and the class REMOVAL that P3-3's read-through
shells were built to make possible. The stencil-v2 revival
(`implementation_plans/stencil-v2-scoping-memo.md` +
`implementation_plans/copy-patch-cells-assessment-2026-09-05.md`) gets its own
full plan, user-timed, now that the seam it rewrites against is real.
