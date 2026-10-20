# fix(A10-F002): EmbedTransformer.visit_Name breaks Store/Del-context logic-var-shaped names in embedded Python

**Problem.** `EmbedTransformer.visit_Name` (clausal/templating/term_rewriting.py:3624-3631)
rewrites EVERY logic-var-shaped Name in outer Python code to
`Attribute(value=<name>, attr="value", ctx=Load)` — regardless of the original
ctx. Any ordinary Python code in a `.clausal` file containing `MAX = 5`,
`_tmp = 5`, or `for I in …` (Store context) fails the whole module load with
`ValueError: expression must have Store context but has Load instead` — a
compile-layer error nowhere near the user's line.

**Repro/test.** test_10_rewriting_import.py::test_F002_allcaps_python_assignment_loads,
::test_F002_underscore_python_local_loads (xfail).

**Fix (recommended, per A10-D001 option (a)).**
```python
def visit_Name(transformer, name):
    if isinstance(name.ctx, Load) and _is_logic_var_name(name.id):
        return replace(Attribute(value=name, attr="value", ctx=load), name)
    return name
```
i.e. only unbox in Load context; leave Store/Del untouched. Audit other
`visit_*` on EmbedTransformer for the same ctx-blindness. If instead the
convention "logic-var names are reserved in embedded Python" is adopted
(A10-D001 option (c)), raise a SyntaxError naming the identifier and line.

**Design ref.** A10-D001 (parked).
