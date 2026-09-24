# A predicate's declaration SITE lives only on the class — one diagnostic line goes quiet at the flip

**Found:** 2026-09-24, fixing F1 rows 27/29. **Minor; flip design.**

`PredicateMeta` records `_registered_at` (`(file, line)` of the declaration)
at mint time (`predicate.py`, `_source_site`). Readers:

* `describe_imported_predicate_redefinition` — the "f is declared at
  file:line" line of the load channel's clause-clobber refusal. Now passed in
  as `declared_at=getattr(pred_cls, "_registered_at", None)` by
  `compiler_v2._redefinition_error`, so after the flip it is `None` and the
  line is omitted. Everything else in that message is era-agnostic
  (`tests/test_import_origins_both_eras.py` pins it, excluding this line).
* `predicate.py` ~281, ~330, ~1344 — other class-side readers; not audited here.

No row or db field holds the site. Decide whether it moves to the row
(stamped at declaration) or is dropped from the messages.

## Decision needed (2026-09-24, fix/small-todos-batch-2026-09-24) -- not implemented

Measured what the site actually IS today (`_registered_at` = the line the
generated `class` block runs at):

```
# line1
-module(siteq, [p(A), d(X), v(K, V)])     # line 2
-dynamic(d/1)                             # line 3
helper(1),                                # line 6
p(1),                                     # line 8
```

| name   | `_registered_at` line | `row.source`          |
|--------|-----------------------|-----------------------|
| p/1    | 2 (the `-module` entry, not the clauses at 8) | `('siteq', <file>)` |
| d/1    | 2 (not the `-dynamic` at 3)                  | `None` (no clauses)  |
| helper | 6 (first clause)                             | `('siteq', <file>)` |

And the refusal it feeds (`clob` imports `p` and writes `p(3),`) already names
the FILE three times; the site adds only `:2`, which points at the export
list:

```
  those 2 clauses are siteq's own
    .../siteq.clausal
  p is declared at .../siteq.clausal:2        <- the only line that goes quiet
  ...
  compile_module step 4: .../clob.clausal may not write p/1: its 2 clauses are owned by .../siteq.clausal
```

**A -- move it to the row** (stamp at declaration; ~3 lines in compiler_v2
step 3/4 + the reader):

```python
# PredRow
declared_at: "tuple[str, int] | None" = None
# compiler_v2, where the row is first minted for a DECLARATION (export entry,
# -dynamic, first clause) -- first writer wins:
row = db.row(functor, arity, create=True)
if row.declared_at is None:
    row.declared_at = (filename, node.lineno)
# _redefinition_error:
declared_at=resolve_predicate_row(pred_cls, arity=arity).declared_at,
```
Output unchanged: `p is declared at .../siteq.clausal:2`. Needs a ruling on
WHICH line is "the declaration" (export entry vs `-dynamic` vs first clause --
today's answer is an accident of where the class block is emitted), and it
edits `compiler_v2` step 3/4, which `feat/drop-vocabulary-implements-2026-09-24`
is also changing.

**B -- drop the line** (delete the `declared_at` kwarg and the 4 lines that
print it in `import_diagnostics.describe_imported_predicate_redefinition`):
output loses only `p is declared at .../siteq.clausal:2`; the file is still
printed by the author line and the gate line. The other `_registered_at`
readers (`predicate.py` construction/arity errors, `specialization._SpecTarget`)
are all class-built paths that retire WITH the class, so nothing else needs a
home.

Recommendation: B (the file is already there twice; the line number names the
export list, not the clauses). Not applied because `import_diagnostics.py` is
owned by the unmerged vocabulary-drop branch right now.
