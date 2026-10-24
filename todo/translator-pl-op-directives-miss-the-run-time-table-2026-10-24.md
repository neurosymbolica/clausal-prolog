# The translator front end does not apply a .pl file's op/3 directives to the run-time operator table

Filed 2026-10-24, found while pinning the `-g` answer printer against
Scryer (tests/iso/test_answer_printer_brackets_scryer.py). Low severity: the
translator is the opt-in legacy `.pl` front end.

## What / Repro

`o.pl`:

```prolog
:- op(200, xfx, foo).
p.
```

```
$ CLAUSAL_PL_FRONTEND=translator clausal o.pl -g "writeq((foo)-a), nl, current_op(P,T,foo)"
foo-a
false.
$ clausal o.pl -g "writeq((foo)-a), nl, current_op(P,T,foo)"     # native
(foo)-a
P = 200, T = xfx.
```

Under the native front end a non-module file's `op/3` directives reach the
run-time table (`prolog_operators.runtime_op_table`, as
`iso_l3_directives` applies them), so `current_op/3`, `writeq/1` and the
`-g` answer printer see them, as in Scryer. The translator reads the file
with the operator but never applies it at run time.
