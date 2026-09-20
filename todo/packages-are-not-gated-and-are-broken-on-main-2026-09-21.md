# The 12 packages have no gate, and 402 of their tests already fail on main

**Status:** open. Found while doing P2 Task 7 (the packages sweep). Task 7's
own work is done and is at parity; this is the ground it landed on.

## The state, measured on main `bd774c46`

Every package's own suite, run in a faithful room:

    clausal-gprolog      failed=0    passed=5     errors=0
    clausal-jax          failed=108  passed=1000  errors=54
    clausal-opencv       failed=61   passed=10    errors=262
    clausal-provenance   failed=39   passed=89    errors=3
    clausal-scipy        failed=26   passed=1493  errors=0
    clausal-scryer       failed=1    passed=10    errors=0
    clausal-sklearn      failed=45   passed=11    errors=0
    clausal-spacy        failed=42   passed=4     errors=0
    clausal-sympy        failed=52   passed=138   errors=0
    clausal-torch        failed=27   passed=724   errors=0
    clausal-trealla      failed=1    passed=9     errors=0
    clausal-yaml         HANGS -- no summary, killed at 900s
    ------------------------------------------------------
    TOTAL                402 failed, 3493 passed, 319 errors

**`clausal-yaml` hangs**, identically on main and on the branch (byte-identical
partial output, 40 tests in). It needs its own investigation; a shell `timeout`
is the only thing that ends it.

Sampled causes are NOT representation-related: `PurityError` on a rule body
calling an unmarked predicate, semiring-protocol `TypeError`s, and a large tail
of missing/renamed wrappers. The packages have drifted from the engine over
many landings and nothing catches it.

## Why nothing catches it

The house run is `tests/`. **It does not touch `packages/` at all**, and the
packages are not installed in the shared venv (only `clausal_jax` and
`clausal_torch` have dist-info). So an engine change can break every package
and the gate stays green -- the same blind spot recorded for `_get_dispatch`'s
~22 out-of-tree implementors.

## Running them, which is harder than it looks

`pip install -e packages/clausal-X` is the supported path, but
`/workspace/clausal/venv` is SHARED between lanes: an editable install there
points every lane at whichever room installed last. A pytest plugin that
extends the already-imported packages' `__path__` does the same job per
process, and that is what these numbers were taken with.

**There are THREE layouts, and missing one is a silent no-op** -- every test in
the package then fails with `ModuleNotFoundError` IDENTICALLY ON BOTH SIDES,
so a NEW-0 comes back over two piles of rubble and proves nothing:

    clausal/modules/py/<name>.py   most wrappers (jax, torch, scipy, yaml, ...)
    clausal/modules/<name>/        provenance
    clausal/<name>/                the backends (gprolog, scryer, trealla)

Each target is a REGULAR package, so PEP 420 does not merge it -- `__path__`
must be extended explicitly, the way the core's own
`clausal/modules/__init__.py` does for installed distributions.

I got this wrong twice before getting a real measurement. The first harness
covered only `clausal/modules`, which crashed pytest in `pytest_configure` for
the three backends (nothing extracted at all) and made the nine `py/` wrappers
look catastrophically broken. Under the corrected harness `clausal-jax` went
from "4 passed" to "1000 passed" and `clausal-scipy` from "4 passed" to
"1493 passed". **Both versions reported NEW 0.**

## What to do

1. **Gate them.** Even a smoke run per package in CI would have caught the
   drift years of landings introduced. Until then, treat `packages/` as
   untested.
2. **Fix `clausal-yaml`'s hang** -- it is the only one that cannot even be
   measured.
3. Triage the 402 against the landings that caused them. The sampled causes
   suggest purity/protocol drift, not the cell flip.
4. When gating, **assert the contribution actually imported** (a
   `PKG_PROBE`-style positive control), never just that the run finished.

## The harness, verbatim

Saved because two wrong versions both reported NEW 0. Run as
`PYTHONPATH=<dir> PKG_ROOT=packages/clausal-X [PKG_PROBE=clausal.modules.X]
venv/bin/python -m pytest packages/clausal-X/tests -q -rfE -p no:cacheprovider
-p pkg_path --continue-on-collection-errors`, from the room (never as a script
file -- `sys.path[0]` would be the script's directory and you would silently
test canonical).

```python
"""Contribute a package's clausal/ tree to the already-imported clausal packages.

What `pip install -e packages/clausal-X` would do, scoped to THIS pytest
process -- /workspace/clausal/venv is shared with other lanes and an editable
install there would point all of them at whichever room installed last.

THREE layouts, and missing any one of them is a silent no-op that makes every
test in the package fail with ModuleNotFoundError *identically on both sides*
-- a NEW-0 that proves nothing because the real code never ran:

    clausal/modules/py/<name>.py   most wrappers (jax, torch, scipy, yaml, ...)
    clausal/modules/<name>/        provenance
    clausal/<name>/                the backends (gprolog, scryer, trealla)

Each target is a REGULAR package (it has __init__.py), so PEP 420 does not
merge them -- the __path__ has to be extended explicitly, which is what the
core's own clausal/modules/__init__.py does for installed distributions.
"""
import os

CONTRIBUTED = []


def pytest_configure(config):
    root = os.environ["PKG_ROOT"]
    import clausal, clausal.modules
    targets = [
        (os.path.join(root, "clausal", "modules", "py"), "clausal.modules.py"),
        (os.path.join(root, "clausal", "modules"), "clausal.modules"),
        (os.path.join(root, "clausal"), "clausal"),
    ]
    import importlib
    for d, modname in targets:
        if not os.path.isdir(d):
            continue
        mod = importlib.import_module(modname)
        if d not in mod.__path__:
            mod.__path__.append(d)
        CONTRIBUTED.append((modname, d))
    assert CONTRIBUTED, "no clausal/ contribution found under %s" % root
    probe = os.environ.get("PKG_PROBE")
    if probe:
        importlib.import_module(probe)


def pytest_report_header(config):
    return "pkg_path contributed: %s" % ", ".join(m for m, _ in CONTRIBUTED)
```
