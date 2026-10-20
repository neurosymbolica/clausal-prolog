# fix-A05: dif/2 constraint dropped for vars inside DictTerm/Seg*/Quantity (A05-F001)

**Severity: correctness (high).** `_collect_free_vars` — both the Python
version (`clausal/logic/constraints.py:152-182`) and the C version
(`clausal/logic/_constraints_dif.c:68-153`, `collect_walk`) — walks only
Var / tuple / list / Compound / term-instances. But dif's sandbox
`_structural_unify_oc` falls through to the *full* unifier, which binds
through any `__unify__`-hooked container (`DictTerm`, `SegList`,
`SegString`, `Quantity`). So for those argument types dif concludes
"could become equal" (pending), then attaches the pair to **zero**
variables — the constraint is silently discarded and the terms may later
become equal without failure.

```python
A = Var(); t = Trail()
dif(DictTerm({"k": A}), DictTerm({"k": 1}), t)  # True (pending)
get_attr(A, "dif")                              # None — nothing attached!
unify(A, 1, t)                                  # True — dif violated silently
```

Language-level: `D is not {"k": 1}, D is {"k": V}, V is 1` succeeds.

`SetTerm` is exempt (the unifier refuses var-element set unification, so
immediate-True is consistent).

## Fix

Add arms to BOTH collectors, keeping them in lockstep with what
`unify()` can bind through:

- `DictTerm` → walk `t.data.values()` (keys too if var keys are legal);
- `SegList` / `SegString` / `SegBytes` → walk each segment
  (`ConcreteSeg.items`, `VarSeg.var`) — or, more robustly, honour a
  `__walk__`/`__collect_vars__` protocol so new container types can't
  reintroduce the blind spot (see A01-F008's two-walkers seam note:
  `_variables.c` already has a `_collect_vars_impl` with *different*
  blind spots — consider unifying them);
- `Quantity` → walk `.value`;
- plain `dict` values for symmetry with DictTerm handling elsewhere.

The same blind-spot list should be checked in `_dif_hook`'s re-attach
path (it calls the same collector, so the fix covers it).

## Verify

Flip `TestF001DifContainerBlindSpots` xfails
(tests/audit_2026_07_05/test_05_constraints_core.py) to plain asserts;
controls and the Python↔C parity test must stay green.
