# ISO canonical comparison builtins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register ISO's comparison, unification and arithmetic predicates under their
own names, reachable from `.clausal` through the quoted canonical form (`'=:='(A, B)`),
so the 964 measured `==` sites have spellings to migrate to.

**Architecture:** One new builtins module registering each family through the existing
`@_builtin(functor, arity)` decorator, which accepts any string functor — symbolic names
need no new machinery. A Scryer-comparing harness lands FIRST and is the oracle for every
answer and every error term. Nothing changes about bare `==`, and nothing adds an infix
surface: the quoted canonical form is the only entry point.

**Tech Stack:** Python 3.13, pytest, `clausal.logic.builtins._registry._builtin`, Scryer
Prolog at `/workspace/scryer-prolog/target/release/scryer-prolog` (verified working, has
`library(clpz)`).

**Spec:** `docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md`
(this worktree, branch `spec/iso-canonical-form-operators-2026-09-08` @dc92fde3)

## Global Constraints

- **Bare `==` is not changed, on any flag.** Spec §5. The migration is the lint plus the
  canonical spelling; a semantic flip would silently re-score the double-quotes ratchet.
- **No infix ISO operators in `.clausal` source.** Spec §5. The quoted canonical form is
  the only entry point. `clausal-fmt` must never rewrite `'=:='(A, B)` to an infix form.
- **Python's `is`, `is not`, `in`, `not in` are untouched** in both host code and clause
  bodies. This plan cannot reach them: Python has no infix syntax for `'is'(X, E)`.
- **Scryer is the reference for every answer and every error shape.** Spec §3.4. Where
  this plan and Scryer disagree, Scryer is right and the task is not done.
- **ISO spells less-or-equal `=<`, never `<=`.**
- **Run tests from the tree under test** and assert it: probes and harnesses must do
  `sys.path.insert(0, os.getcwd())` then
  `assert os.getcwd() in clausal.__file__` — see [[running-tests-in-bug-fix-clone]].
- **Landing gate:** full-suite name-set diff, 0 NEW. Strip ANSI before extracting the
  failure set (`sed -E 's/\x1b\[[0-9;]*m//g'`) or the diff silently reports an empty
  candidate set as success.

---

## Verified starting facts

Probed on canonical `f5ad9a5d`, 2026-09-09. Do not re-derive:

- **None of the target names are registered.** `('=:=', 2)`, `('==', 2)`, `('@<', 2)`,
  `('=', 2)`, `('=..', 2)`, `('is', 2)`, `('#=', 2)` are all absent from
  `clausal.logic.builtins._registry._BUILTINS`. `('structural_eq', 2)` and `('dif', 2)`
  are present.
- **`eval_/2` is NOT a builtin.** The spec says `'is'` is "an alias of `eval_/2`"; there
  is no such builtin to alias. `eval_` exists only as a compiler GOAL-OP
  (`clausal/logic/compiler/terms_to_goalop.py:381`, matching
  `Call(func=LoadName(name="eval_"), ...)`), which a quoted-atom predicate call does not
  reach. **`'is'` must therefore evaluate arithmetic itself** — Task 4.
- **The available evaluator is `clausal.logic.clpfd._eval_ground(expr)`**: returns
  int/float/Fraction when fully ground, `None` when it contains unbound Vars, and raises
  a catchable leaf error for a non-numeric leaf. It does NOT raise ISO's
  `instantiation_error`; the wrapper must.
- **ISO error constructors already exist**: `clausal.logic.exceptions.instantiation_error(context)`
  and `type_error(kind, culprit, context)`, raised inside `LogicException`.
- **`@_builtin` takes any string functor** (`_registry.py:108`), so `@_builtin("=:=", 2)`
  needs no new machinery.
- **Scryer reference behaviour**, measured:

      X is 3 + 4       -> 7                                  1 =:= 1.0  -> true
      1 == 1.0         -> false                              X #= Y+1 (Y=2) -> 3
      _ is foo + 1     -> error(type_error(evaluable,foo/0),(is)/2)
      _ =:= 1          -> error(instantiation_error,(is)/2)

  Note the last: Scryer attributes the `=:=` instantiation error to `(is)/2`, not
  `(=:=)/2`. Pin what Scryer does, not what looks tidy.
- **Scryer invocation**: write a `.pl`, run `scryer-prolog file.pl` with the goal on
  STDIN and **no `?- ` prefix** (the prefix gives
  `existence_error(procedure,(?-)/1)`). Pattern in
  `tests/test_prolog_rule_drop.py:412`.

---

## File Structure

