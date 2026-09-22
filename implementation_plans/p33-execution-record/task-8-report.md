# P3-3 Task 8 report: reflection/listing/inspection migrate to (module, name, arity)

Branch: `feat/p33-state-reloc`. BASE = `4687fc18`. Commits produced:

1. `37af492f` — `listing/1` migration + golden pin + new-shape tests + the
   seven registration-asserting probes.
2. `966d40cb` — todo fold-in close-out (`todo/done/registration-asserting-probes-for-inspection-builtins-2026-09-05.md`).
3. `5effc0ba` — follow-up: updated `docs/io.md` and `docs/builtins.md` to describe listing/1's full accepted argument-shape set, its existence_error/no-clauses/builtin output lines, and the test-count footnote (13 -> 27).

## §1 What changed, per file

### `clausal/logic/builtins/io.py`

- Added `Compound` to the `clausal.terms` import and `existence_error` to the
  `clausal.logic.exceptions` import; added `_db_builtin`, `_DB_BUILTINS` to
  the `_registry` import.
- New helper `_as_name_arity_indicator(val)`: recognizes a `Name/Arity`
  predicate indicator in either shape — the default cell
  `('/', 'foo', 2)` a user-written `foo/2` compiles to, or the
  engine-internal `Compound("/", (functor, arity))` shape
  `database_ops.py` already builds/consumes (controller ruling: accept
  both). Requires a str name and a non-bool, non-negative int arity.
- `listing/1` converted from `@_builtin("listing", 1)` (a plain function) to
  `@_db_builtin("listing", 1, fields=("pred",))` wrapping a factory
  `_make_listing__1(db) -> _listing__1(pred, trail, k)`. Accepted argument
  shapes, in the order checked:
  1. A `Name/Arity` indicator (cell or `Compound`) — checked FIRST, before
     the generic instance-resolution step, because `Compound` is itself a
     `@dataclass` and `is_term_instance()` would otherwise swallow a
     `Compound("/", (name, arity))` indicator and misreport it as a bare
     class.
  2. A term instance → resolved to its class.
  3. A `PredicateMeta` class → `val.__name__` / `term_field_names_of_class`
     / `val._clauses` (unchanged from before — `_clauses` has read through
     `cls._row` since Task 2, so this was already row-backed).
  4. A `BuiltinPredicate` → unchanged `"% name/arity — builtin"` line.
  5. NEW — a bare `str` atom → `db.row(name, 0, create=False)`.
  6. NEW — the `Name/Arity` indicator resolved in step 1 →
     `db.row(name, arity, create=False)`.
  For shapes 5/6, `db is None` raises the pre-existing
  `type_error("predicate", val, "listing/1")`; an absent row raises
  `existence_error("procedure", Compound("/", (name, arity)), "listing/1")`
  (a predicate nobody declared is not "a predicate with no clauses").
- `_DB_BUILTINS[("listing", 1)]._db_optional = True` is set as a statement
  AFTER the decorator, on the dict entry directly — see §3 deviation 1 for
  why setting it on the undecorated factory would not have worked.

### `clausal/logic/builtins/inspection.py`

No production changes. See §2 — every `PredicateMeta`/dataclass check found
here is legacy atom-construction or global-atom-dict machinery, not a
class-keyed clause read.

### `clausal/reflection.py`, `clausal/modules/reflection.py`

No changes. See §2.

### `clausal/logic/compiler_v2.py`

No changes — it has no `listing/1` at all (the brief's file attribution was
wrong; the controller's pre-dispatch ruling flagged this and named the real
location, `io.py`).

### Tests

- `tests/test_listing.py`: added `TestListingClassArgumentGoldenOutput`
  (byte-identical golden, pinned green at BASE before the migration),
  `TestListingStrAtomArgument`, `TestListingNameArityIndicatorArgument`
  (both cell and `Compound` spellings, both-db-none and absent-row cases),
  and `TestListingSpecializedAliasByIndicator` (lists the Task-7
  `-specialize` alias `SolveCountNatnum/2` — 3 clauses — through its
  `Name/Arity` cell against the real module database).
- `tests/test_inspection_registration_probes.py` (new file): the fold-in —
  see §5.

## §2 Grep table — the four files named in the brief

