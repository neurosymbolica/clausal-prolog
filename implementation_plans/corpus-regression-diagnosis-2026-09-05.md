# Corpus regression diagnosis — cross-module atom head args lose their index bucket

Date: 2026-09-05
Status: **ENGINE DEFECT** (single mechanism, all three domains)
First-bad commit: **`3cc2652a` — "P3-1 Task 2: the lowering flip + minting stop"** (clone `/workspace/clausal-bug-fix`)
Fix site: `clausal/logic/compiler/arg_index.py::_arg_to_index_key` (the bare `LoadName`/`LoadAttr` branch, ~line 122)

---

## 1. Repro matrix

Runner: `/workspace/clausal/venv/bin/python -m clausal.testing <file>`, cwd `<downstream-domains-corpus>`,
`PYTHONPATH=[<engine>:]<downstream-library>:<downstream-trunk>:<downstream-domains-corpus>`.
`clausal.__file__` verified on every run.

| test file | pre-sync `4d870b17` shadow | canonical main (`/workspace/clausal`) | canonical main + 1-line patch (§6) |
|---|---|---|---|
| `<downstream-domain>.clausal` | 22 passed, 0 failed | **19 passed, 3 failed** | 22 passed, 0 failed |
| `<downstream-domain>.clausal` | 9 passed, 0 failed | **8 passed, 1 failed** | 9 passed, 0 failed |
| `<downstream-domain>.clausal` | 29 passed, 0 failed | **1 passed, 28 failed** | 29 passed, 0 failed |

Engine paths printed on each side:
- pre-sync: `/tmp/claude-1000/<pre-sync-shadow-worktree>/clausal/__init__.py`
- current: `/workspace/clausal/clausal/__init__.py`

**The 28 amlr failures are ONE root cause**, not 28. The one-line patch in §6 takes the file
straight from 1/29 to 29/29 with no other change.

## 2. First error texts (canonical main, verbatim excerpts)

### amlr_cdd_obligations — FIRST failure

```
  <downstream-domain>.clausal:64 :: PI business relationship -> standard
    goal 2 of 2 failed:
      eu.aml.amlr_cdd_obligations.cdd_level(P, eu.aml.amlr_cdd_obligations.standard)
    bindings at failure: P = {'establishing_business_relationship': True}
    the predicate DID have a solution, which did not unify (argument 2 differs):
      eu.aml.amlr_cdd_obligations.cdd_level(P, 'standard')
```

Note the rendering asymmetry that made this look like an atom-identity bug: the *goal* is rendered
from the clause AST (an unresolved `LoadName`, printed dotted), the *solution* is rendered from the
runtime term (a plain `str`, printed quoted). They are in fact the SAME value — `'standard'`. The
report "argument 2 differs" is the diagnostic's inference from a zero-solution call, not a measured
term difference.

### ai_act prohibited_practices — first of 3

```
  .../test_queries.clausal:243 :: #16 establishing the (f) medical/safety exception clears the practice
    goal 2 of 3 failed:
      eu.ai_act.prohibited_practices.ai_act_what_if(P,
          eu.ai_act.prohibited_practices.exception_f_medical_or_safety_reasons, True, V)
    the predicate DID have a solution, which did not unify (argument 2 differs):
      eu.ai_act.prohibited_practices.ai_act_what_if(P,
          'exception_d_supports_human_assessment', True, V)
```

All three ai_act failures name `'exception_d_supports_human_assessment'` as "the solution it did
have" regardless of which exception was asked for — the signature of a caller that missed its
bucket and fell through to the *default* (var-headed) clause set.

### procurement scope_exclusions — the single red test

