# BUG: symbolic_diff — structural operator heads & different-variable clause don't match

**RESOLVED 2026-07-01.** Two independent root causes, both fixed; all 10
`symbolic_diff.clausal` tests pass. Confirmed unrelated to the map_coloring
first-arg-indexing fix (disabling indexing did not change the failures).

- **(A) Operator nodes had no structural unification** (engine bug). `Add`/
  `Mult`/`Pow` (and all `BinOp`/`UnaryOp` subclasses) lacked `__unify__`, so the
  C `do_unify` fell back to `==`, which never binds a variable — a clause that
  builds `DA + DB` could not unify against another operator term of the same
  shape. Fix: added `BinOp.__unify__` / `UnaryOp.__unify__` (mirroring
  `Compound.__unify__`, ignoring the non-semantic `position` field) in
  `clausal/pythonic_ast/nodes.py`. Regression tests: `tests/test_unify.py`
  `TestUnifyOperatorNodes` (8). Note: the feared `1 + 1 -> 2` collapse in
  `term_to_ast_expr` did NOT bite — the real call-argument path constructs the
  operator term structurally.
- **(B) Wrong guard in the example** (not an engine bug). Variables are
  represented as atoms (`Vx`, `Vy`), but the "different variable" clause guarded
  with `is_str(Y)`, which correctly rejects an atom. Fix: use `atom(Y)` in
  `clausal/examples/symbolic_diff.clausal`.

---

**Found:** 2026-07-01 (triaging the full `clausal/examples/ + tests/fixtures/`
run — pre-existing, unrelated to the trailing-comma fix in commit `d4d1f7d5`).
**Severity:** medium–high. If arithmetic-operator terms in clause *heads*
(`Diff(A + B, ...)`) genuinely don't unify, that breaks a documented core
capability ("operators are structural terms in heads — matched, not evaluated").

## Symptom
`clausal/examples/symbolic_diff.clausal`: 7 of 10 `Test` clauses fail with
`no solutions`.

**Pass (3):** the facts and the `number/1` clause —
```
Diff(X, X, 1)                       % dx/dx = 1        PASS
Diff(C, _, 0) <- number(C)          % d(5)/dx = 0      PASS
```

**Fail (7):** everything relying on either
1. **structural operator heads** —
   ```
   Diff(A + B, X, DA + DB)  <- (Diff(A,X,DA), Diff(B,X,DB))       % d(x+x)/dx  FAILS
   Diff(A * B, X, A*DB + B*DA) <- ...                              % d(x*x)/dx  FAILS
   Diff(E ** N, X, N * E**N1 * DE) <- (number(N), N1 := N-1, ...)  % d(x^n)/dx  FAILS
   ```
2. the **different-variable** clause —
   ```
   Diff(Y, X, 0) <- (is_str(Y), Y is not X)                        % d(y)/dx=0  FAILS
   ```

Confirmed by direct probe:
```
call("Test", "dx/dx = 1")   -> PASS
call("Test", "d(y)/dx = 0") -> no solutions
call("Test", "d(x+x)/dx")   -> no solutions
```

## Isolation (two likely-distinct sub-bugs)
- **(A) Operator-term heads.** `Diff(A + B, X, DA + DB)` — the head's first arg
  is an `Add(A, B)` structural term and the third builds `Add(DA, DB)`. A caller
  `Diff(Vx + Vx, Vx, 1 + 1)` should unify `Add(Vx,Vx)` with `Add(A,B)`. It finds
  nothing, so `+`/`*`/`**` terms in heads are not matching (evaluated away? not
  constructed as `Compound`/operator nodes in the head pattern? compiled to a
  guard that never fires?). This is the higher-value one to chase — same
  mechanism underlies `*` and `**`.
- **(B) Different-variable clause.** `Diff(Y, X, 0) <- (is_str(Y), Y is not X)`.
  Independent of (A). Check `is_str/1` and the `Y is not X` goal (structural
  disequality on two logic vars / atoms) — one of them likely fails or errors
  silently. May relate to how `is not` compiles vs `dif/2`.

