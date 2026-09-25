# Plan: 1.0.0 release and remote push (DRAFT, 2026-09-25; waiting on the operator)

Status: **waiting for stability.** Operator, 2026-09-25: "wait for stability. versioning and push need a plan." Nothing here runs until the operator says go.

## Where things stand (2026-09-25)
- Version is `0.4.0` (pyproject.toml), tagged `v0.4.0`. There is no CHANGELOG.
- 12 packages under `packages/` are all at `0.1.0`.
- Canonical main is e107929e (the W4b-2d flip). The box and GitLab have NOT been pushed since before the 2026-09-24/25 landings, which is 12 engine merges.
- Still ahead: W4b-3, which deletes `PredicateMeta`/`make_predicate` and refuses a Python-defined predicate class at load. That removes public API.

## 1. Preconditions for 1.0.0
1. **W4b-3 has landed**, so no removal of public API follows 1.0.0.
2. **A stability window:** N days, with N set by the operator, in which
   - no engine landing changes behaviour (fixes only),
   - the full gate stays at baseline, and
   - corpus sweeps stay unchanged.
3. **docs/public-api.md exists** (see 2) and the operator has approved it.
4. **CHANGELOG.md exists** (see 3).
5. **Docs match the code:** the flip-era docs branch has landed and the doc-snippet coverage test is triaged.

## 2. docs/public-api.md: the surface semver covers
Proposed as COVERED (a breaking change here means 2.0):
- the `.clausal`/`.seam` surface language: clause forms, directives (`-module`, `-import_from`, `-dynamic`, `-meta_predicate`, `-table`, ...), and literal semantics;
- the ISO builtins and their error terms;
- the Python entry points `solve`, `call`, `query`, `once` with `module=`, and the plain-cell term representation (functor-first tuples);
- the `_get_dispatch` duck-typed protocol, whose signature is already frozen and which out-of-tree code implements;
- the import hook's public behaviour: loading `.clausal` files as modules.

Proposed as INTERNAL (it can change in a minor release):
- compiler internals, PredRow/Database internals, and trampoline/drive internals;
- the mangled predicate-handle spelling. It is opaque: compare handles with `==`, never parse them;
- the C extension ABI, and the cache formats (`.clausal` bytecode cache).

Open for the operator: whether the Prolog exporter (`clausal/tools/clausal_to_prolog.py`) and `clausal-fmt` / `clausal-rewrite` are covered.

## 3. CHANGELOG.md
- Format: Keep-a-Changelog style, with sections Added / Changed / Removed / Fixed.
- Built from the merge commits since `v0.4.0` (`git log --merges v0.4.0..main`), grouped by theme:
  - ISO conformance: error terms, `clause/2`, `call/N`, `findall` type errors, throw copies the ball;
  - modules: `-meta_predicate`, ruling S, name+arity, Q0 registry;
  - the PredicateMeta retirement: the flip, then W4b-3;
  - arithmetic and units: rationals, Decimal, currency;
  - the seam, toklex, the fmt/rewrite tools.
- It includes a **Migration guide 0.x → 1.0**:
  - `m.pred(X)` → `solve(("pred", X), module=m)`;
  - class attributes → Database reads;
  - Python-defined predicate classes → `_get_dispatch` objects.

## 4. Version bump and tag (after 1–3)
1. Bump `pyproject.toml` to `1.0.0` and set `clausal.__version__` if it exists. Commit it on its own.
2. Run the full gate and a corpus sweep on the release commit, as for any landing.
3. Make an annotated tag `v1.0.0` on that commit.
4. Leave `packages/*` at 0.x. Each package is versioned independently. The only change: raise each package's `clausal` dependency pin to `>=1.0,<2` once it has been verified against 1.0.

## 5. Pushing to the remotes
Order: box first, then GitLab.
1. **Information-barrier scan before any push** (memory: clausal-open-source-information-barrier). Scan the range `<last pushed>..main` for downstream names in new commits, using the name list kept in the barrier memory note (never spelled in the engine repo). Historical mentions are clues, not a reason for a history rewrite. NEW commits must be clean. The todo `barrier-scrub-before-gitlab-push` applies.
2. **Box:** direct push is refused, because main is checked out there. Use the `box` ssh alias to reach a shell and fast-forward there. Box is x86_64 and clock-skewed, so rebuild C with `--force` and verify by observation (memory: box-cannot-be-pushed-directly, box-is-x86_64-and-clock-skewed).
3. **GitLab:** a plain fast-forward push of main, then the `v1.0.0` tag. Verify with `git ls-remote`, never with `push | tail`.
4. Do not push backup or WIP branches.

## 6. Open questions for the operator
- How long is the stability window?
- Is the public-API scope in (2) right, and are the exporter, fmt and rewrite tools covered?
- Should the box/GitLab push happen BEFORE 1.0.0 (catching up the 12 merges once stable) or only with the release?
- Are the packages versioned independently, as proposed?