```
  .../test_queries.clausal:75 :: what_if: flipping utilities pursuit to True on near-miss makes it excluded
    goal 2 of 3 failed:
      ...scope_exclusions_what_if(PROFILE,
          ...awarded_for_pursuit_of_utilities_activity, True,
          ...scope_exclusions_verdict(...excluded_from_directive, GROUND_IDS, _))
    the predicate DID have a solution, which did not unify (argument 4 differs):
      ...scope_exclusions_what_if(PROFILE, ..., True,
          scope_exclusions_verdict('not_excluded_from_directive', [], []))
```

Same shape: the `what_if` flip silently did nothing because the flipped-atom lookup missed its
bucket, so the verdict came back unflipped.

## 3. Minimized case

Four files, no corpus dependency, at
`/tmp/claude-1000/-workspace-clausal-bug-fix/527a9322-.../scratchpad/mini/`:

`pkg/schema.clausal`
```
-module(schema, [aa, bb, cc, dd])
-strict_atoms
```

`pkg/computation.clausal`
```
-import_from(pkg.schema, [aa, bb, cc, dd])
-strict_atoms
-module(computation, [level(N, L), src(N)])
src(1), src(2), src(3), src(4),
level(N, aa) <- (src(N), N == 1)
level(N, bb) <- (src(N), N == 2)
level(N, cc) <- (src(N), N == 3)
level(N, dd) <- (src(N), N == 4)
```

`pkg/__init__.clausal` re-exports both; `t_mini.clausal` does
`-import_from(pkg, [level, aa, bb, cc, dd])` and asserts `level(1, aa)` and `level(4, dd)`.

- pre-sync `4d870b17`: **2 passed, 0 failed**
- canonical main: **0 passed, 2 failed** (`the predicate DID have a solution ... pkg.level(1, 'aa')`)

### Three controls that isolate the trigger

| variant | result on canonical main | what it shows |
|---|---|---|
| same file declares AND uses the atoms in the head (`mini1/t_one.clausal`) | PASS | a same-module atom lowers to `ast.Constant('aa')`, so both sides key the plain `str`. Not affected. |
| two files, atoms declared and used in heads in the *same* file, imported only by the caller (`mini2/`) | PASS | same reason — the head arg is a Constant. |
| **3 rule clauses instead of 4** (`mini3/`) | PASS | below `_INDEX_THRESHOLD = 4`; indexing never engages. |

So the trigger is exactly: **an atom imported from ANOTHER module, used as a rule-head argument, in
a predicate with ≥ 4 clauses, called with that argument bound.** That is downstream code's "DAG-root
`schema.clausal` + sibling `computation.clausal`" (Wave B) decomposition idiom.

The engine's own test suite is green because its atom-head fixtures are single-module (Constant
head args) and/or below the 4-clause index threshold.

## 4. Bisect

Scratch worktree of `/workspace/clausal-bug-fix` at
`scratchpad/bisect`, `setup.py build_ext --inplace` with the canonical venv python at every step
(≈4.5 s incremental), driven by `scratchpad/bisect_run.sh` on the minimized case with the worktree
first on `PYTHONPATH` (engine path asserted, else `exit 125`).

```
git bisect start e124754b 659c49e7
good aee10d71  toklex Task 6: incremental driver ...
bad  d83fb324  P3-1 Task 8: close-out docs for the atom pivot
good 8e6d8336  prolog-reader Task 4: PrologReader incremental L1 core + read_module
bad  3cc2652a  P3-1 Task 2: the lowering flip + minting stop
good 5d4e9e31  prolog-reader: park the module-embedded op/3 declarations gap
good 523ae9ef  Phase 3 decomposition (P3-1/2/3) + full P3-1 atom-pivot plan
good 1e73c68f  P3-1 Task 1 fix round: invert atom/1-on-string conformity pin (R2)
=> first bad commit: 3cc2652aa8ed5fca8e8c0324728240656e2d391e
```

`3cc2652a` touched `import_hook.py`, `logic/compiler/terms_to_ast.py`, `logic/compiler_v2.py`,
`templating/term_rewriting.py` (+ tests/fixtures). It did **not** touch
`logic/compiler/arg_index.py` — that is the missed call-site.

