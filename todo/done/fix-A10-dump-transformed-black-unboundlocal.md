# fix(A10-F007): dump_transformed oracle crashes without black + diverges from the import path

**Problems.** clausal/tools/dump_transformed.py (A10's designated differential
oracle):
1. `except (ImportError, black.parsing.InvalidInput)` (:70) — when
   `import black` itself raises ImportError, evaluating the except-clause tuple
   references the unbound local `black` → `UnboundLocalError` on EVERY
   `dump_source` call in a black-less env (this box).
2. `EmbedTransformer()` is built without `source_lines` (:44), so arrow
   detection uses the gap heuristic — `g(X) <- (X< -3)` dumps as a
   Lambda/Predicate while the import hook compiles Lt. The oracle must be
   byte-faithful to `import_hook._parse_clausal_source`.

**Repro/test.** test_10_rewriting_import.py::test_F007_dump_source_runs_without_black,
::test_F007_dump_source_arrow_fidelity (both xfail).

**Fix.** (1) Guard the import separately:
```python
try:
    import black
except ImportError:
    black = None
if black is not None:
    try: …format…
    except black.parsing.InvalidInput: pass
```
(2) Pass `source_lines=source.splitlines(keepends=True)` — or better, call the
shared `_parse_clausal_source` helper so the tool can never drift again.
