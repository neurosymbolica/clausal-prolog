# The CLI's -g goal reads every `_` as one shared variable (2026-10-12)

```
clausal prog.pl -g 'X = [1,_,3], X = [_,C|_]'      % false  (wrong)
p(C) :- X = [1,_,3], X = [_,C|_].                  % clausal prog.pl -g 'p(C)'  ->  true (right)
```

In a `-g` goal, every `_` refers to the same variable. In ISO each `_` is a fresh anonymous
variable. Program clauses read correctly. Verified on main 9ecfb760. It affects both CLP(Q)
solvers and anything typed at `-g`. Found by the CLP(Q) port's Task 16 fix round.

Fix: the `-g` reader must give each `_` its own variable, as the clause reader does. Test with
`-g` goals that use `_` two or three times, including inside a compound and inside a list.

## Fixed (2026-10-12, fix/frontend-anon-var-and-improper-tail-2026-10-12)

The `_` diagnosis was wrong. The `-g` reader (`clausal/cli.py` `_read_goal`, the one reader
for `.pl` under both front ends and for `.clausal`) already gave each `_` its own variable.
It handed the engine the reader's cons cells `'.'(H, T)` for every `[...|T]`, and a proper or
partial list never unifies with a cons cell. So any `[H|T]` pattern failed, with or without `_`:

```
clausal prog.pl -g 'X = [1,2], X = [B|T]'           % false  (Scryer: B = 1, T = [2])
```

Now `_read_goal` lowers a cons chain as the native front end does (iso_l3 `_cons`). A
variable tail becomes the compiler's `[H, *T]`, a list, `[]` or `"..."` tail splices, and any
other tail keeps the cons cells of an improper list. Tests: `tests/test_cli_g_list_patterns.py`.