## 5. Mechanism

A rule head with a structural argument is normalized at assert time by
`database.py::_normalize_structural_head_args`: the arg is replaced by a fresh `Var` and a
`Unify(var, value)` goal is prepended to the body. A cross-module atom reference survives as an
unresolved `LoadName('pkg.schema.aa')` node, which `_is_structural_head_value` classifies as
structural, so the stored clause is:

```
HEAD: level(N=AttVar(_1), L=AttVar(_2))
  G: Unify(left=AttVar(_2), right=LoadName(name='pkg.schema.aa'))
  G: ...
```

Argument indexing then recovers the "real" head key through
`arg_index.py::_extract_arg_key`, which follows the Var into that hoisted `Unify` and calls
`_arg_to_index_key` on its right-hand side. That function's `LoadName`/`LoadAttr` branch still
uses the **pre-pivot** convention:

```python
if isinstance(arg, (LoadName, LoadAttr)):
    dotted = _dotted_name_from_loadattr(arg)
    if dotted is not None:
        return (dotted.rsplit(".", 1)[-1], 0)      # ('aa', 0)
```

`(name, 0)` was correct while an atom was a zero-arity `PredicateMeta` class, because the runtime
mirror `_runtime_arg_key` keyed such a class as `(cls.__name__, 0)`. After `3cc2652a` an atom **is
its spelling** — a plain `str` — and `_runtime_arg_key` keys a `str` as the string itself:

```
index buckets built for level/2 pos 1:  [('aa', 0), ('bb', 0), ('cc', 0), ('dd', 0)]
runtime key for the caller's 'aa':      'aa'
```

Measured on canonical main via `scratchpad/mini/keys.py`. The caller's key matches no bucket, so
dispatch falls back to the bucket's **defaults** (the var-headed clauses only — here, none), and the
call yields **zero solutions** where every clause should have been tried. Second-order effect: when
the predicate *does* have default clauses (`ai_act_what_if/4`, `scope_exclusions_what_if/4`), the
call does not fail — it returns the *wrong* answer produced by whichever default clause fires,
which is why those two domains showed a wrong verdict rather than a hard failure.

This is precisely the failure mode the branch's own comment warns about:
*"…which no runtime value ever matches (leaving ground callers with no bucket and an empty default
set → spurious 'no solutions')."*

**One mechanism, all three domains** — see §6.

## 6. Confirmation: one patched line makes all three green

Probe (no repo file touched — monkeypatch in `scratchpad/patchrun.py`):

```python
def patched(arg):
    if isinstance(arg, (LoadName, LoadAttr)):
        dotted = _dotted_name_from_loadattr(arg)
        return dotted.rsplit(".", 1)[-1] if dotted is not None else ai._INDEX_VAR
    return _orig(arg)
ai._arg_to_index_key = patched
```

| file | canonical main | + patch |
|---|---|---|
| ai_act prohibited_practices test_queries | 19/22 | **22/22** |
| procurement scope_exclusions test_queries | 8/9 | **9/9** |
| aml amlr_cdd_obligations test_public_interface | 1/29 | **29/29** |

Exactly the pre-sync numbers. No second mechanism is hiding behind the 28.

## 7. Verdicts

### Family A — amlr_cdd_obligations, 28 failures (`cdd_level/2`, `determine_cdd/2`, …)
**(i) ENGINE DEFECT.** Correct behavior: a call whose argument is bound to an atom must reach every
clause whose head declares that atom, exactly as it did pre-pivot and exactly as it still does when
the atom is same-module (Constant-lowered) or the predicate has < 4 clauses. No ruling sanctions
"indexing silently drops clauses for cross-module atom head args". R2 (atom/str collapse) is the
*cause* of the stale key, but R2's own direction — quoted/bare/imported all denote the same `str` —
is what says these calls must succeed.