- `clausal/logic/builtins/iso_compare.py` — CREATE. Every predicate in spec §3.1. One
  module because they are one family with one shared arithmetic-evaluation helper, and
  they are registered, never imported by name.
- `tests/iso/conftest.py` — CREATE. The Scryer oracle fixture.
- `tests/iso/test_iso_compare_scryer.py` — CREATE. Engine-vs-Scryer matrices.
- `tests/iso/test_iso_compare_errors.py` — CREATE. Error-term shapes.
- `clausal/logic/builtins/__init__.py` — MODIFY. Import the new module so registration
  runs (follow how `constraints.py` is imported there).

---

### Task 1: The Scryer oracle harness

**Files:**
- Create: `tests/iso/conftest.py`
- Create: `tests/iso/test_iso_compare_scryer.py`

**Interfaces:**
- Produces: `scryer(goal: str, program: str = "") -> str` — a pytest fixture returning
  Scryer's stdout for `goal` run against `program`, stripped. Raises `pytest.skip` if the
  binary is absent. `run_clausal(src: str, goal: tuple) -> list[str]` — loads a
  `.clausal` source and returns `repr(deref(v))` for each solution's first goal variable.

- [ ] **Step 1: Write the failing test**

```python
# tests/iso/test_iso_compare_scryer.py
def test_harness_agrees_with_scryer_on_iso_is(scryer, run_clausal):
    """The oracle itself, proved against a predicate that ALREADY works, so a
    failure here means the harness is broken rather than the builtins."""
    assert scryer("X is 3 + 4, write(X), nl, halt.") == "7"
    got = run_clausal(
        "-module(_h1, [p(X)])\n-double_quotes(chars)\np(X) <- (X == 3 + 4)\n",
        ("p",))
    assert got == ["7"], "bare == already evaluates-and-binds; see the eq measurement"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/test_iso_compare_scryer.py -q`
Expected: FAIL — `fixture 'scryer' not found`.

- [ ] **Step 3: Write the fixtures**

```python
# tests/iso/conftest.py
import os, subprocess, sys, tempfile
import pytest

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"


@pytest.fixture
def scryer():
    if not os.path.exists(SCRYER):
        pytest.skip(f"scryer not built at {SCRYER}")

    def run(goal: str, program: str = "") -> str:
        d = tempfile.mkdtemp()
        pl = os.path.join(d, "w.pl")
        with open(pl, "w") as fh:
            fh.write(program)
        proc = subprocess.run([SCRYER, pl], input=goal + "\n",
                              capture_output=True, text=True, timeout=30)
        return proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else ""
    return run


@pytest.fixture
def run_clausal(tmp_path):
    # Assert the tree under test, per [[running-tests-in-bug-fix-clone]]: a probe
    # that does not do this silently measures the editable-installed canonical.
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__
    from clausal.import_hook import _load_module
    from clausal.logic.solve import solve
    from clausal.logic.variables import Trail, Var, deref
    counter = [0]

    def run(src: str, goal_head: tuple, nargs: int = 1) -> list[str]:
        counter[0] += 1
        name = f"_iso{counter[0]}"
        path = tmp_path / f"{name}.clausal"
        path.write_text(src.replace("_h1", name).replace("_hN", name))
        mod = _load_module(name, str(path))
        v = Var()
        args = (v,) + tuple(Var() for _ in range(nargs - 1))
        return [repr(deref(v)) for _ in solve(goal_head + args, mod, Trail())]
    return run
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/ -q`
Expected: PASS, 1 test. If it SKIPS, the Scryer binary is missing — stop and report;
a skipped oracle is an instrument that verifies nothing.

- [ ] **Step 5: Prove the oracle can fail**

Temporarily change the assertion to `== "8"`, re-run, confirm it FAILS, change it back.
A harness that has only ever passed has proved nothing.

- [ ] **Step 6: Commit**

```bash
git add tests/iso/conftest.py tests/iso/test_iso_compare_scryer.py
git commit -m "test(iso): Scryer oracle harness for the canonical comparison builtins"
```

---

### Task 2: The arithmetic comparison family

**Files:**
- Create: `clausal/logic/builtins/iso_compare.py`
- Modify: `clausal/logic/builtins/__init__.py`
- Test: `tests/iso/test_iso_compare_scryer.py`

**Interfaces:**
- Consumes: `scryer`, `run_clausal` from Task 1.
- Produces: `_iso_eval(term, context: str)` — evaluates an arithmetic term to a number,
  raising `LogicException(instantiation_error(context))` for an unbound operand and
  `LogicException(type_error("evaluable", culprit, context))` for a non-evaluable one.
  Tasks 3–5 call it.

