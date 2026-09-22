# W4a — Instance-Path Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every door through which a `PredicateMeta` INSTANCE can be built or handled — Python and C — without changing any answer the engine gives.

**Architecture:** The engine already stores and lowers clause heads as cells; instances exist only because tests ask for them. So this is a deletion in four layers: the constructors (`_clausal_head`, the `__call__` bridge, `instances=True`, `_clausal_new`), the rebuild arms that only fire on an instance, the Python twins' instance branches, and the three C instance arms — each layer gated, with the tests that pinned the old path retired by name or migrated to cells.

**Tech Stack:** Python 3.13, pytest (house suite ~16.8k tests, ~3 min), the C extension `clausal/logic/variables/_variables.c` (build via `setup.py build_ext` in a same-sha worktree, rename-swap the `.so`), `tools/w3_package_gate.sh`.

**Spec:** `docs/superpowers/specs/2026-09-22-w4a-instance-path-retirement-design.md`

## Global Constraints

- Work in a worktree off `main` (never `git checkout` a branch in the shared clone `/workspace/clausal`): `git -C /workspace/clausal worktree add -b feat/w4a-instance-path-2026-09-22 <room> main`, symlink `venv -> /workspace/clausal/venv`, copy the built `.so` files from any current room (`find . -name '*.so' -not -path './venv/*'`).
- Run pytest FROM the room (`cd <room> && ./venv/bin/python -m pytest ...`); assert `clausal.__file__` starts with the room before trusting any number.
- Gate command: `./venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider --continue-on-collection-errors --ignore=tests/test_clportools.py`. Extract the failure SET with `grep -E "^(FAILED|ERROR) " out.txt | sed -E 's/ - .*//' | sort -u`; compare with `comm`. Baseline: regenerate on `main` at the start (do not trust a number from a file).
- **GONE must equal exactly the retired-test list** (Task 2's `RETIRED` list); NEW must be 0. Package gate: `./tools/w3_package_gate.sh <venv> <room> <out>` NEW 0 / GONE 0.
- Stage explicit paths only (never `git add -A`); commit messages carry the retired-test names; end with the Co-Authored-By / Claude-Session trailers used on this branch's history.
- Closed-side terms never enter commits (`clausify`, harness/gates tooling names, corpus domain paths); scan the range before landing.
- In zsh: write `"${VAR}:path"` for git rev:path; never gate a chain on `grep -c`'s exit.

---

### Task 1: Retire the instance constructors (Python)

**Files:**
- Modify: `clausal/logic/predicate.py` — `PredicateMeta.__call__` (bridge branch, ~line 1043), `PredicateMeta._clausal_head` (~line 1059), `make_predicate` (line 1806), `_make_fast_new` (line 373) and its `_clausal_new` attachment (~line 764), `_RETIRED_STATE_NAMES` (~line 592)
- Test: `tests/test_instance_path_retired.py` (create)

**Interfaces:**
- Produces: `PredicateMeta._clausal_head` is a raising tombstone (`RetiredStateError`); `make_predicate(name, fields)` takes NO `instances` keyword (passing it is a `TypeError`); `cls(...)` always builds the cell `(cls.__name__, *args-or-fresh-Vars)`; no class has `_clausal_new`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_instance_path_retired.py
"""W4a: the PredicateMeta INSTANCE path is retired (spec
docs/superpowers/specs/2026-09-22-w4a-instance-path-retirement-design.md).
A predicate class builds CELLS, and every door that built an instance is
a loud refusal, so an out-of-tree minter fails rather than drifting."""
import pytest

from clausal.logic.predicate import PredicateMeta, RetiredStateError, make_predicate
from clausal.logic.variables import Var


def test_clausal_head_is_a_raising_tombstone():
    Pt = make_predicate("Pt", ["x", "y"])
    with pytest.raises(RetiredStateError, match="_clausal_head"):
        Pt._clausal_head(x=1, y=2)


def test_make_predicate_refuses_the_instances_keyword():
    with pytest.raises(TypeError, match="instances"):
        make_predicate("Old", ["a"], instances=True)


def test_calling_a_class_always_builds_the_cell():
    Pt = make_predicate("Pt2", ["x", "y"])
    cell = Pt(x=1)
    assert cell[0] == "Pt2" and cell[1] == 1 and isinstance(cell[2], Var)
    assert type(cell) is tuple, "never an instance, whatever the class carries"


def test_no_fast_instance_constructor_is_attached():
    Pt = make_predicate("Pt3", ["x"])
    assert not hasattr(Pt, "_clausal_new")
```

- [ ] **Step 2: Run to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_instance_path_retired.py -q -p no:cacheprovider`
Expected: 4 failed — `_clausal_head` returns an instance, `instances=True` is accepted, `_clausal_new` exists.

- [ ] **Step 3: Implement**

In `predicate.py`:

1. Replace the body of `_clausal_head` with a tombstone and keep the name (an out-of-tree caller must fail loudly, not by `AttributeError`):

```python
    def _clausal_head(cls, *args: Any, **kwargs: Any) -> Any:
        """RETIRED (W4a, 2026-09-22): the clause-HEAD instance constructor.
        A head is a CELL; ``cls(...)`` builds it.  Raises, never builds."""
        raise RetiredStateError(
            f"{cls.__name__}._clausal_head was retired (W4a, 2026-09-22): a "
            f"clause head is a cell; call {cls.__name__}(...) for the cell")
```

2. In `__call__`, delete the `if cls.__dict__.get("_clausal_instances"): return cls._clausal_head(*args, **kwargs)` branch and its comment; the method falls straight through to the cell construction that follows it.

3. `make_predicate`: change the signature to `def make_predicate(name: str, fields: list[str], **refused) -> "PredicateMeta":` and add at the top:

```python
    if refused:
        raise TypeError(
            f"make_predicate() got {sorted(refused)}: the `instances=` bridge "
            f"was retired (W4a, 2026-09-22); a predicate class builds cells")
```
   and delete the `if instances: cls._clausal_instances = True` lines.

4. Delete `_make_fast_new` (line 373 through its `return fn`) and the block in `__new__` that attaches `cls._clausal_new` (the `if "_clausal_new" not in fields:` lines and their comment). Grep the file for `_clausal_new` afterwards: only docstring mentions may remain.

5. Add `"_clausal_instances": "nothing -- the P2 instance bridge is gone (W4a); a class builds cells"` to `_RETIRED_STATE_NAMES` so a stray `cls._clausal_instances = True` raises instead of silently doing nothing.

- [ ] **Step 4: Run the new tests and the neighbours**

Run: `./venv/bin/python -m pytest tests/test_instance_path_retired.py tests/test_predicate_meta.py tests/test_predrow.py -q -p no:cacheprovider`
Expected: the 4 new tests PASS; some tests in `test_predrow.py` (the W2 "instances carry no state face" tests that build an instance via `_clausal_head`) now FAIL — that is Task 2's input, not a defect here.

- [ ] **Step 5: Run the whole house suite and SAVE the failure set as Task 2's worklist**

Run: the gate command, output to `w4a_t1.txt`; extract to `w4a_t1.set`; `comm -13 base.set w4a_t1.set > w4a_newly_failing.txt`.
Expected: every newly failing test is in one of the files the spec names (test_python_fallbacks, test_fast_construction, test_predrow, test_funnel_accessors, test_clpb, test_predicate_class_as_term_value, test_tagged_terms, test_second_package_copy_term_identity, audit_2026_07_05/test_01_term_layer, audit_2026_07_05/test_04_runtime_tabling). A newly failing test OUTSIDE that list means an engine path still minted an instance: stop and read it before continuing.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/predicate.py tests/test_instance_path_retired.py
git commit -m "W4a: retire the instance constructors -- _clausal_head tombstoned, the bridge and instances= gone, no _clausal_new"
```

---

### Task 2: Retire or migrate the tests that pinned the instance path

**Files:**
- Modify (decide per test by READING it): `tests/test_python_fallbacks.py`, `tests/test_fast_construction.py`, `tests/test_predrow.py`, `tests/test_funnel_accessors.py`, `tests/test_clpb.py`, `tests/test_predicate_class_as_term_value.py`, `tests/test_tagged_terms.py`, `tests/test_second_package_copy_term_identity.py`, `tests/audit_2026_07_05/test_01_term_layer.py`, `tests/audit_2026_07_05/test_04_runtime_tabling.py`
- Create: `RETIRED.txt` in the scratchpad (the list of retired test node ids, verbatim, for the gate and the commit message)

**Interfaces:**
- Consumes: Task 1's worklist `w4a_newly_failing.txt`.
- Produces: `RETIRED.txt`; every remaining test in those files passes on the cell.

- [ ] **Step 1: For each test in the worklist, classify by reading it**

Rule from the spec: if the test's SUBJECT is the instance path (it asserts something only an instance has: attribute access on a term, `_clausal_new`, the instance arms of the C corpus), RETIRE it — delete the function and append its node id to `RETIRED.txt`. Otherwise MIGRATE: replace the instance construction with the cell and assert the same thing about the cell.

Known decisions (verify each by reading; do not apply blindly):

- `tests/test_python_fallbacks.py`: the corpus rows `("instance", Pt._clausal_head(x=X, y=2))`, `("cell_in_instance", ...)`, `("instance_in_cell", ...)` (lines ~523, 542, 543) are DELETED, and the class `TestTheCorpusStillCoversInstances` (~line 613) is DELETED — its docstring says "these rows go with the arms, together". The five `t = Pt._clausal_head(x=1, y=2)` uses near lines 43/85/125/168/238 become `t = Pt(x=1, y=2)` IF the surrounding test is about term walking generally (read the assertion: if it asserts `.x`/`.y` attribute reads, retire it instead).
- `tests/test_fast_construction.py`: the file's subject is `_clausal_new` and `instances=True`; read each test: tests of the fast constructor itself are retired; a test that only used `instances=True` to get a class and then asserts on cell/functor behaviour is migrated by dropping the keyword.
- `tests/test_predrow.py`: `test_instances_no_longer_carry_a_state_face` and the `inst = cls._clausal_head(...)` line in `test_a_field_named_like_a_retired_attribute_stays_a_field` (W2's F1 section): retire the first (there are no instances); in the second, delete the two `inst._locked` assertions and keep the class-level ones.
- `tests/test_funnel_accessors.py` (4 sites), `tests/test_clpb.py`, `tests/test_predicate_class_as_term_value.py` (`make_predicate("pcatv_cite_inst", ["key"], instances=True)`), `tests/test_tagged_terms.py`, `tests/test_second_package_copy_term_identity.py`, the two audit files: drop the keyword / replace `_clausal_head(` with the cell call, then run the file; a test that then fails on an attribute read is retired.

- [ ] **Step 2: Run each touched file alone**

Run: `./venv/bin/python -m pytest <file> -q -p no:cacheprovider`
Expected: 0 failed in each; any failure is either a migration mistake (fix) or an instance-only assertion (retire and record).

- [ ] **Step 3: Whole-suite gate**

Run: the gate command → `w4a_t2.set`. Then:
```bash
comm -13 base.set w4a_t2.set          # NEW: must be EMPTY
comm -23 base.set w4a_t2.set          # GONE: must equal RETIRED.txt, sorted
diff <(sort -u RETIRED.txt) <(comm -23 base.set w4a_t2.set) && echo "GONE == RETIRED"
```
Expected: NEW empty; GONE identical to RETIRED.txt. Note: a retired test that was already in `base.set` (failing before) appears in GONE as well; that is correct and stays on the list.

- [ ] **Step 4: Commit, naming every retired test**

```bash
git add tests/test_python_fallbacks.py tests/test_fast_construction.py tests/test_predrow.py tests/test_funnel_accessors.py tests/test_clpb.py tests/test_predicate_class_as_term_value.py tests/test_tagged_terms.py tests/test_second_package_copy_term_identity.py tests/audit_2026_07_05/test_01_term_layer.py tests/audit_2026_07_05/test_04_runtime_tabling.py
git commit -F - <<'MSG'
W4a: tests -- instance-path tests retired by name, the rest migrated to cells

RETIRED (subject was the instance path):
<paste RETIRED.txt here, one node id per line>

MIGRATED (subject reached through an instance, now through the cell):
<list the files>
MSG
```

---

### Task 3: Delete the Python rebuild arms and the twins' instance branches

**Files:**
- Modify: `clausal/logic/database.py` (the two `new_head = type(head)._clausal_head(**new_kwargs)` sites, ~lines 1330 and 1460, and the helper code above each that builds `new_kwargs` from `fields`), `clausal/logic/compiler/list_dispatch.py` (~lines 368–371, the `else:  # is_term_instance` arm), `clausal/logic/builtins/database_ops.py` (~lines 116–121, the `if is_term_instance(head):` arm), `clausal/logic/solve.py` (~lines 123–133, `rebuild = getattr(cls, "_clausal_head", cls)`), `clausal/logic/predicate.py` (`_is_term_instance_py` ~line 1557: the `if isinstance(type(obj), PredicateMeta): return True` arm; `_term_field_names_py` ~line 1580: its PredicateMeta arm)
- Test: `tests/test_instance_path_retired.py` (extend)

**Interfaces:**
- Produces: `is_term_instance(x)` is True only for a `@dataclass` instance; `term_field_names(x)` answers only for one; every head-rewrite helper handles `Compound` and cells only.

- [ ] **Step 1: Write the failing tests**

```python
def test_is_term_instance_is_dataclass_only():
    import dataclasses
    from clausal.logic.predicate import is_term_instance, term_field_names
    @dataclasses.dataclass
    class D:
        a: int
    assert is_term_instance(D(1)) is True and term_field_names(D(1)) == ("a",)
    Pt = make_predicate("Pt4", ["x"])
    assert is_term_instance(Pt(x=1)) is False, "a cell is not an instance"
    assert is_term_instance(Pt) is False, "nor is the class"


def test_the_python_twins_no_longer_carry_a_predicatemeta_instance_arm():
    import inspect
    from clausal.logic import predicate as P
    src = inspect.getsource(P._is_term_instance_py) + inspect.getsource(P._term_field_names_py)
    assert "PredicateMeta" not in src, "the instance arm is gone; only the dataclass arm remains"
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_instance_path_retired.py -q -p no:cacheprovider -k "dataclass_only or twins"`
Expected: the source-scan test FAILS (the arm is present); the first may pass already — that is fine, it pins the invariant.

- [ ] **Step 3: Implement**

- `predicate.py`: in `_is_term_instance_py` delete the `if isinstance(type(obj), PredicateMeta): return True` lines; in `_term_field_names_py` delete the branch that reads `_fields` off a PredicateMeta instance's type (keep the dataclass branch and the error for anything else).
- `solve.py` `_deref_walk_py`: replace `rebuild = getattr(cls, "_clausal_head", cls)` with `rebuild = cls` and delete the comment block that explains the old lookup; the surrounding code (`rebuild(**{name: _deref_walk_py(getattr(term, name)) for name in term_field_names(term)})`) is unchanged and now serves dataclass terms only.
- `database.py` both sites, `list_dispatch.py`, `database_ops.py`: delete the instance arm (the `if is_term_instance(head):` / `else:  # is_term_instance` branch and its `_clausal_head` rebuild). Where the arm was the final `else`, the function now ends after the cell arm; add a final `raise TypeError(f"head is neither a Compound nor a cell: {head!r}")` so an unexpected shape is loud.

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_instance_path_retired.py tests/test_python_fallbacks.py tests/test_bytes_indexing.py tests/test_predicate_arity_mismatch_diagnostic.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Whole-suite gate** — as Task 2 Step 3; NEW empty, GONE == RETIRED.txt.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/database.py clausal/logic/compiler/list_dispatch.py clausal/logic/builtins/database_ops.py clausal/logic/solve.py clausal/logic/predicate.py tests/test_instance_path_retired.py
git commit -m "W4a: delete the instance rebuild arms and the twins' PredicateMeta-instance branch"
```

---

### Task 4: Delete the C instance arms 0/2/3 and rebuild the extension

**Files:**
- Modify: `clausal/logic/variables/_variables.c` — `c_is_term_instance` (~line 2223: the `PyObject_IsInstance((PyObject *)Py_TYPE(obj), PredicateMeta_type)` fast path), `py_term_field_names` (~line 2260: the `if (PredicateMeta_type) { ... PyObject_IsInstance(cls, PredicateMeta_type) ... return fields; }` block), `c_term_field_names` (~line 2313: the same shape)
- Test: `tests/test_instance_path_retired.py` (extend), `tests/test_python_fallbacks.py` (the twin-parity corpus, already without instance rows after Task 2)

**Interfaces:**
- Produces: the C entry points `is_term_instance` / `term_field_names` agree with the Python twins for every corpus shape; `py_register_predicate_meta` and `PredicateMeta_type` STAY (arms 4–7 use them; W4b).

- [ ] **Step 1: Write the failing test (twin parity, C-observed)**

```python
def test_c_and_python_twins_agree_and_neither_knows_an_instance():
    """A positive control that OBSERVES the C arm's removal: the C entry
    point must classify a @dataclass instance as a term instance and a
    predicate CLASS / CELL as not one, exactly as the Python twin does --
    and its source no longer names the instance arm."""
    import dataclasses, pathlib
    from clausal.logic.variables import _variables as C
    from clausal.logic import predicate as P
    @dataclasses.dataclass
    class D:
        a: int
    Pt = make_predicate("Pt5", ["x"])
    for obj in (D(1), Pt, Pt(x=1), "atom", ("f", 1)):
        assert bool(C.is_term_instance(obj)) == P._is_term_instance_py(obj), obj
    src = pathlib.Path(C.__file__).with_suffix("").with_name("_variables.c").read_text()
    assert "Fast path: PredicateMeta instance" not in src
```

(If `_variables.c` is not beside the `.so`, read it from the repo root: `pathlib.Path(P.__file__).parent / "variables" / "_variables.c"`.)

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_instance_path_retired.py -q -p no:cacheprovider -k twins_agree`
Expected: FAIL on the source assertion (the arm's comment is present).

- [ ] **Step 3: Delete the three arms in `_variables.c`**

In `c_is_term_instance`: delete the three lines from `/* Fast path: PredicateMeta instance */` through `if (r) return 1;` (keep the `PyType_Check` exclusion and the dataclass probe). In `py_term_field_names` and `c_term_field_names`: delete the `if (PredicateMeta_type) { ... }` block that returns `_fields` off a PredicateMeta instance's class (keep the dataclass fallback that follows). Do NOT touch `py_register_predicate_meta`, `PredicateMeta_type`, or the `PyType_Check(term) && ...` class arms.

- [ ] **Step 4: Rebuild the extension in a SAME-SHA worktree and swap it into the room**

```bash
git -C /workspace/clausal worktree add --detach <build_wt> $(git rev-parse HEAD)   # same sha as the room
cd <build_wt> && cp <room>/clausal/logic/variables/_variables.c clausal/logic/variables/_variables.c
/workspace/clausal/venv/bin/python setup.py build_ext --inplace 2>&1 | tail -3
NEW=$(find clausal/logic/variables -name '_variables.cpython-313-*-linux-gnu.so')
cp "$NEW" <room>/clausal/logic/variables/_variables.new.so && mv <room>/clausal/logic/variables/_variables.new.so <room>/clausal/logic/variables/$(basename "$NEW")   # cp-then-mv inside the dest dir
```
Never `build_ext --inplace` in a room a long-lived process has imported. Verify by OBSERVATION, not exit code: Step 5.

- [ ] **Step 5: Run the parity test and the corpus**

Run: `./venv/bin/python -m pytest tests/test_instance_path_retired.py tests/test_python_fallbacks.py -q -p no:cacheprovider`
Expected: all pass, and the `twins_agree` test passed only because the rebuilt `.so` is the one imported (print `C.__file__` and its mtime if in doubt).

- [ ] **Step 6: Whole-suite gate + package gate**

Run: the gate command → `w4a_t4.set` (NEW empty, GONE == RETIRED.txt); `./tools/w3_package_gate.sh <w3venv> <room> w4a_pkg` (NEW 0 / GONE 0 vs the current package baseline).

- [ ] **Step 7: Commit**

```bash
git add clausal/logic/variables/_variables.c tests/test_instance_path_retired.py
git commit -m "W4a: delete the C instance arms (c_is_term_instance, py_/c_term_field_names); class arms and registration stay for W4b"
```

---

### Task 5: Review, scan, land, swap, notify

**Files:**
- Modify: `implementation_plans/w3-get-dispatch-scope-2026-09-22.md` (append the landing), `todo/task-5-c-arms-are-all-still-live-2026-09-20.md` (close: arms 0/2/3 gone; 4–7 wait for W4b)

- [ ] **Step 1: roborev review of the branch** — `roborev review <tip> --wait`; verify each finding against the code before acting (two of three reviews today had a wrong claim); fix with red tests first; re-gate.

- [ ] **Step 2: Barrier scan of the range** — messages and added lines, closed-side terms → 0; note `harness` is a legitimate in-repo identifier, so scan for the closed IDENTIFIERS, not English words.

- [ ] **Step 3: Land** — main will have moved by note commits: cherry-pick the branch's commits onto current main in a detached worktree, assert `git rev-parse "${NEW}:clausal"` and `"${NEW}:tests"` equal the gated tip's, then `git merge --ff-only` in `/workspace/clausal` (checked out on `main`, `git status` clean of tracked changes). Smoke from the clone: `_clausal_head` raises; `is_term_instance(cell)` is False.

- [ ] **Step 4: Swap the `.so` in the clone** — the clone `/workspace/clausal` and every room symlinking its venv import THEIR OWN `.so` files; the clone's own copy must be replaced by the cp-then-mv procedure of Task 4 Step 4, and any room other lanes read (ask them) needs the same. Enumerate live importers via `/proc/*/map_files` for `_variables.cpython` before swapping; a process that imported the old `.so` keeps it until restart (never delete the old file while mapped).

- [ ] **Step 5: Notify the lanes** — main moved AND the engine tree changed AND a `.so` changed: tell the downstream lane (its reference engine and tree hash), the corpus lane and the export lane (they run against `CLAUSAL_ROOT`). State plainly: no answer changes; instance-only doors now raise.

- [ ] **Step 6: Record** — append to the scope note and close the task-5 todo (arms 0/2/3 gone; the four class arms and `py_register_predicate_meta` are W4b's); update memory.
