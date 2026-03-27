# Phase 10: Call-Site Specialization

**Goal:** when a clause body calls a locked predicate with a statically-known argument
in an indexed position, bypass the dispatch closure entirely and emit a direct reference
to the pre-compiled bucket function for that argument value.

This is the natural extension of Phase 7 (which cached the *dispatch closure* for locked
predicates) to the next level: caching the *specific bucket function* selected by a
statically-known argument.

---

## Motivation

After Phase 7, a locked-predicate call site looks like:

```python
# base_globals['_disp_Color2_2'] = Color2._dispatch_fn  (injected once at compile time)
StepGenerator(_disp_Color2_2, this_generator, 'red', _v_cat, trail)
```

At runtime `_disp_Color2_2` is the dispatch closure, which inspects `deref(args[0])` and
does a dict lookup to find the right bucket.  But when the call site itself has `'red'`
as a literal, the bucket to call is determined statically — the runtime dict lookup is
redundant.

After Phase 10 the same call becomes:

```python
# base_globals["Color2.bucket(pos=0, 'red')"] = <bucket fn>  (injected at compile time)
StepGenerator(Color2.bucket(pos=0, 'red'), this_generator, 'red', _v_cat, trail)
```

The dispatch closure is skipped entirely: one less deref, one less dict lookup per call.

The globals key uses an arbitrary string (not a valid Python identifier).  Python's
`compile()` on an AST tree — which is how clausal executes generated code — resolves
`ast.Name(id=k)` via a plain dict lookup, so any string works.  `ast.unparse()` renders
it verbatim, making the visualised generated code very readable (it shows exactly which
predicate and bucket is being called) even though the output does not re-parse.

---

## Sub-phases

### 10a — Expose bucket dicts on pred_cls  _(prerequisite)_

**Location:** `compile_predicate_trampoline`, just after the `plans` list is built
(around line 4055).

After all bucket functions and dispatch closures have been assembled, store the
single-position bucket dicts on the predicate class:

```python
# existing line:
plans.append((pos, idx_dict, pos_default_fn))

# NEW — after the loop:
if hasattr(pred_cls, '_index_plans') or True:          # always set
    pred_cls._index_plans = {pos: idx_dict
                             for pos, idx_dict, _ in plans}
```

Also expose the joint bucket dict when Phase 9b/9c produced a joint dispatch, by
storing it as `pred_cls._index_plans_joint`:

```python
# within the joint-dispatch branch (Phase 9b), after building joint_dict:
pred_cls._index_plans_joint = {(pos_i, pos_j): joint_dict}
```

For hierarchical (Phase 9c), expose:
```python
pred_cls._index_plans_hierarchical = {(pos_i, pos_j): level0_compiled}
```

**Clearing on recompile:** Lazy recompile already calls `compile_predicate_trampoline`
again and replaces `pred_cls._dispatch_fn`.  The same call will overwrite `_index_plans`
atomically.  No extra clearing needed.  Dynamic predicates will have their `_index_plans`
replaced on every retract/assertz cycle; because Phase 10 only specialises *locked*
predicates this is never observed by call-site-specialised code.

**Risk:** None — this is purely additive metadata on the class.

---

### 10b — Static-key extraction from AST arg expressions

**New helper:** `_static_call_key(arg_expr: ast.expr) -> Any | None`

Location: near `_runtime_arg_key` / `_extract_arg_key` (around line 5162).

```python
def _static_call_key(arg_expr: ast.expr) -> Any | None:
    """Return the index key if arg_expr is statically known at compile time.

    Mirrors _runtime_arg_key for the compile-time call-site analysis path.
    Returns None if the argument is a variable or otherwise unknown.
    """
    if isinstance(arg_expr, ast.Constant):
        # scalar: int, str, float, bool, None — key is the value itself
        return arg_expr.value
    if isinstance(arg_expr, ast.Call):
        # compound term constructor:  Dog(_v_name, _v_age)
        # The index key is (functor_name, arity).
        func = arg_expr.func
        if isinstance(func, ast.Name):
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            return (func.id, n_args)
        if isinstance(func, ast.Attribute):
            # qualified:  module.Dog(...)
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            return (func.attr, n_args)
    return None
```

