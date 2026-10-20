# fix-A01: Seg* __getitem__ rejects in-prefix slices (A01-F010)

**Severity: design/completeness (low).** Non-ground Seg* `__getitem__`
serves int indices that land inside the knowable concrete prefix but raises
`PartialTermError` for *slices* that lie entirely inside the same prefix:

```python
ss = SegString(["abc", VarSeg(B)])
ss[1]     # 'b' — served
ss[0:2]   # PartialTermError — but "ab" is fully knowable
```

Sites: `SegString.__getitem__` (`terms.py:993-1009`),
`SegList.__getitem__` (`terms.py:515-546`), `SegBytes.__getitem__`
(`terms.py:1275-1291`) — each checks `isinstance(index, int)` only.

## Fix

Before raising, handle non-negative-bounded slices whose `stop` is within
the collected prefix (`start >= 0`, `stop is not None`, `0 <= stop <=
len(prefix)`, `step` forward): return `prefix[index]` (str/list/bytes typed
per container). Negative or open-ended slices still depend on the VarSeg and
must keep raising.

## Verify

Flip `TestF010SliceWithinPrefix::test_segstring_slice_in_prefix`; the
int-index control (in-prefix serves, beyond-prefix raises) stays green. Add
the SegList/SegBytes analogues when fixing.
