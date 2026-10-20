# investigate(A03): parked design decisions (Opus)

**Status: RESOLVED 2026-10-20 (split).** Each item is settled, overtaken or split out:
- **A03-D001** overtaken: `Compound` is deleted (09d77d93, 2026-09-28) and terms are tuples, so a catcher and a thrown term are the same kind of object; the tactical fix had landed earlier (todo/done/fix-A03-catch-functor-catcher.md). Pinned in tests/audit_2026_07_05/test_03_compiler_goals.py::TestF004CatchFunctorCatcher.
- **A03-D002** settled as recommended (ISO copy) by commit 4851e69e (todo/done/fix-A03-findall-template-sharing.md). Pinned in tests/audit_2026_07_05/test_03_compiler_goals.py::TestF005F006FindallFamily.
- **A03-D003** settled as recommended (refuse loudly) by commit 44ad6f02; docs/specialization.md lists the recognised MI patterns. Pinned in tests/audit_2026_07_05/test_03_compiler_goals.py::TestF007SpecializationDropsMidBodyGoals::test_midbody_goal_specialize_refused.
- **`_DETERMINISTIC_BUILTINS` governance** and the **`_tro_state` free-threading** note: split out to todo/tro-determinism-table-is-hand-written-2026-07-05.md.
- **Zero-arity predicates queried from Python**: fixed; `solve("fal", m)` and `solve("yes", m)` on user 0-arity predicates answer as `call/1` does (probed 2026-10-20). Pinned in tests/test_solve_zero_arity_control_atoms.py.

**Source:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/design-questions.md`
Parked per standing user preference (A01/A02 precedent).

- **A03-D001 — exception-term identity for catch/3.** The tactical fix
  (`fix-A03-catch-functor-catcher.md`: resolve catcher through the module's
  term classes) does not need this; the strategic question is whether
  `unify(Compound(f, args), f_instance)` should ever succeed. Interacts
  with A01-D004 (parked), index keys (`(functor, arity)` canonicalisation
  already coalesces them at the DISPATCH layer — A02), and tabling keys.
  Decide once for the whole term layer, not per-consumer.

- **A03-D002 — findall/bagof/setof template copy semantics.** ISO copies
  with fresh vars; Clausal shares the caller's vars (A03-F006 retroactive
  mutation). Recommendation: ISO copy (rename vars unbound at collection).
  If sharing is ever deemed intentional, it must be documented loudly and
  the cheat-sheet's "findall/bagof/setof: same" row amended.

- **A03-D003 — `-specialize` policy for unrecognized MI shapes.** Today:
  some shapes raise `CannotSpecialize` (module load fails — loud), others
  silently degrade (mid-body goals dropped, A03-F007; imported
  `MatchClause` refused with a confusing message). Pick one posture:
  recommend "refuse loudly with a precise reason" + a documented list of
  supported MI shapes. Also consider recognising the stock imported
  `MatchClause` (compare resolved target, not the literal LoadName name).

Also worth an Opus look while in the area (from the A03 coverage map):

- `_DETERMINISTIC_BUILTINS` governance: the table serves both TRO and DR;
  entries are only safe if semidet in EVERY mode. Consider deriving it
  from per-builtin mode declarations instead of a hand-written list
  (`fix-A03-tro-nondet-prefix.md` step 3 is the tactical prune).
- `_tro_state` shared-list signalling under free threading (unconfirmed —
  needs the 3.14t build; single-threaded interleaving probed clean).
- Zero-arity predicate query APIs (`solve()`/direct iteration) — seam note
  in the A03 findings, crosses A01/A02/A04 ownership.
