# F026 (`_multi_star_splits` timing) fails under machine load

`tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input`
asserts `list(_multi_star_splits(10, 20))` (10,015,005 tuples) finishes in under 3 s. Measured
2026-10-08 on unchanged code: passes alone on an idle machine, fails at load ~3-4 (4.49 s), and showed
up as NEW in four engine gates that day, every time while another suite shared the machine.

It guards against an algorithmic blow-up, so the bound should not depend on wall time: count the
tuples (or compare against a smaller instance's time, as a ratio), or mark it as a perf test that
gates run serially.