This mirrors `_runtime_arg_key` exactly: scalars map to themselves, compound terms map
to `(functor, arity)`.

---

### 10c — Globals key naming convention

**New helper:** `_bucket_key(fname: str, pos: int, key: Any) -> str`

```python
def _bucket_key(fname: str, pos: int, key: Any) -> str:
    """Readable globals key for a bucket function.

    The returned string is used as an ast.Name id and as a base_globals key.
    It is not a valid Python identifier (contains dots, brackets, quotes) so
    generated code won't re-parse, but ast.unparse() renders it readably and
    compile(ast_tree, ...) resolves it via a plain dict lookup.
    """
    return f"{fname}.bucket(pos={pos}, {key!r})"


def _joint_bucket_key(fname: str, pos_i: int, pos_j: int,
                       ki: Any, kj: Any) -> str:
    return f"{fname}.bucket(pos=({pos_i},{pos_j}), ({ki!r},{kj!r}))"
```

---

### 10d — Pre-scan and injection: `_inject_bucket_refs_trampoline`

**Location:** new function in compiler.py, called from `compile_predicate_trampoline`
right after `_inject_resolved_targets_trampoline`.

This pass scans all clause bodies for call sites where a static argument key can be
resolved to a bucket function, injects those bucket functions into `base_globals`, and
records the mapping in `_compile_context_local.bucket_ref_map` for use by
`_dispatch_call_trampoline`.

```
_inject_bucket_refs_trampoline(
    clauses:     list[Clause],
    base_globals: dict,
    globals_:    dict | None,
) -> None
```

**Algorithm:**

```
for clause in clauses:
    for goal in _iter_call_goals(clause.body):
        fname, arity, arg_term_list = _decode_call_goal(goal)
        pred_obj = base_globals.get(fname)   # already resolved by Phase 6/7
        if pred_obj is None:
            continue
        if not (isinstance(pred_obj, PredicateMeta)
                and getattr(pred_obj, '_locked', False)):
            continue
        if not hasattr(pred_obj, '_index_plans'):
            continue

        # compile the arg terms to AST expressions (re-use existing helper)
        arg_exprs = [term_to_ast_expr(a, var_context={}) for a in arg_term_list]

        # single-argument specialisation
        for pos, idx_dict in pred_obj._index_plans.items():
            if pos >= len(arg_exprs):
                continue
            key = _static_call_key(arg_exprs[pos])
            if key is None or key not in idx_dict:
                continue
            gkey = _bucket_key(fname, pos, key)
            if gkey not in base_globals:
                base_globals[gkey] = idx_dict[key]
            _add_bucket_ref(fname, arity, pos, key, gkey)

        # joint specialisation (Phase 9b)
        if hasattr(pred_obj, '_index_plans_joint'):
            for (pi, pj), jdict in pred_obj._index_plans_joint.items():
                if pi >= len(arg_exprs) or pj >= len(arg_exprs):
                    continue
                ki = _static_call_key(arg_exprs[pi])
                kj = _static_call_key(arg_exprs[pj])
                if ki is None or kj is None:
                    continue
                jkey = (ki, kj)
                if jkey not in jdict:
                    continue
                gkey = _joint_bucket_key(fname, pi, pj, ki, kj)
                if gkey not in base_globals:
                    base_globals[gkey] = jdict[jkey]
                _add_joint_bucket_ref(fname, arity, pi, pj, ki, kj, gkey)
```

`_add_bucket_ref` records into `_compile_context_local.bucket_ref_map`:
```
(fname, arity, pos, key)  →  gkey_string
```

`_add_joint_bucket_ref` records into `_compile_context_local.joint_bucket_ref_map`:
```
(fname, arity, pos_i, pos_j, ki, kj)  →  gkey_string
```

