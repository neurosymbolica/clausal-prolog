# Under the `.pl` translator, call/N of a file's own `not/1` is existence_error

Found 2026-11-03 while fixing
[a module's own forall/2](done/a-module-own-forall-definition-is-ignored-in-its-bodies-2026-10-24.md).
Only the legacy translator front end (`CLAUSAL_PL_FRONTEND=translator`); the
native front end (the default) and `.clausal` agree with Scryer. The same
before and after that fix.

```
not(X) :- X = mine.
q2(L) :- findall(Y, call(not, Y), L).
```

| | `q2(L)` |
|---|---|
| native `.pl`, `.clausal`, Scryer | `L = [mine]` |
| translator `.pl` | `error(existence_error(procedure, not/1), not/1)` |

The body goal `not(Y)` and `G = not(Y), call(G)` do run the definition
under the translator. The translator spells `\+` as the seam's `not`, which
is the likely cause. `tests/iso/test_own_special_form_names_scryer.py`
skips the `not/1` row on the translator surface for this reason.
