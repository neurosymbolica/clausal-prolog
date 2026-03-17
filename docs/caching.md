# Clausal — Bytecode Caching (V2-3)

## Overview

When a `.clausal` file is imported, two expensive operations occur:

1. **Parsing and AST transformation** — the source is parsed into a Python AST and rewritten by `EmbedTransformer` (converting `head <- body` syntax, trailing-comma facts, logic variables, and functor declarations into valid Python code).

2. **Predicate compilation** — each predicate's clauses are compiled into dispatch functions via `compile_predicate`.

V2-3 addresses both:
- **`.pyc` caching** eliminates step 1 on subsequent imports by caching the transformed bytecode.
- **Deferred compilation** reduces step 2 from O(N^2) to O(N) per predicate by compiling once after all clauses are asserted, rather than recompiling after each clause.

---

## `.pyc` caching via SourceLoader

`PredicateLoader` extends `importlib.abc.SourceLoader`, which provides Python's standard bytecode caching mechanism. The key methods:

| Method | Role |
|---|---|
| `source_to_code(data, path)` | Parse source + `EmbedTransformer` + `compile()` — the cached transform |
| `get_data(path)` | Read file bytes (source or `.pyc`) |
| `path_stats(path)` | Return `{'mtime': ..., 'size': ...}` for cache validation |
| `set_data(path, data)` | Write `.pyc` file, creating `__pycache__/` if needed |
| `get_code(fullname)` | Inherited from `SourceLoader` — handles the full cache lookup/write cycle |

### Cache lifecycle

**First import:**
1. `get_code()` checks for a cached `.pyc` via `importlib.util.cache_from_source(path)`.
2. No cache exists → calls `source_to_code()` to parse, transform, and compile.
3. `set_data()` writes the bytecode to `__pycache__/<name>.cpython-<ver>.pyc`.
4. Returns the code object.

**Subsequent imports (cache hit):**
1. `get_code()` finds the `.pyc` file.
2. Validates it against the source's mtime and size via `path_stats()`.
3. If valid, loads the bytecode directly — `source_to_code()` is never called.
4. Returns the cached code object.

**Source modification (cache invalidation):**
1. `get_code()` finds the `.pyc` file.
2. mtime or size has changed → discards the cache, calls `source_to_code()` fresh.
3. Writes a new `.pyc`.

### What is cached

The `.pyc` contains the bytecode for the **transformed module** — i.e., the output of `EmbedTransformer`. This means:
- `$define_predicate(Predicate(head=..., body=...), $module)` calls (from `head <- body` rules)
- `$assert_fact(term)` calls (from trailing-comma facts)
- `class foo(metaclass=PredicateMeta): _fields = (...)` declarations (from functor auto-generation)
- `Var()` allocations (from logic variable names)

These calls still execute at import time (they assert clauses), but the parsing and AST transformation cost is eliminated.

### What is NOT cached

Predicate **compilation** (the `compile_predicate` step that produces dispatch functions) is not cached in the `.pyc`. It runs every import. This is because dispatch functions depend on runtime state (module globals, cross-predicate references) that cannot be serialized into bytecode.

A future V2-3b could cache dispatch functions separately, but the current approach already eliminates the most expensive per-import cost.

---

## Deferred compilation

### The N^2 problem

Previously, each `$define_predicate` call immediately compiled the predicate with all accumulated clauses. For a predicate with N clauses:
- After clause 1: compile 1 clause
- After clause 2: compile 2 clauses
- ...
- After clause N: compile N clauses
- Total: 1 + 2 + ... + N = O(N^2) compilation work

### The fix

With deferred compilation, `$define_predicate` and `$assert_fact` only assert clauses and record the predicate key in a `pending` dict. After `exec()` completes, `_compile_all_pending()` compiles each predicate exactly once with the full clause set:

```
exec() phase:     assert clause 1, assert clause 2, ..., assert clause N
compile phase:    compile_predicate(all N clauses)  ← once
```

Total: O(N) compilation work per predicate.

### Safety

Deferred compilation is safe because:
- No predicate is queried during module load — `.clausal` files only contain definitions.
- Directives (`-dynamic`, `-discontiguous`, `-table`) execute before clause definitions, so metadata like `db.is_dynamic()` is set correctly before compilation runs.
- Cross-predicate references are resolved via `module_dict` globals, which are fully populated after `exec()`.

---

## Suppressing cache writes

Setting `sys.dont_write_bytecode = True` before import prevents `.pyc` files from being written. The module still loads correctly — it just won't benefit from caching on subsequent imports.

```python
import sys
sys.dont_write_bytecode = True

import clausal
from my_predicates import foo  # works, but no .pyc written
```

---

## Per-module loader instances

Each `.clausal` file gets its own `PredicateLoader(fullname, path)` instance, created by `PredicateFinder.find_spec()`. There is no shared global loader singleton. This ensures each module's path and caching state are independent.

The old `_predicate_loader` global is set to `None` for backward compatibility detection. New code should use `_load_module(fullname, path)` for programmatic loading.

---

??? info "Test coverage"

    `tests/test_pycache.py` covers:
    - `.pyc` file creation and correct path
    - Cache hit verification (`source_to_code` not called on second import)
    - Cache invalidation on source modification
    - Query correctness from cached bytecode (facts and rules)
    - Dynamic predicates remain unlocked after cached load
    - `sys.dont_write_bytecode` suppression
    - Deferred compilation: `compile_predicate` called once per predicate, not once per clause
