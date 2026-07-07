# fix(A11-F022): Prolog↔Clausal variable renaming is non-injective (both directions)

`tools/prolog_dialect.py:121-158`: `Foo`→`_foo` and `FOO`→`_foo`;
`_Ignored`/`Ignored` collide too; reverse maps `_foo` and `FOO` both to `Foo`.
Executed: `p(Foo, FOO) :- Foo = 1, FOO = 2.` → `P(_foo, _foo) <- (_foo is 1,
_foo is 2)` — a satisfiable clause becomes unsatisfiable, silently.

**Fix** (A11-D009-adjacent): per-clause rename tables with collision
disambiguation (append `_2`, `_3`, …); document names as best-effort.

**Test**: test_F022_var_mapping_injective (xfail).
