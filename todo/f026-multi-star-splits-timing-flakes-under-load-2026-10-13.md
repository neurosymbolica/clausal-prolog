# F026 timing test flakes under box load

`tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input`
asserts that `_multi_star_splits(10, 20)` finishes in under 3.0 s. On the box, at rest, it takes 1.84–2.02 s.
On 2026-10-13 it failed three times, at 3.74 s and similar, every time while another full suite or an A/B
was running on the same box. Direct timings of the function on the base and the candidate were equal
each time, and none of those candidates changed the function.

A gate that runs alongside other work keeps reporting it as NEW. Options:
- time a fixed smaller input relative to a calibration loop, rather than wall-clock against a constant;
- or count the splits generated, which is the property F026 protects (no combinatorial explosion), and drop the timing.
