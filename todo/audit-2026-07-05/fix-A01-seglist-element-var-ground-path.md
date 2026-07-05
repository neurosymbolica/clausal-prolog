# fix-A01: SegList "ground" unify path drops element Vars (A01-F006)

**Severity: correctness.** `SegList.__unify__` (`terms.py:404-415`): when
`__walk__()` returns a plain list the code treats the SegList as "fully
ground" and compares with `==`. But `__walk__` returns a plain list whenever
no unbound **VarSeg** remains — ConcreteSeg **element** Vars stay in the
list. `Var == 1` is identity-False, so satisfiable unifications fail:

```python
A, E = Var(), Var()
sl = SegList([VarSeg(A), ConcreteSeg([E])])   # the [*A, E] pattern
unify(A, [1], t)
unify(sl, [1, 2], t)    # False — should be True with E=2
```

`SegList.is_ground()` (`terms.py:340-344`) has the same mislabel (True with
unbound element Vars) — cross-ref prior art F083, which flagged the sibling
VarSeg-level `ground/1` issue.

## Fix

In the `isinstance(walked, (list, str))` branch of `__unify__`, delegate to
real unification instead of `==`:

```python
from .logic.variables import unify as _unify
if isinstance(walked, str):
    walked = list(walked)
if isinstance(other, str):
    other = list(other)
return _unify(walked, other, trail)
```

(C list↔list unification is element-wise and Var-aware; it also restores the
trail on failure.) For `is_ground()`, either use the C `_is_ground` on the
walked result or document that it means "no unbound VarSeg holes" and rename
callers' expectations — the former is the honest fix.

## Verify

Flip the three `TestF006SegListElementVarGroundPath` xfails; the
unbound-VarSeg control must stay green.
