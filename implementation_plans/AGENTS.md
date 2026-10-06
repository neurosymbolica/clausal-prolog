# implementation_plans/ — dated plans, specs, handoffs and execution records

The project's working history: design memos, census results, phase plans,
session handoffs between agent instances, and per-task execution records. Use it
for **why** something is the way it is. It is not the current truth: plans were
written before the work, handoffs describe the tree on their date, and many
predate the 2026-09 term-representation changes and the 2026-10-02 extension
flip (where `.clausal` meant seam source, and names were TitleCase). The truth
is the code, the tests and `../CHANGELOG.md`.

Up: [../AGENTS.md](../AGENTS.md)

## Map

| Kind | Files | Notes |
|---|---|---|
| Session handoffs | `SESSION-HANDOFF-2026-09-*-engine-lane*.md`, `W4B2D-LANE-HANDOFF-2026-09-23.md`, `p32-cell-flip-handoff.md`, `p33-state-relocation-handoff.md`, `p34-dict-set-tagging-handoff.md` | "What landed, what is open, what next" on a date; latest engine-lane handoff is 2026-09-25 |
| Execution records | `p32-execution-record/`, `p33-execution-record/` (`progress.md` + `task-N-report.md`), `*-execution-record-*.md` | What each task actually did, with commits |
| Dated design / scope memos | `*-2026-09-*.md` at top level (e.g. `multi-arity-names-2026-09-29.md`, `truth-values-as-atoms-2026-09-30.md`, `native-iso-reader-step2-2026-09-29.md`, `release-1.0.0-and-push-plan-2026-09-25.md`) | Census numbers, options, the operator ruling taken |
| Term-representation program | `phase3-decomposition-and-p31-atom-pivot.md`, `tagged-tuple-term-representation.md`, `p4-predicatemeta-retirement-scope-*.md`, `w3-*`, `w4-*`, `w4b*` | The cells/atoms-as-str/PredicateMeta-retirement series; reasoning also in `../docs/superpowers/specs/` |
| Reader / front end | `toklex-*.md`, `prolog-reader-l1l2-plan.md`, `prolog-parser-formalism-handoff.md`, `prolog-*-lowering.md` | `toklex-token-formalism-design.md` carries an IMPLEMENTED status line |
| Subsystem folders (mostly older, undated) | `compiler/`, `clpfd/`, `clpb/`, `clpq/`, `clpr/`, `chr/`, `data_structures/`, `import_system/`, `reflection/`, `meta_interpreter/`, `std_modules/`, `naming/`, `free_threaded/`, `docs/`, `benchmarking/`, `prolog_interop/` | Original plans per subsystem; several have a `todo/` subfolder of old todos |
| Optional-package plans | `jax/`, `pytorch/`, `opencv/`, `ortools/`, `pysat/`, `z3/`, `scipy/`, `scikit_learn/`, `neurosymbolic_platform/`, `package_extraction/` | Phase-by-phase port plans for `../packages/clausal-*` |
| Prototypes with code | `z3-c-bridge-prototype-2026-09-13/` (`FINDINGS.md`, a C bridge, benches), `native-iso-reader-step2-2026-09-29/` (probes, `.pl` fixtures), `dcg_audit/` (probes), `big_rename/` (scripts), `proto_termproxy.py` | Not part of the package; not maintained |
| Roadmaps / sketches | `ROADMAP_V2.md`, `NEUROSYMBOLIC_PLATFORM_SKETCH.md`, `USEFUL_LIBRARIES.md`, `COPY_AND_PATCH_BACKEND.md`, `STARTUP_LATENCY.md`, ... | Early vision documents; `ROADMAP_V2.md` still describes TitleCase naming |
| `superpowers/plans/` | One plan (2026-05-24) | The rest of the superpowers specs/plans are in `../docs/superpowers/` |

## Finding the relevant one

1. `grep -ril '<topic>' implementation_plans docs/superpowers` — names are
   descriptive; dated files carry the date in the name.
2. Order by when they were written: `git log --diff-filter=A --format='%ad' --date=short -- <file>`
   (checkout mtimes are meaningless).
3. Code comments, todos and `CHANGELOG.md` cite plans by path and rulings by
   date ("operator ruling 2026-09-26"); follow those links from the code you are
   changing rather than reading folders front to back.
4. For "what is the state now", prefer the newest handoff or execution record
   on the topic, then confirm against the code and tests.

## Gotchas

- Paths like `/workspace/clausal`, `/workspace/_d47` and branch/worktree names
  are from the machine the work was done on; they do not exist here.
- A plan's checkboxes and "Status" lines are rarely updated after landing.
  `../docs/design-records/README.md` lists what it treats as authoritative.
- `implementation_plans/*/todo/` are old todos outside the `../todo/` system
  (see [../todo/AGENTS.md](../todo/AGENTS.md)); verify before acting on them.
- The prototype `.pl`/`.seam` files here are collected by a bare `pytest` run
  from the repo root; run `python -m pytest tests` instead.
- Doc-snippet testing pattern: [docs/DOC_SNIPPET_TESTING.md](docs/DOC_SNIPPET_TESTING.md)
  (examples there still say ```` ```clausal ```` / `.clausal`; today it is
  ```` ```seam ```` / `.seam`, see [../docs/AGENTS.md](../docs/AGENTS.md)).