- [ ] **Step 1: Write the failing test**

```python
import pytest

ARITH_ROWS = [("'=:='(1, 1.0)", "1 =:= 1.0", True),
              ("'=:='(1, 2)",   "1 =:= 2",   False),
              ("'=\\\\='(1, 2)", "1 =\\= 2",  True),
              ("'<'(1, 2)",     "1 < 2",     True),
              ("'=<'(2, 2)",    "2 =< 2",    True),
              ("'>='(2, 3)",    "2 >= 3",    False)]


@pytest.mark.parametrize("clausal_goal, scryer_goal, expected", ARITH_ROWS)
def test_arithmetic_comparison_matches_scryer(scryer, run_clausal,
                                              clausal_goal, scryer_goal, expected):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           f"p(R) <- if_({clausal_goal}, R is yes, R is no)\n")
    got = run_clausal(src, ("p",))
    assert got == [repr(("yes",) if expected else ("no",))]
    ref = scryer(f"({scryer_goal} -> write(yes) ; write(no)), nl, halt.")
    assert ref == ("yes" if expected else "no"), "Scryer disagrees; Scryer is right"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/ -q`
Expected: FAIL — `PredicateNotFoundError: =:=/2`.

- [ ] **Step 3: Write the implementation**

```python
# clausal/logic/builtins/iso_compare.py
"""ISO comparison, unification and arithmetic builtins under their ISO names.

Reachable from `.clausal` ONLY through the quoted canonical form —
`'=:='(A, B)` — because Python has no infix syntax for these; natively in
`.pl`. Spec: docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md
"""
from clausal.logic.builtins._registry import _builtin
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.logic.variables import deref, is_var


def _iso_eval(term, context: str):
    """Evaluate an arithmetic term to a number, with ISO's errors.

    `clpfd._eval_ground` returns None for an unbound operand and raises its own
    leaf error for a non-number; ISO wants instantiation_error and
    type_error(evaluable, F/N). Scryer attributes BOTH to (is)/2 regardless of
    which comparison raised them — pin what it does, not what reads tidily.
    """
    from clausal.logic.clpfd import _eval_ground
    t = deref(term)
    if is_var(t):
        raise LogicException(instantiation_error(context))
    try:
        value = _eval_ground(t)
    except LogicException:
        raise
    except Exception:
        raise LogicException(type_error("evaluable", t, context)) from None
    if value is None:
        raise LogicException(instantiation_error(context))
    return value


def _arith_cmp(name, op):
    @_builtin(name, 2)
    def _cmp(a, b, trail, k, _op=op, _name=name):
        if _op(_iso_eval(a, "is/2"), _iso_eval(b, "is/2")):
            yield None
    return _cmp


import operator as _o
_arith_cmp("=:=", _o.eq)
_arith_cmp("=\\=", _o.ne)
_arith_cmp("<", _o.lt)
_arith_cmp(">", _o.gt)
_arith_cmp("=<", _o.le)     # ISO spells it =<, never <=
_arith_cmp(">=", _o.ge)
```

Then in `clausal/logic/builtins/__init__.py`, alongside the other module imports, add:

```python
from clausal.logic.builtins import iso_compare  # noqa: F401  (registers by import)
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/ -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/builtins/iso_compare.py clausal/logic/builtins/__init__.py tests/iso/test_iso_compare_scryer.py
git commit -m "feat(iso): '=:=' and the arithmetic comparison family"
```

---

### Task 3: Error shapes

**Files:**
- Create: `tests/iso/test_iso_compare_errors.py`
- Modify: `clausal/logic/builtins/iso_compare.py` (only if a shape disagrees)

**Interfaces:**
- Consumes: `_iso_eval` from Task 2; `scryer`, `run_clausal` from Task 1.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from clausal.logic.exceptions import LogicException


def _err(run_clausal, goal):
    src = ("-module(_hN, [p(R), ok])\n-double_quotes(chars)\n"
           f"p(R) <- ({goal}, R is ok)\n")
    with pytest.raises(LogicException) as e:
        run_clausal(src, ("p",))
    return str(e.value)


def test_unbound_operand_is_instantiation_error(scryer, run_clausal):
    assert "instantiation_error" in _err(run_clausal, "'=:='(X, 1)")
    assert "instantiation_error" in scryer("catch(_ =:= 1, E, (write(E), nl)), halt.")


