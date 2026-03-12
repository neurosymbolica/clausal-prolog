# Clausal — Module System and Import Hook

## Overview

Clausal predicate files use the `.clausal` extension. Importing one with a normal Python `import` statement is enough to load and compile all predicates in that file. The `clausal.import_hook` module installs a `sys.meta_path` finder that intercepts these imports before Python's standard machinery runs.

```python
import clausal  # installs the import hook as a side effect

from fibonacci import fib         # loads fibonacci.clausal
from edge_graph import edge, reach
```

After the import:
- `fib` is a `PredicateMeta` class with all clauses compiled and dispatch installed
- `fib(7)` creates a term; `fib._get_dispatch()` returns the compiled search function
- `from fibonacci import fib` in another module brings both the term constructor and dispatch together — no separate wiring step needed

On the first import, the source is parsed, AST-transformed, and compiled to Python bytecode. The bytecode is cached in `__pycache__/` as a `.pyc` file. Subsequent imports of the same file load the cached bytecode directly, skipping parsing and transformation entirely. See [caching.md](caching.md) for details.

---

## The two module objects

Every `.clausal` file has **two** associated objects, both stored in the module's globals dict:

| Name | Type | Role |
|---|---|---|
| Python module (`sys.modules[name]`) | `types.ModuleType` | Standard Python module; holds predicate classes and anything else defined in the file |
| `$module` | `clausal.logic.database.Module` | Logic module; holds the `Database` (clause store) and a reference to the Python module's `__dict__` |

The `$` prefix makes `$module` inaccessible as a normal Python identifier — it is injected by the import hook and used only by generated code (`$define_predicate`, `$assert_fact`).

### Module vs Database

`Module` wraps a `Database`. The `Database` stores:
- `_clauses: dict[(functor, arity), list[Clause]]` — raw clauses (used as the authoritative normalization source)
- `_signatures: dict[(functor, arity), tuple[str,...]]` — keyword parameter name lists
- `_dispatch: dict[(functor, arity), Callable|None]` — compiled dispatch functions (kept in sync with PredicateMeta classes)

The `Module` also holds `module_dict: dict | None` — a reference to the Python module's `__dict__`. This is used by the compiler for cross-predicate name resolution and by runtime builtins like `assertz`.

---

## Import hook mechanics

### PredicateFinder

