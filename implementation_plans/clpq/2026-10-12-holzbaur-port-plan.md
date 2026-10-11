# CLP(Q) Holzbaur port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a faithful, C-portable Python port of clp(q,r) 1.3.3 that runs
beside today's solver behind a switch and passes the oracle, the fuzzers and
`filled_rectangle`.

**Architecture:**
- Today's `clausal/logic/clpq.py` becomes `clausal/logic/clpq/legacy.py`
  inside a package.  `clausal/logic/clpq/__init__.py` exports the same names
  from whichever solver the switch selects.
- The port is one module per 1.3.3 file, in full-word names.  State lives in
  one immutable attribute record per variable, trailed by the engine.
- Answers are checked against the Scryer CLP(Q) oracle by solution-set
  equivalence, decided with z3.

**Tech Stack:**
- Python 3.13 (the repository venv `/workspace/clausal/venv`) and the
  engine's attributed variables and trail;
- pytest;
- z3 (`z3-solver`, already in the venv) and scipy, for the oracle comparison
  and the fuzzers;
- Scryer with CLP(Q) at `/workspace/scryer-prolog-clpq`, through
  `tests/_oracles.py`.

**Spec:** `implementation_plans/clpq/2026-10-12-holzbaur-port-design.md`.
Read it first.  Every task argues from it.

**Scope:** this plan covers switch-over steps 1 and 2 of the spec: the
reading copy and comparison tool, then the port behind the switch.  Step 3
(flip the default, with downstream answer comparison) and step 4 (delete the
legacy solver) get their own plan once this one has landed.

## Global Constraints

- **Port source:** only `/workspace/sicstus/lib/sicstus-4.10.1/library/clpq/*.pl`,
  the files dated 2018-11-08.
- **Never read for the port:** SWI-Prolog `clpqr`, `library/clpq/clpq-algorithm.md`,
  and the notes in `/workspace/claude_sicstus_clpq/`.  A claim taken from them
  counts only once checked against the `.pl` source or a test.
- **Names:** full words for every module, function, field and local.  No
  abbreviations, including in the reading copy.  `NAMES.md` maps each 1.3.3
  name to its new name.
- **C-portable subset:**
  - Use: `__slots__` records, `int`, `dict`, `list`, `tuple`, explicit loops.
  - Do not use: `Fraction`, generators or closures in the solver core,
    recursion whose depth grows with input size, `getattr` or `isinstance`
    dispatch on hot paths.
- **Errors:** failure is `return False`.  An exception means only what a C
  error return would mean.
- **No module-level mutable state in the port.**  All state is in attribute
  records or in locals.
- **Hook cascades are queued, never nested.**  `Later` work goes through
  `trail.push_pending` (under `trail.defer`) or a local worklist drained by
  one loop.
- **Comments:** a comment saying how something works must name the test or
  profile that shows it.  Otherwise, leave it out.
- **Deviations:** every difference from 1.3.3 gets an entry in
  `clausal/logic/clpq/DEVIATIONS.md`.  An optimisation needs a measurement
  in its entry.
- **Provenance:** every ported module begins with:

  ```
  # Ported from clp(q,r) version 1.3.3, file <name>.pl
  # (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
  # Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
  # See clausal/logic/clpq/PROVENANCE.md.
  ```

- **Barrier:** the repository is public.  No downstream project names in any
  file, test or commit.  Run the barrier scan before each commit.
- **Process:**
  - Stage explicit paths only; never `git add -A`.
  - Run the suite and A/B from a worktree pinned to the commit under test,
    never from the tree being edited.
- **Run Python as** `PYTHONPATH=<worktree> /workspace/clausal/venv/bin/python`.
  A new worktree needs `setup.py build_ext --inplace` first.

## Review Focus

These five failure modes are implied by the spec but no task's main tests
exercise them.  Each line's test is added to the task named.

1. **Strictness after backtracking.**  A strict bound tightened and then
   undone must come back strict, not as `=<`.  Expected: `{X < 3},
   ({X =< 2}, fail ; true), sup(X, S)` gives `S = 3`, not attained.  Owner:
   Task 8.
2. **Unifying two constrained variables from different components.**  The
   classes must merge, bounds must combine, and both must be undone on
   backtracking.  Expected: `{X >= 1}, {Y =< 0}, X = Y` fails;
   `{X >= 1}, {Y =< 5}, (X = Y, fail ; true)` leaves both stores as they were.
   Owner: Task 11.
3. **Coefficient growth.**  Rationals with numerators over 10^60 must stay
   exact: no floats, no overflow, results equal `Fraction` arithmetic.
   Expected: a 30-step chain `X_{i+1} = (7/13)*X_i + 1/3` solves exactly.
   Owner: Task 4 (unit) and Task 9 (end to end).
4. **Variables with units, through the switch.**  The units layer must give
   the same answers with either solver.  Expected: today's
   `tests/test_units_clp.py` passes with `CLAUSAL_CLPQ=holzbaur`.  Owner:
   Task 14.
5. **Residuals that keep delayed non-linear goals.**  An answer whose store
   holds a waiting `X*Y = 6` must show it and not drop it.  Expected:
   `{X*Y = 6}` with nothing bound answers with that goal in the residual,
   as the oracle does.  Owner: Task 12.

---

## File map

| Path | Responsibility | Task |
|---|---|---|
| `clausal/logic/clpq/__init__.py` | the switch; exports the public names | 1, 14 |
| `clausal/logic/clpq/legacy.py` | today's solver, moved unchanged | 1 |
| `clausal/logic/clpq/PROVENANCE.md`, `DEVIATIONS.md`, `NAMES.md` | records | 2, then every task |
| `clausal/logic/clpq/arithmetic.py` | rationals on (numerator, denominator) ints | 4 |
| `clausal/logic/clpq/attributes.py` | the attribute record, its key, trailed get/put, the later-work queue | 5 |
| `clausal/logic/clpq/variable_ordering.py` | `ordering.pl` | 6 |
| `clausal/logic/clpq/linear_forms.py` | `store.pl` | 6 |
| `clausal/logic/clpq/components.py` | `class.pl` | 7 |
| `clausal/logic/clpq/delayed_goals.py` | `geler.pl` | 7 |
| `clausal/logic/clpq/bounded_simplex.py` | `bv.pl` | 8 |
| `clausal/logic/clpq/inequalities.py` | `ineq.pl` | 9 |
| `clausal/logic/clpq/normal_form.py` | `nf.pl`, `nfq.pl` | 10 |
| `clausal/logic/clpq/attribute_hooks.py` | `itf3.pl` | 11 |
| `clausal/logic/clpq/fourier_motzkin.py`, `redundancy.py`, `projection.py`, `residual_constraints.py` | `fourmotz.pl`, `redund.pl`, `project.pl`, `dump.pl` | 12 |
| `clausal/logic/clpq/branch_and_bound.py` | `bb.pl` | 13 |
| `clausal/logic/clpq/holzbaur.py` | the legacy-compatible API over the port | 14 |
| `tools/clpq_reference/rename.py`, `tools/clpq_reference/rename_map.tsv` | builds the private reading copy | 2 |
| `tests/clpq_oracle.py` | runs a goal on Scryer and on Clausal, compares solution sets | 3 |
| `tests/clpq_port/` | per-task tests | 3 to 15 |

Not ported:
- `arith.pl`'s `compile_Qn`/`linearize` (goal-expansion code generation).
  This is deviation D1, recorded in Task 4.
- `compenv.pl` (SICStus compile environment).  This is D2.

The reading copy lives outside the repository, at `/workspace/clpq-reference/`.

---

### Task 1: Turn `clpq` into a package, with no change in behaviour

**Files:**
- Move: `clausal/logic/clpq.py` to `clausal/logic/clpq/legacy.py`, using
  `git mv` and then staging the destination path explicitly.
- Create: `clausal/logic/clpq/__init__.py`
- Test: `tests/clpq_port/test_package_surface.py`