### Family B — ai_act `ai_act_what_if/4` (3 failures)
**(i) ENGINE DEFECT**, same mechanism, same commit. The what_if machinery is not implicated: the
reified-rule/`replace_subterm` path is untouched. What breaks is the ordinary indexed dispatch on
the flipped-key argument, which returns the default clause's answer
(`'exception_d_supports_human_assessment'`) for every requested exception.

### Family C — procurement `scope_exclusions_what_if/4` (1 failure)
**(i) ENGINE DEFECT**, same mechanism, same commit. The flip is a no-op because the atom lookup
misses its bucket; the verdict comes back `not_excluded_from_directive` unflipped.

### Explicitly NOT the verdict
- **Not (ii) INTENDED SEMANTICS.** R2 makes quoted `'x'`, bare `x` and an imported `x` the identical
  `str`; the calibration warning in the escalation is borne out — the comparison path (the index
  key), not unification, is what broke. Corpus source needs no migration.
- **Not (iii) HARNESS ARTIFACT.** `clausal.testing` is not implicated. The same zero-solution result
  reproduces through plain `clausal.logic.solve.call` on an ordinary `importlib`-imported corpus
  module (`scratchpad/probe9.py`: `cdd_level(P, 'standard')` → 0 solutions, `cdd_level(P, V)` → 1
  solution binding `V='standard'`). `testing.py`'s diagnostic rendering is *misleading* (see §2) but
  it is reporting a real engine failure.

## 8. Blast radius

### Measured: full corpus sweep, patched vs. unpatched (same engine, one line differs)

Every corpus test file (308 collected `test_*.clausal`, one subprocess each) run twice on canonical
main — once unmodified, once with the §6 probe patch. `scratchpad/sweep_current.tsv`,
`sweep_patched.tsv`, diffed by `scratchpad/diff_sweeps.py`:

```
unpatched: 4530 pass /  773 fail
patched:   5163 pass /  140 fail
tests FIXED by the one line:  633
files improved: 90            files worsened: 0
```

**633 corpus tests across 90 files in 17 domain areas** are red on canonical main purely because of
this defect. Zero tests regress under the patch. The residual 140 failures in 25 files are
unrelated to this mechanism (unchanged on both sides).

By domain area (tests fixed):

```
<downstream-domain> 328   <downstream-domain> 52   <downstream-domain> 40   <downstream-domain> 37
<downstream-domain> 31      <downstream-domain> 31       <downstream-domain> 20
<downstream-domain> 19          <downstream-domain> 17   <downstream-domain> 17
<downstream-domain> 12   <downstream-domain> 11   <downstream-domain> 10   <downstream-domain> 3
<downstream-domain> 2   <downstream-domain> 2   <downstream-domain> 1
```

The three escalated files are a 32-test slice of a 633-test regression.

### Static proxy (cross-check)

`scratchpad/static_scan.py` over `<downstream-domains-corpus>` (850 `.clausal` files): a rule head
arg naming an `-import_from`'d identifier in a predicate with ≥ 4 clauses.

```
files with >=1 at-risk predicate: 57
at-risk predicates:               99
domain areas touched:             29
top: <downstream-domain> 33, <downstream-domain> 7, <downstream-domain> 6,
     <downstream-domain> 5, <downstream-domain> 5, <downstream-domain> 4,
     <downstream-domain> 3, <downstream-domain> 3, then ~2 each across
     <downstream-domain>, <downstream-domain>, <downstream-domain>, <downstream-domain>, <downstream-domain>,
     <downstream-domain>, <downstream-domain>, <downstream-domain>, <downstream-domain>, <downstream-domain>, <downstream-domain>, <downstream-domain> …
```

This is an upper bound on *predicates* (an at-risk predicate only misbehaves when actually called
with that argument bound) and a lower bound on *impact* (a broken predicate poisons many downstream
queries — one broken `cdd_level/2` produced 28 red tests). It agrees with the measured sweep on the
ranking (`<downstream-domain>` far in front, then `<downstream-domain>`, `<downstream-domain>`, `<downstream-domain>`,
`<downstream-domain>`, `<downstream-domain>`, `<downstream-domain>`).