**Note on `_iter_call_goals` and `_decode_call_goal`:** these are small helpers that walk
a clause body (a list of term-level goal objects) and yield `(fname, arity, args)` tuples
for `Call` nodes.  The existing `_collect_call_targets` pass already does the same
traversal; we can factor out the shared walker.

**Note on var_context:** when calling `term_to_ast_expr` during the pre-scan, variables
are mapped to distinct names via an empty `var_context={}`.  We only care about whether
the resulting expression is a constant; we ignore the exact variable names.

---

### 10e — extend `_dispatch_call_trampoline`

**Location:** `_dispatch_call_trampoline` in compiler.py (around line 2739).

Add a new highest-priority check before the Phase 7 check:

```python
def _dispatch_call_trampoline(
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
    trail_name: str,
    self_name: str,
) -> ast.expr:
    # Phase 10: direct bucket ref for statically-known indexed argument
    brmap = getattr(_compile_context_local, "bucket_ref_map", {})
    jbrmap = getattr(_compile_context_local, "joint_bucket_ref_map", {})

    # Try joint first (more selective)
    for pos_i in range(arity):
        for pos_j in range(arity):
            if pos_i == pos_j or pos_i >= len(arg_exprs) or pos_j >= len(arg_exprs):
                continue
            ki = _static_call_key(arg_exprs[pos_i])
            kj = _static_call_key(arg_exprs[pos_j])
            if ki is None or kj is None:
                continue
            gkey = jbrmap.get((fname, arity, pos_i, pos_j, ki, kj))
            if gkey is not None:
                dispatch_expr = ast.Name(id=gkey, ctx=ast.Load())
                return ast.Call(
                    func=_name("StepGenerator"),
                    args=[dispatch_expr, _name(self_name)] + arg_exprs + [_name(trail_name)],
                    keywords=[],
                )

    # Try single-argument bucket
    for pos, arg_expr in enumerate(arg_exprs):
        key = _static_call_key(arg_expr)
        if key is None:
            continue
        gkey = brmap.get((fname, arity, pos, key))
        if gkey is not None:
            dispatch_expr = ast.Name(id=gkey, ctx=ast.Load())
            return ast.Call(
                func=_name("StepGenerator"),
                args=[dispatch_expr, _name(self_name)] + arg_exprs + [_name(trail_name)],
                keywords=[],
            )

    # Phase 7: locked-predicate dispatch cache (fallback)
    dk = _disp_key(fname, arity)
    locked_keys = getattr(_compile_context_local, "locked_dispatch_keys", frozenset())
    if dk in locked_keys:
        dispatch_expr = _name(dk)
    else:
        dispatch_expr = ast.Call(
            func=ast.Attribute(value=_name(fname), attr="_get_dispatch"),
            args=[], keywords=[],
        )
    return ast.Call(
        func=_name("StepGenerator"),
        args=[dispatch_expr, _name(self_name)] + arg_exprs + [_name(trail_name)],
        keywords=[],
    )
```

---

### 10f — Wire into `compile_predicate_trampoline`

in_ `compile_predicate_trampoline`, after the existing
`_inject_resolved_targets_trampoline(...)` call and before
`_build_predicate_trampoline_funcdef(...)`, add:

```python
_inject_bucket_refs_trampoline(clauses, base_globals, globals_)
```

Also initialise the new context maps at the start of the compile context block
(alongside the existing `locked_dispatch_keys`):

```python
_compile_context_local.bucket_ref_map = {}
_compile_context_local.joint_bucket_ref_map = {}
```

And clear them at the end (after `_build_predicate_trampoline_funcdef`):

```python
_compile_context_local.bucket_ref_map = {}
_compile_context_local.joint_bucket_ref_map = {}
```

---

## Priority of specialisation at a call site

| Condition | Dispatch expression emitted |
|-----------|----------------------------|
| Two static args, joint bucket exists | `"Foo.bucket(pos=(0,1), ('red', 2))"` |
| One static arg, single-pos bucket exists | `"Foo.bucket(pos=0, 'red')"` |
| Locked predicate, no static match | `_disp_Foo_2` (Phase 7) |
| Dynamic predicate | `Foo._get_dispatch()` |