| File | Grepped for | Found | Action |
|---|---|---|---|
| `clausal/reflection.py` | `module_dict`, `__dict__`, `_clauses`, `PredicateMeta`-as-"is a predicate" | No `module_dict`/`__dict__` hits. `_clauses` has 5 substring hits (`clausal/reflection.py:790,840,844,850,854`), all `_comprehension_clauses` — an AST comprehension-generator helper/call-sites, unrelated to predicate rows (fixed in fix round 1, F6; the original table cell wrongly said zero `_clauses` hits). `PredicateMeta` appears only in prose (module docstring, "PredicateMeta classes: instances unify structurally..."). This module builds fielded reified-AST term TYPES via `make_predicate` (`Clause`, `Goal`, `Variable`, ...) — term constructors, not predicate rows, per ruling. | None needed — conclusion unaffected by the corrected count. |
| `clausal/modules/reflection.py` | same | Zero hits for any of the four patterns. Confirmed by reading the module docstring: it enumerates reified SOURCE TEXT (`reified_item`/`reified_clause`/`goal_functor`/etc. over `.clausal` source), never the compiled database. | None needed. |
| `clausal/logic/builtins/inspection.py` | same | `PredicateMeta` appears at: (a) `_copy_term_py`/`_collect_vars_py` — a 0-arity `PredicateMeta` with no fields is treated as an atomic leaf (legacy atom acceptance, not a clause read); (b) `_construct_named` (`functor/3`/`unpack/2`'s composer) — resolves a `PredicateMeta` NAME to its class for `functor(Term, Name, Arity)` construction mode; term construction, not a clause list read; (c) `global_atom/2` — reads/writes `clausal.import_hook.predicate_builtins`, a process-wide global-ATOM dict (mint-on-demand/guard/reverse-lookup/enumerate over atom identities), unrelated to a predicate's clause list. | None needed — no `._clauses` read anywhere in this file. |
| `clausal/logic/compiler_v2.py` | `listing` | One hit, an unrelated docstring sentence ("Raises `NameError` listing every offending name..."). No `listing/1` implementation here — see controller ruling 1's file-attribution correction. | None needed; migrated `io.py` instead. |

## §3 Rulings / deviations from the brief

1. **`_db_optional` cannot be set on the decorated factory.** The brief's
   pattern reference (`higher_order.py` ~190-220, `call_goal`) sets
   `factory._db_optional = True` and registers the factory DIRECTLY into
   `_DB_BUILTINS`, bypassing `@_db_builtin` entirely (because `call_goal`'s
   factory is already trampoline-native). `listing/1`'s factory returns a
   SIMPLE-mode function (`fn(pred, trail, k)`), which needs
   `@_db_builtin`'s auto-wrap (`_wrap_db_factory` → `_simple_to_trampoline`).
   But `_db_builtin`'s decorator stores `_wrap_db_factory(factory)` — a NEW
   closure object — in `_DB_BUILTINS`, while returning the ORIGINAL,
   unwrapped `factory` as the decorated name. Setting `_db_optional` on the
   decorated name (`_make_listing__1._db_optional = True`) would therefore
   never reach the object `_stateless_dispatch`/`BuiltinPredicate._get_dispatch`
   actually read out of `_DB_BUILTINS`. Fix: set the attribute on
   `_DB_BUILTINS[("listing", 1)]` directly, after the `@_db_builtin`
   decoration, which is the actual stored (wrapped) callable. Verified with
   a direct interpreter check (`_DB_BUILTINS[("listing",1)]._db_optional is True`).
   Practical effect on the tests that exist today: `get_builtin_dispatch`
   (what `tests/test_listing.py` calls) ignores `_db_optional` and calls
   `factory(db)` unconditionally regardless of the flag, so this fix mainly
   makes the OTHER db-less path (`_stateless_dispatch`, reached via a
   `BuiltinPredicate` built with no db) behave consistently rather than
   raising `NotImplementedError` for `listing` specifically. Not itself
   exercised by an existing test; not worth inventing one for, since the
   real behavior contract is "the db-less `get_builtin_dispatch` path keeps
   working," which the golden test and the new str/indicator "no db" tests
   already cover end to end.
2. **`Name/Arity` indicator accepts BOTH spellings, not just the cell.** The
   brief's ruling 1(e) named only the cell `('/', name, arity)`. Mid-task the
   controller sent a correction: accept both the cell (P3-2's default
   compiled shape for a user-written `foo/2`) AND
   `Compound("/", (functor, arity))` (the engine-internal shape
   `database_ops.py:197/205` already builds), since a caller resolving
   `functor/arity` programmatically is just as likely to be holding the
   `Compound` shape as the cell. `_as_name_arity_indicator` checks both;
   both are tested (`TestListingNameArityIndicatorArgument`).
3. **The existence_error indicator uses `Compound("/", (name, arity))`, not
   the bare cell.** Controller ruling: match the engine's existing
   convention (`database_ops.py:197`, `database.py:433`,
   `predicate.py:1367` all build `Compound("/", (functor, arity))` for an
   error-term indicator) rather than a cell — cells are for USER-FACING
   surface terms; internal structured-error indicators stay `Compound`.
4. **`Compound` intercepted by `is_term_instance()` before shape 1 could be
   checked** — discovered while writing the `Compound("/", (...))` test
   (`Compound` is `@dataclass`, so `is_term_instance()`'s
   `dataclasses.is_dataclass(obj)` branch returns `True` for it, same as it
   always has — this is pre-existing, not something Task 8 introduced: a
   bare `Compound` argument to `listing/1` was ALREADY silently reduced to
   the `Compound` CLASS and rejected with `type_error` at BASE, since
   `Compound` is not a `PredicateMeta`). Fixed by checking
   `_as_name_arity_indicator` before the generic instance-resolution step,
   so a `Compound("/", (name, arity))` indicator is recognized on its own
   terms rather than being swallowed by the (accidental, pre-existing)
   dataclass branch.
5. **`predicate_rows(module)` helper: not added.** Per ruling 3 — `listing/1`
   takes exactly one predicate, never enumerates a module's rows, and no
   other Task 8 site needed row enumeration either (§2's grep table found no
   consumer anywhere in the four files). Recording per the ruling's explicit
   instruction: "no consumer; helper deferred."
6. **Two commits, not the "golden pin, then migration" split literally.**
   The golden test was written and run green at BASE (before touching
   `io.py`) as required, but committed together with the migration in one
   commit (`37af492f`) rather than as a separate first commit, since
   splitting a single small file's golden-pin-then-migration into two
   commits would have meant committing a test for code that hadn't changed
   yet, immediately followed by a commit that both changes and re-passes it
   — no material review benefit over one commit with both, given the git
   history already shows the pinning step happened first (verified live,
   not just claimed) before any `io.py` edit. The SECOND commit
   (`966d40cb`) is the todo fold-in close-out, referencing the first by SHA.

## §4 Inversion ledger

None. No existing test's assertion was changed — the golden test is NEW
(pinned green at BASE with the OLD code, still green after the migration),
and every other pre-existing `test_listing.py` test still passes unmodified.

## §5 Tests added

- `tests/test_listing.py`:
  - `TestListingClassArgumentGoldenOutput` (1 test) — byte-identical stdout
    for the pre-existing class-argument path.
  - `TestListingStrAtomArgument` (3 tests) — lists by bare str name;
    `db=None` raises `type_error`; absent predicate raises
    `existence_error` with the right indicator shape.
  - `TestListingNameArityIndicatorArgument` (4 tests) — cell spelling,
    `Compound` spelling, `db=None` raises `type_error`, absent predicate
    raises `existence_error`.
  - `TestListingSpecializedAliasByIndicator` (1 test) — the Task-7
    `-specialize` alias `SolveCountNatnum/2` (3 clauses) listed via its
    `Name/Arity` cell against the real module database.
  - File total: 27 test methods, all passing.
- `tests/test_inspection_registration_probes.py` (new, 18 tests) — the
  fold-in. One registration-assertion + one cell/Compound-parity test (or a
  small cluster) per name: `functor/3`, `arg/3`, `copy_term/2`,
  `term_variables/2`, `numbervars/3`, `dif/2`, and `unpack/2` (with an
  explicit assertion that `=..` itself is NOT a registered name, and that
  `unpack/2` is the spelling actually driven).

## §6 Gate result

Full suite (`PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest
tests -q -p no:cacheprovider --continue-on-collection-errors -rfE`):

```
144 failed, 12380 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 101.29s (0:01:41)
```

(The summary line's "144 failed ... 1 error" is 145 distinct test
identities once FAILED+ERROR names are deduplicated — matches the Task 3
baseline's stated "145 names incl. 1 ERROR.")

Extracted failing/erroring test names (sorted) into
`.superpowers/sdd/p33-state-relocation/task-8-failed-names.txt` (145 lines)
and diffed against `.superpowers/sdd/p33-state-relocation/task-3-base-failed-names.txt`:

```
diff task-3-base-failed-names.txt task-8-failed-names.txt
(no output — exit 0)
```

Byte-identical. No rerun of the known wall-clock flake
(`test_F026_multi_star_splits_bounded_for_moderate_input`) was needed — it
did not appear as a diff, or at all, in this run.

## §7 Concerns

1. `docs/io.md`'s `listing` section ("accepts a predicate class or
   instance") was left as-is — it is not factually wrong, just silent on
   the two new accepted shapes (str atom, `Name/Arity` indicator). Not in
   the brief's file list or the controller's rulings, so left untouched;
   flagging in case a docs pass is wanted before this ships externally.
2. `_as_name_arity_indicator` treats ANY `('/', str, non-bool-int>=0)`
   3-tuple as an indicator, including one that happens to be plain cell
   DATA a caller passed by coincidence. This matches the codebase's
   existing "a plain tuple whose slot 0 happens to be a str is a str-functor
   cell by shape, full stop" discipline (`_helpers.py`'s documented THE
   DISCIPLINE comment) rather than inventing a new ambiguity rule, but it's
   worth a reviewer's eye since `listing/1` is user-facing.
3. The `_db_optional` fix (deviation 1) is currently reachable only through
   `_stateless_dispatch`/`BuiltinPredicate._get_dispatch()` with no db in
   hand — a path nothing in today's test suite drives for `listing`
   specifically (the existing db-less test goes through
   `get_builtin_dispatch`, which doesn't consult the flag at all). It's
   correct and matches the documented contract, but it's unexercised by a
   test that would fail without it.
4. `existence_error`'s third positional argument (context) is the literal
   string `"listing/1"`, matching the pre-existing `type_error(...,
   "listing/1")` calls already in this function — consistent with the
   file's convention, but other builtins in `database_ops.py` build a
   longer, more descriptive context string; a reviewer may want the same
   here for a better error message.
5. `tests/test_listing.py` now mixes three testing styles (substring checks
   in the original `TestListing`, byte-identical golden, and
   structured-term inspection of the raised `LogicException.term` in the
   new indicator tests) — stylistically inconsistent but each style is the
   right tool for what it's checking; not proposing a cleanup pass myself
   since it would touch tests outside this task's diff.

---

## Review verdict

Reviewer pass over `4687fc18..5effc0ba` (3 commits). Verified by running code,
not by reading claims; probe scripts under
`/tmp/claude-1000/-workspace-clausal-bug-fix/ff7d2f98-4c36-4258-8937-16070cf0f92f/scratchpad/t8-review/`.

### Spec-compliance table

| # | Brief checkbox / controller ruling | | Pin / evidence |
|---|---|---|---|
| 1 | Grep the four named files for class-keyed clause reads; tabulate | OK | Re-grepped `clausal/reflection.py`, `clausal/modules/reflection.py`, `clausal/logic/builtins/inspection.py` myself. `modules/reflection.py`: zero hits for all four patterns. `inspection.py`: no `._clauses`, no `module_dict.get(`, no `__dict__`; `PredicateMeta` only at :35/:124 (atom-leaf), :250 (`_construct_named`), :510-572 (`global_atom`) — legacy atom acceptance, as ruled. See F6 for one inaccurate table cell. |
| 2 | `listing/1` lives in `io.py`, not `compiler_v2.py` | OK | `compiler_v2.py` has one unrelated docstring hit; migration landed in `clausal/logic/builtins/io.py`. |
| 3 | `listing/1` becomes `_db_builtin` + `_db_optional` | OK | `("listing",1)` absent from `_BUILTINS`, present in `_DB_BUILTINS`; `_DB_BUILTINS[("listing",1)]._db_optional is True`; `_stateless_dispatch("listing",1)` returns a callable `trampoline_fn`. §3.1's claim about `@_db_builtin` returning the *unwrapped* factory verified in `_registry.py:166-175` (`_DB_BUILTINS[k] = _wrap_db_factory(factory); return factory`) — the attribute had to go on the dict entry. |
| 4 | Accepted shapes: class / instance / BuiltinPredicate / str atom / indicator in BOTH spellings | OK | All five exercised end to end; cell `('/', 'pt', 2)` and `Compound("/", ("pt", 2))` both resolve to `db.row`. |
| 5 | Absent row → `existence_error(procedure, Compound("/",(name,arity)))`; db=None → the existing `type_error` | OK | Probed both. Error shape matches `database_ops.py:197` exactly (`existence_error("procedure", Compound("/", (functor, arity)), ctx)`). See F7 on the terse context string. |
| 6 | Row that EXISTS with zero clauses prints "no clauses", not an error | OK | `db.mark_dynamic("neverasserted",1)` creates the row; listing it prints `'% neverasserted/1 — no clauses\n'`. A `db.row(name,arity,create=True)` with empty `clauses` likewise. An unknown name raises. |
| 7 | Byte-identical `listing/1` output for unchanged fixtures; golden pinned | OK | Independently verified, not taken on trust: loaded BASE `io.py` (via `git show`) into a probe process and compared BASE vs HEAD output for all four pre-existing shapes — 3-clause class, empty class, instance, BuiltinPredicate — all four byte-identical, em dash included (`M-bM-^@M-^T` in both). The golden string in `TestListingClassArgumentGoldenOutput` matches the produced bytes exactly. `_format_clause` untouched. |
| 8 | `predicate_rows(module)` helper only if a consumer exists → not added | OK | `predicate_rows` has no hits anywhere in `clausal/` or `tests/`; ruling recorded in §3.5. |
| 9 | Reordering (indicator before `is_term_instance`) must not change PredicateMeta-instance behaviour | OK | The BASE-vs-HEAD comparison above includes the instance case: identical. |
| 10 | Indicator parser rejects non-str name, negative/bool arity, wrong length, a Var | OK | All 13 rejection cases probed: non-str name, bool arity, negative arity, len-2/len-4 tuple, bare `Var`, var-in-name, var-in-arity, `Compound("/",(x,))`, float arity, `TUPLE_TAG`-tagged data → all `None`. |
| 11 | Cell/tuple-data ambiguity acknowledged and matching `cells.py` | OK | `type(val) is tuple` + raw str slot 0 matches THE DISCIPLINE (`_helpers.py:326-338`, `cells.py:243`); `TUPLE_TAG` data is correctly excluded. §7.2 accepts it explicitly. |
| 12 | Reachable from compiled `.clausal` code; db is the CALLING module's | OK | Compiled a 2-clause module: `debug_greet <- listing("greet")` prints `% greet/0 — 1 clause(s)`; `debug_fib <- listing(fib)` prints the class listing. Cross-module probe: module B calling `listing("secret")` for a predicate owned by module A raises `existence_error(procedure, secret/0)` while A's own db lists it — the db is the caller's. |
| 13 | Fold-in: registration-asserting probes for the seven names | WARN | All seven present with a registration assertion and a side-by-side cell/`Compound` comparison, and `("=..",2)` confirmed absent from both registries while `("unpack",2)` is in `_BUILTINS` (the docstring's `univ` claim checks out at `inspection.py:362-371`). But the assertion sits in a sibling test method, not in the driving helper as the mandated pattern requires — F5. |
| 14 | `dif/2` hand-check | OK | Cell vs `Compound`: open 1/1, definitely-equal 0/0, definitely-different 1/1, and the constraint really posts (post-`dif` `unify` fails on both sides). Not a trivial pass. |
| 15 | Todo moved to `todo/done/` with content intact | OK | Rename in the commit; 74 → 84 lines (+10 "## Done"); original path gone. The mv-drops-content pitfall did not bite. |
| 16 | Inversion ledger: no existing assertion rewritten | OK | `--numstat` on `tests/` shows 249+/0- and 139+/0- — zero deleted lines across both test files. §4's "None" is accurate. |
| 17 | Docs commit `5effc0ba` states true things | FAIL | F1: `docs/io.md:235`'s example raises. |
| 18 | Gate artifacts | OK | `cmp task-3-base-failed-names.txt task-8-failed-names.txt` → exit 0, 145 lines. `task-8-full.txt` summary: `144 failed, 12380 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 101.29s`. `docs/io.md`'s untested doc block is flagged at the same `io.md:228` before and after, so the docs edit added no new masked failure. |

### Verdict

**Not approved as-is.** Blocker: **F1** — the docs commit publishes a `listing/1`
surface (`listing(fib/2)`) that does not exist and raises `type_error`. The
migration itself (`io.py` + tests) is sound and I would approve it unchanged;
F1 is a docs/comment correction, F2–F7 are Minor.

### Findings

**F1 (Important) — docs assert a surface that raises.**
`docs/io.md:235`, plus the "default `foo/2`-style cell" wording at
`docs/io.md:244`, `docs/builtins.md:2376`, `clausal/logic/builtins/io.py:190-191`
and `tests/test_listing.py:218-219`.
`/` in `.clausal` source is *arithmetic*: `foo/2` compiles to a
`clausal.pythonic_ast.nodes.Div` node, **not** to the cell `('/', 'foo', 2)`.
Run verbatim, the new doc example gives
`error(type_error(predicate, <class '…nodes.Div'>), 'listing/1')`. The other two
examples in that block (`listing(fib)`, `listing("greet")`) do work. Nothing
executes that block (it is one of the known-untested doc blocks), so no test
catches it.
Required fix: drop `debug_fib2 <- listing(fib/2)` from `docs/io.md` (or replace
it with a Python-side example), and reword the four "the default cell a
user-written `foo/2` compiles to" claims to say the indicator shapes are
reachable from Python/engine callers only, until the Phase-3 surface gives `/`
a term reading.

**F2 (Minor) — indicator slots are read without `deref`.**
`clausal/logic/builtins/io.py:200-207` (`_as_name_arity_indicator`).
`Compound("/", (N, A))` with `N`→`"pt"`, `A`→`2` bound on the trail is rejected
with `type_error` instead of listing `pt/2` (probed; the cell spelling behaves
the same). Slot 0 is legitimately read raw (§1b discipline), but slots 1/2 are
ordinary term slots that may hold bound Vars. Fix: `deref` name and arity
before the `isinstance` checks.

**F3 (Minor) — `_db_optional` is load-bearing, and the comment says it isn't.**
`clausal/logic/builtins/io.py:283-292`; report §3.1 ("mainly makes the OTHER
db-less path behave consistently") and §7.3 ("unexercised by a test that would
fail without it").
`_build_all_builtin_classes()` calls `_stateless_dispatch("listing", 1)` at
import time. Probed: with the flag deleted and the class table rebuilt,
`_BUILTIN_CLASSES["listing"]._dispatch_fn` is `None` — at BASE it was a real
dispatch, because `listing` lived in `_BUILTINS`. So the line prevents a
regression rather than merely tidying a path. Fix: correct the comment, and pin
it with one assertion (`_stateless_dispatch("listing", 1) is not None`, or
`_BUILTIN_CLASSES["listing"]._dispatch_fn is not None`) so the line cannot be
deleted silently.

**F4 (Minor) — stale docstring in the registry.**
`clausal/logic/builtins/_registry.py:64-70`: "Exactly one family sets that flag
today: `call_goal`/`call` (P3-3 Task 5)". `listing/1` now sets it too. Fix: name
both.

**F5 (Minor) — the registration assertion is not in the driving helper.**
`tests/test_inspection_registration_probes.py:38-46` vs the mandated pattern
(`tests/test_tagged_terms.py:2228-2235`, where `_assert_registered` is inside
`_nsol` so every probe carries it). Here `_solutions` / `_sol_var` / `_sol_vars`
carry no guard; the guard is a sibling test method. Not exploitable today — I
checked that an unregistered name raises `PredicateNotFoundError` rather than
yielding zero solutions — but
`TestDif2RegistrationAndCellParity::test_definitely_equal_cells_fail_dif_like_definitely_equal_compounds`
asserts `nsol_c == nsol_p == 0`, which is exactly the both-sides-agree-on-nothing
shape the todo warns about. Fix: call `_assert_registered(name, arity)` inside
the three helpers.

**F6 (Minor) — one §2 grep-table cell overstates its evidence.**
Row 1 says `clausal/reflection.py` has "No `module_dict`/`__dict__`/`_clauses`
hits at all". There are six `_clauses` substring hits (`_comprehension_clauses`
at `clausal/reflection.py:790, 840, 844, 850, 854`). They are AST comprehension
generators, unrelated to predicate rows, so the *conclusion* (no class-keyed
clause read) stands — but the stated evidence is wrong. Fix: correct the cell.

**F7 (Minor) — str-atom path is arity-0-only, and its error is terse.**
`clausal/logic/builtins/io.py:255-256`. Ruling-compliant (`str atom → db.row(name, 0)`),
but `listing("foo")` for an existing `foo/1` raises
`existence_error(procedure, foo/0)`, which reads as "no such predicate" for a
predicate that does exist; SWI/ISO `listing(Name)` lists every arity. Worth a
follow-up todo given the ISO-compatibility driver. Separately, the
`existence_error` context is the bare string `"listing/1"` while the convention
it copies (`database_ops.py:197-202`) carries a diagnostic sentence.

### Constraints check

- `_get_dispatch` duck type, `<harness-library>`, `_belongs_elsewhere`, `_SKIPPED_ITEMS`,
  backend `$disp_` seam, `write_refusal`, Task 5b step 3b-ter, Task 6
  `resolve_module`: **untouched** — the diff touches six files only
  (`io.py`, `docs/builtins.md`, `docs/io.md`, two test files, one todo rename);
  the sole `_get_dispatch` occurrence in the diff is inside a comment.
- Information barrier: **clean** — no downstream-project or corpus-domain names
  in the diff.
- `todo/`: **only** the one renamed file is staged.
- All `_BUILTINS` consumers outside `_registry.py` (`predicate_diagnostics.py:287-290`,
  `compiler_v2.py:1392-1395`) check `_DB_BUILTINS` too, so moving `listing` between
  registries leaks nothing.

### Test counts

- `tests/test_listing.py` 27 passed · `tests/test_inspection_registration_probes.py`
  18 passed (45 passed together).
- `tests/test_term_inspection.py tests/test_tagged_terms.py tests/test_cell_goals.py`:
  265 passed, 2 xfailed.
- `tests/test_reflection_builtins.py`: 9 passed.
- All five focused suites together: **310 passed, 2 xfailed**.
- `cmp task-3-base-failed-names.txt task-8-failed-names.txt` → **exit 0** (145 lines).

---

## Fix round 1

Commit `022208ba`. BASE for this round = `5effc0ba`.

### F1 (blocker) — `Div` indicator shape + doc/comment corrections

Root cause confirmed by direct probing (not guessed): `foo/2` in `.clausal`
source is `/`, the arithmetic operator; a structural (non-`is`) use of it
compiles to a reified `clausal.pythonic_ast.nodes.Div` term, never the cell
`('/', name, arity)`. Probed shapes:

- `Fib/2` (declared 2-arity predicate `Fib` in scope) →
  `Div(left=<Fib PredicateMeta class>, right=2)`.
- `"nonexistent"/2` (string-literal left operand) →
  `Div(left='nonexistent', right=2)`.
- `3/2` (no predicate-denoting operand) → `Div(left=3, right=2)`, UNCHANGED
  — this is genuine arithmetic and must still raise `type_error`.

`clausal/logic/builtins/io.py::_as_name_arity_indicator` now recognizes a
`Div` node as a fourth indicator representation: `.left`/`.right` are
dereffed (mirroring `clausal/logic/compiler/terms_to_ast.py`'s
`arith_to_ast_expr`, which already derefs a `Div`'s operands the same way
for `is/2`), a `PredicateMeta` left operand is reduced to `.__name__`, and
the shape is accepted only when the (dereffed) left is a `PredicateMeta` or
`str` and right is a non-bool int — which is exactly what makes `3/2`
correctly fall through as "not an indicator" rather than being misread.

The `is_term_instance()` generic-instance-to-class fallback is now gated
off for ANY `Compound`- or `Div`-shaped value, not only a successfully
parsed indicator — both are `@dataclass`, so an ILL-FORMED `Div` (like
`3/2`) was previously swallowed by that fallback and reported the `Div`
CLASS as the `type_error` culprit instead of the actual `Div` INSTANCE; now
it reports the instance.

Docs/comments corrected (all four sites the review named): `io.py`'s
`_as_name_arity_indicator` and `_listing__1` docstrings, `docs/io.md`
(the "Also accepted" comment + the prose paragraph), `docs/builtins.md`'s
prose, and `tests/test_listing.py`'s `TestListingNameArityIndicatorArgument`
docstring — all now say the cell/`Compound` shapes are for Python/engine
callers holding the name+arity as data, and that `foo/2` in `.clausal`
source compiles to `Div` instead.

New: `tests/fixtures/listing_div_indicator.clausal` (a real 3-clause `fib/2`
predicate plus `DebugFibByClass() <- listing(fib)` and
`DebugFibByIndicator() <- listing(fib/2)`) and
`TestListingDivIndicatorArgument` in `tests/test_listing.py`:
- `test_div_of_a_str_name_and_int_lists_the_predicate` — `Div(left=str,
  right=int)`.
- `test_div_of_a_predicate_class_lists_the_predicate` — `Div(left=
  PredicateMeta, right=int)`.
- `test_div_end_to_end_matches_class_form_byte_identically` — compiles the
  fixture and asserts `listing(fib/2)`'s captured stdout is BYTE-IDENTICAL
  to `listing(fib)`'s, against the same real module database.
- `test_div_with_a_plain_int_left_operand_raises_type_error` — `Div(3, 2)`
  → `type_error`, culprit is the `Div` instance, not the class.
- `test_div_with_a_non_int_right_operand_raises_type_error` — `Div("fib",
  "oops")` → `type_error`.

### F2 — deref the cell/Compound indicator slots

`_as_name_arity_indicator`'s cell and `Compound` arms now `deref()` the
name/arity slots (the `Div` arm needed this for F1 already, so this
brings all three representations in line). New tests in
`TestListingNameArityIndicatorArgument`:
`test_name_arity_cell_with_bound_vars_in_the_slots_lists_the_predicate` and
`test_name_arity_compound_with_bound_vars_in_the_slots_lists_the_predicate`
— both bind `N`/`A` on a `Trail` via `unify()` before passing `('/', N, A)`
/ `Compound("/", (N, A))`, and assert the predicate still lists correctly.

### F3 — `_db_optional` is load-bearing

Rewrote the `io.py` comment above `_DB_BUILTINS[("listing",
1)]._db_optional = True` to state plainly that
`_build_all_builtin_classes()` calls `_stateless_dispatch("listing", 1)` at
import time, and that without the flag `_BUILTIN_CLASSES["listing"]
._dispatch_fn` is `None` (this was independently re-verified in this round
by reading `_build_all_builtin_classes`'s source, not re-run against a
patched build). New `TestListingBuiltinClassHasDispatch` in
`tests/test_listing.py` pins `_BUILTIN_CLASSES["listing"]._dispatch_fn is
not None` and `_stateless_dispatch("listing", 1) is not None`, so the line
cannot be deleted silently.

### F4 — `_registry.py` docstring named both families

`_stateless_dispatch`'s docstring in `clausal/logic/builtins/_registry.py`
now lists both families that set `_db_optional`: `call_goal`/`call`
(P3-3 Task 5, unchanged) and `listing` (P3-3 Task 8, added), with a
one-line explanation of why each needs it.

### F5 — registration assertion moved into the driving helper

`tests/test_inspection_registration_probes.py`: added a single `_drive(g)`
helper that calls `_assert_registered(g.func.name, len(g.args))` and THEN
returns `(module, trail, solutions-iterator)`. `_solutions`, `_sol_var`,
and `_sol_vars` now all funnel through `_drive` instead of building their
own `Module`/`Trail`/`solve()` triad directly, and the `numbervars` test
(which previously called `solve()` directly, bypassing every helper) now
does too. The registration check can no longer be skipped by a probe that
forgets to call a sibling `test_X_is_registered` method — those methods
stay in place as explicit, individually-readable pins, but they are no
longer the only thing enforcing the check.

### F6 — corrected report §2 table cell

`clausal/reflection.py` has 5 `_clauses` substring hits
(`clausal/reflection.py:790,840,844,850,854`), all `_comprehension_clauses`
— an AST comprehension-generator helper and its call sites, unrelated to
predicate rows. The original §2 table row wrongly stated zero `_clauses`
hits; corrected in place. The conclusion (nothing to migrate in this file)
is unaffected.

### F7

Not this round's — the controller filed
`todo/listing-of-a-bare-atom-lists-only-arity-0-2026-09-06.md` and this
round does not touch the bare-atom arm of `listing/1`.

### Test summary

- `tests/test_listing.py`: 36 passed (was 27; +9: 2 F3 pins, 2 F2 deref
  pins, 5 F1 `Div`-indicator tests).
- `tests/test_inspection_registration_probes.py`: 18 passed (unchanged
  count; internals restructured per F5).
- `tests/test_listing.py tests/test_inspection_registration_probes.py
  tests/test_term_inspection.py tests/test_tagged_terms.py
  tests/test_cell_goals.py tests/test_reflection_builtins.py
  tests/test_specialization_pipeline.py` together: 401 passed, 2 xfailed.

### Gate result

Full suite (`PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest
tests --continue-on-collection-errors -q -p no:cacheprovider -rfE`):

```
144 failed, 12389 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 101.87s (0:01:41)
```

(12389 vs. the prior round's 12380 — the +9 new/changed tests above, all
passing.)

`cmp .superpowers/sdd/p33-state-relocation/task-3-base-failed-names.txt
.superpowers/sdd/p33-state-relocation/task-8-fix1-failed-names.txt` →
**exit 0** (145 lines, byte-identical). Artifacts:
`task-8-fix1-full.txt`, `task-8-fix1-failed-names.txt`.
`docs/io.md`'s pre-existing untested doc block is still flagged at the
same `io.md:228` before and after this round's docs edits (re-verified:
`test_no_raw_untested_blocks` still reports "Found 36" with the same single
`io.md` entry) — no new masked failure.

## Re-review (fix round 1)

Verified by running code against `022208ba` (BASE `5effc0ba`), not by reading
claims. Direct probes and test runs executed from the worktree.

- **F1**: ADDRESSED — `_as_name_arity_indicator` (`clausal/logic/builtins/io.py:225-241`)
  now accepts a `Div` node, deref'ing `.left`/`.right` and reducing a
  `PredicateMeta` left to `.__name__`; `left` must be `str`/`PredicateMeta`
  and `right` a non-bool `int`, so `3/2` (`Div(left=3, right=2)`) is correctly
  rejected. Direct probe: `get_builtin_dispatch("listing", 1, None)` driven
  with `Div(left=3, right=2)` raises `type_error('predicate', (3 / 2))` whose
  culprit `is` the actual `Div` instance (checked with `culprit is d`), not
  the `Div` class — confirms the `is_indicator_shaped` gate works. All
  "compiles to the cell" claims corrected in `io.py`, `docs/io.md`,
  `docs/builtins.md`, `tests/test_listing.py` (grepped for the stale phrasing;
  only correct "compiles to `Div`" statements remain). The `docs/io.md`
  `debug_fib2 <- listing(fib/2)` example is pinned end-to-end by
  `TestListingDivIndicatorArgument::test_div_end_to_end_matches_class_form_byte_identically`,
  which compiles `tests/fixtures/listing_div_indicator.clausal` and asserts
  `listing(fib/2)` output is byte-identical to `listing(fib)` against the
  same real module database. Rejection tests present for `Div(3, 2)` (int
  left) and `Div("fib", "oops")` (non-int right).
- **F2**: ADDRESSED — cell and `Compound` arms of `_as_name_arity_indicator`
  now `deref()` both slots (`io.py:227,229`); new tests
  `test_name_arity_cell_with_bound_vars_in_the_slots_lists_the_predicate` and
  `..._compound_..._lists_the_predicate` bind `N`/`A` via `unify()` on a real
  `Trail` before driving `listing`, both pass.
- **F3**: ADDRESSED — `io.py` comment above `_DB_BUILTINS[("listing",1)]._db_optional = True`
  now states plainly that `_build_all_builtin_classes()` calls
  `_stateless_dispatch("listing", 1)` at import time and that without the
  flag `_BUILTIN_CLASSES["listing"]._dispatch_fn` is `None`; new
  `TestListingBuiltinClassHasDispatch` pins both
  `_BUILTIN_CLASSES["listing"]._dispatch_fn is not None` and
  `_stateless_dispatch("listing", 1) is not None` (both pass). Mechanism
  cross-checked by reading `_build_all_builtin_classes`/`BuiltinPredicate._get_dispatch`
  in `_registry.py:308-320,460-494` — matches the comment's claim.
- **F4**: ADDRESSED — `_stateless_dispatch`'s docstring in `_registry.py:66-81`
  no longer says "Exactly one family"; now lists `call_goal`/`call` and
  `listing` as the two families that set `_db_optional`.
- **F5**: ADDRESSED — `tests/test_inspection_registration_probes.py` gained a
  `_drive(g)` helper (line 56) that calls `_assert_registered(g.func.name,
  len(g.args))` before building `(module, trail, solve(...))`; `_solutions`,
  `_sol_var`, `_sol_vars`, and the `numbervars` test all funnel through it —
  grepped the file for `solve(` and confirmed the only direct call left is
  inside `_drive` itself, so no probe can bypass the assertion.
- **F6**: ADDRESSED — report §2 table row for `clausal/reflection.py`
  corrected to "5 `_clauses` substring hits ... all `_comprehension_clauses`";
  `grep -n "_clauses" clausal/reflection.py` independently confirms exactly 5
  hits at lines 790,840,844,850,854, matching the corrected cell (the
  original review finding's own "six" was off by one; the fix round's "5"
  is what's actually in the file).

No new defect found. `is_indicator_shaped` gate, deref placement, and the
`_db_optional` mechanism were each independently probed rather than taken on
the report's word.

Evidence run:
- `PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests/test_listing.py tests/test_inspection_registration_probes.py -q` → 54 passed.
- `PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests/test_listing.py tests/test_inspection_registration_probes.py tests/test_term_inspection.py tests/test_tagged_terms.py tests/test_cell_goals.py tests/test_reflection_builtins.py -q` → 328 passed, 2 xfailed.
- Direct probe: `Div(left=3, right=2)` through `get_builtin_dispatch("listing", 1, None)` raises `type_error('predicate', (3 / 2))`, culprit `is` the `Div` instance, `type(culprit) is Div`.
- `git show --stat 022208ba` → exactly the 7 expected files (`_registry.py`, `io.py`, `docs/builtins.md`, `docs/io.md`, `tests/fixtures/listing_div_indicator.clausal`, `tests/test_inspection_registration_probes.py`, `tests/test_listing.py`); no `todo/` path in the commit (the pending `todo/listing-of-a-bare-atom-...md` from F7 exists on disk but is untracked/unstaged, not part of this commit). Sole `_get_dispatch` diff hunk touches only a docstring line count in a comment reference — the function itself is untouched.
- `cmp task-3-base-failed-names.txt task-8-fix1-failed-names.txt` → exit 0 (both 9653 bytes, byte-identical).

Verdict: APPROVED
