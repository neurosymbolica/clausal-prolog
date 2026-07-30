# Tabling lifecycle gaps: runtime recompiles strip the wrapper; -table on imported/specialized targets is a silent no-op

DONE 2026-07-29 on `fix/tabling-wrapper-survives-recompile`. Both faults
reproduced, both fixed, 12 tests in `tests/test_tabling_lifecycle.py` (7 of
which fail at the parent commit).

Found by the 2026-07-11 Fable audit (tabling-gate lens) of the call-site
fixes. All pre-existing — the cb92f009 tabled-predicate gate itself was
verified correctly computed, correctly timed, and enforced across both
module pipelines (import_hook v1 and compiler_v2), both walker
generations, and recompiles.

## 1. P1 (VERIFIED): assertz/asserta/retract on a dynamic+tabled predicate silently strips the tabling wrapper

`database_ops.py` (assertz ~:119-123, asserta ~:155-159, retract ~:227-231)
and the lazy-recompile path (`logic/predicate.py:250-252`,
`database.py:206-211` → `_recompile_trampoline`) all recompile via
`compile_predicate_trampoline` → `_install`, which overwrites
`pred_cls._dispatch_fn` and the db dispatch with the RAW compiled fn.
`make_tabled_wrapper_trampoline` is only ever applied at module load
(import_hook step 6 / compiler_v2 step 6).

Repro: `-table(Dp/1)` + `-dynamic(Dp/1)`, two clauses both true for Dp(1):
before assertz → dispatch is tabled_dispatch, Dp(1) = 1 answer; after
`assertz(Dp(9))` → dispatch is raw `Dp__1`, Dp(1) = 2 duplicate answers.

Fix sketch: in `_install` (single choke point), re-wrap when
`db is not None and db.is_tabled(functor, arity)`, and invalidate stale
table entries for that predicate.

### FIXED — and the severity was understated

The mechanism is exactly as described. What the todo did not say is that this
is a **correctness** bug, not a performance one. Reproduced verbatim, on a
left-recursive `-table` + `-dynamic` `Path/2` over `Edge(1,2), Edge(2,3)`:

    before assertz, dispatch: tabled_dispatch
    before answers: [2, 3]
    after assertz(Path(9,9)), Path dispatch: Path__2
    after answers: <never returns — killed at 60s>

A program that answers before an `assertz` never returns after it. Left
recursion terminates *only* because the table cuts the cycle, so stripping the
wrapper does not degrade the query, it removes the answer. P1 undersells it;
this is the kind of fault that hangs a production run.

Fixed as sketched, with three additions the sketch did not anticipate:

* `ensure_tabled_wrapper(db, functor, arity, fn)` in `logic/tabling.py` is the
  single decision point, and is idempotent — `make_tabled_wrapper_trampoline`
  stamps its result with `_tabled_for`. Without that, `_install` wrapping at
  step 5 and step 6 wrapping again would stack two table lookups.
* `_install` returns the function it installed, and the recompile consumers
  (`PredicateMeta._get_dispatch`, `Database.get_dispatch`) prefer what
  `_install` stored over what the recompile *returned*. Assigning the return
  value blind was the actual mechanism: `_recompile_trampoline` hands back the
  raw `fn` it compiled. This also repairs a latent `-shallow` fault —
  `compile_predicate_shallow` returns the simple-mode function while installing
  the trampoline adapter, so a recompiled shallow predicate was being called
  through the wrong calling convention.
* `_install` abolishes the predicate's table when it re-establishes the wrapper.
  Required, not belt-and-braces: the `retract/1` builtin deletes straight out of
  `db._clauses` and so never reaches `Database.retract`'s auto-invalidation, and
  `PredicateMeta._assertz`/`_retract` only clear the dispatch. Before the
  wrapper survived a recompile this was invisible — a raw dispatch reads no
  table, so a stale entry could not be served. `test_04_runtime_tabling.py::
  test_dynamic_tabled_assertz_retract_invalidation` was passing *because of*
  the bug and went red on the half-fix; it is a genuine regression guard now.

## 2. P2 (VERIFIED, imported case): `-table` targeting an IMPORTED predicate validates but never installs a wrapper

`_validate_directive_targets` (compiler_v2.py ~:350-352) accepts any
PredicateMeta in module_dict; `mark_tabled` lands in the importer's db,
but step-6 wrapping iterates only `pending` (same-module predicates) and
the callee's own module compiled it untabled with non-empty
`_index_plans`. Result: the author asked for tabling and silently got
none — AND call-site bucket specialisation of the raw plans proceeds.
Repro: importer `db.is_tabled("PCat",2)=True`, callee dispatch raw,
ground call site → 2 answers, no dedup.

