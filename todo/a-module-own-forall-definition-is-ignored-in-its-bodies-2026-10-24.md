# A module's own definition of `forall/2` is ignored in its own bodies

Filed 2026-10-24, split from
[the builtin-redefinition todo](done/iso-a-file-can-redefine-a-builtin-2026-10-16.md)
when its ISO part was fixed. OPEN.

`forall/2` is no ISO built-in, so a `.pl` or `.clausal` file may define it
(Scryer loads such a file and runs the definition). In its own clause
bodies the compiler's special form still runs instead:

```
forall(X, _) :- X = mine.
q(L) :- findall(X, forall(X, true), L).
```

| | `q(L)` |
|---|---|
| Clausal (`.pl`) | `error(instantiation_error, call/1)` (the special form) |
| Scryer | `L = [mine]` (the file's definition) |

An IMPORTED definition already runs on every route
(`tests/test_imported_special_form_names.py`). The same may hold for the
other non-ISO special-form names a file may now define (`ignore/1`,
`call_cleanup/2`, `setup_call_cleanup/3`, `call_nth/2`, `phrase/2`);
`logic/special_forms.py` lists them.
