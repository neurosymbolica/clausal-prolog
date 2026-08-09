# P2: bytecode cache serves stale .pyc for same-size edits within one second

STATUS: DONE (2026-07-19). Minimal fix landed: `SourceLoader.path_stats`
(`clausal/import_hook.py:316`) now reports
`(st.st_mtime_ns ^ CLAUSAL_BYTECODE_TAG) & 0xFFFFFFFF` instead of truncating to
`int(st.st_mtime)`, closing the same-size/same-second stale window. The tag XOR
still participates, so a tag bump still invalidates old caches. New test
`test_same_size_same_second_edit_recompiles` in `tests/test_pycache.py` (mtimes
pinned via `os.utime(ns=...)`, `val(1)`→`val(2)` same size); existing cache-hit
and A10-F018 tag-fold tests updated to the ns formula and still pass. NOTE:
landing this changes the reported mtime for every cached module, so it
invalidates every existing `.pyc` once (expected, harmless — recompiles on next
load). Did NOT implement the PEP-552 source-hash variant.

## Mechanism
`clausal/import_hook.py:327-334` — `SourceLoader.path_stats` returns
`{"mtime": int(st.st_mtime) ^ CLAUSAL_BYTECODE_TAG, "size": st.st_size}`. `int(st.st_mtime)` truncates to whole
seconds. Size IS in the key (CPython parity), so the stale window is specifically a **same-size edit within the
same integer second** — which is exactly the mutation-testing workload (operator/atom flips are usually
same-size; patch→run→restore completes in <1s). A mutant then runs against the ORIGINAL bytecode and falsely
SURVIVES; kill rates silently drop.

Demonstrated: pinned-mtime demo (first load `val -> [1]`; edit source to `val(2)` same second; reload → still
`[1]`; next second → `[2]`). The repo's own invalidation test (`tests/test_pycache.py:104`
`test_modified_source_recompiles`) appends a fact — different size — so it never covers this window.

Downstream impact: every mutation harness in a downstream rulebase corpus now hand-busts `__pycache__` on patch
AND restore (e.g. one domain's `eval/mutation_test.py` cites this bug); a decomposition
brief hardcodes the workaround. Engine fix removes a whole class of silent false-greens.

## Fix
Minimal: use nanosecond mtime in the reported field, e.g.
`"mtime": (st.st_mtime_ns ^ CLAUSAL_BYTECODE_TAG) & 0xFFFFFFFF` — importlib stores/compares the field
`& 0xFFFFFFFF`, so any deterministic int works; ns granularity closes the window in practice.
Robust (bigger): PEP-552-style source-hash pycs behind a flag.

## Acceptance
New test in `tests/test_pycache.py`: same-size same-second edit (pin mtimes with `os.utime` ns precision)
recompiles. Existing cache-hit tests still pass (tag-bump invalidation unaffected).