def test_non_evaluable_operand_is_type_error_evaluable(scryer, run_clausal):
    assert "evaluable" in _err(run_clausal, "'=:='(1, foo)")
    ref = scryer("catch(_ is foo + 1, E, (write(E), nl)), halt.")
    assert "type_error(evaluable,foo/0)" in ref
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/test_iso_compare_errors.py -q`
Expected: FAIL if the raised shape differs from Scryer's. If it PASSES immediately,
weaken nothing — instead check the test actually reaches the builtin by asserting the
error text is non-empty first; an assertion that cannot fail is not a test.

- [ ] **Step 3: Reconcile with Scryer**

If the engine's culprit differs from Scryer's (`foo/0` vs `foo`), change `_iso_eval` to
build the culprit as `Name/Arity`. Scryer is the reference.

- [ ] **Step 4: Run and watch it pass**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/ -q`

- [ ] **Step 5: Commit**

```bash
git add tests/iso/test_iso_compare_errors.py clausal/logic/builtins/iso_compare.py
git commit -m "feat(iso): pin the ISO error terms against Scryer"
```

---

### Task 4: `'is'`, `'='`, `'\\='`, `'=='`, `'\\=='`

**Files:**
- Modify: `clausal/logic/builtins/iso_compare.py`
- Test: `tests/iso/test_iso_compare_scryer.py`

**Interfaces:**
- Consumes: `_iso_eval` from Task 2.
- Produces: nothing new; registers `('is', 2)`, `('=', 2)`, `('\\=', 2)`, `('==', 2)`,
  `('\\==', 2)`.

- [ ] **Step 1: Write the failing test**

```python
def test_iso_is_evaluates_and_binds(scryer, run_clausal):
    """NOT the same as Clausal's infix `is`, which is unification: measured,
    `X is 3 + 4` in a clause body yields the TERM Add(3, 4). The canonical
    form is ISO's evaluate-and-bind."""
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- 'is'(X, 3 + 4)\n", ("p",))
    assert got == ["7"]
    assert scryer("X is 3 + 4, write(X), nl, halt.") == "7"


def test_structural_identity_distinguishes_int_from_float(scryer, run_clausal):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('=='(1, 1.0), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("no",))]
    assert scryer("(1 == 1.0 -> write(yes) ; write(no)), nl, halt.") == "no"
```

- [ ] **Step 2: Run and watch it fail**

Expected: FAIL — `PredicateNotFoundError: is/2`.

- [ ] **Step 3: Write the implementation**

```python
# appended to clausal/logic/builtins/iso_compare.py
from clausal.logic.constraints import structural_eq as _structural_eq
from clausal.logic.variables import unify as _unify


@_builtin("is", 2)
def _iso_is(result, expr, trail, k):
    """ISO is/2: evaluate Expr, unify with Result.

    NOT Clausal's infix `is`, which is unification (nodes.Unify) and leaves
    `X is 3 + 4` as the term Add(3, 4). Both spellings coexist: Python has no
    infix syntax for `'is'(X, E)`, so they never collide. See
    todo/is-and-eq-are-swapped-relative-to-iso-2026-09-09.md
    """
    if _unify(result, _iso_eval(expr, "is/2"), trail):
        yield None


@_builtin("=", 2)
def _iso_unify(a, b, trail, k):
    if _unify(a, b, trail):
        yield None


@_builtin("\\=", 2)
def _iso_not_unifiable(a, b, trail, k):
    mark = trail.mark()
    ok = _unify(a, b, trail)
    trail.undo(mark)
    if not ok:
        yield None


@_builtin("==", 2)
def _iso_structural_eq(a, b, trail, k):
    if _structural_eq(a, b):
        yield None


@_builtin("\\==", 2)
def _iso_structural_ne(a, b, trail, k):
    if not _structural_eq(a, b):
        yield None
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/ -q`

- [ ] **Step 5: Verify the infix spelling is untouched**

```python
def test_infix_is_still_means_unification(run_clausal):
    """Global constraint: this plan must not change Clausal's infix `is`."""
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- (X is 3 + 4)\n", ("p",))
    assert got == ["Add(left=3, right=4)"]
```

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/builtins/iso_compare.py tests/iso/test_iso_compare_scryer.py
git commit -m "feat(iso): 'is', '=', '\\=', '==', '\\==' under their ISO names"
```

---

### Task 5: `'#='` and the CLP constraint family

**Files:**
- Modify: `clausal/logic/builtins/iso_compare.py`
- Test: `tests/iso/test_iso_compare_scryer.py`

**Interfaces:**
- Produces: registers `('#=', 2)`, `('#\\=', 2)`, `('#<', 2)`, `('#>', 2)`,
  `('#=<', 2)`, `('#>=', 2)`.

- [ ] **Step 1: Write the failing test**

```python
def test_hash_eq_is_valid_in_every_mode(scryer, run_clausal):
    """The 33 FORCED sites from the eq measurement take {BIND, TEST}: the same
    site binds on one call and tests on another. `#=` is the only spelling
    valid in both, which is why it is in the spec at all."""
    # BIND mode: the right side is ground, so X is bound.
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- '#='(X, 2 + 1)\n", ("p",))
    assert got == ["3"]
    assert scryer("X #= 2 + 1, write(X), nl, halt.",
                  ":- use_module(library(clpz)).\n") == "3"


