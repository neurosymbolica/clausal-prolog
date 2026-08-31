# rewrite corpus: catch_trampolined fixture fails with RenderError on "goal args 't'"

**Filed:** 2026-08-31, found while capturing a chunked-suite baseline for the
v1-pipeline deletion. **Pre-existing on main** — verified by restoring all
session-touched source files to `3978020c` and re-running: still fails.

## The failure

    tests/rewrite/test_corpus.py::test_rewrite_is_conserving_localized_idempotent_and_arrow_safe[tests/fixtures/catch_trampolined.clausal]
    clausal.reflection.RenderError: cannot render goal args: expected a sequence, got 't'
    (raised from _deref_seq_field, clausal/reflection.py:458, via rewrite_source → _render_head,
     head position (102, 0, 102, 83))

The rewriter (`rewrite_source` with the shipped rules) reifies the fixture and
hits a Goal whose `args` field holds the string `'t'` rather than a list —
either the reifier produced a malformed Goal for something in
`tests/fixtures/catch_trampolined.clausal` (look near line 102), or the
rewriter's own rebuild put a scalar where an arg list belongs.

Not in the 2026-08-26 61-name environmental baseline, so it arrived with a
commit between then and 2026-08-31. Candidates from `git log` over the fixture
and tests/rewrite/: `09c7b486` (if_/3 reified rename, 2026-08-26), `35ad41df`
(ite exception routing), `883cdf08` (catch/3 `not`-loop routing, 2026-08-26) —
the if_/3 reified-vocabulary rename is the most likely suspect for a Goal whose
args reify wrong.

## Repro

    cd /workspace/clausal-bug-fix
    /workspace/clausal/venv/bin/python -m pytest \
      "tests/rewrite/test_corpus.py::test_rewrite_is_conserving_localized_idempotent_and_arrow_safe[tests/fixtures/catch_trampolined.clausal]" -q