## Hypothesis / suggested fix area
For (A): dump the compiled `Diff(A + B, ...)` clause head and a caller like
`Diff(Vx + Vx, Vx, D)`; verify the head pattern is an operator/`Compound` node
and that the argument `Vx + Vx` is passed as the same structural term (not
pre-evaluated). The module comment claims `+ * **` are structural in heads and
call args — check the transform actually preserves them as term constructors in
*head* position (it may only do so in body/goal position).

For (B): probe `is_str(Vy)` and `Vy is not Vx` in isolation.

## Repro
```
pytest clausal/examples/symbolic_diff.clausal -q
# 7 failed, 3 passed
```

## Diagnosis (2026-07-01) — root causes found; NOT indexing-related

Confirmed **unrelated** to the map_coloring first-arg-indexing fix (`2bc2788e`):
raising `_INDEX_THRESHOLD` to disable all indexing leaves every failure
unchanged. Two independent root causes, both about term semantics, not dispatch.

### (A) Operator/BinOp nodes have no structural `__unify__`
`Add`/`Mult`/`Pow` subclass `clausal.pythonic_ast.nodes.BinOp`/`Node` — they are
**not** `Compound`, and (unlike `Compound`, `DictTerm`, `SetTerm`) they define no
`__unify__` / `__walk__` / `__occurs_check__` hooks. The C `do_unify` therefore
treats them as opaque values compared by `==`:

```
unify(Add(1,1), Add(1,1))      -> True    # identical ground: == holds
unify(Add(X,Y), Add(1,1))      -> False   # any Var in a field: == fails, no binding
unify(Add(X,Y), Add(V,V))      -> False
```

Head matching still works because the compiler emits a `MatchClass(Add, ...)`
structural *pattern* (not a runtime `unify`). But the moment a clause builds an
operator term through a variable and must unify it — e.g. clause `Diff(A+B, X,
DA+DB)` binds head DERIV var to `Add(DA,DB)` in the body, then the caller's
DERIV must unify with that — `unify(Add(_,_), Add(_,_))` fails. So:
- `Diff(Add(Vx,Vx), Vx, D)` with **unbound** D succeeds (computes
  `D = Add(1,1)`), but
- `Diff(Add(Vx,Vx), Vx, Add(1,1))` with a **ground** operator DERIV fails,
  because unifying the two `Add` terms structurally is unsupported.

Fix area: give `BinOp`/operator nodes the structural-unify protocol
(`__unify__`/`__walk__`/`__occurs_check__`) the way `Compound`/`DictTerm`/
`SetTerm` have it, in `clausal/pythonic_ast/nodes.py` + the C `do_unify`
dispatch. Decide how the non-semantic `position` field participates (it should
be ignored for unification, as it already is `compare=False` for `==`).

Secondary note (same area): `term_to_ast_expr` renders an operator term as a
Python operator expression (`Add(1,1)` -> `1 + 1`). For atom/var operands this
reconstructs the node via the operand's `__add__`, but for pure numeric operands
Python folds it (`1 + 1` -> `2`), silently collapsing the structural term. Once
(A) is fixed, verify whether this second collapse still bites for the
numeric-deriv tests (`d(x+x)/dx` expects `1 + 1`).

### (B) `is_str` on an atom — example uses atoms where clause expects strings
`Vx`/`Vy` are capital-V-lowercase, i.e. **atoms** (`PredicateMeta`), not
variables (variables are ALLCAPS or leading `_`). Clause
`Diff(Y, X, 0) <- (is_str(Y), Y is not X)` guards on `is_str(Y)`; `is_str(Vy)`
is correctly `False` for an atom, so the clause fails. This is arguably an
**example bug** (should use string literals `"x"`/`"y"`, or the clause should
accept atoms). Lower value than (A); decide intended semantics before changing
`is_str` vs. the example.

Direct probes used:
```
unify(Add(X,Y), Add(1,1))          -> False   # (A)
call('is_str', Vy)                 -> []       # (B) Vy is a PredicateMeta atom
# disabling indexing (_INDEX_THRESHOLD = 1e9) does not change any failure
```