def test_hash_eq_also_TESTS_two_ground_values(run_clausal):
    """The other half of the {BIND, TEST} pair. Both must work through the
    SAME spelling or `#=` does not solve the forced sites."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('#='(3, 2 + 1), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]
    src_f = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
             "p(R) <- if_('#='(4, 2 + 1), R is yes, R is no)\n")
    assert run_clausal(src_f, ("p",)) == [repr(("no",))]
```

- [ ] **Step 2: Run and watch it fail**

Expected: FAIL — `PredicateNotFoundError: #=/2`.

- [ ] **Step 3: Write the implementation**

```python
# appended to clausal/logic/builtins/iso_compare.py
@_builtin("#=", 2)
def _clp_eq(a, b, trail, k):
    """CLP arithmetic constraint — binds, propagates, valid in every mode.

    This is what `==` ALREADY does: `==` compiles to nodes.ArithEq, a CLP(FD)
    equality constraint. Registering `#=` names an existing behaviour rather
    than adding one. Required by the eq measurement: 33 corpus sites take two
    arithmetic modes and `#=` is the only spelling correct for all of them.
    """
    from clausal.logic.clpfd import fd_eq
    if fd_eq(a, b, trail):
        yield None
```

Register the rest the same way. All six targets are VERIFIED to exist in
`clausal/logic/clpfd.py` (both the pure-Python definitions and, for four of them, the
C-accelerated shadows further down the file), so none of these is speculative:

| canonical | clpfd function | line |
|---|---|---|
| `'#='`   | `fd_eq` | 1855 |
| `'#\\='` | `fd_ne` | 1924 |
| `'#<'`   | `fd_lt` | 1959 |
| `'#=<'`  | `fd_le` | 2000 |
| `'#>'`   | `fd_gt` | 2038 |
| `'#>='`  | `fd_ge` | 2047 |

Import them INSIDE each builtin body, not at module import time: `clpfd` swaps in
C-accelerated versions further down its own module, and a top-level `from ... import
fd_eq` would capture the pure-Python one.

- [ ] **Step 4: Run and watch it pass**

Run: `cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests/iso/ -q`

- [ ] **Step 5: Full gate**

```bash
cd <tree> && /workspace/clausal/venv/bin/python -m pytest tests -q \
  --continue-on-collection-errors -p no:randomly > /tmp/gate.log 2>&1
sed -E 's/\x1b\[[0-9;]*m//g' /tmp/gate.log | tail -1
sed -E 's/\x1b\[[0-9;]*m//g' /tmp/gate.log | grep -E "^(FAILED|ERROR) " \
  | sed -E 's/^(FAILED|ERROR) //; s/ - .*$//' | sort -u > /tmp/cand.txt
```
Diff against the baseline failure set; expected 0 NEW. Confirm the run executed by
checking the summary line reports a pass/fail count, AND that `cand.txt` is non-empty —
"the run happened" and "my extraction worked" are two different checks.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/builtins/iso_compare.py tests/iso/test_iso_compare_scryer.py
git commit -m "feat(iso): '#=' — the name for the constraint `==` already posts"
```

---

## Out of scope for this plan

Spec §4 Tasks 3–5, each worth its own plan once spellings exist:
- The lint that flags ambiguous bare `==` and names the canonical spelling.
- The translator emitting canonical forms 1:1 — note a `'#='` site emits `#=`, which is
  `library(clpz)`, so such an export is no longer pure ISO.
- `docs/builtins.md` and `docs/syntax.md`.

Also out of scope: `'@<'`, `'@>'`, `'@=<'`, `'@>='` and `compare/3` (standard order),
and `'=..'`. They are in spec §3.1 but need the standard-order comparator and its ruling
on engine-native values ISO does not have (Decimal, Quantity, dict terms) — spec §6's
second risk. That is a design question, not a registration, and deserves its own plan.