**Interfaces:**
- **Produces:** `clausal.logic.clpq` exports every name it exports today.
  `clausal.logic.clpq.SOLVER` is `"legacy"` or `"holzbaur"`, read once from
  the environment variable `CLAUSAL_CLPQ` (default `"legacy"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/clpq_port/test_package_surface.py
"""clausal.logic.clpq exports the same names whichever solver is selected."""
import importlib

import clausal.logic.clpq as clpq

LEGACY_NAMES = sorted(n for n in dir(importlib.import_module(
    "clausal.logic.clpq.legacy")) if not n.startswith("__"))


def test_the_package_exports_every_legacy_name():
    missing = [n for n in LEGACY_NAMES if not hasattr(clpq, n)]
    assert missing == []


def test_the_default_solver_is_legacy(monkeypatch):
    monkeypatch.delenv("CLAUSAL_CLPQ", raising=False)
    assert importlib.reload(clpq).SOLVER == "legacy"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `PYTHONPATH=$W /workspace/clausal/venv/bin/python -m pytest tests/clpq_port/test_package_surface.py -q`
Expected: FAIL, `ModuleNotFoundError: clausal.logic.clpq.legacy`.

- [ ] **Step 3: Move the module and write the package init**

```bash
mkdir -p clausal/logic/clpq
git mv clausal/logic/clpq.py clausal/logic/clpq/legacy.py
```

```python
# clausal/logic/clpq/__init__.py
"""CLP(Q): constraint logic programming over the rationals.

``CLAUSAL_CLPQ`` selects the solver: ``legacy`` (default, the pre-2026-10-12
solver) or ``holzbaur`` (the port of clp(q,r) 1.3.3, see PROVENANCE.md).
"""
import os as _os

SOLVER = _os.environ.get("CLAUSAL_CLPQ", "legacy")
if SOLVER not in ("legacy", "holzbaur"):
    raise ValueError(f"CLAUSAL_CLPQ must be legacy or holzbaur, not {SOLVER!r}")

from clausal.logic.clpq.legacy import *  # noqa: E402,F401,F403
from clausal.logic.clpq import legacy as _legacy  # noqa: E402

# Private names other modules import today (Q_KEY users, tests, the CLI).
for _name in dir(_legacy):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)
```

`legacy.py` has no `__all__`, so the `*` import skips private names.  The
loop re-exports the private ones that tests and `cli.py` use today:
`_tableaux`, `_last_snapshot`, `_get_tableau`, `_linearize`.

- [ ] **Step 4: Check that hooks are registered once**

`legacy.py` calls `register_attr_hook(Q_KEY, _q_hook)` at import, and the
package imports it once.  Check this with `grep -n register_attr_hook
clausal/logic/clpq/legacy.py` (one line) and by running the step 5 tests.

- [ ] **Step 5: Run the surface test and every CLP test file**

Run:
`PYTHONPATH=$W /workspace/clausal/venv/bin/python -m pytest tests/clpq_port/test_package_surface.py $(ls tests/test_clp*.py tests/test_units_clp.py tests/test_integral_rationals.py tests/test_seam_set_goal_clpq.py tests/test_cli.py tests/test_dump_q_projection.py) -q`
Expected: PASS, with the same pass and skip counts as on `main`.

- [ ] **Step 6: Check the C importer**

`clausal/logic/_clpfd_propagate.c` calls
`PyImport_ImportModule("clausal.logic.clpq")` and reads attributes from it.
Run `grep -n "clpq_mod" clausal/logic/_clpfd_propagate.c` and confirm that
every attribute it reads is exported by the package.  Then run
`tests/test_clpz*.py` and `tests/test_clpfd*.py` and confirm they pass.

- [ ] **Step 7: Commit**

```bash
git add clausal/logic/clpq/__init__.py clausal/logic/clpq/legacy.py tests/clpq_port/test_package_surface.py
git commit -m "clpq: become a package (legacy solver unchanged, CLAUSAL_CLPQ switch)"
```

---

### Task 2: The private reading copy, the name map, and the records

**Files:**
- Create: `tools/clpq_reference/rename.py`, `tools/clpq_reference/rename_map.tsv`
- Create: `clausal/logic/clpq/PROVENANCE.md`, `clausal/logic/clpq/DEVIATIONS.md`,
  `clausal/logic/clpq/NAMES.md`
- Output, outside the repository: `/workspace/clpq-reference/sicstus/*.pl` and
  `/workspace/clpq-reference/scryer/clpq.pl`
- Test: `tests/clpq_port/test_rename_preserves_answers.py`

**Interfaces:**
- **Produces:**
  - `rename_map.tsv`: one `old<TAB>new` per line, covering atoms that are
    predicate names, attribute names or bound-type functors.
  - `rename.py SRC DST`: rewrites Prolog atoms outside quoted strings and
    comments, keeping variables and comments.
  - `NAMES.md`: the same map, as a table.

- [ ] **Step 1: List every atom to rename**

Run, and save the output to `/workspace/clpq-reference/atoms.txt`:

```bash
cd /workspace/sicstus/lib/sicstus-4.10.1/library/clpq
grep -ohE "^[a-z][a-zA-Z0-9_]*" *.pl | sort -u
```

Also list the bound-type functors (`t_none`, `t_l`, `t_u`, `t_lu`, `t_L`,
`t_U`, `t_Lu`, `t_lU`) and the attribute names (`class`, `order`, `lin`,
`forward`, `type`, `strictness`, `nonzero`, `target`, `keep_indep`, `keep`,
`goals`, `all_nonlin`).

- [ ] **Step 2: Write `rename_map.tsv`**

Every abbreviation becomes full words.  These rows are fixed by the spec:

```
lin	linear_form
nf	normal_form
solve_x	solve_for_variable
class	component
order	ordering
t_none	bounds_none
t_l	bounds_lower
t_u	bounds_upper
t_lu	bounds_lower_upper
t_L	bounds_strict_lower
t_U	bounds_strict_upper
t_Lu	bounds_strict_lower_upper
t_lU	bounds_lower_strict_upper
arith_eval	evaluate_arithmetic
nf_ordering	compare_variable_order
add_linear_ff	add_linear_forms_scaled
add_linear_11	add_linear_forms
mult_hom	multiply_homogeneous_part
decompose	split_linear_form
```

Every other atom from step 1 gets a row too.  An atom that is already full
words maps to itself, so the map stays complete.  Built-ins and library
predicates (`append`, `length`, `var`, `nonvar`, `is`, `compare`, `put_atts`,
`get_atts`) are not renamed.

- [ ] **Step 3: Write `rename.py`**

```python
# tools/clpq_reference/rename.py
"""Rename atoms in a Prolog file per rename_map.tsv (the reading copy).

Usage: rename.py MAP SRC DST.  Rewrites unquoted atoms only, leaving
variables, numbers, quoted atoms, strings and comments as they are.
"""
import re
import sys

TOKEN = re.compile(
    r"(%[^\n]*)"                    # line comment
    r"|(/\*.*?\*/)"                 # block comment
    r"|('(?:[^'\\]|\\.|'')*')"      # quoted atom
    r"|(\"(?:[^\"\\]|\\.)*\")"      # string
    r"|(0'.)"                       # character code
    r"|([a-z][A-Za-z0-9_]*)"        # unquoted atom: the only thing renamed
    r"|(.)", re.S)


