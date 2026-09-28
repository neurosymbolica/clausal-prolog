# Clausal — Predicate Indexing

## Problem

Without indexing, every query against a predicate tries all clauses sequentially. For a predicate with N fact clauses, a ground lookup costs O(N) — each clause's `match` block is entered and compared. This is acceptable for small predicates but becomes a bottleneck for large fact tables (100+ clauses).

```clausal
color('red',   [255,   0,   0]),
color('green', [  0, 128,   0]),
color('blue',  [  0,   0, 255]),
...  # 200 more colors
```

Querying `color("blue", X)` without indexing tries all 203 match blocks. With first-argument indexing, it jumps directly to the one clause whose first argument is `"blue"`.

---

??? abstract "Design"

    First-argument indexing partitions a predicate's clauses into buckets keyed on the first argument's value. At call time, the dispatch function inspects `arg0`:

    1. If `arg0` is an unbound `Var` (output-mode query), all clauses must be tried — fall back to the unindexed path.
    2. If `arg0` is ground, look up the value in a dict to find the right bucket.
    3. If no bucket matches (the value wasn't seen in any clause head), try only the default clauses.

    ### Clause classification

    Each clause's first-argument position is classified at compile time:

    | First arg in clause head | Index key | Bucket |
    |---|---|---|
    | Literal scalar (int, str, float, bytes, bool, None) | The value itself | Specific bucket for that value |
    | Var with `Unify(var, scalar)` in body (normalized fact) | The scalar value | Specific bucket |
    | Compound term (`circle(R)`, `rect(W,H)`, …) | `(functor, arity)` tuple | Specific bucket |
    | PredicateMeta instance | `(class_name, field_count)` tuple | Specific bucket |
    | Var with `Unify(var, compound)` in body | `(functor, arity)` tuple | Specific bucket |
    | Unbound Var (no body unification) | `_INDEX_VAR` sentinel | Default bucket |
    | List or other non-indexable value | `_INDEX_VAR` sentinel | Default bucket |

    The Var+Unify pattern comes from fact normalization (`_normalize_dataclass_fact` / `_normalize_fact_clause`), which replaces ground head values with fresh Vars and adds `Unify(var, value)` goals to the body. This is the standard representation for facts in clausal — the indexer recognises it and extracts the original ground value, including compound-term values.

    ### Bucket merging

    A critical correctness requirement: **clause ordering must be preserved.** In Prolog and clausal, clause order determines solution order. Consider:

    ```
    f(1, "a"),          # clause 0, key=1
    f(X, "b"),          # clause 1, default
    f(2, "c"),          # clause 2, key=2
    f(3, "d"),          # clause 3, key=3
    f(X, "e"),          # clause 4, default
    ```

    when querying `f(1, Y)`, the expected solution order is `"a"`, `"b"`, `"e"` — clause 0 (matches key=1), clause 1 (default, matches anything), clause 4 (default, matches anything). Clause 2 and 3 are skipped because their first arg doesn't match 1.

    To achieve this, each bucket's clause list **merges the bucket-specific clauses with all default clauses, in their original order:**

    ```
    bucket[1] = [clause_0, clause_1, clause_4]   # key=1 + defaults
    bucket[2] = [clause_1, clause_2, clause_4]   # key=2 + defaults
    bucket[3] = [clause_1, clause_3, clause_4]   # key=3 + defaults
    defaults  = [clause_1, clause_4]              # only defaults (for miss)
    all       = [clause_0 .. clause_4]            # for Var first-arg queries
    ```

    Each bucket is compiled as an independent dispatch function containing only its merged clause subset. The unindexed "all" function contains every clause.

    ### Threshold

    Indexing is only applied when `arity >= 1` and the predicate has at least 4 clauses (`_INDEX_THRESHOLD = 4`). Below this threshold, the overhead of the index dict lookup and multiple sub-functions outweighs the savings from skipping clauses.

    Indexing is also skipped when all clauses have variable first arguments (all defaults) — there's nothing to index on.

    ---

??? abstract "Implementation"

    ### Compile-time: building the index

    ```python
    _extract_first_arg_key(clause, arity) -> key | _INDEX_VAR
    ```

    Extracts the indexing key from a clause. Handles three head representations:

    - a cell `(functor, *args)` — `args[0]`
    - `Call(func=LoadName(f), args)` — `args[0]`
    - PredicateMeta instance — `getattr(head, fields[0])`

    If the first arg is a Var, scans the clause body for `Unify(left=same_var, right=scalar)` or `Unify(left=scalar, right=same_var)` and returns the scalar. Identity comparison (`is`) ensures we match the exact Var object from the head.

    ```python
    _build_first_arg_index(clauses, arity, threshold=4) -> dict | None
    ```

    Returns `None` if indexing is not beneficial. Otherwise returns:

    ```python
    {
        "buckets": {key: [Clause, ...]},  # merged with defaults
        "defaults": [Clause, ...],
        "all": [Clause, ...],
    }
    ```

    ### Runtime: indexed dispatch

    The indexed dispatch function is a Python closure that wraps three categories of sub-functions:

    ```
                        ┌─ is_var(arg0)? ──→ all_fn(*args)
                        │
    dispatch(*args) ────┤
                        │                  ┌─ hit ──→ bucket_fn(*args)
                        └─ idx.get(arg0) ──┤
                                           └─ miss ─→ default_fn(*args)
    ```

    #### Simple mode

    ```python
    def _make_indexed_dispatch_simple(all_fn, idx_dict, default_fn):
        def dispatch(*args):
            _a0 = deref(args[0])
            if is_var(_a0):
                yield from all_fn(*args)
                return
            try:
                _bfn = idx_dict.get(_a0)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from default_fn(*args)
        return dispatch
    ```

    The `try/except TypeError` handles unhashable values (e.g., lists) gracefully — they fall through to the default bucket.

    #### Trampoline mode

    ```python
    def _make_indexed_dispatch_trampoline(all_fn, idx_dict, default_fn, done):
        def dispatch(*args):
            parent = args[1]
            _a0 = deref(args[2])      # first predicate arg is at index 2
            if is_var(_a0):
                yield from all_fn(*args)
            else:
                ...                    # same lookup logic
            yield (parent, done)       # DONE after all sub-functions
        return dispatch
    ```

    **Critical detail:** sub-functions in trampoline mode must NOT yield `(parent, DONE)` at the end. Since they are consumed via `yield from`, a DONE yield would be forwarded to the trampoline, which would interpret it as the wrapper being exhausted — even though the wrapper still has more sub-functions to try. The `_build_predicate_trampoline_funcdef` function accepts an `emit_done=False` parameter for this purpose. The wrapper itself emits the final `yield (parent, DONE)`.

    ### Sub-function compilation

    Each sub-function (all, bucket, default) is compiled through the same `_build_predicate_funcdef` / `_build_predicate_trampoline_funcdef` machinery as a normal predicate, just with a subset of clauses. This means:

    - Head pattern compilation, body goal compilation, variable pre-allocation, and call target injection all work identically.
    - All sub-functions share the same `base_globals` dict, so they have access to the same builtins, predicate classes, and call targets.
    - The `_collect_globals_info` + `_inject_resolved_targets` pass uses the **full** clause list, not the subset — ensuring all needed names are available in every sub-function.

    Sub-functions get distinct names (`{functor}__all`, `{functor}__b0`, `{functor}__dflt`) to avoid collisions when compiled via `functiondef_to_function`.

    ### Bucket head lifting

    The `.clausal` term rewriter normalises every clause head to all-Var arguments, moving ground values into body `Unify` goals. A fact `color("red", "warm")` is stored as:

    ```
    head = color(arg_0=Var(_5), arg_1=Var(_6))
    body = [Unify(left=Var(_5), right="red"), Unify(left=Var(_6), right="warm")]
    ```

    Inside a bucket function for arg_0 = `"red"`, the body goal `Unify(Var(_5), "red")` is guaranteed to succeed — the dispatch layer already confirmed the argument is `"red"`. The resulting `trail.mark()` + `unify()` + `trail.undo()` triple is wasted work.

    Before bucket compilation, `_lift_clause_at_pos(clause, pos)` removes this redundant Unify and places the ground value directly in the head. The head pattern compiler then emits `MatchValue("red")` instead of a wildcard capture, eliminating the three wasted operations:

    ```python
    # Before (wildcard + body unify):
    case [_v0, _v1]:
        _mark = trail.mark()
        try:
            _m = trail.mark()
            if unify(_v0, "red", trail):   # always succeeds in this bucket
                ...
            trail.undo(_m)
        finally: trail.undo(_mark)

    # After (MatchValue — always matches in bucket context):
    case ["red", _v1]:
        _mark = trail.mark()
        try:
            ...
        finally: trail.undo(_mark)
    ```

    The **fallback function** (called for unbound first arguments) always uses the original, unlifted clauses — so output-mode queries (`color(NAME, 'warm')`) remain fully correct. Only bucket functions are affected.

    ### Lazy recompile integration

    No changes to the Database or PredicateMeta invalidation mechanism were needed. when `assertz` or `retract` invalidates a predicate's dispatch function, the lazy recompile closure calls `compile_predicate` (or `compile_predicate_trampoline`) from scratch. Since the compilation functions now build an index automatically when beneficial, the recompiled dispatch function gets a fresh index reflecting the updated clause list.

    ---

## What is NOT indexed

The following remain in the default bucket (no bucket discrimination):

- **Lists** — including empty lists. List first-args could be indexed by structure (empty vs cons), but this is deferred.
- **Nested structures** — only the top-level functor/arity is extracted; argument positions *inside* a compound term are not recursively indexed.

Scalar values, Compound terms (via functor/arity), and PredicateMeta instances are all indexed.

---

??? info "Testing"

    `tests/test_first_arg_index.py` covers:

    - **Key extraction**: scalar values, Var+Unify pattern, None, booleans, zero arity, non-indexable types
    - **Index building**: threshold enforcement, all-defaults detection, bucket merging with defaults
    - **Simple mode dispatch**: ground lookup, Var enumeration, no-match fallback, mixed var+specific clauses, integer and string keys
    - **Trampoline mode dispatch**: same scenarios as simple mode, verifying `yield from` + DONE protocol correctness
    - **Dynamic re-indexing**: `assertz` triggers lazy recompile with updated index (both modes)
    - **PredicateMeta integration**: normalized Var+Unify heads from PredicateMeta facts
    - **Edge cases**: arity-1 predicates, duplicate first-arg keys, None as key, bool/int hash collision

    ---
    ---

# Groundness-Keyed Dispatch

Groundness-keyed dispatch generalises first-argument indexing to **multi-argument indexing** with a runtime selector. Instead of indexing only on `arg0`, the compiler analyses every argument position and builds an independent index for each one that has useful discriminating power. At call time, a lightweight selector inspects which arguments are ground and dispatches to the best available index.

## Motivation

First-argument indexing only helps when the first argument is ground. Many predicates are queried in multiple modes:

```clausal
--8<-- "tests/fixtures/docs/indexing_sigs.txt:color_query_modes"
```

With groundness-keyed dispatch, querying `color(NAME, 'warm')` uses a second-argument index and jumps directly to the clauses whose second arg is `'warm'`, skipping all others.

??? abstract "Design"

    ### Multi-position analysis

    At compile time, `_analyze_index_positions(clauses, arity)` scans every argument position:

    ```python
    for pos in range(arity):
        index = _build_arg_index(clauses, arity, pos)
        if index is useful:
            results.append((pos, index))
    ```

    Each position is ranked by **selectivity** — the number of distinct keys. The most selective position (most distinct values, best at narrowing the clause set) is checked first at runtime.

    ### Generalised key extraction

    `_extract_arg_key(clause, pos, arity)` generalises `_extract_first_arg_key` to work on any argument position. Classification rules:

    | arg at position `pos` | Key | Bucket |
    |---|---|---|
    | Scalar (int, str, float, bytes, bool, None) | The value | Specific |
    | Var with `Unify(var, scalar)` in body | The scalar | Specific |
    | Compound (cell) | `(functor, arity)` tuple | Specific |
    | PredicateMeta instance | `(class_name, field_count)` tuple | Specific |
    | Var with `Unify(var, compound)` in body | `(functor, arity)` tuple | Specific |
    | Unbound Var, list | `_INDEX_VAR` | Default |

    The Var identity check (`goal.left is arg`) ensures we match the correct Var when multiple positions have Var+Unify patterns — each position's Var object is distinct.

    **Runtime key extraction** mirrors the compile-time rules. The `_runtime_arg_key(a)` helper (used by all dispatch closures) maps a deref'd runtime value to the same key space so that compound-term buckets are reachable:

    ```python
    def _runtime_arg_key(a):
        if isinstance(a, _INDEXABLE_TYPES):
            return a
        if is_term_instance(a):
            return (type(a).__name__, len(type(a)._fields))
        return _INDEX_VAR   # unhashable / lists → default
    ```

    All four dispatch closures call `_runtime_arg_key` instead of using the raw deref'd value directly.

    ### Plan structure

    For a predicate with indexable positions at, say, positions 0, 1, and 2, the compiler builds:

    ```
    plans = [
        (1, idx_dict_1, default_fn_1),   # position 1 (most selective)
        (0, idx_dict_0, default_fn_0),   # position 0
        (2, idx_dict_2, default_fn_2),   # position 2 (least selective)
    ]
    fallback_fn = all_clauses_fn         # for when no arg is ground
    ```

    Each plan's `idx_dict` maps values to compiled sub-functions (exactly like first-arg index buckets), and `default_fn` handles values not in the index at that position. The `fallback_fn` is the full linear-scan function used when all arguments are unbound.

    ### Runtime selector

    ```
                            ┌─ ground? ──→ idx_1.get(val) ──→ bucket / default
                            │
    dispatch(*args) ────────┤  (check positions in selectivity order)
                            │
                            ├─ ground? ──→ idx_0.get(val) ──→ bucket / default
                            │
                            └─ all Var  ──→ fallback_fn
    ```

    The selector is a Python closure:

    ```python
    def dispatch(*args):
        for pos, idx_dict, default_fn in plans:
            a = deref(args[pos])
            if not is_var(a):
                bfn = idx_dict.get(a)       # O(1) hash lookup
                yield from (bfn or default_fn)(*args)
                return
        yield from fallback_fn(*args)        # all-Var fallback
    ```

    **Single-position fast path:** when only one position is indexable, the loop is eliminated and the selector degenerates to the same structure as first-argument indexing — no performance regression.

    ### Trampoline mode

    The trampoline selector accounts for the different argument layout (`this_generator, parent, arg0, ..., trail`) by offsetting position indices by 2. Sub-functions use `emit_done=False` as in first-argument indexing — the selector emits the final `yield (parent, DONE)`.

## Example: colour database

```clausal
color('red',    'warm'),
color('blue',   'cool'),
color('green',  'cool'),
color('yellow', 'warm'),
color('white',  'neutral'),
```

Analysis finds both positions indexable:

- **Position 0**: 5 distinct keys (red, blue, green, yellow, white) — most selective
- **Position 1**: 3 distinct keys (warm, cool, neutral) — less selective

Plans sorted by selectivity: position 0 first, then position 1.

| Query | Selector path | Clauses tried |
|---|---|---|
| `color("blue", X)` | arg0 ground → pos-0 index → bucket["blue"] | 1 |
| `color(X, "cool")` | arg0 Var → skip; arg1 ground → pos-1 index → bucket["cool"] | 2 |
| `color("red", "warm")` | arg0 ground → pos-0 index → bucket["red"] | 1 |
| `color(X, Y)` | arg0 Var → skip; arg1 Var → skip; fallback | 5 |

## Interaction with first-argument indexing

Groundness-keyed dispatch fully subsumes first-argument indexing. The `compile_predicate` and `compile_predicate_trampoline` functions use `_analyze_index_positions` instead of `_build_first_arg_index`. when only position 0 is indexable, the result is behaviourally identical to first-argument indexing.

The first-arg index functions (`_extract_first_arg_key`, `_build_first_arg_index`, `_make_indexed_dispatch_simple`, `_make_indexed_dispatch_trampoline`) are retained as thin wrappers or standalone utilities for backward compatibility with tests that reference them directly.

## Interaction with dynamic predicates

No changes to the invalidation mechanism. when [`assertz` or `retract`](database_ops.md) modifies a predicate, the lazy recompile closure calls `compile_predicate` from scratch. The fresh compilation analyses all positions and builds new indexes reflecting the updated clause list.

## Limitations

- **No cross-position indexing** (single-arg only): positions are checked independently; the selector picks the single best ground position at runtime. Multi-argument indexing extends this — see below.
- **Compilation cost**: each indexable position produces its own set of sub-functions (buckets + default). For a predicate with `P` indexable positions and `K` average distinct keys, compilation produces roughly `P * K` sub-functions.

---

??? info "Testing"

    `tests/test_groundness_dispatch.py` covers:

    - **Generalised key extraction**: arbitrary position, Var+Unify at non-first positions, PredicateMeta second field
    - **Per-position index building**: position 0 index, position 1 index, `n_distinct` field
    - **Position analysis**: both positions indexable, single-position detection, selectivity sorting, three-arg predicates
    - **Second-arg lookup (simple mode)**: ground second arg, ground first arg, both ground, neither ground, no-match, three-arg middle/last ground
    - **Second-arg lookup (trampoline mode)**: same scenarios
    - **Different-mode dispatch**: same predicate queried in four modes (first-ground, second-ground, both-ground, neither-ground)
    - **Mixed clauses**: var-headed clauses in position-specific buckets, true catch-all clauses (Var at all positions)
    - **Dynamic re-indexing**: `assertz` triggers multi-plan recompile (both modes)
    - **Backward compatibility**: single-position matches first-argument indexing, below-threshold still works
    - **PredicateMeta integration**: second-field lookup on PredicateMeta facts

---

# Multi-Argument Indexing

Single-arg groundness-keyed dispatch picks the *best single position* that is ground. Multi-argument indexing extends this in three steps:

- **Compound keys** — Compound terms and PredicateMeta instances are indexable (via functor/arity tuples).
- **Flat joint key** — index on `(argI, argJ)` pairs when both are ground and the pair uniquely discriminates clauses much better than any single arg.
- **Secondary (hierarchical) dispatch** — two-level index on `(argI, argJ)` that also handles partial groundness (`argI` ground, `argJ` unbound) without falling all the way back to the full scan.

---

## Compound functor/arity keys

Without compound-key indexing, Compound and PredicateMeta heads fell into the default bucket.  A predicate like:

```clausal
--8<-- "tests/fixtures/docs/indexing_sigs.txt:compound_keys"
```

had no indexing at all on `arg0`, even though the four clauses are perfectly discriminated by functor name.

With compound-key indexing, `_extract_arg_key` returns `("circle", 1)`, `("rect", 2)`, `("triangle", 3)`, `("sq", 1)` as bucket keys. The runtime dispatch uses `_runtime_arg_key` to extract the same tuple from the caller's argument before dict lookup. Scalar keys and compound-tuple keys coexist safely in the same `idx_dict` because `(functor, arity)` tuples never equal plain integers or strings.

```clausal
--8<-- "tests/fixtures/docs/indexing_sigs.txt:compound_dispatch"
```

---

## Flat joint key

Some predicates have poor single-arg discrimination but perfect joint discrimination:

```clausal
--8<-- "tests/fixtures/docs/indexing_sigs.txt:flat_joint_example"
```

- arg 0 (`fire/ice/wind`): 3 distinct values
- arg 1 (`dry/wet`): 2 distinct values
- Joint `(arg0, arg1)`: 6 distinct values — uniquely identifies every clause

`_analyze_joint_index_positions` selects the pair `(best_single_pos, k)` with the largest improvement.  The quality criterion is `joint_distinct > best_single_distinct × 1.5`.

when activated (joint coverage ≥ 80%, meaning ≥80% of clauses have both args ground), the dispatch uses a **flat joint dict**:

```clausal
--8<-- "tests/fixtures/docs/indexing_sigs.txt:flat_joint_dispatch"
```

Single-arg fallbacks ensure correct behaviour for partial-groundness queries.

---

## Secondary (hierarchical) dispatch

when joint coverage < 80%, secondary (hierarchical) dispatch is preferred over flat joint key.  Secondary indexing builds a **two-level nested structure** that efficiently handles partial groundness:

```clausal
--8<-- "tests/fixtures/docs/indexing_sigs.txt:secondary_structure"
```

Within each level-0 bucket (all clauses sharing a given `argI` key), a second `_build_arg_index` on `argJ` is attempted with a lower threshold (2 instead of 4).

**Level-1 default is all clauses in the level-0 bucket** (not just var-headed clauses). This is the key correctness requirement: when `argJ` is unbound at call time, every clause in the level-0 bucket is a potential match and must be tried.

```clausal
--8<-- "tests/fixtures/docs/indexing_sigs.txt:secondary_dispatch"
```

**Performance characteristics** relative to single-arg dispatch on `argI`:

| Query mode | Single-arg | Secondary |
|---|---|---|
| `argI` ground, `argJ` ground | O(1) + O(n_bucket) scan | O(1) + O(1) |
| `argI` ground, `argJ` unbound | O(1) + O(n_bucket) scan | O(1) + O(n_bucket) scan (same) |
| `argI` unbound | O(n) full scan | O(n) full scan (same) |

Secondary indexing never regresses relative to single-arg: the worst case is identical, and the both-ground case is strictly better.

---

## Compiler integration

Both flat joint and secondary dispatch are integrated into `compile_predicate_trampoline` and `compile_predicate_shallow`.  After single-arg plans are built, the compiler checks for a multi-arg opportunity:

```python
joint_result = _analyze_joint_index_positions(clauses, arity, index_positions)
if joint_result is not None:
    pos_i, pos_j, joint_info = joint_result
    if joint_info["coverage"] < _JOINT_COVERAGE_THRESHOLD:
        # secondary dispatch (low joint coverage)
        sec = _build_secondary_index(clauses, arity, pos_i, pos_j)
        fn = _make_secondary_dispatch_trampoline(sec, ...)
    else:
        # flat joint dispatch (high joint coverage)
        fn = _make_joint_dispatch_trampoline(pos_i, pos_j, ...)
else:
    fn = _make_groundness_dispatch_trampoline(plans, fallback_fn, DONE)
```

`_JOINT_COVERAGE_THRESHOLD = 0.8` is the fraction of clauses that must have both `argI` and `argJ` ground (at compile time) before the flat joint index is preferred over secondary.

---

??? info "Testing"

    `tests/test_compiler_optimizations.py` covers multi-argument indexing in three test classes:

    **TestCompoundKeyIndexing**:

    - `_extract_arg_key` returns `(functor, arity)` tuples for compound (cell) heads
    - `_build_arg_index` yields distinct buckets for compound-headed clauses
    - Dispatch correctness: `circle(42)` → `Q=42`, `rect(3,4)` → `Q=3`
    - Unknown functor (no bucket) falls through to default
    - Scalar keys and compound-tuple keys coexist without collision
    - PredicateMeta heads produce `(class_name, field_count)` keys

    **TestSecondaryIndexing**:

    - `_build_secondary_index` structure: 3 level-0 keys, 2 level-1 keys each
    - All-ground exact match and no-match
    - `argI` ground, `argJ` unbound → all level-0 bucket clauses returned
    - `argJ` ground, `argI` unbound → correct single-arg fallback via arg-1 plan
    - Fully unbound → all 6 facts

    **TestJointKeyIndexing**:

    - `_build_joint_arg_index` returns 6 distinct `(group, subtype)` pairs
    - `_analyze_joint_index_positions` identifies the correct pair
    - Both-ground exact match and no-match
    - First-arg-only ground → two solutions from single-I fallback
    - Second-arg-only ground → three solutions from single-J fallback
    - Fully unbound → all 6 facts

---

# Call-Site Bucket Specialisation

The indexing optimisations described above all apply to the *callee*: how quickly a called predicate routes an incoming query to the right bucket of clauses. Call-site specialisation optimises the *caller*: when a call passes a statically-known literal to a locked predicate, the dispatch closure is bypassed entirely and the bucket function is referenced directly.

## Motivation

Without call-site specialisation, a call to a locked predicate looks like:

```python
# base_globals["$disp_color_1"] = resolve_predicate_row(color, arity=1, db=db).dispatch_fn  (captured at compile time)
StepGenerator($disp_color_1, this_generator, 'red', trail)
```

At runtime `$disp_color_1` is the dispatch closure. It calls `deref(args[0])`, computes `_runtime_arg_key`, and does a dict lookup. But when the call site already has `'red'` as a literal, the bucket to call is known at compile time — the runtime lookup is redundant.

With call-site specialisation the same call becomes:

```python
# base_globals["color.bucket(pos=0, 'red')"] = <bucket fn>  (injected at compile time)
StepGenerator(color.bucket(pos=0, 'red'), this_generator, 'red', trail)
```

One deref, one dict lookup, and the dispatch closure itself are all eliminated.

The globals key `"color.bucket(pos=0, 'red')"` is not a valid Python identifier, but Python's `compile(ast_tree, ...)` resolves `ast.Name(id=k)` via a plain dict lookup on the function's globals, so any string works. `ast.unparse()` renders it verbatim, making generated code self-documenting.

## Priority table

| Condition at call site | Dispatch expression emitted |
|---|---|
| Two static args, joint bucket exists | `"foo.bucket(pos=(0,1), ('red', 2))"` |
| One static arg, single-pos bucket exists | `"foo.bucket(pos=0, 'red')"` |
| Locked predicate, no static match | `$disp_foo_2` (cached dispatch closure) |
| Dynamic predicate | `$dispatch_at(foo, 2)` (the binding — the owner's handle — resolved to its row's dispatch at each call) |

## Key invariants

**Locked-only.** Only call sites targeting a predicate whose row is locked (`row.locked`) at the caller's compile time are specialised. [Dynamic predicates](directives.md) always go through `$dispatch_at` because their clause set may change at runtime.

**`_index_plans` set before locking.** The import hook locks predicates after all their clauses are compiled and the dispatch function is installed. when a cross-module call is compiled the callee is already locked and `_index_plans` is already populated. Self-recursive calls are compiled while the predicate is still unlocked, so they fall back to the cached dispatch closure / `$dispatch_at` — which is correct.

**Recompilation safety.** Lazy recompile (triggered by `assertz`/`retract`) calls `compile_predicate_trampoline` from scratch, overwriting `_dispatch_fn` and `_index_plans` atomically. Call-site specialisation only ever applies to calls *to* locked predicates; locked predicates never change after locking. Callers of dynamic predicates are never specialised and are therefore unaffected by dynamic recompilation.

??? abstract "Implementation"

    **Bucket dict exposure** — `_index_plans`. After the final dispatch fn is built inside `compile_predicate_trampoline`, the per-position dicts are stored on the predicate's row with every bucket wrapped by `_make_call_site_bucket_trampoline` — call sites drive these functions *directly* via `StepGenerator`, so each SIGNAL-mode bucket is completed to the full trampoline contract (terminal `(fail, DONE)` yield, TRO re-dispatch through the dispatch fn):

    ```python
    _plan_row = _plan_row_for(pred_cls, db, functor, arity)   # the Database's row
    _plan_row.index_plans = {
        pos: {key: _make_call_site_bucket_trampoline(bfn, fn, DONE, ...)
              for key, bfn in idx_dict.items()}
        for pos, idx_dict, _ in plans
    }
    ```

    The joint variant `_index_plans_joint` is wrapped the same way; `_index_plans_hierarchical` stays raw (its level-0 entries are `(level1_fns, level1_default_fn)` tuples — informational only, no walker drives them). **Tabled predicates expose empty dicts for all three** — a direct bucket ref would bypass the tabling wrapper. If the predicate has no indexing (below threshold), all three are set to `{}` to clear any stale value from a previous compilation.

    **`_static_call_key(arg_expr)`** — Mirrors `_runtime_arg_key` for compile-time AST analysis:

    ```python
    def _static_call_key(arg_expr: ast.expr) -> Any | None:
        if isinstance(arg_expr, ast.Constant):
            return arg_expr.value           # int, str, float, bool, None
        if isinstance(arg_expr, (ast.List, ast.Tuple)):
            # literal 1-char-str elements canonicalise to the joined str
            # (or joined bytes for 0-255 ints), same as _runtime_arg_key
            ...
        if isinstance(arg_expr, ast.Call):
            func = arg_expr.func
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            if isinstance(func, ast.Name):
                return (func.id, n_args)
            if isinstance(func, ast.Attribute):
                # Cls._clausal_new(...) (Phase 0 construction fast path):
                # the class name is func.value, not func.attr — func.attr is
                # always the literal "_clausal_new".  A qualified mod.Dog(...)
                # call still keys on func.attr.
                if func.attr == "_clausal_new" and isinstance(func.value, ast.Name):
                    return (func.value.id, n_args)
                return (func.attr, n_args)
        return None                         # variable or unknown
    ```

    **Key naming helpers:**

    ```python
    _bucket_key("Color", 0, "red")            →  "color.bucket(pos=0, 'red')"
    _joint_bucket_key("Pair", 0, 1, "x", 2)  →  "Pair.bucket(pos=(0,1), ('x',2))"
    ```

    **`_inject_bucket_refs_trampoline(clauses, base_globals)`** — Scans all clause bodies, finds call sites where the callee is locked and has `_index_plans`, converts the term-level argument to an AST expression via `term_to_ast_expr`, calls `_static_call_key`, and if a match is found injects the bucket function into `base_globals` and records the mapping in `_compile_context_local.bucket_ref_map` / `joint_bucket_ref_map`.

    **`_dispatch_call_trampoline` extension** — Before the locked dispatch check, consults `bucket_ref_map` and `joint_bucket_ref_map` (joint tried first, being more selective):

    ```python
    gkey = brmap.get((fname, arity, pos, key))
    if gkey is not None:
        return ast.Call(
            func=_name("StepGenerator"),
            args=[ast.Name(id=gkey, ctx=ast.Load()), _name(self_name)]
                + arg_exprs + [_name(trail_name)],
            keywords=[],
        )
    ```

    **Wiring** — `_inject_bucket_refs_trampoline` is called in `compile_predicate_trampoline` immediately after `_inject_resolved_targets`. The context maps are initialised before the `try` block and restored in `finally` (re-entrant, thread-safe via `threading.local`).

??? info "Testing"

    `tests/test_callsite_specialization.py` covers call-site specialisation in four test classes:

    **TestIndexPlansExposed / TestIndexPlansJoint**:

    - `_index_plans` is populated for indexed predicates (integer and atom keys)
    - Keys are ints (positions), values are dicts mapping index keys to callables
    - `_index_plans` is set to `{}` below the threshold or on recompilation to fewer clauses
    - `_index_plans_joint` is populated when joint dispatch is used; keys are `(pi, pj)` tuples, values are dicts of `(ki, kj)` tuples

    **TestStaticCallKey**:

    - Integer, string, float, bool, None constants → value itself
    - `ast.Name` (variable) → `None`
    - `ast.Call` with `ast.Name` func → `(id, n_args)` tuple
    - `ast.Call` with `ast.Attribute` func → `(attr, n_args)` tuple
    - `ast.List` → `None`

    **TestBucketKeyNaming**:

    - Atom, integer, second-position, compound-key variants
    - Joint key format; asymmetry between `(0,1)` and `(1,0)` orderings

    **TestInjectBucketRefs** and **TestCallsiteCorrectnessAndFallback**:

    - Bucket fn injected into `base_globals` for literal arg call
    - `bucket_ref_map` entry created with correct `(fname, arity, pos, key)` tuple
    - No injection for variable args, unlocked predicates, unknown keys
    - Injected fn is identical to `_index_plans[pos][key]`
    - Idempotent: second call does not replace an already-injected entry
    - Multiple literal calls in different clauses each get their own bucket ref
    - Dynamic predicates not specialised
    - Self-recursive unlocked predicates not specialised

---

*See also: [Architecture](architecture.md) — overall pipeline overview · [Compiler](compiler.md) — how predicates are compiled to Python generators · [Specialization](specialization.md) — call-site specialization via partial deduction.*
