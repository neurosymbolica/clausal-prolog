# Extract shared _pure() helper

`_pure()` is duplicated in 4 files, each with slightly different behaviour:

- `clausal/modules/py/torch.py` — has `_deep_deref()`, most complete
- `clausal/modules/py/torch_distributions.py` — imports `_deep_deref` from torch.py
- `clausal/modules/py/scipy_spatial.py` — no `_deep_deref`, original version
- `clausal/modules/py/scipy_sparse.py` — no `_deep_deref`, original version

Other duplicated helpers: `_pred()`, `_property_2()`, `_bidir_2()`,
`_fact_table_2()`, `_check_1()`.

## Problem

Bug fixes don't propagate. The `_deep_deref` fix (Phase 1) and the
`DictTerm` fix (Phase 9) only landed in torch.py. The scipy copies
are still vulnerable.

## Fix

Extract into a shared module, e.g. `clausal/modules/py/_helpers.py`:
- `_pure(fn)` — with `_deep_deref`
- `_deep_deref(val)` — handles list, dict, DictTerm
- `_pred(name, *arity_fns)` — ModulePredicate factory
- `_property_2(getter)` — multi-mode property dispatch
- `_bidir_2(forward_fn, backward_fn)` — bijective dispatch
- `_fact_table_2(build_fn)` — lazy nondeterministic fact table
- `_check_1(fn)` — boolean check predicate

Then each wrapper imports from `_helpers` instead of defining its own.

## Priority

Medium — more wrappers means more copies. Fix before adding new
library wrappers to avoid further divergence.
