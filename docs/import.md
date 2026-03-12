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

`PredicateFinder.find_spec` searches for `<name>.clausal` files in `sys.path` (or the package's `__path__` for sub-packages). On a match it returns a `ModuleSpec` pointing to `PredicateLoader`.

### PredicateLoader.exec_module

1. **Inject builtins** — all `simple_ast` names (term constructors), plus `PredicateMeta`, `Var`, `Compound`, `Trail`, `unify`, `deref`, `walk`, and `$ast` are merged into the module's `__dict__`. This makes them available in clause bodies without explicit imports.

2. **Create LogicModule** — a `clausal.logic.database.Module` is created with `module_dict=module.__dict__`. It is stored as `$module` in the globals.

3. **Install per-module closures** — `$define_predicate` and `$assert_fact` are closures that capture the specific `LogicModule` and `module_dict` for this module. This is why they are set per-module rather than as shared globals.

4. **Parse and transform** — the source is parsed into a Python AST, then `EmbedTransformer` rewrites it:
   - `head <- body` statements → `$define_predicate(Predicate(head=…, body=…), $module)`
   - trailing-comma expression statements → `$assert_fact(term)`
   - logic variable names → `Var()` allocations
   - functor names → `try: name except NameError: class name(metaclass=PredicateMeta): _fields=(...)` declarations

5. **Execute** — the transformed AST is compiled and executed in the module's `__dict__`.

---

## `$define_predicate` — compiling a rule

Called once per `head <- body` clause as the module executes. Steps:

1. `logic_module.define_predicate(predicate_node)` — flattens the `And`-chain body, normalises fact heads (ground values → `Var + Is`), asserts the resulting `Clause` to the database, and registers the keyword signature.

2. Look up the predicate class from `module_dict` by functor name. If it is a `PredicateMeta` instance:
   - Replace `pred_cls._clauses[:]` with the DB's full clause list (the DB performs normalisation; pred_cls stays in sync).
   - Set `pred_cls._signature = pred_cls._fields` if not yet set.

3. Call `compile_predicate(functor, arity, clauses, db, globals_=module_dict, pred_cls=pred_cls)` — compile all current clauses for this predicate and install the dispatch function on both the PredicateMeta class and the Database entry.

The predicate is recompiled from scratch on every new clause during module load. This is efficient enough for load time and ensures the final dispatch function covers all clauses.

---

## `$assert_fact` — compiling a fact

Called once per trailing-comma fact statement. Steps are identical to `$define_predicate` except the head term is passed directly rather than wrapped in a `Predicate` node.

Fact normalization: ground values in functor field positions are replaced with fresh `Var` objects and corresponding `Is(var, value)` body goals. This enables output-mode queries — e.g., `fib(N, RESULT)` with both args unbound can enumerate facts rather than only checking them.

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
