# fix-A07: bool_labeling/1 accepts non-Boolean ground elements silently

**Finding:** A07-F009.
**Severity:** error-path.

`clausal/logic/clpb.py:631-672`: `_label_bools` looks for the first unbound
var; if all elements are bound it yields a solution WITHOUT validating that
the bound values are 0/1. `bool_labeling([2, "a"], trail)` yields one
solution. SWI clpb raises `type_error(sat, 2)`-style errors; Clausal should
raise TypeError (matching `label_sat`'s behaviour in clpsat.py:519-522) or
fail. Also handle the scalar coercion arm (`vars_ = [vars_list]`) the same
way.

**Test:** `test_A07_F009_bool_labeling_validates_ground_elements`
(xfail strict=False; passes if either TypeError/ValueError is raised or zero
solutions are yielded).