`PredicateFinder.find_spec` searches for `<name>.clausal` files in `sys.path` (or the package's `__path__` for sub-packages). On a match it creates a per-file `PredicateLoader(fullname, path)` instance and returns a `ModuleSpec` pointing to it.

### PredicateLoader (SourceLoader subclass)

`PredicateLoader` extends `importlib.abc.SourceLoader`, which provides automatic `.pyc` caching via the `get_code()` method. The key override is `source_to_code(data, path)`, which performs the AST transformation step — parsing the `.clausal` source and running `EmbedTransformer`. The resulting bytecode is what gets cached.

### PredicateLoader.exec_module

1. **Inject builtins** — all `simple_ast` names (term constructors), plus `PredicateMeta`, `Var`, `Compound`, `Trail`, `unify`, `deref`, `walk`, and `$ast` are merged into the module's `__dict__`. This makes them available in clause bodies without explicit imports.

2. **Create LogicModule** — a `clausal.logic.database.Module` is created with `module_dict=module.__dict__`. It is stored as `$module` in the globals.

3. **Install per-module closures** — `$define_predicate` and `$assert_fact` are deferred closures that assert clauses to the database and sync them to the PredicateMeta class, but do **not** compile. They record each predicate's `(functor, arity)` in a pending dict for later compilation.

4. **Load bytecode** — `self.get_code(module.__name__)` either loads the cached `.pyc` or calls `source_to_code()` to parse and transform fresh source. The `SourceLoader` protocol handles cache validation automatically (comparing mtime and size).

5. **Execute** — the bytecode is executed in the module's `__dict__`. Each `$define_predicate` / `$assert_fact` call asserts clauses but defers compilation.

6. **Compile all pending predicates** — `_compile_all_pending(pending, db, module_dict)` iterates the pending dict and calls `compile_predicate` once per predicate. This is O(N) per predicate (one compilation with all N clauses) instead of the O(N²) that would result from recompiling after every single clause assertion. In a second pass, predicates marked with `-table(pred/arity)` are wrapped with `make_tabled_wrapper_trampoline`. The two-pass approach ensures cross-predicate references resolve before wrapping. See [tabling.md](tabling.md).

7. **Lock non-dynamic predicates** — iterate module globals and lock every `PredicateMeta` class that was not declared with `-dynamic(pred/arity)`.

---

## `$define_predicate` — asserting a rule (deferred)

Called once per `head <- body` clause as the module executes. Steps:

1. `logic_module.define_predicate(predicate_node)` — flattens the `And`-chain body, normalises fact heads (ground values → `Var + Is`), asserts the resulting `Clause` to the database, and registers the keyword signature.

2. Look up the predicate class from `module_dict` by functor name. If it is a `PredicateMeta` instance:
   - Replace `pred_cls._clauses[:]` with the DB's full clause list (the DB performs normalisation; pred_cls stays in sync).
   - Set `pred_cls._signature = pred_cls._fields` if not yet set.

3. Record `(functor, arity) → pred_cls` in the pending dict. Compilation is deferred until all clauses have been asserted.

---

## `$assert_fact` — asserting a fact (deferred)

Called once per trailing-comma fact statement. Steps are identical to `$define_predicate` except the head term is passed directly rather than wrapped in a `Predicate` node. Compilation is equally deferred.

Fact normalization: ground values in functor field positions are replaced with fresh `Var` objects and corresponding `Is(var, value)` body goals. This enables output-mode queries — e.g., `fib(N, RESULT)` with both args unbound can enumerate facts rather than only checking them.

---

## Deferred compilation

Prior to V2-3, each `$define_predicate` / `$assert_fact` call immediately recompiled the predicate with all accumulated clauses. For a predicate with N clauses, this meant N compilations — O(N²) work.

With deferred compilation, assertions and compilation are separated:
- During `exec()`, each `$define_predicate` / `$assert_fact` only asserts the clause and records the predicate in a pending dict.
- After `exec()` completes, `_compile_all_pending()` compiles each predicate exactly once with the full clause set.

This is safe because no predicate is queried during module load — `.clausal` files only contain definitions. Directives (`-dynamic`, etc.) execute before clause definitions, so `db.is_dynamic()` is already set when compilation runs.

---

## Cross-module predicate calls

A clause in `edge_graph.clausal` that calls `reach(X, Y)` from `fibonacci.clausal` (hypothetically) works because:

1. `from fibonacci import fib` brings the `fib` PredicateMeta class into `edge_graph`'s module globals.
2. When the compiler processes `edge_graph.clausal`, it finds `fib` in `module_dict` and injects the class into the compiled function's `__globals__`.
3. The compiled call `for _ in fib._get_dispatch()(args, trail, k):` resolves `fib` by name at call time.

No separate wiring, no module-qualified call syntax, no `use_module` directive. Python `import` is the entire module system.

---

## Builtin injection

The following names are injected into every predicate module's namespace by the import hook:

**Simple AST constructors**: all names from `clausal.pythonic_ast.__all__` — `LoadName`, `Call`, `Compound`, `IntLiteral`, `Is`, `And`, `Or`, `Not`, etc.

**Runtime types**: `PredicateMeta`, `Var`, `Compound`, `Trail`, `unify`, `deref`, `walk` — needed by generated functor class code (`__call__` uses `Var()`) and by compiled predicate bodies.

**Hidden globals** (inaccessible as normal identifiers):
- `$module` — the `LogicModule` for this file
- `$define_predicate` — per-module closure for `head <- body` clauses
- `$assert_fact` — per-module closure for fact statements
- `$ast` — the Python `ast` standard library module

---

## IPython integration

`clausal.import_hook.enable_ipython(globals())` installs the `EmbedTransformer` as an IPython AST transformer and injects the same builtin set into the IPython namespace. This lets you write `.clausal` syntax in IPython cells interactively. Per-module LogicModules are not used in IPython; the session shares a single namespace.

---

## File discovery

`PredicateFinder` searches for `<modulename>.clausal` in:
- `sys.path` for top-level module names
- the parent package's `__path__` for sub-modules

The `.clausal` extension is the sole distinguishing criterion. Files with this extension are always handled by the import hook; standard `.py` files are unaffected.

---

## Loading `.clausal` files programmatically

For tests and external callers, `_load_module(fullname, path)` is the recommended way to load a `.clausal` file without relying on `sys.path` discovery:

```python
from clausal.import_hook import _load_module

mod = _load_module("my_predicates", "/path/to/my_predicates.clausal")
logic_module = mod.__dict__["$module"]
```

Each call creates a fresh `PredicateLoader` and module instance. Any previously cached `sys.modules` entry for the name is evicted first. This is the standard pattern used by all test helpers in the test suite.
