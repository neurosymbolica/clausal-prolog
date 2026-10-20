# fix-A01: SegList.__unify__ has no bytes-target arm (A01-F007)

**Severity: correctness (mode-incompleteness).** `SegList.__unify__`
(`terms.py:404`) accepts `list` and `str` targets only. Under the codes
model the C layer unifies plain int-lists with `bytes`
(`unify([71,B], b"GE")` binds `B=69`), and `SegBytes.__unify__` accepts
`list` targets — but a SegList of codes vs `bytes` silently fails:

```python
A = Var()
unify(SegList([ConcreteSeg([71]), VarSeg(A)]), b"GET", t)   # False
# expected True with A = [69, 84] (VarSegs of a SegList bind to lists)
```

This is the exact mirror of prior-art F023 (SegString vs list), which was
fixed by converting and delegating.

## Fix

Add a `bytes` arm to `SegList.__unify__` that converts the target to its
code list and reuses the existing list path:

```python
if isinstance(other, bytes):
    return self.__unify__(list(other), trail)
```

(`list(b"GET") == [71, 69, 84]`.) Note `_seg_unify_cache_key` already
handles `bytes` keys defensively (`terms.py:226-227`), so the generator
cache works unchanged; going through `list(other)` keys on the tupled codes,
which is consistent for retry drives since the conversion is deterministic.

## Verify

Flip `TestF007SegListVsBytes::test_seglist_of_codes_unifies_with_bytes`;
controls stay green.