def load_map(path):
    pairs = {}
    with open(path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                old, new = line.rstrip("\n").split("\t")
                pairs[old] = new
    return pairs


def rename(text, pairs):
    out = []
    for m in TOKEN.finditer(text):
        atom = m.group(6)
        out.append(pairs.get(atom, atom) if atom is not None else m.group(0))
    return "".join(out)


if __name__ == "__main__":
    pairs = load_map(sys.argv[1])
    with open(sys.argv[2]) as f:
        text = f.read()
    with open(sys.argv[3], "w") as f:
        f.write(rename(text, pairs))
```

- [ ] **Step 4: Write the test that the rename keeps every answer**

It renames the runnable Scryer copy with the same map and compares answers
to the original Scryer copy on the 1.3.3 examples.  The example file has no
licence issue: it is run, not copied into the repository.

```python
# tests/clpq_port/test_rename_preserves_answers.py
"""The renamed reading copy answers exactly as the original (Scryer copy)."""
import pathlib
import subprocess

import pytest

from tests._oracles import SCRYER, run_scryer

HERE = pathlib.Path(__file__).resolve().parents[2]
RENAME = HERE / "tools/clpq_reference/rename.py"
MAP = HERE / "tools/clpq_reference/rename_map.tsv"
ORIGINAL = pathlib.Path("/workspace/scryer-prolog-clpq/src/lib/clpq.pl")
EXAMPLES = pathlib.Path("/workspace/claude_sicstus_clpq/test_examples_clpq.pl")

pytestmark = pytest.mark.skipif(
    not (ORIGINAL.exists() and EXAMPLES.exists() and pathlib.Path(SCRYER).exists()),
    reason="needs the local Scryer CLP(Q) build and the 1.3.3 examples")


def test_renamed_copy_gives_the_same_example_results(tmp_path):
    renamed = tmp_path / "clpq.pl"
    subprocess.run(["python3", RENAME, MAP, ORIGINAL, renamed], check=True)
    goal = "run_tests"          # the examples file's entry point
    before = run_scryer([str(ORIGINAL), str(EXAMPLES)], goal, timeout=600)
    after = run_scryer([str(renamed), str(EXAMPLES)], goal, timeout=600)
    assert after.stdout == before.stdout
    assert "error" not in after.stdout.lower()
```

Before relying on the test, check the examples file's real entry predicate
with `grep -n "^run\|^main\|initialization" $EXAMPLES` and set `goal` to it.
If the file uses `user:` hooks that name renamed predicates, rename the
examples file with the same map as well.

- [ ] **Step 5: Run it and confirm it passes**

Expected: PASS.  If it fails, the map renamed a built-in or missed one
occurrence.  Fix the map; don't special-case the test.

- [ ] **Step 6: Build the reading copy**

```bash
mkdir -p /workspace/clpq-reference/sicstus /workspace/clpq-reference/scryer
for f in /workspace/sicstus/lib/sicstus-4.10.1/library/clpq/*.pl; do
  python3 tools/clpq_reference/rename.py tools/clpq_reference/rename_map.tsv "$f" \
    /workspace/clpq-reference/sicstus/$(basename "$f")
done
python3 tools/clpq_reference/rename.py tools/clpq_reference/rename_map.tsv \
  /workspace/scryer-prolog-clpq/src/lib/clpq.pl /workspace/clpq-reference/scryer/clpq.pl
```

- [ ] **Step 7: Write the three records**

- `PROVENANCE.md` covers:
  - the source path and its date;
  - clp(q,r) 1.3.3, (c) 1992-1995 OFAI, Christian Holzbaur;
  - the operator's decision of 2026-10-12, with its reasons: the copyright
    holder cannot be reached, the operator accepts the risk, and clean room
    carries a correctness risk;
  - that SWI's rework is not used;
  - that `clpq-algorithm.md` and the `/workspace/claude_sicstus_clpq` notes
    are excluded.
- `DEVIATIONS.md` starts with:
  - D1: rationals as (numerator, denominator) ints, with `compile_Qn`
    goal expansion not ported;
  - D2: `compenv.pl` not ported;
  - D3: the hook mapping, with a list of sites, filled in by Task 11.
- `NAMES.md` is `rename_map.tsv` as a table: old name, new name, file.

- [ ] **Step 8: Barrier scan and commit**

```bash
git add tools/clpq_reference/rename.py tools/clpq_reference/rename_map.tsv \
  clausal/logic/clpq/PROVENANCE.md clausal/logic/clpq/DEVIATIONS.md \
  clausal/logic/clpq/NAMES.md tests/clpq_port/test_rename_preserves_answers.py
git commit -m "clpq: full-word name map, reading-copy tool, provenance and deviation records"
```

---

### Task 3: The oracle comparison tool

**Files:**
- Create: `tests/clpq_oracle.py`
- Test: `tests/clpq_port/test_oracle_tool.py`

**Interfaces:**
- **Produces:**
  - `oracle_answers(program_text: str, goal: str, variables: list[str]) -> list[Answer]`
    runs on Scryer.
  - `clausal_answers(program_text, goal, variables, solver: str) -> list[Answer]`
    runs on Clausal, in a subprocess with `CLAUSAL_CLPQ=solver`.
  - `same_solution_sets(a: list[Answer], b: list[Answer]) -> tuple[bool, str]`
    compares the answers in order.  Two answers are equal when the shown
    variables' bindings match and z3 proves the two residual conjunctions
    equivalent over the shown variables, with the other variables existential.
  - `Answer` is `(bindings: dict[str, Fraction | None], residual: list[str])`.

The answers are collected with one goal per system:

```
findall(Vs-Cs, (Goal, clpq:dump(Vs, Names, Cs)), L)
```

Scryer runs this through `run_scryer`.  Clausal runs the same program with
`CLAUSAL_PL_FRONTEND=native`.  It uses `-g` when that can collect all
answers; otherwise it loads the program through
`clausal.import_hook._load_module` and solves `findall` itself.  Use
whichever path Clausal's `dump/3` supports.  Check with
`git grep -n "def _dump" clausal/logic/builtins/constraints.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/clpq_port/test_oracle_tool.py
from tests.clpq_oracle import Answer, same_solution_sets


def test_the_same_residual_in_another_form_is_equal():
    a = [Answer({}, ["X+Y=<3", "X>=0"])]
    b = [Answer({}, ["0=<X", "Y=<3-X"])]
    assert same_solution_sets(a, b)[0]


def test_a_weaker_residual_is_not_equal():
    a = [Answer({}, ["X<3"])]
    b = [Answer({}, ["X=<3"])]
    ok, why = same_solution_sets(a, b)
    assert not ok and "X" in why


def test_bindings_must_match():
    assert not same_solution_sets([Answer({"X": 1}, [])], [Answer({"X": 2}, [])])[0]


def test_the_number_and_order_of_answers_count():
    one = Answer({"X": 1}, [])
    two = Answer({"X": 2}, [])
    assert not same_solution_sets([one, two], [two, one])[0]
```

- [ ] **Step 2: Run them and confirm they fail**

Expected: `ModuleNotFoundError: tests.clpq_oracle`.

- [ ] **Step 3: Write the comparison**

```python
# tests/clpq_oracle.py
"""Answer sets from Scryer's CLP(Q) and Clausal's, compared by equivalence."""
import re
from collections import namedtuple
from fractions import Fraction

import z3

Answer = namedtuple("Answer", "bindings residual")

_RELATIONS = {"=<": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
              "<": lambda a, b: a < b, ">": lambda a, b: a > b,
              "=": lambda a, b: a == b, "=:=": lambda a, b: a == b,
              "=\\=": lambda a, b: a != b}
_SPLIT = re.compile(r"(=<|>=|=:=|=\\=|<|>|=)")


def _expression(text, names):
    """A residual side (``2*X + 1/3 - Y``) as a z3 term over *names*."""
    text = text.replace(" ", "")
    text = re.sub(r"(\d+)/(\d+)", r"(Q(\1,\2))", text)
    return eval(text, {"Q": z3.Q, "__builtins__": {}}, names)  # noqa: S307


def _formula(residual, names):
    parts = []
    for constraint in residual:
        constraint = constraint.strip().strip("{}")
        left, relation, right = _SPLIT.split(constraint, maxsplit=1)
        parts.append(_RELATIONS[relation](_expression(left, names),
                                          _expression(right, names)))
    return z3.And(parts) if parts else z3.BoolVal(True)


def _names(*residuals):
    found = set()
    for residual in residuals:
        for constraint in residual:
            found.update(re.findall(r"\b[A-Z_][A-Za-z0-9_]*\b", constraint))
    return {n: z3.Real(n) for n in found}


def _equivalent(first, second):
    names = _names(first, second)
    solver = z3.Solver()
    solver.add(z3.Not(_formula(first, names) == _formula(second, names)))
    return solver.check() == z3.unsat


def same_solution_sets(left, right):
    if len(left) != len(right):
        return False, f"{len(left)} answers against {len(right)}"
    for i, (a, b) in enumerate(zip(left, right)):
        if a.bindings != b.bindings:
            return False, f"answer {i}: bindings {a.bindings} against {b.bindings}"
        if not _equivalent(a.residual, b.residual):
            return False, f"answer {i}: residual {a.residual} against {b.residual}"
    return True, ""
```

Internal variables (`_A`, `_Q1`) in a residual are free in the formula.  This
compares two sets whose internal variables are both existentially closed.
Wrap each side in `z3.Exists` over its names that start with `_` before
comparing:

```python
def _closed(residual, names):
    inner = [names[n] for n in names if n.startswith("_")]
    body = _formula(residual, names)
    return z3.Exists(inner, body) if inner else body
```

`_equivalent` then compares `_closed(first)` with `_closed(second)`.  Add a
test that two residuals differing only in internal names are equal.

- [ ] **Step 4: Run the tests and confirm they pass**

- [ ] **Step 5: Add the two runners and a self-check against the oracle**

`oracle_answers` and `clausal_answers` build the `findall`/`dump` goal above
and parse the printed list with the same `_SPLIT` and fraction syntax.  Add:

```python
def test_scryer_against_itself_on_a_known_store():
    program = ":- use_module(library(clpq)).\np(X, Y) :- {X + Y =< 3, X >= 0}.\n"
    answers = oracle_answers(program, "p(X, Y)", ["X", "Y"])
    assert same_solution_sets(answers, [Answer({}, ["X+Y=<3", "X>=0"])])[0]
```

Skip it when the Scryer build is missing, like Task 2's test.

- [ ] **Step 6: Commit**

```bash
git add tests/clpq_oracle.py tests/clpq_port/test_oracle_tool.py
git commit -m "tests: CLP(Q) answer-set comparison against the Scryer oracle (z3 equivalence)"
```

---

### Task 4: Rational arithmetic

**Files:**
- Create: `clausal/logic/clpq/arithmetic.py`
- Test: `tests/clpq_port/test_arithmetic.py`

**Interfaces:**
- **Produces:** plain functions on `Rational = tuple[int, int]` (numerator,
  denominator), with denominator > 0 and gcd 1:
  - `make_rational(numerator: int, denominator: int) -> Rational`
  - `add`, `subtract`, `multiply`, `divide`: `(Rational, Rational) -> Rational`
  - `negate(Rational) -> Rational`
  - `compare(Rational, Rational) -> int`, returning -1, 0 or 1
  - `sign(Rational) -> int`
  - `is_zero(Rational) -> bool`
  - `ZERO`, `ONE`
  - `from_number(x) -> Rational`, accepting `int`, `Fraction` or `Decimal`
  - `to_number(Rational) -> int | Fraction`, giving an int when the
    denominator is 1, as `present_number` does

  `divide` by zero raises `ZeroDivisionError`.  That is a programming error,
  never solver failure.

- [ ] **Step 1: Write the failing tests**, comparing against `Fraction`:

```python
# tests/clpq_port/test_arithmetic.py
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.clpq import arithmetic as a


def _fraction(r):
    return Fraction(*r)


@pytest.mark.parametrize("seed", range(200))
def test_operations_agree_with_fractions(seed):
    rng = random.Random(seed)
    x = a.make_rational(rng.randint(-10**40, 10**40), rng.randint(1, 10**30))
    y = a.make_rational(rng.randint(-10**40, 10**40), rng.randint(1, 10**30))
    fx, fy = _fraction(x), _fraction(y)
    assert _fraction(a.add(x, y)) == fx + fy
    assert _fraction(a.subtract(x, y)) == fx - fy
    assert _fraction(a.multiply(x, y)) == fx * fy
    if fy:
        assert _fraction(a.divide(x, y)) == fx / fy
    assert a.compare(x, y) == (fx > fy) - (fx < fy)


def test_normal_form():
    assert a.make_rational(4, -6) == (-2, 3)
    assert a.make_rational(0, 5) == (0, 1)


def test_coefficient_growth_stays_exact():           # Review Focus 3
    x = a.ZERO
    step = a.make_rational(7, 13)
    third = a.make_rational(1, 3)
    for _ in range(30):
        x = a.add(a.multiply(step, x), third)
    expected = Fraction(0)
    for _ in range(30):
        expected = Fraction(7, 13) * expected + Fraction(1, 3)
    assert _fraction(x) == expected and x[1] > 10**30


def test_numbers_in_and_out():
    assert a.from_number(Decimal("0.25")) == (1, 4)
    assert a.to_number((6, 1)) == 6 and type(a.to_number((6, 1))) is int
    assert a.to_number((1, 2)) == Fraction(1, 2)
```

- [ ] **Step 2: Run them and confirm they fail** (module missing).

- [ ] **Step 3: Implement**

```python
# clausal/logic/clpq/arithmetic.py
"""Exact rationals as (numerator, denominator) pairs of ints.

Deviation D1 (DEVIATIONS.md): 1.3.3 evaluates rat(N,D) terms through
arith_eval, expanded at compile time; this module is the plain-function
equivalent, written so it maps one-to-one onto C over PyLong.
"""
from decimal import Decimal
from fractions import Fraction
from math import gcd

ZERO = (0, 1)
ONE = (1, 1)


def make_rational(numerator, denominator):
    if denominator == 0:
        raise ZeroDivisionError("rational with denominator 0")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    common = gcd(numerator, denominator)
    if common > 1:
        numerator //= common
        denominator //= common
    return (numerator, denominator)


def add(x, y):
    return make_rational(x[0] * y[1] + y[0] * x[1], x[1] * y[1])


def subtract(x, y):
    return make_rational(x[0] * y[1] - y[0] * x[1], x[1] * y[1])


def multiply(x, y):
    return make_rational(x[0] * y[0], x[1] * y[1])


def divide(x, y):
    if y[0] == 0:
        raise ZeroDivisionError("rational division by zero")
    return make_rational(x[0] * y[1], x[1] * y[0])


def negate(x):
    return (-x[0], x[1])


def compare(x, y):
    left = x[0] * y[1]
    right = y[0] * x[1]
    return (left > right) - (left < right)


def sign(x):
    return (x[0] > 0) - (x[0] < 0)


def is_zero(x):
    return x[0] == 0


def from_number(x):
    if type(x) is int:
        return (x, 1)
    if type(x) is Fraction:
        return (x.numerator, x.denominator)
    if type(x) is Decimal:
        f = Fraction(x)
        return (f.numerator, f.denominator)
    raise TypeError(f"not an exact number: {x!r}")


def to_number(x):
    return x[0] if x[1] == 1 else Fraction(x[0], x[1])
```

- [ ] **Step 4: Run the tests and confirm they pass**

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpq/arithmetic.py tests/clpq_port/test_arithmetic.py
git commit -m "clpq port: exact rationals as integer pairs (D1)"
```

---

### Task 5: The attribute record and the later-work queue

**Files:**
- Create: `clausal/logic/clpq/attributes.py`
- Test: `tests/clpq_port/test_attributes.py`

**Interfaces:**
- **Produces:**
  - `CLPQ_KEY = "clpq_holzbaur"`.  This is a new key, so the port never
    collides with legacy's `Q_KEY` while both solvers coexist.
  - `class SolverState` (`__slots__`, immutable by convention).  Fields:
    - `linear_form`
    - `bounds` (one of the `bounds_*` names, holding the bound values)
    - `lower_strict`, `upper_strict`
    - `component`
    - `ordering`
    - `nonzero`
    - `delayed_goals`
    - `forward`, `target`, `keep_independent`, `keep`

    Unset fields are `None` or `False`.
  - `state_of(variable) -> SolverState | None`
  - `with_changes(state, **fields) -> SolverState` (a copy)
  - `put_state(variable, state, trail) -> None`, which uses `put_attr` and
    so is trailed
  - `class LaterWork`, a local worklist: `push(callable)`, `drain() -> bool`.
    `drain` runs items in first-in-first-out order, including items that
    running items push, and returns False on the first failure.

  The field names are the spec's table; `NAMES.md` maps them to 1.3.3's
  attributes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/clpq_port/test_attributes.py
from clausal.logic.clpq.attributes import (
    LaterWork, SolverState, put_state, state_of, with_changes)
from clausal.logic.variables import Trail, Var


def test_a_state_change_is_undone_on_backtracking():
    trail, x = Trail(), Var()
    put_state(x, SolverState(), trail)
    mark = trail.mark()
    put_state(x, with_changes(state_of(x), lower_strict=True), trail)
    assert state_of(x).lower_strict
    trail.undo(mark)
    assert state_of(x).lower_strict is False


def test_later_work_runs_in_order_and_nests_no_frames():
    order = []
    work = LaterWork()

    def chain(i):
        def step():
            order.append(i)
            if i < 50_000:          # far past the recursion limit
                work.push(chain(i + 1))
            return True
        return step

    work.push(chain(0))
    assert work.drain()
    assert order == list(range(50_001))


def test_later_work_stops_at_the_first_failure():
    work = LaterWork()
    ran = []
    work.push(lambda: ran.append(1) or False)
    work.push(lambda: ran.append(2) or True)
    assert work.drain() is False and ran == [1]
```

The `lambda`s are test code only.  The solver core pushes named functions,
or bound methods of records, which map to C function pointers plus data.

- [ ] **Step 2: Run them and confirm they fail**

- [ ] **Step 3: Implement**

```python
# clausal/logic/clpq/attributes.py
"""The per-variable solver state and the queue for follow-up work.

The state is one record per constrained variable, replaced (never mutated)
through put_attr, so the engine's trail undoes every change.  The fields
are clp(q,r) 1.3.3's attributes in full words (NAMES.md).
"""
from collections import deque

from clausal.logic.variables import get_attr, put_attr

CLPQ_KEY = "clpq_holzbaur"

_FIELDS = ("linear_form", "bounds", "lower_strict", "upper_strict",
           "component", "ordering", "nonzero", "delayed_goals", "forward",
           "target", "keep_independent", "keep")


class SolverState:
    __slots__ = _FIELDS

    def __init__(self, linear_form=None, bounds=None, lower_strict=False,
                 upper_strict=False, component=None, ordering=None,
                 nonzero=False, delayed_goals=None, forward=None,
                 target=False, keep_independent=False, keep=False):
        self.linear_form = linear_form
        self.bounds = bounds
        self.lower_strict = lower_strict
        self.upper_strict = upper_strict
        self.component = component
        self.ordering = ordering
        self.nonzero = nonzero
        self.delayed_goals = delayed_goals
        self.forward = forward
        self.target = target
        self.keep_independent = keep_independent
        self.keep = keep


def state_of(variable):
    return get_attr(variable, CLPQ_KEY)


def with_changes(state, **fields):
    copy = SolverState.__new__(SolverState)
    for name in _FIELDS:
        setattr(copy, name, fields[name] if name in fields else getattr(state, name))
    return copy


def put_state(variable, state, trail):
    put_attr(variable, CLPQ_KEY, state, trail)


class LaterWork:
    """Follow-up work (1.3.3's Later goals), run by one loop, never nested."""
    __slots__ = ("queue",)

    def __init__(self):
        self.queue = deque()

    def push(self, work):
        self.queue.append(work)

    def drain(self):
        queue = self.queue
        while queue:
            if not queue.popleft()():
                queue.clear()
                return False
        return True
```

`with_changes` uses `setattr` on purpose: it is not a hot path, and it is one
C function in the port.  If profiling later shows it hot, that is a
deviation entry.

- [ ] **Step 4: Run the tests and confirm they pass**

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpq/attributes.py tests/clpq_port/test_attributes.py
git commit -m "clpq port: solver state record (trailed) and later-work queue"
```

---

## How to port a 1.3.3 file (Tasks 6 to 13)

Each porting task applies this procedure to its file(s).  The reading copy
in `/workspace/clpq-reference/sicstus/` is the text you translate.  The
original in `/workspace/sicstus/.../library/clpq/` is the authority when
the two differ.

1. **One Python function per predicate,** named by `NAMES.md`.  A
   predicate with several clauses becomes one function whose `if`/`elif`
   chain follows the clause order.  The first clause whose head and guard
   match wins; a cut ends the chain.
2. **Arguments.**  Input arguments become parameters.  Output arguments
   become return values: a tuple if there are several, `None` or `False`
   on failure.  Mode comes from the call sites.  Check every call site
   with `grep -n "<name>(" /workspace/clpq-reference/sicstus/*.pl`.
3. **Linear forms.**  1.3.3's `[Inhomogeneous, Rest | Terms]`, with
   `Terms = [X*K, ...]` sorted by `compare_variable_order`, becomes the
   record `LinearForm(constant: Rational, rest: Rational, terms:
   list[tuple[variable, Rational]])`.  The `terms` list is kept in the same
   order.  `rest` is always zero in Q.  Port it anyway, and delete it only
   with a deviation entry backed by a test.
4. **Recursion over lists becomes a loop.**  Recursion that halves its input
   (`renormalize_log`) may stay recursive, since its depth is log n.  Note
   that in a comment.
5. **Arithmetic** goes through `arithmetic.py`.  `arith_eval(Expression,
   Result)` becomes direct calls.  `arith_eval(Relation)` becomes `compare`.
6. **Attribute reads and writes** go through `attributes.py`.  1.3.3's
   `get_atts(V, -A)` (absent) is `state_of(V) is None` or a `None` field.
7. **Backtracking inside the solver** becomes `mark = trail.mark()` … then
   `trail.undo(mark)`, with the carried value in a local.  `bb_put`/`bb_get`
   values become locals.
8. **Every function gets a comment** citing `file.pl, name/arity`.

**Worked example** (`store.pl`, `add_linear_ff/5` and its helper
`add_linear_ffh/5,7`):

```python
def add_linear_forms_scaled(form_a, factor_a, form_b, factor_b):
    """store.pl add_linear_ff/5: factor_a*form_a + factor_b*form_b."""
    constant = add(multiply(form_a.constant, factor_a),
                   multiply(form_b.constant, factor_b))
    rest = add(multiply(form_a.rest, factor_a), multiply(form_b.rest, factor_b))
    terms = []
    i, j = 0, 0
    a, b = form_a.terms, form_b.terms
    while i < len(a) and j < len(b):           # add_linear_ffh/7
        x, kx = a[i]
        y, ky = b[j]
        relation = compare_variable_order(x, y)
        if relation == 0:
            k = add(multiply(kx, factor_a), multiply(ky, factor_b))
            if not is_zero(k):
                terms.append((x, k))
            i += 1
            j += 1
        elif relation < 0:
            terms.append((x, multiply(kx, factor_a)))
            i += 1
        else:
            terms.append((y, multiply(ky, factor_b)))
            j += 1
    while i < len(a):                          # mult_hom on the rest of A
        terms.append((a[i][0], multiply(a[i][1], factor_a)))
        i += 1
    while j < len(b):                          # mult_hom on the rest of B
        terms.append((b[j][0], multiply(b[j][1], factor_b)))
        j += 1
    return LinearForm(constant, rest, terms)
```

The two-way merge is the recursion of `add_linear_ffh/7`, unrolled.  Its
argument swap (`add_linear_ffh(Ys, X, Kx, Xs, Ztail, Kb, Ka)`) becomes the
two index variables.

**Tests for every porting task** are of three kinds:
- **Unit tests** for pure functions, compared against a straightforward
  reference (`Fraction`-based dict arithmetic for linear forms).
- **Depth tests,** where the task owns list recursion: an input of 50,000
  terms runs without `RecursionError`.
- **Oracle tests** with `tests/clpq_oracle.py`, once enough exists to post
  and dump.  From Task 12 on, every task adds its oracle tests to
  `tests/clpq_port/test_against_oracle.py`.

---

### Task 6: `variable_ordering` and `linear_forms` (`ordering.pl`, `store.pl`)

**Files:**
- Create: `clausal/logic/clpq/variable_ordering.py` (`ordering.pl`, 138 lines)
- Create: `clausal/logic/clpq/linear_forms.py` (`store.pl`, 279 lines)
- Test: `tests/clpq_port/test_linear_forms.py`

**Interfaces:**
- **Produces:**
  - `compare_variable_order(x, y) -> int`
  - `LinearForm`
  - every `store.pl` predicate under its `NAMES.md` name.  These include
    `add_linear_forms`, `add_linear_forms_scaled`, `multiply_linear_form`,
    `normalize_scalar`, `renormalize`, `delete_factor`,
    `multiply_homogeneous_part`, `split_linear_form`, and the
    `nf_coefficient_of` and `nf_substitute` equivalents.  Use the names the
    map assigns.

- [ ] **Step 1: Write the failing tests**

```python
# tests/clpq_port/test_linear_forms.py
import random
from fractions import Fraction

import pytest

from clausal.logic.clpq.arithmetic import make_rational, to_number
from clausal.logic.clpq.linear_forms import LinearForm, add_linear_forms_scaled
from clausal.logic.clpq.variable_ordering import compare_variable_order
from clausal.logic.variables import Var


def _as_dict(form):
    d = {id(v): Fraction(*k) for v, k in form.terms}
    return Fraction(*form.constant), d


def _sorted_terms(pairs):
    return sorted(pairs, key=lambda p: p[0]._id)


@pytest.mark.parametrize("seed", range(100))
def test_scaled_addition_agrees_with_fraction_dicts(seed):
    rng = random.Random(seed)
    xs = [Var() for _ in range(6)]
    def form():
        chosen = rng.sample(xs, rng.randint(0, 6))
        return LinearForm(make_rational(rng.randint(-9, 9), 1), (0, 1),
                          _sorted_terms([(v, make_rational(rng.randint(-9, 9) or 1,
                                                           rng.randint(1, 5)))
                                         for v in chosen]))
    a, b = form(), form()
    ka, kb = make_rational(rng.randint(-5, 5), 3), make_rational(rng.randint(-5, 5), 7)
    got = add_linear_forms_scaled(a, ka, b, kb)
    ca, da = _as_dict(a)
    cb, db = _as_dict(b)
    fa, fb = Fraction(*ka), Fraction(*kb)
    want = {k: fa * da.get(k, 0) + fb * db.get(k, 0) for k in set(da) | set(db)}
    want = {k: v for k, v in want.items() if v}
    assert _as_dict(got) == (fa * ca + fb * cb, want)
    assert [v for v, _ in got.terms] == sorted((v for v, _ in got.terms),
                                               key=lambda v: v._id)


def test_a_long_form_needs_no_recursion():
    xs = [Var() for _ in range(50_000)]
    big = LinearForm((0, 1), (0, 1), [(v, (1, 1)) for v in xs])
    assert len(add_linear_forms_scaled(big, (1, 1), big, (1, 1)).terms) == 50_000
```

The sort key `_id` is a stand-in.  Use the order `compare_variable_order`
defines, which is `ordering.pl`'s stable order.  When porting `ordering.pl`,
replace the key with that function and keep the assertion.

- [ ] **Step 2: Run them and confirm they fail**
- [ ] **Step 3: Port `ordering.pl`, then `store.pl`,** following the procedure.
  Every predicate in each file, in file order, each with its citation.
- [ ] **Step 4: Run the tests and confirm they pass**
- [ ] **Step 5: Update `NAMES.md`** for any name the port needed beyond the map.
- [ ] **Step 6: Commit**

```bash
git add clausal/logic/clpq/variable_ordering.py clausal/logic/clpq/linear_forms.py \
  clausal/logic/clpq/NAMES.md tests/clpq_port/test_linear_forms.py
git commit -m "clpq port: variable ordering and linear forms (ordering.pl, store.pl)"
```

---

### Task 7: `components` and `delayed_goals` (`class.pl`, `geler.pl`)

**Files:**
- Create: `clausal/logic/clpq/components.py` (`class.pl`, 110 lines)
- Create: `clausal/logic/clpq/delayed_goals.py` (`geler.pl`, 124 lines)
- Test: `tests/clpq_port/test_components.py`

**Interfaces:**
- **Consumes:** `attributes.py` (Task 5).
- **Produces:**
  - `components.py`: `new_component(...)`, `component_drop`,
    `component_all_variables`, `component_basis`, `component_basis_add`,
    `component_basis_drop`, `component_get_priority`,
    `component_put_priority`, and `verify_component(x, y, trail) ->
    LaterWork | False`.  These are `class.pl`'s predicates in full words.
    A component is a hidden `Var` whose attribute holds the component's
    record (members, tail, basis, priority).
  - `delayed_goals.py`: `delay_until_linear` and the `verify_delayed` hook
    part.

- [ ] **Step 1: Write the failing tests**
  1. A new component, then adding a variable to its basis, then undoing to a
     mark, gives the component back as it was.
  2. Merging two components through `verify_component`, then undoing,
     leaves two separate components.
  3. Dropping a variable from a 50,000-member component needs no recursion.

  Write them in the style of Task 5's undo test.

- [ ] **Step 2: Run them and confirm they fail**
- [ ] **Step 3: Port `class.pl` and `geler.pl`**
- [ ] **Step 4: Run the tests and confirm they pass**
- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpq/components.py clausal/logic/clpq/delayed_goals.py tests/clpq_port/test_components.py
git commit -m "clpq port: components and delayed goals (class.pl, geler.pl)"
```

---

### Task 8: `bounded_simplex` (`bv.pl`, 1,266 lines)

**Files:**
- Create: `clausal/logic/clpq/bounded_simplex.py`
- Test: `tests/clpq_port/test_bounded_simplex.py`

**Interfaces:**
- **Consumes:** Tasks 4 to 7.
- **Produces:** every `bv.pl` predicate in full words.  These include
  `solve_for_variable`, the basis maintenance, `pivot`, the `increase_step`
  and `decrease_step` family, `infimum`, `supremum`, `minimize`, `maximize`,
  the `backsubstitute` family, and `determine_active`.

`inf/2` and `sup/2` use 1.3.3's failure-driven loop: pivot to the optimum,
store it with `bb_put`, fail back to the start vertex.  In the port that
becomes:

```python
mark = trail.mark()
optimum = iterate_decrease(dependent)     # the pivots
trail.undo(mark)                          # back to the start vertex
return optimum
```

Unify the result after the undo, as 1.3.3 does after `bb_delete`.

- [ ] **Step 1: Write the failing tests** (they run once Tasks 9 to 11 exist):
  1. `inf`/`sup` leave the store as it was: dump before and after are
     equivalent under `same_solution_sets`.
  2. Review Focus 1: `{X < 3}, ({X =< 2}, fail ; true), sup(X, S)` gives
     `S = 3` against the oracle.
  3. The box-bounded LP from 2026-10-11 (maximise `X + 3*Y` in
     `0=<X=<2, 0=<Y=<3, X+2*Y=<6`) gives 9 at (0, 3).

  Mark them with `pytest.mark.skipif` until `normal_form` exists, and remove
  the skip in Task 10.
- [ ] **Step 2: Port `bv.pl`,** every predicate in file order.  The pivot
  updates every dependent row's `linear_form` through `put_state`, one
  trailed replace per touched row, as 1.3.3 does through `put_atts`.
- [ ] **Step 3: Write unit tests for the pure pieces** (pivot row algebra
  against `Fraction` dicts, as in Task 6) and run them.
- [ ] **Step 4: Commit**

```bash
git add clausal/logic/clpq/bounded_simplex.py tests/clpq_port/test_bounded_simplex.py
git commit -m "clpq port: bounded-variable simplex (bv.pl)"
```

---

### Task 9: `inequalities` (`ineq.pl`, 984 lines)

**Files:**
- Create: `clausal/logic/clpq/inequalities.py`
- Test: `tests/clpq_port/test_inequalities.py`

**Interfaces:**
- **Consumes:** Task 8.
- **Produces:** `ineq.pl`'s predicates.  These include the posting entry
  points that `normal_form` calls for `<`, `=<`, `>`, `>=`, each with its
  bound-type case analysis (`bounds_*`, strict and non-strict).

- [ ] **Step 1: Port `ineq.pl`**
- [ ] **Step 2: Write unit tests on the bound-type case analysis.**  For
  each of the eight `bounds_*` types, tightening and loosening with strict
  and non-strict bounds is compared against a direct interval computation.
  Write them and run them.
- [ ] **Step 3: Review Focus 3, end to end.**  Add the 30-step
  `X_{i+1} = (7/13)*X_i + 1/3` chain as an oracle test, skipped until Task 10.
- [ ] **Step 4: Commit**

```bash
git add clausal/logic/clpq/inequalities.py tests/clpq_port/test_inequalities.py
git commit -m "clpq port: inequalities (ineq.pl)"
```

---

### Task 10: `normal_form` (`nf.pl` 835 lines, `nfq.pl` 76 lines)

**Files:**
- Create: `clausal/logic/clpq/normal_form.py`
- Test: `tests/clpq_port/test_normal_form.py`

**Interfaces:**
- **Consumes:** Tasks 6 to 9.
- **Produces:**
  - `post_constraint(term, trail) -> bool`, the `{}/1` entry: parse,
    normalise to a linear form, and dispatch to equality (Gaussian
    `solve_for_variable`) or `inequalities`.  Non-linear constraints go to
    `delayed_goals`.
  - `entailed(term, trail) -> bool`

  Terms are Clausal's operator nodes (`Add`, `Mult`, …, as
  `legacy._linearize` reads them) and the comparison nodes `lowering`
  produces.  Check the node classes with
  `git grep -n "_ArithEq\|_LtE" clausal/logic/clpq/legacy.py`.

- [ ] **Step 1: Port `nf.pl` and `nfq.pl`**
- [ ] **Step 2: Remove the skips** in Tasks 8 and 9's tests.  Run them.
  Expected: PASS against the oracle.
- [ ] **Step 3: Write and run the first oracle tests,** in
  `tests/clpq_port/test_against_oracle.py`:

```python
import pytest

from tests.clpq_oracle import clausal_answers, oracle_answers, same_solution_sets

CASES = [
    ("p(X, Y) :- {X + Y = 3, 2*X + 2*Y = 6}.", "p(X, Y)", ["X", "Y"]),
    ("p(X) :- {X > 1, X < 3}.", "p(X)", ["X"]),
    ("p(X, Y) :- {X + Y >= 2}.", "p(X, Y)", ["X", "Y"]),
    ("p(X, Y) :- {1 =< X, X =< 5, X = Y + 1}, Y = -10.", "p(X, Y)", ["X", "Y"]),
    ("p(X, Y) :- {X < Y, Y =< 3}, X = 3.", "p(X, Y)", ["X", "Y"]),
    ("p(X) :- {X =< 3}, ({X >= 1}, fail ; true), X = 0.", "p(X)", ["X"]),
]


@pytest.mark.parametrize("body, goal, names", CASES)
def test_the_port_answers_as_the_oracle(body, goal, names):
    program = ":- use_module(library(clpq)).\n" + body + "\n"
    want = oracle_answers(program, goal, names)
    got = clausal_answers(program, goal, names, solver="holzbaur")
    ok, why = same_solution_sets(got, want)
    assert ok, why
```

These are the cases from the 2026-10-11 bug list, so the port is checked on
exactly what legacy got wrong.  Until Task 12 exists, the residual side is
empty: compare bindings only.  Remove that restriction in Task 12.

- [ ] **Step 4: Commit**

```bash
git add clausal/logic/clpq/normal_form.py tests/clpq_port/test_normal_form.py tests/clpq_port/test_against_oracle.py
git commit -m "clpq port: normal form and constraint posting (nf.pl, nfq.pl)"
```

---

### Task 11: `attribute_hooks` (`itf3.pl`, 268 lines)

**Files:**
- Create: `clausal/logic/clpq/attribute_hooks.py`
- Modify: `clausal/logic/clpq/DEVIATIONS.md` (D3 site list)
- Test: `tests/clpq_port/test_attribute_hooks.py`

**Interfaces:**
- **Consumes:** Tasks 5, 7 and 10.
- **Produces:** `holzbaur_hook(state, bound_to, trail) -> bool`, registered
  with `register_attr_hook(CLPQ_KEY, holzbaur_hook)` only when `SOLVER ==
  "holzbaur"`.  It ports `verify_attributes/3`: `verify_itf`,
  `verify_geler` and `verify_class`, combined.  Each returns `LaterWork`
  items rather than calling posts.  The hook drains the work, or pushes it
  with `trail.push_pending` under `trail.defer`, never nested.

Clausal's hook runs after the binding.  For every site in `itf3.pl` that
reads X's attributes or tests `var(X)` expecting X still unbound, record it
in D3 with what the port does instead: usually, it reads the state passed
in.  Find the sites with
`grep -n "verify_\|var(" /workspace/clpq-reference/sicstus/itf3.pl`.

- [ ] **Step 1: Write the failing tests**
  1. **Review Focus 2.**  `{X >= 1}, {Y =< 0}, X = Y` fails.
     `{X >= 1}, {Y =< 5}, (X = Y, fail ; true)` leaves both stores as they
     were (oracle and dump equivalence).
  2. **Binding to a number** inside bounds succeeds, and outside fails.  The
     strict edge: `{X < 3}, X = 3` fails.
  3. **A chain of 10,000 implied bindings** (`{X1 = X0}, {X2 = X1}, …`, then
     `X0 = 5`) binds every `Xi` to 5 without `RecursionError`.
  4. **The `dif` trial unify from 2026-10-11:**
     `{Z >= 0, Z =< 10}, {X =< 3}, dif(X-Z, 3-5), {X >= 3}, Z = 4` answers
     `Z = 4`.
- [ ] **Step 2: Run them and confirm they fail**
- [ ] **Step 3: Port `itf3.pl`** and write the D3 entries.
- [ ] **Step 4: Run the tests and confirm they pass**
- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpq/attribute_hooks.py clausal/logic/clpq/DEVIATIONS.md tests/clpq_port/test_attribute_hooks.py
git commit -m "clpq port: unification hook (itf3.pl), Later work queued not nested (D3)"
```

---

### Task 12: Projection and residuals (`fourmotz.pl`, `redund.pl`, `project.pl`, `dump.pl`)

**Files:**
- Create: `clausal/logic/clpq/fourier_motzkin.py` (294 lines),
  `clausal/logic/clpq/redundancy.py` (157 lines),
  `clausal/logic/clpq/projection.py` (147 lines),
  `clausal/logic/clpq/residual_constraints.py` (121 lines)
- Test: `tests/clpq_port/test_residuals.py`

**Interfaces:**
- **Consumes:** Tasks 6 to 11.
- **Produces:**
  - `dump(target_variables, names, trail) -> list[constraint terms]`
    (1.3.3's `dump/3`)
  - `residual_strings(target_variables, trail, name_of) -> list[str]`, in
    the form today's `-g` printer takes (`{X + Y = 3}`), with strictness
    kept
  - delayed non-linear goals included

- [ ] **Step 1: Port the four files**
- [ ] **Step 2: Turn on residual comparison** in
  `test_against_oracle.py`, so `clausal_answers` passes the dump.  Run it.
  Expected: PASS for every case.
- [ ] **Step 3: Write the Review Focus 5 test.**  `{X*Y = 6}` with nothing
  bound: the residual holds the delayed goal, as the oracle shows.  Compare
  the delayed goals textually after normalising spaces, since z3 equivalence
  does not apply to non-linear text.
- [ ] **Step 4: Write the projection fuzz test.**  For 200 seeded random
  stores (2 to 6 variables, 4 to 12 constraints, mixed `<`, `=<`, `=`), the
  dump projected onto each variable has the same infimum and supremum,
  strictness included, as the port's own `inf`/`sup`.  Compare against the
  oracle for the first 30 seeds.
- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpq/fourier_motzkin.py clausal/logic/clpq/redundancy.py \
  clausal/logic/clpq/projection.py clausal/logic/clpq/residual_constraints.py \
  tests/clpq_port/test_residuals.py tests/clpq_port/test_against_oracle.py
git commit -m "clpq port: projection and residual constraints (fourmotz, redund, project, dump)"
```

---

### Task 13: `branch_and_bound` (`bb.pl`, 139 lines)

**Files:**
- Create: `clausal/logic/clpq/branch_and_bound.py`
- Test: `tests/clpq_port/test_branch_and_bound.py`

**Interfaces:**
- **Consumes:** Task 8 (`infimum`/`supremum`) and Task 10.
- **Produces:** `bb_inf(integer_variables, expression, trail) ->
  (optimum, vertex) | None`.  The search is an explicit loop over a stack of
  branches, with `trail.mark()` and `undo` per branch.  The incumbent (1.3.3's
  `bb_put(incumbent, …)`) is a local.

- [ ] **Step 1: Write the failing tests**
  1. `{X > 0, X =< 2}, bb_inf([X], X, I)` gives `I = 1`.  This was legacy's
     strict-bound bug.
  2. Three integer knapsack instances, compared against brute force.
  3. A 12-variable instance whose search tree is deeper than 1,000 branches
     needs no recursion.
- [ ] **Step 2: Run them and confirm they fail**
- [ ] **Step 3: Port `bb.pl`**
- [ ] **Step 4: Run the tests and confirm they pass,** plus the oracle on
  test 1.
- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpq/branch_and_bound.py tests/clpq_port/test_branch_and_bound.py
git commit -m "clpq port: branch and bound (bb.pl), iterative"
```

---

### Task 14: The legacy-compatible API and the switch

**Files:**
- Create: `clausal/logic/clpq/holzbaur.py`
- Modify: `clausal/logic/clpq/__init__.py`
- Test: `tests/clpq_port/test_switch.py`

**Interfaces:**
- **Consumes:** every earlier task, and legacy's units layer
  (`_units_strip`, `_units_strip_expr`, `_units_result`, `_cell_as_node`,
  `_cells_as_nodes`).  Import these from `legacy.py`; they don't touch the
  tableau.
- **Produces:** the same callable names and signatures as legacy:
  - `q_eq`, `q_ne`, `q_le`, `q_lt`, `q_gt`, `q_ge`
  - `in_q`
  - `sup`, `inf`, `maximize`, `minimize`
  - `entailed(constraint_type, l, r, trail)`
  - `dump_q(target_vars, trail, name_of=None, *, toplevel=False)`
  - `residual_q(target_vars, trail, name_of)`
  - `bb_inf(int_vars, expr, result_var, trail)`
  - `clpq_constraint_block(constraints, trail)`
  - `Q_KEY`

  Each strips units, posts through `normal_form`, and re-attaches units on
  results.  `Q_KEY` is `CLPQ_KEY` under the port, for `sandbox.py`'s
  allowlist and `clpfd.py`'s FD-to-Q promotion.

- [ ] **Step 1: Write the failing tests**

```python
# tests/clpq_port/test_switch.py
import os
import subprocess
import sys

import pytest

LEGACY_SUITES = ["tests/test_clpq.py", "tests/test_clpq_box_bounded_optimum.py",
                 "tests/test_clpq_undo_on_backtracking.py",
                 "tests/test_dump_q_projection.py", "tests/test_units_clp.py",
                 "tests/test_seam_set_goal_clpq.py", "tests/test_cli.py"]


@pytest.mark.parametrize("suite", LEGACY_SUITES)
def test_the_suite_passes_under_the_port(suite):          # Review Focus 4
    env = dict(os.environ, CLAUSAL_CLPQ="holzbaur")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p",
                        "no:cacheprovider", suite], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:]
```

- [ ] **Step 2: Run it and confirm it fails**
- [ ] **Step 3: Write `holzbaur.py` and the switch.**  In `__init__.py`,
  under `SOLVER == "holzbaur"`, import from `holzbaur` instead of `legacy`.
  Register only the selected solver's hook.
- [ ] **Step 4: Run the suites under the port.**  A failure is one of
  three things:
  1. A porting bug: fix it in the port.
  2. A test pinned to a legacy-only answer: confirm with the oracle that
     legacy was wrong, then fix the test and note it in the commit.
  3. Output spelling: for example, Holzbaur prints `X =< 3` where legacy
     prints `{X =< 3}`.  The `-g` printer keeps Clausal's spelling, so fix
     the adapter.

  Each fixed test names its category in a comment.
- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpq/holzbaur.py clausal/logic/clpq/__init__.py tests/clpq_port/test_switch.py
git commit -m "clpq: CLAUSAL_CLPQ=holzbaur selects the port behind the legacy API"
```

---

### Task 15: Acceptance: `filled_rectangle`, the fuzzers, depth, and timing

**Files:**
- Create: `tests/clpq_port/test_acceptance.py`
- Create: `tests/clpq_port/fuzz/` (the 2026-10-11 fuzzers, rewritten as
  tests: scipy LP, z3 strictness, undo with replay, projection)
- Modify: `clausal/logic/clpq/DEVIATIONS.md` (timings, evidence)

- [ ] **Step 1: Write the `filled_rectangle` test**
  - Load `/workspace/claude_sicstus_clpq/filled_rectangle.pl`, with
    `use_module(clpq)` changed to `library(clpq)`, under the port and under
    the oracle.
  - Collect every solution of `filled_rectangle(A, C)` with `C` of length 9.
  - Assert the same solutions in the same order, with
    `same_solution_sets`.
  - Record the wall time of both runs in the test output.
  - Skip when the oracle is missing.
- [ ] **Step 2: Rewrite the four fuzzers as seeded pytest tests**
  - Each runs 300 cases by default and 9,000 with `CLPQ_FUZZ=full`.
  - Expected: zero mismatches.  The only exception is HiGHS presolve calling
    an unbounded LP infeasible; confirm each such case with an exact z3
    check rather than skipping it.
- [ ] **Step 3: Run the whole acceptance set under the port**

Expected:
- `filled_rectangle` matches the oracle;
- the fuzzers give 0 mismatches;
- the depth tests from Tasks 5, 6, 11 and 13 pass.

- [ ] **Step 4: Record evidence in `DEVIATIONS.md`.**  Record the
  `filled_rectangle` time under the port, legacy and the oracle, plus a
  `cProfile` top 15 of the port's run.  This is the first measured baseline
  for any later optimisation entry.  A comment about how something works
  goes into the port only with the test or profile that shows it.
- [ ] **Step 5: Commit**

```bash
git add tests/clpq_port/test_acceptance.py tests/clpq_port/fuzz clausal/logic/clpq/DEVIATIONS.md
git commit -m "clpq port: acceptance (filled_rectangle vs oracle), fuzzers as tests, timing baseline"
```

---

### Task 16: Gate the branch as one candidate

- [ ] **Step 1: Pin a gate worktree** at the branch tip, and build it.
- [ ] **Step 2: Run the full suite twice** in it, with `CLAUSAL_CLPQ`
  unset (legacy) and set to `holzbaur`.  Diff each failure set against
  `main`.  Expected: no new failures under legacy.  Under the port, every
  difference is explained in the commit message or fixed.
- [ ] **Step 3: Run the box gate and the interleaved A/B**, with
  `CLAUSAL_CLPQ` unset.  The default path must be unchanged.
- [ ] **Step 4: Security review** of the package, scoped to the hook, the
  queue and `bb_inf`'s loop.  Run review rounds until one is clean.
- [ ] **Step 5: Ask the two downstream gates for GOs** on the exact commit.
  The default solver is unchanged, so their answer comparison should show
  no movement.  The flip is the next plan.

---

## Self-review

- **Spec coverage:**
  - data model: Task 5;
  - module map and names: Tasks 2 and 6 to 13;
  - translation rules: the "How to port" section;
  - search and depth: Tasks 5, 6, 8, 11 and 13;
  - outside the port (units, `-g`, public names): Task 14;
  - comments and deviations: the Global Constraints and Task 15;
  - testing table: Tasks 3, 10, 12 and 15;
  - switch-over steps 1 and 2: Tasks 1, 2 and 14;
  - steps 3 and 4: deferred to the next plan, as stated in Scope;
  - provenance: Task 2.
- **Placeholders:** each porting task's code is the 1.3.3 file it names,
  translated by the stated procedure.  The worked example shows the
  translation exactly.  Writing out 5,600 lines of translated code in the
  plan would only duplicate the source.  Every task has concrete tests.
- **Names across tasks:** `LinearForm`, `SolverState`, `put_state`,
  `state_of`, `with_changes`, `LaterWork`, `CLPQ_KEY`, `make_rational`,
  `compare_variable_order` and `add_linear_forms_scaled` are used
  consistently.
- **Review Focus:** all five lines have a test in a named task.
