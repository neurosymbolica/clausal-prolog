# Wire pytest into CI

Current `.gitlab-ci.yml` has a single job (`pages`) that installs
`mkdocs-material` and builds the site. The test suite is **not**
run in CI. A PR that breaks tests can still pass CI.

## What breaks as a result

The compiler migration adds several structural tests — the
runtime/compiler boundary check
(`tests/test_runtime_compiler_boundary.py`), invariant assertions
to come in slice F, the parallel-implementation AST-diff harness
in slice D. These tests encode architectural rules. They only
*enforce* those rules if CI fails the merge when they fail.

Right now they're enforcement-on-paper only — they run when
someone runs `pytest` locally, but the merge gate doesn't depend
on them.

## What's needed

Add a `test` stage to `.gitlab-ci.yml`:

```yaml
test:
  stage: test
  image: python:3.13-slim
  before_script:
    - apt-get update && apt-get install -y gcc
    - pip install -e .
  script:
    - python -m pytest --ignore=tests/test_trealla_backend.py -q
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
```

Things that need to be worked out:

- Python version pinning (test under 3.13; consider matrix
  across 3.12 and 3.13).
- Caching pip + compiled C extensions across jobs (the build is
  non-trivial).
- Excluding trealla backend tests (they require the `trealla`
  binary; already excluded locally).
- Running the docs-snippet tests — they currently have 32 pre-
  existing failures, orthogonal to the compiler. Either fix them
  or mark as expected-failure.
- Deciding whether to fail the job on the 32 known pre-existing
  failures or to exclude them from CI while tracked separately.

## Why not blocked right now

The compiler migration can proceed without CI enforcement — tests
still run locally and PRs can be reviewed. But each slice that
relies on "CI catches violations" is degraded to "manual-review
catches violations" until this is in place. Wire it in before
slice F (which adds ~10 invariant assertions) and ideally before
slice D (which adds the parallel-implementation harness whose
entire value is CI-level diff detection).

## Out of scope

- Switching from GitLab CI to GitHub Actions.
- Adding coverage, linting, type-checking jobs.
- Release-automation, artifact publishing, etc.
