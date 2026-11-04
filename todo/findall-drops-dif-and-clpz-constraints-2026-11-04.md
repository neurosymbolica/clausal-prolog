# findall/3 and bagof/3 drop dif and CLP(Z) constraints from the collected answers

**Status: open, needs a ruling.**

`copy_term/2` keeps `dif/2` on the copy (`dif(X,a), copy_term(X,Y)` gives
`dif(Y,a)`), but `findall/3` does not:

```prolog
?- findall(X, dif(X,a), L).
L = [_A].                      % the dif is gone
?- findall(I-D, (I in 0..100000, if_(I #< 1000, D = low, D = high)), L).
L = [_A-high, _B-low].         % the domains are gone
```

Seen on e1b23bfb from `.pl` and `.clausal`. This matters when a rulebase is run
"backwards" (inputs unbound or constrained) and the answer classes are
collected: each class loses the condition that defines it.

## The ruling needed

Prolog systems differ here, so this is not a plain bug:

- (a) Keep the current behaviour (no attributes in the copy), and document it.
- (b) Have `findall/3`, `bagof/3` and `setof/3` copy attributes like
  `copy_term/2` does, so the collected copies carry their constraints.
- (c) Add a separate collector that keeps residuals, and leave findall alone.

## Workaround today

Turn the residual into data inside the goal:
`findall(I-D-Dom, (Goal, fd_dom(I, Dom)), L)` gives
`L = [_A-high-1000..100000, _B-low-0..999]`.

Related: `copy-term-attributes-freeze-clpz-and-copy-term-3-2026-09-30.md`
(`copy_term/2` drops `freeze` and CLP(Z) domains),
`copy-term-3-attribute-goals-2026-09-08.md`,
`tabled-answers-drop-their-constraints-on-replay-2026-07-05.md`.
