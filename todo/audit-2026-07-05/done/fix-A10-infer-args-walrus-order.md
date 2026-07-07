# fix(A10-F015): codegen._infer_args visits walrus target before value

**Problem.** `clausal/codegen.py` `_Scanner` has no `visit_NamedExpr`;
`ast.NamedExpr._fields = (target, value)` so generic traversal marks the
target assigned BEFORE scanning the value. `y = (x := x + 1)` therefore fails
to infer `x` as a parameter even though it is loaded before assignment.
Assign/AnnAssign/AugAssign/For all have explicit value-first ordering — the
walrus is the one omission.

**Repro/test.** test_10_rewriting_import.py::test_F015_infer_args_walrus_load_before_store
(xfail); guard ::test_F015_guard_infer_args_basics.

**Fix.**
```python
def visit_NamedExpr(self, node):
    self.visit(node.value)
    self.visit(node.target)
```
