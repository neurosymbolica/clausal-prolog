# `assertz/1` accepts a clause whose head is `(:-)/1` or `(:-)/2`

**Filed:** 2026-11-03, found while investigating
`todo/done/colon-dash-dot-reads-as-a-fact-2026-09-04.md`.

**Status: FIXED 2026-11-03 (commit 1adbe9c4).** assertz/1, asserta/1, retract/1 and retractall/1 raise `permission_error(modify, static_procedure, (:-)/N)` for a `(:-)/1` or `(:-)/2` head, with Scryer's contexts (`database_ops._refuse_neck_head`). Not done: clause/2 and abolish/1 of `(:-)/N` (Scryer: permission errors; Clausal: fail / succeed). Pinned in tests/iso/test_colon_dash_head_scryer.py::test_runtime.

## Repro

```
$ clausal -g "assertz(((a:-b):-true))" p.pl     # true.
$ clausal -g "assertz(((:-a):-true))" p.pl      # true.
```

Scryer (the oracle in `tests/_oracles.py`):

```
assertz(((a:-b):-true))  -> error(permission_error(modify,static_procedure,(:-)/2),assertz/1)
assertz(((:-a):-true))   -> error(permission_error(modify,static_procedure,(:-)/1),assertz/1)
```

Loading a file has the same split. The native front end refuses
`((:- a) :- true).` and `((a:-b) :- true).`, as Scryer does
(`iso_l3.lower_clause`, the control-construct name check), but `assertz/1`
and `asserta/1` do not. `assertz((:-))` succeeds in both Scryer and Clausal.

## Expected

`assertz/1` and `asserta/1` raise
`permission_error(modify, static_procedure, (:-)/N)` for N = 1 or 2, the
same answer the loader gives. Whether `(:-)/0` is definable is the open
question in the related todo.
