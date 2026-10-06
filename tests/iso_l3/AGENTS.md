# tests/iso_l3/ — the native `.pl` / `.clausal` front end

Tests for "L3", the native ISO front end: the ISO reader
(`clausal/tools/prolog_reader.py`) followed by `clausal/tools/iso_l3.py`, which
lowers clauses straight to the transformed AST the seam produces, with
directives handled by `clausal/tools/iso_l3_directives.py`. `.clausal` (Clausal
Prolog) files always load through it; a `.pl` file does only when
`CLAUSAL_PL_FRONTEND=native` (unset or `translator` is the default: the older
`prolog_to_clausal` → seam text path). Plan:
`implementation_plans/native-iso-reader-step2-2026-09-29.md`.
Up: [../AGENTS.md](../AGENTS.md).

## Map

| Path | What it is |
|---|---|
| `conftest.py` | The `native` fixture (`NativeLoads.load(name, text, suffix=".pl", frontend="native", refused=0)`): writes a file to `tmp_path`, clears `__pycache__`, imports it, and asserts the loader class and the L3 stats (`read > 0`, `read == lowered + refused`). The `ans` fixture returns `answers(mod, name, arity, *fixed)`. |
| `test_l3_slice0.py`, `test_l3_s1_*.py` … `test_l3_s6_*.py` | One file group per plan slice (terms, bodies, refusals, directives, declarations, constructs, CLP, constants/units/dicts). |
| `test_l3_s{1,2,4,5}_exit.py` | Slice exit tests: a rulebase run natively, compared answer-for-answer with a hand-written seam twin and/or Scryer. |
| `rulebase_s1.pl` + `rulebase_s1_twin.seam`, `s2/` (`native/`, `twin/`, `oracle/`), `s3/` (`native/`, `twin/`), `s4/`, `s5/` | DATA for the exit tests. |
| `test_l3_frontend_switch.py` | `CLAUSAL_PL_FRONTEND` selection and the front end being part of the bytecode cache key. |
| other `test_l3_*.py` | Single features or review findings (DCG, lambdas, `end_module`, library facades, truth atoms, `retract`, ...). |

## Gotchas

- The rulebases and `s2`–`s5` are listed in `conftest.py`'s `collect_ignore`:
  collected by the root plugin they would load under the default (translator)
  front end and test the wrong thing. Add new rulebase data there too.
- Always assert which front end ran (use the `native` fixture, or check the
  loader class). Both front ends write the same `__pycache__` file name with
  different cache keys; a stale cache or a missing env var silently tests the
  other front end.
- Several tests call Scryer through `tests/_oracles.py` and skip (or fail, by
  their own policy) when the binary is missing.

See also [../../docs/clausal_prolog.md](../../docs/clausal_prolog.md) and
[../../docs/importing_prolog.md](../../docs/importing_prolog.md).
