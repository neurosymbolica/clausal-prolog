# Engine limitation: redriving a tabled call resumes the parked generator instead of consulting the table

Found during the bench_tabling diagnosis (2026-09-03): after a tabled predicate yields its
answer(s), continuing to drive the SAME query resumes the parked trampoline frame — the leader
fixpoint loop (clausal/logic/tabling.py:1170-1213) re-walks the nested call tree by generator
state, exponential for recursive predicates. A FRESH call correctly hits the COMPLETE fast path
(tabling.py:1047). Benchmarks/callers sidestep it via break-after-first (see
benchmarks/workloads.py bench_tabling). Verified property: an abandoned-via-break query leaves
db.table_store empty (tests/test_tabling.py::test_nats_break_drops_table).
Fix direction: on redo of an exhausted/completed subgoal, consult the table instead of resuming
the generator. Relevant to the tagged-tuple program: self-keying tabling (§3c of the design doc)
would make redo-time table consultation cheaper.
