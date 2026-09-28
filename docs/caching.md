# Clausal — Bytecode Caching

## Overview

when a `.clausal` file is imported, two expensive operations occur:

1. **Parsing and AST transformation** — the source is parsed into a Python AST and rewritten by `EmbedTransformer` (converting `head <- body` syntax, trailing-comma facts, logic variables, and functor declarations into valid Python code).

2. **Predicate compilation** — each predicate's clauses are compiled into dispatch functions via `compile_predicate`.

Both are addressed:
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
| `set_data(path, data)` | write `.pyc` file **atomically** (temp file in the same directory, then `os.replace`), creating `__pycache__/` if needed |
| `get_code(fullname)` | Inherited from `SourceLoader` — handles the full cache lookup/write cycle |

### Cache lifecycle

**First import:**
1. `get_code()` checks for a cached `.pyc` via `importlib.util.cache_from_source(path)`.
2. No cache exists → calls `source_to_code()` to parse, transform, and compile.
3. `set_data()` writes the bytecode to `__pycache__/<name>.cpython-<ver>.pyc`.
   The write is atomic, as CPython's own `.pyc` writes are: the bytes go to a
   uniquely named temp file beside the target, which `os.replace` swaps in, so
   several processes sharing one `__pycache__` never read a torn file. A failed
   write removes its temp file and is ignored (the import still succeeds).
4. Returns the code object.

**Subsequent imports (cache hit):**
1. `get_code()` finds the `.pyc` file.
2. Validates it against the source's mtime and size via `path_stats()`.
3. If valid, loads the bytecode directly — `source_to_code()` is never called.

The validation stamp is not the raw mtime: `path_stats()` XORs the source's
nanosecond mtime with a tag derived from a **content digest of the engine
sources that decide the emitted code** (plus a hand-maintained
`CLAUSAL_BYTECODE_TAG`). That set is every module whose content can change
emitted code: the compiler (`templating/`, `pythonic_ast/`,
`logic/compiler/`), the tables it reads at compile time
(`logic/exact_arith.py`, `modules/units.py`, `modules/countries/_data.py`,
`logic/generated_names.py`, `terms.py`),
and the `.pl` translator with its token spec (`tools/prolog_*.py`,
`tools/toklex/`); see `_COMPILATION_ROOTS`/`_COMPILATION_FILES` in
`clausal/import_hook.py`. Upgrading or editing the engine therefore invalidates
every cached `.clausal` bytecode automatically; there is nothing to clear by
hand.
4. Returns the cached code object.

**Source modification (cache invalidation):**
1. `get_code()` finds the `.pyc` file.
2. mtime or size has changed → discards the cache, calls `source_to_code()` fresh.
3. Writes a new `.pyc`.

### What is cached

The `.pyc` contains the bytecode for the **transformed module** — i.e., the output of `EmbedTransformer`. This means:
- `$define_predicate($Predicate(head=..., body=...), $module)` calls — one per clause, for `head <- body` rules and trailing-comma facts alike; the head and body are built from compiler node constructors (`$Call`, `$LoadName`, …)
- `$declare_head('foo', (...))` statements — one per predicate name, binding the module's predicate handle and recording its head's field names
- `$Var()` allocations (from logic variable names)

These calls still execute at import time (they assert clauses), but the parsing and AST transformation cost is eliminated.

### What is NOT cached

Predicate **compilation** (the `compile_predicate` step that produces dispatch functions) is not cached in the `.pyc`. It runs every import. This is because dispatch functions depend on runtime state (module globals, cross-predicate references) that cannot be serialized into bytecode.

A future enhancement could cache dispatch functions separately, but the current approach already eliminates the most expensive per-import cost.

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

With deferred compilation, `$define_predicate` only collects predicate nodes. After `exec()` completes, `compiler_v2.compile_module` asserts and compiles each predicate exactly once with the full clause set:

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:caching_phases"
```

Total: O(N) compilation work per predicate.

### Safety

Deferred compilation is safe because:
- No predicate of the file itself is queried during its load. A module-level goal-position `--goal` over a predicate defined in the same file therefore fails at load (the file's clauses are not compiled yet); put it inside a `def`, or query an imported predicate.
- [Directives](directives.md) (`-dynamic`, `-discontiguous`, `-table`) execute before clause definitions, so metadata like `db.is_dynamic()` is set correctly before compilation runs.
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

For programmatic loading of a file by path, use `clausal.testing.load_clausal_module(path)`.

---

??? info "Test coverage"

    `tests/test_pycache.py` covers:
    - `.pyc` file creation and correct path
    - Cache hit verification (`source_to_code` not called on second import)
    - Cache invalidation on source modification
    - Query correctness from cached bytecode (facts and rules)
    - Dynamic predicates remain unlocked after cached load
    - `sys.dont_write_bytecode` suppression
    - Atomic `.pyc` writes (temp file + `os.replace`; no stray temp file on failure)
    - Deferred compilation: `compile_predicate` called once per predicate, not once per clause

---

*See also: [Module System](import.md) — the import hook that drives caching · [Architecture](architecture.md) — where caching fits in the compilation pipeline.*