---

## Key invariants

- **Locked-predicate guard only.** Only predicates with `_locked=True` at the time the
  *caller* is compiled have their buckets specialised.  Dynamic predicates always go
  through the dispatch closure.

- **`_index_plans` is set before locking.** The import hook locks predicates after
  loading all clauses and compiling.  when a cross-module call is compiled, the callee
  is already locked (and `_index_plans` is already populated).  Self-recursive calls
  within the same module are compiled while the predicate is not yet locked, so they fall
  back to Phase 7 / `_get_dispatch()` — which is correct.

- **Recompilation safety.** Lazy recompile rewrites `_dispatch_fn` and `_index_plans`
  atomically.  Phase 10 only applies at *compile time* of the *caller*, not the callee.
  The caller is compiled once and not recompiled when the callee changes (because callers
  only call locked predicates for Phase 10; locked predicates never change).

- **Fallback correctness.** If `_index_plans` is absent (predicate compiled before Phase
  10 or without indexing), the code falls through to Phase 7 / `_get_dispatch()`.

---

## Files changed

| File | Change |
|------|--------|
| `clausal/logic/compiler.py` | Add `_static_call_key`, `_bucket_key`, `_joint_bucket_key` helpers (~25 lines) |
| `clausal/logic/compiler.py` | Add `_inject_bucket_refs_trampoline` (~60 lines) |
| `clausal/logic/compiler.py` | extend `_dispatch_call_trampoline` with Phase 10 block (~25 lines) |
| `clausal/logic/compiler.py` | Wire `_inject_bucket_refs_trampoline` into `compile_predicate_trampoline` (~8 lines) |
| `clausal/logic/compiler.py` | Store `pred_cls._index_plans` after building `plans` (~3 lines) |
| `clausal/logic/compiler.py` | Store `pred_cls._index_plans_joint/hierarchical` in joint dispatch branches (~6 lines) |
| `tests/test_callsite_specialization.py` | New test file (~120 lines) |

Total new code: ~150 lines in compiler.py, ~120 lines in tests.

---

## Tests (`tests/test_callsite_specialization.py`)

1. **`_index_plans` is populated after compilation** — compile a simple predicate with
   integer and atom keys, assert `pred_cls._index_plans` contains the expected keys.

2. **`_static_call_key` unit tests** — constants, compound constructors, variables →
   expected key or None.

3. **`predicate_to_source` shows bucket ref in generated code** — compile a predicate
   that calls a locked predicate with a literal first argument.  assertz the source
   contains `"bucket(pos=0,"` and does NOT contain `"_get_dispatch"` or `"_disp_"`.

4. **Correctness: results identical to non-specialised** — run a query that exercises
   a specialised call site, confirm all solutions match the expected set.

5. **Phase 7 fallback still used for variable-arg calls** — a call site where the
   indexed position is a Var should still show `_disp_` in the generated source.

6. **Dynamic predicate unchanged** — a call to a `-dynamic` predicate should still
   show `._get_dispatch()`.

7. **Joint-key specialisation** — when two arguments are both static and a joint bucket
   exists, generated code uses the joint bucket ref.

8. **Self-recursive predicate not specialised** — a predicate calling itself is compiled
   while still unlocked; generated code falls back to `_get_dispatch()`.

---

## Interaction with existing phases

| Phase | Interaction |
|-------|------------|
| Phase 5 (deep structural trie) | Bucket functions are already the correct grain; Phase 10 just skips the dispatch wrapper that routes to them |
| Phase 7 (cached dispatch) | Phase 10 takes priority when a static key is found; Phase 7 remains the fallback |
| Phase 9a/9b/9c (multi-arg indexing) | Phase 10 can specialise on any position exposed by 9a, and on joint pairs exposed by 9b; hierarchical (9c) buckets are exposed via `_index_plans_hierarchical` for future extension |
| `predicate_to_source` / visualize | The arbitrary-string globals key renders readably via `ast.unparse()` — a call to `Color2.bucket(pos=0, 'red')` looks exactly like what it is |
