# P2: bytecode cache serves stale .pyc for same-size edits within one second

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

Downstream impact: every mutation harness in /workspace/clausify-domains now hand-busts `__pycache__` on patch
AND restore (e.g. `eu/schengen_90_180/eval/mutation_test.py:16-18` cites this bug); the Wave-B decomposition
brief hardcodes the workaround. Engine fix removes a whole class of silent false-greens.

## Fix
Minimal: use nanosecond mtime in the reported field, e.g.
`"mtime": (st.st_mtime_ns ^ CLAUSAL_BYTECODE_TAG) & 0xFFFFFFFF` — importlib stores/compares the field
`& 0xFFFFFFFF`, so any deterministic int works; ns granularity closes the window in practice.
Robust (bigger): PEP-552-style source-hash pycs behind a flag.

## Acceptance
New test in `tests/test_pycache.py`: same-size same-second edit (pin mtimes with `os.utime` ns precision)
recompiles. Existing cache-hit tests still pass (tag-bump invalidation unaffected).
