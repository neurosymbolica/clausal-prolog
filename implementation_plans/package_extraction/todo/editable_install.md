# Editable installs (`pip install -e`) don't expose package modules

## Symptom

`pip install -e packages/clausal-<pkg>` "succeeds" but
`import clausal.modules.<pkg>` fails with `ModuleNotFoundError`.
Tests that depend on the package's predicates being importable
(e.g. the per-package `test_doc_integrity.py` running its
inline-block compile-check) fail. Non-editable
`pip install packages/clausal-<pkg>` works correctly.

## Why

`clausal/modules/__init__.py` extends `__path__` to include
`<site-packages>/clausal/modules/`:

```python
import os as _os, site as _site
for _sp in _site.getsitepackages():
    _candidate = _os.path.join(_sp, "clausal", "modules")
    if _os.path.isdir(_candidate) and _candidate not in __path__:
        __path__.append(_candidate)
```

Non-editable installs copy the package's `clausal/modules/<pkg>.py`
into `<site-packages>/clausal/modules/`, where `__path__`
extension finds it.

Editable installs use a **PEP 660 meta-path finder** that maps
top-level packages (`clausal`) to source-tree paths
(`packages/clausal-<pkg>/clausal/`). The finder doesn't extend an
existing `clausal.modules.__path__` — it shadows the whole
`clausal` package, but only when no other `clausal` is found
first. Since core's `/workspace/clausal/clausal/` is on
`sys.path` (pytest's `pythonpath = ["."]`), it wins, and the
editable finder for `clausal-spacy` etc. is never consulted for
`clausal.modules.spacy` lookup.

## What to do

Either:

1. **Document the constraint** in
   `implementation_plans/PACKAGE_EXTRACTION.md` and / or each
   package's README: "use non-editable install for testing;
   editable install does not work because of `__path__`
   extension."

2. **Make `__path__` extension finder-aware**: in
   `clausal/modules/__init__.py`, after `_site.getsitepackages()`,
   also walk `sys.path` looking for editable `__editable__.<pkg>.pth`
   files and extract package source paths from them. Adds the
   editable source dirs to `__path__`. Tricky because the editable
   `.pth` indirection isn't a stable API.

3. **Replace `__path__` extension with proper namespace
   packaging**: drop the explicit `clausal/modules/__init__.py`
   file in core and make it a true PEP 420 namespace package.
   Each `clausal-<pkg>` distribution then ships its own
   `clausal/modules/` directory and Python's import machinery
   merges them. Biggest change, cleanest end state.

## Why it's filed, not done

Option 1 is fast but doesn't fix anything. Option 2 is brittle.
Option 3 is the right answer but touches a load-bearing piece of
the import machinery and wants its own design pass — out of scope
for the docs-migration cleanup.

In the meantime: anyone running `pytest packages/clausal-<pkg>/`
needs to `pip install packages/clausal-<pkg>` (no `-e`) first.
The docs-migration commits assume this workflow.

## Acceptance

A clean fix lands when `pip install -e packages/clausal-<pkg>`
makes `clausal.modules.<pkg>` importable in test contexts that
also have core on `sys.path`. Bonus points for a regression
test in `tests/test_namespace_packaging.py` (or wherever) that
exercises both editable and non-editable installs.