Same structure suspected (UNVERIFIED) for `-table(SpecializedName/N)`:
meta-interpreter specialization compiles at step 6b against a FRESH
Database with empty `_tabled` (specialization.py ~:1339-1343, :1695-1717).

Fix sketch: restrict `-table` validation to same-module clause-bearing /
dynamic targets (error otherwise), or wrap non-pending PredicateMeta
targets in step 6.

### FIXED by refusing at load. Both cases verified, and it was genuinely silent

Imported case, reproduced as described:

    WARNINGS: []
    importer db.is_tabled(PCat,2): True
    PCat dispatch: PCat__2
    PCat(1,C) answers: ['a', 'a']      # 1 answer if tabled
    table_store after: {}

Specialized case, previously UNVERIFIED, now confirmed the same way:
`-table(SolveGraph/1)` on a `-specialize` alias leaves dispatch
`SolveGraph__1` and `table_store` empty.

Genuinely silent in both: no warning, no log line, nothing. Searched for any
existing diagnostic the todo might have overlooked — there is none; the only
check in the area, `_validate_directive_targets` (A12-F003), *deliberately*
accepts these, its docstring saying "A target that is a defined PredicateMeta
class (e.g. an imported or -private-declared predicate) also counts as
defined."

**Design question, decided: refuse at load, not warn, and not "make it work".**

* *Warn.* Rejected. The author's program is wrong in a way that changes its
  answers and possibly its termination; a warning on stderr during an import is
  the diagnostic most likely to be scrolled past. And there is no
  partially-correct behaviour to preserve — the directive does exactly nothing.
* *Make it work by wrapping the imported class.* Rejected, and this is the load-
  bearing argument. `pred_cls._dispatch_fn` is shared: wrapping it from the
  importer gives tabling to the defining module and to every *other* importer,
  none of whom asked, keyed into the importing module's `table_store`. Two
  importers each declaring `-table` would stack two wrappers over two different
  stores. Modules that already compiled against the raw dispatch keep it baked
  in `$disp_<name>_<n>`, so the same predicate would be tabled or not depending
  on load order. A directive with cross-module side effects that depend on
  import order is worse than the no-op it replaces.
* *Make it work for the `-specialize` alias.* Deferred, not rejected. This one is
  legitimately wantable and the obstacle is local: `_run_specialization` builds a
  fresh `Database` whose `_tabled` and `table_store` are its own, so the module's
  `abolish_all_tables` could not reach the table it built. Threading tabledness
  through needs a decision about which store owns the entries. Refusing is the
  honest interim, and the message says which predicate to table instead.
* *Refuse.* Chosen. It also matches Prolog practice — in XSB `:- table p/2`
  tables the p/2 of the module it appears in, and tabling someone else's
  predicate from outside is not expressible.

`_refuse_untablable_target` names which of the three shapes it found, because
the remedies differ: "move the directive into `<module>`" for an import, "table
the meta-interpreter or the object predicate" for a `-specialize` alias, "give it
clauses or declare `-dynamic`" for a bare declaration. `-dynamic` clause-less
targets are still accepted (this module compiles them). `-discontiguous` and
`-shallow` keep the looser check — unlike `-table` they are statements about this
module's own view of the predicate.

Known limitation, matching the pre-existing A12-F003 gap: the refusal lives in
`compiler_v2._validate_directive_targets`, so it does not fire under the legacy
`_USE_V2_PIPELINE = False` path, which validates no directive target at all.

## 3. P3 (noted): cross-module tabled NAF never fires WFS delay semantics

`_is_tabled_naf` (tabled_naf.py:22-32) consults the caller's per-module
db under the dotted name — imported tabled callees are not marked there,
so `not Imported(...)` compiles as plain NAF. Sound for completed
evaluations (dedup intact); WFS delay/conditional-answer semantics do not
propagate across modules.

### NOT FIXED — moved to `todo/cross-module-tabled-naf-loses-wfs-delay.md`

Still open, still untriaged (recorded from the code, never reproduced). It is a
third fault, not one of the two this todo is titled for, and the fix for finding
2 changes its shape — a local `-table` on the imported callee is now a load
error, so it cannot be used as a workaround.

## Corpus

`/workspace/clausify-domains` does not use `-table` anywhere: zero `-table`
directives across every `.clausal` file in the corpus. No domain is affected by
either fault, which is the one piece of good news here — the faults were found
by audit, not by a domain hitting them.
