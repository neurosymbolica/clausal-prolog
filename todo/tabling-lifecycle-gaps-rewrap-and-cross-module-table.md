# Tabling lifecycle gaps: runtime recompiles strip the wrapper; -table on imported/specialized targets is a silent no-op

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

## 3. P3 (noted): cross-module tabled NAF never fires WFS delay semantics

`_is_tabled_naf` (tabled_naf.py:22-32) consults the caller's per-module
db under the dotted name — imported tabled callees are not marked there,
so `not Imported(...)` compiles as plain NAF. Sound for completed
evaluations (dedup intact); WFS delay/conditional-answer semantics do not
propagate across modules.
