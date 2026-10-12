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
