# fix(A10-F016): pythonic_ast traversal gaps, dead REMOVED sentinel, __all__ holes

Three related hygiene bugs in `clausal/pythonic_ast/` (latent — no in-tree
consumer is currently bitten, but any new transform pass will be):

1. **Traversal gaps.** `ElementsLiteral` (base of ListLiteral / TupleLiteral /
   SetLiteral, nodes.py:268-271) and `Yield` (:855-860) are plain `@dataclass`
   — they inherit Node's no-op `visit_children`/`transform_children`, so their
   child nodes are silently skipped by generic walkers (goal_expansion works
   around TupleLiteral explicitly). Fix: decorate with `@node_class` (elements
   is `list[Node]` → node_list; Yield's `Optional[Node]` → optional_node) or
   hand-write the two methods.
2. **REMOVED sentinel is dead.** `nodes.REMOVED` is exported (also re-exported
   by `clausal/pythonic_terms.py`) and `_transform_node_list`'s docstring says
   "Node items that are REMOVED are removed" — but the code appends the
   sentinel object instead of filtering it. Fix: `if transformed_node is
   REMOVED: changed = True; continue` (both loops), or delete the sentinel and
   the docstring claim (empty-list splice already covers removal).
3. **`__all__` holes.** `SpecializeDirective`, `EdcgAccDecl`, `EdcgPassDecl`,
   `EdcgPredDecl` are missing from `nodes.__all__` — so they are absent from
   the injected predicate builtins and `import *` surfaces. Sibling of
   fix-A01-terms-all-exports.md.

**Repro/tests.** test_10_rewriting_import.py::test_F016_list_literal_transform_children,
::test_F016_removed_sentinel_honored, ::test_F016_all_exports_module_items (xfail);
::test_F016_guard_yield_dataclass_traversal_documented pins current behavior.
