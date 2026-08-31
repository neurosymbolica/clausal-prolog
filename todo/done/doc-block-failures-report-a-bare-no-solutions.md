# A failing docs code block still reports a bare "no solutions"

**Filed:** 2026-07-30, while wiring goal-level diagnostics into the pytest
plugin ([[test-diagnostics-not-wired-into-the-pytest-plugin]], now done).

`ClausalItem.runtest` (the `.clausal` file path) now runs a failing test through
`diagnose_failure` and reports which conjunct failed, the bindings live at that
point and the nearest solution. `DocItem.runtest` — the sibling collector for
```` ```clausal ```` blocks in `docs/*.md` — was left alone and still raises:

```
Test('sum [1,2,3,4] = 10') has no solutions
```

That is the same missing signal, on the collector that fires whenever a tutorial
example rots.

It was left out because the two cases are not symmetric, and the asymmetry is
the open question:

* `DocItem` compiles its block into a `NamedTemporaryFile` and **unlinks it**
  (`conftest.py`, `DocMdFile.collect`) before any item runs. `diagnose_failure`
  takes `path` only to reify the source, so a doc block has no `path` to pass.
  Without it the diagnosis degrades to the runtime term's `term_str` and
  `bindings at failure: (unavailable — could not recover source variable
  names …)` — real signal, but a fraction of what the file path gets.
* Keeping the temp file alive until the item runs (or writing blocks into a
  session-scoped directory) would restore the full diagnosis, but it changes
  when doc-block temp files are cleaned up, and a whole-docs run compiles a lot
  of blocks. `_REIFY_CACHE` is capped at 16 entries, so a run with many failing
  blocks would also thrash it.

So the choice is: accept the degraded (path-less) diagnosis, which is cheap and
strictly better than today; or give doc blocks a stable on-disk home for the
duration of the session and get the same report the file path gets. The second
is the better report and the larger change.

Either way the plumbing already exists — `run_test(..., diagnose=True)` and
`conftest._with_diagnosis` — so the work is the temp-file lifetime decision,
not the diagnostic.
