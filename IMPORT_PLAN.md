# V3-1: Module System

## Context

Clausal `.clausal` files are currently self-contained — no file can import predicates from another. V3-1 adds `-import_from` and `-import_module` directives so `.clausal` files can share predicates with each other and with Python modules.

### Why Prolog modules suck (and how we dodge every pitfall)

| Prolog pain point | Clausal's advantage |
|---|---|
| **Meta-predicate context module confusion** (#1 complaint) | Predicates are `PredicateMeta` *classes* — concrete Python objects that carry their own `_get_dispatch()`. No "context module" resolution needed. |
| **Flat namespace** | Python packages give us hierarchical dotted paths for free. |
| **Operator scoping** | No user-defined operators. Non-issue. |
| **Export list maintenance** | No export lists. Follow Python convention: everything public unless `_`-prefixed. |
| **assert/retract module context** | Each `pred_cls` owns its `_clauses`. `assertz` on an imported class modifies *that class* directly. |
| **ISO standard fragmentation** | We use Python's `importlib` — one standard, universally implemented. |

**Core insight:** Since predicates are Python classes, cross-module import is *just Python import*. The directives translate directly to Python import statements in generated code.

---

## Design

### Directive syntax

```
-import_from(myapp.graphs.utils, [ShortestPath, Reachable])
-import_from(myapp.graphs.utils, [alias(Reachable, Reach)])
-import_module(myapp.graphs.utils)
```

### Generated Python code

`-import_from(mod, [Pred1, Pred2])` emits:
```python
from mod import Pred1, Pred2
```

`-import_from(mod, [alias(Orig, Local)])` emits:
```python
from mod import Orig as Local
```

`-import_module(mod)` emits:
```python
import mod
```

This piggybacks entirely on Python's import system. `PredicateFinder` already handles `.clausal` files. The imported `PredicateMeta` classes land in `module_dict`, where `_inject_call_targets` already picks them up.

### Qualified calls (`mod.Pred(X_)`)

After `-import_module(graphs)`, a clause body can use `graphs.Path(A_, B_)`.

**AST flow:**
1. Python parser produces `ast.Call(func=ast.Attribute(value=Name("graphs"), attr="Path"), ...)`
2. New `TermTransformer.visit_Attribute` produces `LoadAttr(object=LoadName("graphs"), attr="Path")`
3. So the goal becomes `Call(func=LoadAttr(...), args=[...])`
4. Compiler's `_collect_call_targets` recognizes `Call(func=LoadAttr(...))` and extracts `("graphs.Path", arity)`
5. `_inject_call_targets` resolves `"graphs.Path"` via `getattr(globals_["graphs"], "Path")` and stores the class into `base_globals["graphs.Path"]`
6. Compiled code emits `ast.Name(id="graphs.Path")` which Python looks up as the dict key `"graphs.Path"` in globals — no mangling needed

**No mangling:** Module globals are just a `dict[str, Any]`. Keys don't need to be valid Python identifiers — `"graphs.Path"` works fine as a dict key. The `ast.Name(id="graphs.Path")` node compiles to a `LOAD_GLOBAL "graphs.Path"` bytecode instruction, which does a dict lookup. The imported module object (`graphs`) also stays in globals under its own name, available to any inline Python code (`++()` escapes), but we document that overwriting it won't affect predicate dispatch since qualified predicates are resolved at compile time.

### Circular imports

Same strategy as Python — partial module objects. The deferred compilation model (V2-3) helps: all clauses are asserted before any compilation happens. If module A imports module B which imports module A, B sees A's partially-loaded module object (classes defined, dispatch not yet compiled). When B's predicates call A's predicates at runtime, A's dispatch is already compiled by then (lazy recompile covers any edge cases).

### Error handling

- Unknown module → Python's `ImportError` (natural, good error messages)
- Unknown predicate in import list → Python's `ImportError` from `from X import Y`
- Bad directive syntax → `SyntaxError` with clear message (same as existing directives)

---

## Implementation steps

### Step 1: `TermTransformer.visit_Attribute` (term_rewriting.py)

Add visitor so `ast.Attribute(value, attr)` → `LoadAttr(object=visit(value), attr=attr)` simple_ast node. Currently `ast.Attribute` falls through to `generic_visit`, which is wrong for qualified predicate calls.

### Step 2: `-import_from` directive handler (term_rewriting.py:~1758)

Add to `_handle_directive`:
```python
if name == "import_from":
    return transformer._handle_import_from_directive(args, expr_stmt)
```

`_handle_import_from_directive(args, expr_stmt)`:
- `args[0]` is the module path — an `ast.Attribute` chain or `ast.Name`. Extract dotted string.
- `args[1]` is `ast.List` of import names. Each element is either:
  - `ast.Name(id="Pred")` → plain import
  - `ast.Call(func=Name("alias"), args=[Name("Orig"), Name("Local")])` → aliased import
- Emit `ast.ImportFrom(module=dotted_str, names=[ast.alias(name=..., asname=...)])`.

Helper: `_dotted_name_from_ast(node)` — recursively extracts `"a.b.c"` from nested `ast.Attribute` nodes. Returns `None` if not a valid dotted path.

### Step 3: `-import_module` directive handler (term_rewriting.py:~1758)

Add to `_handle_directive`:
```python
if name == "import_module":
    return transformer._handle_import_module_directive(args, expr_stmt)
```

`_handle_import_module_directive(args, expr_stmt)`:
- `args[0]` is the module path (same Attribute-chain handling).
- Emit `ast.Import(names=[ast.alias(name=dotted_str)])`.

### Step 4: Compiler — qualified call target collection (compiler.py:~584)

Extend `_collect_call_targets` to also handle `Call(func=LoadAttr(...))`:
```python
if isinstance(term, Call) and isinstance(term.func, LoadAttr):
    dotted = _dotted_name(term.func)  # "graphs.Path"
    targets.add((dotted, len(term.args) + n_kwargs))
```

Helper: `_dotted_name(node)` — walks `LoadAttr` chain to produce `"a.b.c"`.

### Step 5: Compiler — qualified call target injection (compiler.py:~613)

Extend `_inject_call_targets` to resolve dotted names. Use the dotted string directly as the globals key — no mangling:
```python
if "." in target_name:
    parts = target_name.split(".")
    obj = globals_.get(parts[0])
    for part in parts[1:]:
        if obj is None: break
        obj = getattr(obj, part, None)
    if obj is not None and hasattr(obj, "_get_dispatch"):
        base_globals[target_name] = obj  # e.g. base_globals["graphs.Path"] = <class>
```

### Step 6: Compiler — qualified call code generation (compiler.py:~808)

In `term_to_ast_expr` and the goal compilation functions, handle `Call(func=LoadAttr(...))`:
- Flatten the `LoadAttr` chain to a dotted string (e.g. `"graphs.Path"`)
- Emit `ast.Name(id="graphs.Path")` — Python looks this up as a dict key in globals, finding the class injected in step 5

Anywhere the compiler does `_name(term.func.name)` for `LoadName`, add a parallel path for `LoadAttr` that does `_name(dotted_string)`. Same simple `_name()` call, just with dots in the string.

### Step 7: Update error message in `_handle_directive` (term_rewriting.py:~1772)

Add `import_from` and `import_module` to the known directives list in the error message.

### Step 8: Tests (tests/test_module_imports.py)

Create test file with fixtures:

**Fixtures:**
- `tests/fixtures/importable_utils.clausal` — defines `Helper(X_, Y_)`, `Double(X_, R_)`
- `tests/fixtures/imports_from.clausal` — uses `-import_from(tests.fixtures.importable_utils, [Helper])`
- `tests/fixtures/imports_module.clausal` — uses `-import_module(tests.fixtures.importable_utils)`
- `tests/fixtures/imports_alias.clausal` — uses `-import_from(tests.fixtures.importable_utils, [alias(Helper, H)])`

**Test cases:**
1. `-import_from` brings selective predicates into namespace
2. `-import_module` makes predicates accessible via qualified names
3. `alias(Name, LocalName)` works correctly
4. Dotted paths resolve through nested packages
5. Python module defining `make_predicate` classes is importable from `.clausal`
6. `.clausal` module is importable from Python (existing behaviour preserved)
7. Circular import between two `.clausal` files does not deadlock
8. Unknown module in `-import_from` raises `ImportError`
9. Unknown predicate name in import list raises `ImportError`
10. Imported predicate works with `assertz` (modifies the original class's clauses)
11. Imported predicate works with meta-predicates (FindAll, etc.)
12. Imported tabled predicate works correctly

---

## Files to modify

| File | Changes |
|---|---|
| `clausal/templating/term_rewriting.py` | `visit_Attribute`, `_handle_import_from_directive`, `_handle_import_module_directive`, `_dotted_name_from_ast` helper, update error message |
| `clausal/logic/compiler.py` | `_collect_call_targets` handles `LoadAttr`, `_inject_call_targets` resolves dotted names, `term_to_ast_expr` handles `LoadAttr` func, goal compilation handles qualified calls |
| `tests/test_module_imports.py` | New test file |
| `tests/fixtures/importable_utils.clausal` | New fixture |
| `tests/fixtures/imports_from.clausal` | New fixture |
| `tests/fixtures/imports_module.clausal` | New fixture |
| `tests/fixtures/imports_alias.clausal` | New fixture |

## Key functions to reuse

- `_handle_directive` dispatch (term_rewriting.py:1758) — add new cases
- `_parse_pred_arity_args` pattern (term_rewriting.py:1012) — similar arg parsing
- `_collect_call_targets` (compiler.py:584) — extend for LoadAttr
- `_inject_call_targets` (compiler.py:613) — extend for dotted resolution
- `term_to_ast_expr` (compiler.py:~808) — extend for LoadAttr func
- `replace()` (term_rewriting.py:13) — source position copying
- `node_ast()` — simple_ast node construction
- `_load_module()` helper from import_hook.py — for test module loading

## Verification

```bash
# Run existing tests first to ensure no regressions
python -m pytest tests/ -x -q

# Run new module import tests
python -m pytest tests/test_module_imports.py -v
```
