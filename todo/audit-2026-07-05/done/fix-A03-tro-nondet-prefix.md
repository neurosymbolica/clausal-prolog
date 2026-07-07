# fix(A03-F001): TRO drops solutions behind nondeterministic prefix goals

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F001
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF001TroNondetPrefix` (4 xfail — flip to pass)

## Bug

TRO eligibility requires every prefix goal to be deterministic (the restart
mechanism supports exactly one continuation per clause activation). The
shared determinism classifier says True for goals that are NOT:

- `tro.py:106-122` `_is_deterministic_op_ir`: `MemberIn()` → True (`X in L`
  generates members / succeeds once per occurrence) and `Branch()` → True
  (reified `If` explores BOTH arms when the condition is undetermined).
- `tro.py:293-339` legacy `_is_deterministic_goal`: same wrong arms
  (`in_() | NotIn()` — NotIn is fine, in_ is not; `IfExpr()`).
- `tro.py:343-370` `_DETERMINISTIC_BUILTINS` contains multi-solution modes:
  `("atom_concat", 3)` (split mode enumerates — probed: 3 solutions for
  `atom_concat(P,Q,"ab")`), `("sub_atom", 5)` (probed: enumerates). Audit
  the rest of the table mode-by-mode (`length/2` both-unbound is generative,
  etc.) — entries are only safe if EVERY mode is semidet.

Effect: the emitted restart (`_compile_tro_tail` snapshot + `_tro` flag)
runs once with the LAST prefix solution; all earlier prefix solutions are
silently dropped. `trm(2,0,OUT)` → `[4]` instead of `[2,3,3,4]`.

## Fix direction

1. `MemberIn` → deterministic only if `negate=True`; positive membership is
   nondeterministic (even ground: duplicates succeed per occurrence).
2. `Branch` → deterministic only if BOTH arms are deterministic AND the
   test is guaranteed ground at runtime — not decidable statically, so the
   safe call is `False` unless both arms and the (reifiable) test are
   provably single-solution; simplest correct: `False`.
3. Prune `_DETERMINISTIC_BUILTINS` to entries semidet in ALL modes, or key
   the table by mode and consult groundness (bigger job — start by removing
   `atom_concat/3`, `sub_atom/5`, re-audit the list/string entries).
4. Mirror 1–3 in the legacy `_is_deterministic_goal` (still imported by
   `predicate.py`) or delete it if truly dead.
5. While in `_compile_tro_tail`: delete the dead first
   `_compile_predicate_call_impl(...)` call (`tro.py:601-613`, result
   unconditionally overwritten at `:633`). Also note
   `_head_has_unifying_list_pattern` (`:455-471`) only checks
   `is_term_instance` heads, not `Compound` heads — add the Compound arm
   while touching the file (cr, no repro found).

## Acceptance

- 4 xfails flip; the 8 controls (shallow oracles, non-tail, cnt/trob/ctp,
  deep-stack cnt(3000)) stay green.
- A03-F002's DR tests flip too (same classifier) — see
  `fix-A03-dr-nondet-prefix.md`.
- Perf note: predicates whose prefixes are genuinely det keep TRO; run the
  compiler benchmarks if the table shrinks materially.
