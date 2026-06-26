# reverse/2 is forward-only (not bidirectional)

**Found 2026-06-26** during the input/output mode-coverage audit
(`todo/audit-tests-input-output-mode-coverage.md`).

## Symptom

`reverse(List, Rev)` only works when `List` (the first arg) is a ground/usable
sequence. The reverse direction — first arg an unbound `Var`, second arg a ground
list — yields **no solution**:

```clausal
Test("reverse fwd")  <- (reverse([1, 2, 3], R), R == [3, 2, 1])   # passes
Test("reverse bwd")  <- (reverse(L, [3, 2, 1]), L == [1, 2, 3])   # FAILS — no solution
```

SWI/SICStus `reverse/2` is bidirectional (reversing a reversed list recovers the
original), so this is a mode-incompleteness relative to standard Prolog. It is
**not** a silent-correctness bug: it fails rather than returning a wrong answer.

## Cause

`clausal/logic/builtins/lists.py::_reverse__2` calls `_as_items(deref(lst))` on
the **first** arg only; when that is an unbound `Var`, `_as_items` returns `None`
and the predicate falls straight through to `yield (_fail, DONE)`. There is no
"second arg ground → reverse it into the first" branch.

## Fix sketch

Symmetric: if the first arg is unbound and the second is a usable sequence,
`unify(lst, reversed(second), trail)` (preserving the str/bytes seq-result
contract via `_seq_result` / `_was_string` / `_was_bytes`, mirroring the forward
branch). Two ground lists should still verify (already works via the forward
branch). Two unbound args → instantiation behaviour TBD (SWI enumerates
increasingly-long lists; clausal may prefer an error or leave it unsupported).

## Priority

Low — forward mode is the common case and the failure is loud (no solution, not a
wrong answer). Worth doing for parity with standard `reverse/2` and to let
libraries rely on it relationally.

## Done when

- `reverse(L, [3,2,1])` binds `L = [1,2,3]`; regression test covers both
  directions (and the str/bytes seq-result contract in reverse mode).
