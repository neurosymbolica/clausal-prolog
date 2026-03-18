# Clausal — Predicate Indexing

## Problem

Without indexing, every query against a predicate tries all clauses sequentially. For a predicate with N fact clauses, a ground lookup costs O(N) — each clause's `match` block is entered and compared. This is acceptable for small predicates but becomes a bottleneck for large fact tables (100+ clauses).

```
color("red",   [255,   0,   0]),
color("green", [  0, 128,   0]),
color("blue",  [  0,   0, 255]),
...  # 200 more colors
```

Querying `color("blue", X_)` without indexing tries all 203 match blocks. With first-argument indexing, it jumps directly to the one clause whose first argument is `"blue"`.

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
    | Unbound Var (no body unification) | `_INDEX_VAR` sentinel | Default bucket |
    | List, term instance, or other non-scalar | `_INDEX_VAR` sentinel | Default bucket |

    The Var+Unify pattern comes from fact normalization (`_normalize_dataclass_fact` / `_normalize_fact_clause`), which replaces ground head values with fresh Vars and adds `Unify(var, value)` goals to the body. This is the standard representation for facts in clausal — the indexer recognises it and extracts the original ground value.

    ### Bucket merging

    A critical correctness requirement: **clause ordering must be preserved.** In Prolog and clausal, clause order determines solution order. Consider:

    ```
    f(1, "a"),          # clause 0, key=1
    f(X_, "b"),         # clause 1, default
    f(2, "c"),          # clause 2, key=2
    f(3, "d"),          # clause 3, key=3
    f(X_, "e"),         # clause 4, default
    ```

    When querying `f(1, Y_)`, the expected solution order is `"a"`, `"b"`, `"e"` — clause 0 (matches key=1), clause 1 (default, matches anything), clause 4 (default, matches anything). Clause 2 and 3 are skipped because their first arg doesn't match 1.

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

    - `Compound(functor, args)` — `args[0]`
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

    ### Bucket head lifting (Phase 8)

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

    The **fallback function** (called for unbound first arguments) always uses the original, unlifted clauses — so output-mode queries (`color(Name_, "warm")`) remain fully correct. Only bucket functions are affected.

    ### Lazy recompile integration

    No changes to the Database or PredicateMeta invalidation mechanism were needed. When `assertz` or `retract` invalidates a predicate's dispatch function, the lazy recompile closure calls `compile_predicate` (or `compile_predicate_trampoline`) from scratch. Since the compilation functions now build an index automatically when beneficial, the recompiled dispatch function gets a fresh index reflecting the updated clause list.

    ---

## What is NOT indexed

The current implementation indexes only scalar values. These are not indexed (they go to the default bucket):

- **Lists** — including empty lists. List first-args could be indexed by structure (empty vs cons), but this is deferred.
- **Term instances** (PredicateMeta classes, Compound) — could be indexed by type/functor, but requires a two-level dict (value dict + type dict) to avoid collisions between a type used as a literal value and a type used as an index key.
- **Nested structures** — only the top-level value is checked; no deep indexing.

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

```
color("red", Temp_)      # first arg ground  → first-arg index handles this
color(Name_, "warm")     # second arg ground → first-arg index can't help
color(Name_, Temp_)      # neither ground    → full scan either way
```

With groundness-keyed dispatch, querying `color(Name_, "warm")` uses a second-argument index and jumps directly to the clauses whose second arg is `"warm"`, skipping all others.

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

    `_extract_arg_key(clause, pos, arity)` generalises `_extract_first_arg_key` to work on any argument position. The same classification rules apply:

    | Arg at position `pos` | Key | Bucket |
    |---|---|---|
    | Scalar (int, str, float, bytes, bool, None) | The value | Specific |
    | Var with `Unify(var, scalar)` in body | The scalar | Specific |
    | Unbound Var, list, term instance | `_INDEX_VAR` | Default |

    The Var identity check (`goal.left is arg`) ensures we match the correct Var when multiple positions have Var+Unify patterns — each position's Var object is distinct.

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

```
color("red",    "warm"),
color("blue",   "cool"),
color("green",  "cool"),
color("yellow", "warm"),
color("white",  "neutral"),
```

Analysis finds both positions indexable:

- **Position 0**: 5 distinct keys (red, blue, green, yellow, white) — most selective
- **Position 1**: 3 distinct keys (warm, cool, neutral) — less selective

Plans sorted by selectivity: position 0 first, then position 1.

| Query | Selector path | Clauses tried |
|---|---|---|
| `color("blue", X_)` | arg0 ground → pos-0 index → bucket["blue"] | 1 |
| `color(X_, "cool")` | arg0 Var → skip; arg1 ground → pos-1 index → bucket["cool"] | 2 |
| `color("red", "warm")` | arg0 ground → pos-0 index → bucket["red"] | 1 |
| `color(X_, Y_)` | arg0 Var → skip; arg1 Var → skip; fallback | 5 |

## Interaction with first-argument indexing

Groundness-keyed dispatch fully subsumes first-argument indexing. The `compile_predicate` and `compile_predicate_trampoline` functions use `_analyze_index_positions` instead of `_build_first_arg_index`. When only position 0 is indexable, the result is behaviourally identical to first-argument indexing.

The first-arg index functions (`_extract_first_arg_key`, `_build_first_arg_index`, `_make_indexed_dispatch_simple`, `_make_indexed_dispatch_trampoline`) are retained as thin wrappers or standalone utilities for backward compatibility with tests that reference them directly.

## Interaction with dynamic predicates

No changes to the invalidation mechanism. When `assertz` or `retract` modifies a predicate, the lazy recompile closure calls `compile_predicate` from scratch. The fresh compilation analyses all positions and builds new indexes reflecting the updated clause list.

## Limitations

- **Indexed types**: only scalar types are indexed. Lists, term instances, and compound structures go to the default bucket at every position.
- **No cross-position indexing**: positions are checked independently. There is no combined multi-key hash table (e.g., indexing on `(arg0, arg1)` jointly). The selector picks the single best position, not a combination.
- **Compilation cost**: each indexable position produces its own set of sub-functions (buckets + default). For a predicate with `P` indexable positions and `K` average distinct keys, compilation produces roughly `P * K` sub-functions. This is acceptable because indexing only kicks in at 4+ clauses and the sub-functions are small.

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
