# same_length/2 of a text builds substring holes, so the length is lost

Found 2026-10-09 on main fcdd82c2. Reachable from Prolog syntax:

```prolog
s(L) :- same_length("abc", L), L = "xy".     % succeeds, should fail
t(L) :- same_length("abc", L), L = "wxyz".   % succeeds, should fail
u(L) :- same_length("abc", L), L = "xyz".    % succeeds
```

In all three, `L.value` comes back as the unfilled
`SegString([VarSeg(_), VarSeg(_), VarSeg(_)])`, not the text.

## Cause

`_fresh_same_shape` (`clausal/logic/builtins/lists.py`, F053 option A) gives a text sibling a
`SegString` of N `VarSeg` holes. A `VarSeg` is a hole of ANY length (a substring), not one char, so
the term means "three substrings": every text unifies with it. With two or more holes, unify also
binds only the first split (see
`todo/multi-star-pattern-unified-as-a-value-binds-only-its-first-split-2026-10-08.md`). The same
applies to the `SegBytes` arms.

## Fix direction

A text of length N must be N single chars. Either return a list of N fresh `Var`s (the list arm),
or a char-list carrier whose elements are variables, if F053's "input type wins" rule must hold.
Then `L = "xy"` fails on length and `L = "xyz"` binds each char. Check what F053's tests pin first.

Also check the `.value` of an unfilled `SegString` after a successful unify: the holes stay
unbound in the printed answer, which looks like a second bug in how the split is bound or read back.

## 2026-10-10: done (with candidate 2)

`_fresh_same_shape` returns a list of N fresh variables for every sibling,
text and bytes included (Scryer: `[_, _, _]`). It had to ship with the split
pending goal: on that candidate the old holes gave 6, 15 and 10 answers for
`s`, `t` and `u` above. The two tests that pinned the hole shape (C09 F053,
`test_same_length_bytes_var_binds_shape`) now pin the list. A filled answer
reads back as the char list `['x', 'y', 'z']`, not text: a char list's two
shapes are a seam matter (2026-10-08).
