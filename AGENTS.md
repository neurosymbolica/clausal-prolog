# AGENTS.md — start here

**For AI agents coming in cold.** You have no memory of this project or of
earlier sessions. This file tells you what the system is and where things are;
it is a map, not documentation. Read it first, then the `AGENTS.md` in the
folder you are about to work in — most large folders have one, and each links
up to its parent and down to its children.

## What this is

**Clausal Prolog** is a cut-free Prolog that aims for ISO Prolog conformity,
running *inside* CPython: the Python package `clausal` (Python ≥ 3.13), with C
extensions for logic variables, the trail, the trampoline and the constraint
solvers. Prolog and Python share one process, one set of objects and one garbage
collector, and call each other. Engine features: unification and backtracking
without a WAM, SLG tabling with well-founded semantics, CLP(Z)/CLP(B)/CLP(Q)/
CLP(R), `dif/2`, DCGs, modules, and a large standard library over Python.

Terms are plain Python values: an atom is a `str`, a compound is a tuple
`(functor, *args)` (a "cell"), a list is a Python `list`, a string is the carrier
`('$chars', text)`. The 1-tuple is reserved — never build `('name',)`.

## Three source surfaces

| Extension | Surface | Notes |
|---|---|---|
| `.clausal` | **Clausal Prolog** | ISO syntax; `!`, `->`, `*->` refused; a module file ends with `:- end_module(Name).`; may not import `.pl`; reaches Python only through `library(...)` facades, Python-free `.seam` modules, or `python_bridges` allowlisted in `pyproject.toml`. Read by the native ISO front end. |
| `.pl` | **ISO Prolog** | Regular ISO Prolog, cut included. Importing one in-process is experimental (and that loader refuses cut today); full ISO runs in the Scryer/Trealla embeddings under `packages/`. |
| `.seam` | **the seam** | The Python-syntax surface and the boundary with Python: `<-` rules, trailing-comma facts, ALL_CAPS variables, `++expr` (call Python), `--goal` (query from Python). In the seam, `==` evaluates arithmetic and `is` unifies — the reverse of ISO. Atoms must be declared (`-module`/`-private`). |

**The extension flip (2026-10-02).** Before it, `.clausal` *was* seam source.
Old docs, todos, comments and history may still say `.clausal` meaning the seam.
Suffixes are defined once in [`clausal/_suffixes.py`](clausal/_suffixes.py);
never spell a suffix elsewhere.

## Repository map

| Path | What | Map |
|---|---|---|
| `clausal/` | The package: import hook, CLI, test runner, term layer, front ends, engine | [clausal/AGENTS.md](clausal/AGENTS.md) |
| `clausal/logic/` | The engine core: variables/trail (C), solve, compiler, builtins, constraints, tabling | [clausal/logic/AGENTS.md](clausal/logic/AGENTS.md) |
| `clausal/templating/` | The seam compiler (seam source → Python AST) | [clausal/templating/AGENTS.md](clausal/templating/AGENTS.md) |
| `clausal/tools/` | Prolog reader, native ISO front end, `.pl`↔seam translators | [clausal/tools/AGENTS.md](clausal/tools/AGENTS.md) |
| `clausal/modules/` | Python-backed modules: `py/` adapters, units, currency, countries | [clausal/modules/AGENTS.md](clausal/modules/AGENTS.md) |
| `clausal/library/` | Generated `library(...)` `.seam` facades for Clausal Prolog | [clausal/library/AGENTS.md](clausal/library/AGENTS.md) |
| `tests/` | The engine's test suite (pytest + `test/1` clauses in source files) | [tests/AGENTS.md](tests/AGENTS.md) |
| `packages/` | Optional `clausal-*` packages (scipy, jax, torch, Scryer, Trealla, ...) | [packages/AGENTS.md](packages/AGENTS.md) |
| `docs/` | The MkDocs site (clausal.pl) | [docs/AGENTS.md](docs/AGENTS.md) |
| `todo/` | Open problems; `done/`, `rejected/` | [todo/AGENTS.md](todo/AGENTS.md) |
| `implementation_plans/` | Dated plans, specs, session handoffs (history) | [implementation_plans/AGENTS.md](implementation_plans/AGENTS.md) |
| `tools/`, `scripts/` | Dev tools (`wheel_smoke.py` for releases) and one-off scripts | [tools/AGENTS.md](tools/AGENTS.md) |
| `benchmarks/` | Benchmark workloads and profilers | [benchmarks/AGENTS.md](benchmarks/AGENTS.md) |
| `pyproject.toml`, `setup.py`, `MANIFEST.in` | Packaging; `setup.py` lists the C extensions | |
| `CHANGELOG.md` | Every behaviour change and ruling since 0.4.0, under "Unreleased" | |
| `.github/workflows/` | `docs.yml` (GitHub Pages), `release.yml` (wheels → PyPI on a release) | |
| `.gitlab-ci.yml` | GitLab Pages copy of the docs (the repo has both remotes) | |

## Build, run, test

```bash
pip install -e .                       # builds the C extensions; needs a C compiler
clausal prog.clausal -g "goal(X)"      # run a program (docs/cli.md)
python -m pytest tests                 # the engine suite
python -m pytest packages              # optional packages: in a SEPARATE session
mkdocs build                           # the docs site (pip install mkdocs-material)
```

- Expect failures in a bare environment: tests for z3, OR-Tools and pysat, and
  the `tests/iso/*_scryer.py` oracles (they need the Scryer binary). Compare
  against a baseline run by test name, not by count. Without OR-Tools (and,
  for `packages`, numpy) a collection error stops the run: add
  `--continue-on-collection-errors`. See [tests/AGENTS.md](tests/AGENTS.md).
- If `pytest-timeout` is installed, `pyproject.toml`'s `timeout = 10` uses the
  thread method and one slow test kills the whole run: add
  `--timeout-method=signal`.
- Some tests pin source **line numbers** (e.g. `tests/test_funnel_lint.py`,
  the allowlist in `tests/test_doc_snippet_coverage.py`); moving code can break
  them — shift the pin and say why.

## Where the truth is

- **Code and tests** are the truth. Run things; don't trust prose.
- **`CHANGELOG.md`** (Unreleased) records each behaviour change and the
  *operator ruling* behind it; code comments cite rulings by date
  ("operator ruling 2026-10-04").
- **`docs/public-api.md`** is the 1.0 semantic-versioning surface.
- **`todo/`** holds known open problems — check it before "fixing" something
  that is a recorded, deliberate gap.
- **`implementation_plans/`, `docs/superpowers/`, `docs/design-records/`** are
  dated history and rationale. Useful for *why*; often stale on *what is*.

## Conventions

- Commit subjects are `area: what changed` (`docs:`, `todo:`, `fix(reif):`,
  `compiler:`); the body says why and how it was verified.
- Behaviour changes get a `CHANGELOG.md` entry under "Unreleased".
- Docs code blocks are tested: ```` ```seam ```` blocks compile, Python blocks
  run (`tests/test_doc_*.py`). Clausal Prolog examples go in ```` ```prolog ````.
- Todos: fix → add a `**Status: FIXED date (commit).**` line naming the
  pinning test and move the file to `done/`; see [todo/AGENTS.md](todo/AGENTS.md).
- Clausal is cut-free on every surface, by design. Don't add committed choice.