Anything outside downstream code that uses the same decomposition idiom (a shared vocabulary module +
sibling rule modules, ≥ 4 clauses) is equally exposed. Everything single-module, or below the
4-clause index threshold, is unaffected — which is why the engine's own suite stayed green and why
this reached downstream code rather than CI.

## 9. Recommended action

**Fix the engine.** The defect is one branch in one function.

Primary fix (correct, keeps the indexing win):
resolve the dotted name at index-build time and key the *resolved value* through
`_runtime_arg_key`, rather than guessing a key from the spelling.
`_analyze_index_positions` / `_build_arg_index` / `_build_joint_arg_index` /
`_build_secondary_index` are all called from `logic/compiler/predicate.py` (≈ lines 958, 1090, 1097
and the shallow twin at 1766, 1807, 1814) where `base_globals` — which already holds
`'pkg.schema.aa' → 'aa'`, injected by `globals_env._inject_resolved_targets` — is in scope. Thread
that dict down to `_arg_to_index_key` and do:

```python
if isinstance(arg, (LoadName, LoadAttr)):
    dotted = _dotted_name_from_loadattr(arg)
    if dotted is None:
        return _INDEX_VAR
    if env is not None and dotted in env:
        return _runtime_arg_key(env[dotted])       # atom -> its str; class -> (name, 0)
    return _INDEX_VAR                              # unresolvable: scan, never mis-bucket
```

This is also the only variant that is right for a `-hide`-mangled atom (whose runtime `str` is
`module\x1fname`, not the bare tail) and for a dotted `LoadName` that denotes a *non*-atom value
(e.g. an imported `py.sympy.inf`, where keying the tail `'inf'` would relocate the very same bug).
Note the crude spelling-tail patch used in §6 is a *diagnostic probe*, not the recommended fix, for
exactly those two reasons.

Safe immediate stopgap if the threading is deemed too large for a hotfix:
make the branch `return _INDEX_VAR`. Always correct; costs cross-module atom-headed predicates a
linear clause scan (the perf win commit `92ce2636` added back).

Regression tests to pin it (the gap that let this through):
1. cross-module imported atom as a rule-head arg, ≥ 4 clauses, called with the arg **bound** —
   the `mini/` shape above;
2. the same with the atom re-exported through a package `__init__` (two import hops);
3. a `-hide`-mangled atom in the same position;
4. a dotted `LoadName` head arg that resolves to a non-atom Python value, asserting it is not
   mis-bucketed.

Also worth an audit pass in the same sitting: every other place that still assumes the pre-pivot
`(name, 0)` atom key shape. `_runtime_arg_key`'s and `_arg_to_index_key`'s `PredicateMeta` branches
are now vestigial for atoms; `_static_call_key` never produced an atom key for a dotted name
(`ast.Name` → `None`), so it degraded to the runtime path and is not a second defect — but it is a
second missed pivot call-site worth confirming.

## 10. Artifacts

All under `/tmp/claude-1000/-workspace-clausal-bug-fix/527a9322-1d31-48c9-84fe-c3199aa9846e/scratchpad/`:

- `run.sh` — two-sided corpus runner (prints `clausal.__file__` first)
- `mini/`, `mini1/`, `mini3/`, `mini2/` — minimized case + the three controls
- `mini/keys.py` — prints the index buckets and the runtime key side by side
- `probe9.py`, `probe10.py` — the engine-level (non-harness) reproduction and the stored-clause dump
- `patchrun.py`, `sweep.py`, `sweep_child.py` — one-line-patch verification and corpus sweep
- `static_scan.py` — blast-radius proxy
- `bisect/` (git worktree, detached), `bisect_run.sh`, `bisect.log`

No repo file was modified; nothing was committed anywhere.
