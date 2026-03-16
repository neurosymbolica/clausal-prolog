# Compiler Refactor: Pipeline Split

## Status: Part 1 complete, Part 2 in progress

Part 1 (pipeline split) is done and all 2571 tests pass through the new
pipeline. Part 2 (term expansion) has the engine wired in but needs end-to-end
tests with actual TermExpansion rules.

---

## What was done

### Pipeline split (V3-2)

The module loading pipeline is now split into two phases:

```
Phase A: Source --> EmbedTransformer --> module_items + Python AST bytecode
Phase B: compile_module(predicate_nodes, module_items, module_dict) --> compiled predicates
```

**New files:**
- `clausal/logic/compiler_v2.py` — `compile_module()` orchestrator
- `clausal/logic/term_expansion.py` — `run_term_expansion()` engine
- `tests/test_compiler_v2.py` — 15 equivalence tests
- `tests/test_term_expansion.py` — 8 tests (pass-through, detection, q())

**Modified files:**
- `clausal/pythonic_ast/nodes.py` — added `Directive`, `ImportFromDirective`,
  `ImportModuleDirective`, `ModuleDeclaration`, `PrivateDeclaration` node types
- `clausal/templating/term_rewriting.py` — `EmbedTransformer._module_items`
  accumulates directives/imports at AST transform time; `q()` quasi-quotation
  in `TermTransformer.visit_Call`
- `clausal/import_hook.py` — `_USE_V2_PIPELINE = True`, `_exec_module_v2`
  path alongside preserved v1 path

### How the v2 pipeline works

```
PredicateLoader.exec_module(module)
  |
  v
get_code(module_name)                    # Runs source_to_code → .pyc caching
  |  source_to_code stores transformer on self._last_transformer
  |  _module_items accumulated: DirectiveItem, ImportFromItem, etc.
  |
  v
exec(code, module_dict)                  # Bytecode creates functor classes
  |  $define_predicate = lambda pred, lm: predicate_nodes.append(pred)
  |  $assert_fact = lambda term: predicate_nodes.append(_fact_to_predicate_node(term))
  |  → collects runtime Predicate nodes (simple_ast) into predicate_nodes list
  |
  v
compile_module(predicate_nodes, module_items, module_dict, module_name)
  |  0. run_term_expansion(predicate_nodes, module_dict)  → returns unchanged if no TE
  |  1. _process_imports(module_items, module_dict)
  |  2. _process_directives(module_items, db)
  |  3. _process_declarations(module_items, module_dict)
  |  4. Assert all clauses via logic_module.define_predicate()
  |  5. compile_predicate_trampoline/shallow for each (functor, arity)
  |  6. Wrap tabled predicates with SLG wrapper
  |  7. Lock non-dynamic predicates
  |
  v
module_dict["$module"] = logic_module    # Ready for queries
```

### Design decisions made during implementation

1. **Bytecode still executed** — We still exec the Python AST bytecode to get
   functor class definitions (`_make_functor_class_ast`) and to collect runtime
   Predicate nodes. The v2 pipeline captures Predicate nodes via a
   `$define_predicate` closure that appends to a list instead of asserting.

2. **.pyc caching preserved** — V2 uses `get_code()` which triggers SourceLoader's
   `.pyc` caching. On cache hit, `source_to_code` doesn't run, so we re-parse
   just for `_module_items` (directives/imports only — lightweight).

3. **Node types not dicts** — Module items are proper `@node_class` instances
   (`DirectiveItem`, `ImportFromItem`, etc.) rather than plain dicts. This
   enables future unification-based matching.

4. **q() is identity** — `q(expr)` in TermTransformer simply calls `visit(expr)`.
   It's syntactic documentation that says "this produces a simple_ast constructor",
   not a separate code path. Variables are shared via the same `seen_vars`.

---

## What remains

### Term expansion end-to-end tests

The expansion engine (`term_expansion.py`) is wired in and has the zero-overhead
pass-through tested. What's missing:

- [ ] Test that a TermExpansion rule actually rewrites a clause
- [ ] Test one-to-many expansion (single clause → multiple clauses)
- [ ] Test clause suppression (expansion returns `"none"`)
- [ ] Test module state accumulation (init/final injection)
- [ ] Test that TermExpansion clauses are NOT themselves expanded
- [ ] Test with `q()` in expansion patterns
- [ ] `.clausal` fixture file that uses TermExpansion
- [ ] Test imported expansion rules via `-import_from`

### Potential future work

- **Remove v1 path** — Once confident, delete `_exec_module_v1` and the
  `_USE_V2_PIPELINE` flag
- **Cache module_items** — Currently re-parsed on .pyc cache hit. Could serialize
  `_module_items` alongside the bytecode cache for true zero-overhead cached loads
- **Self-hosting compiler** — Write code generation rules in Clausal consuming
  simple_ast → producing Python AST. Bootstrap with current `compiler.py`.

---

## Verification

```
$ python -m pytest tests/ -q
2571 passed in 14s

$ python -m pytest tests/test_compiler_v2.py -q
15 passed

$ python -m pytest tests/test_term_expansion.py -q
8 passed
```

All existing 2548 tests continue to pass through the new v2 pipeline.
