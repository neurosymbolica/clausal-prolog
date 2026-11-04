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

## What other systems do (measured 2026-11-04)

Scryer (the oracle build in `tests/_oracles.py`) drops the attributes in
`findall/3` and `bagof/3` too, for `dif/2`, CLP(Z) and `freeze/2` alike;
the collected copy is a plain variable that any value unifies with:

```prolog
?- findall(X, dif(X,a), L).            % L = [_A].
?- findall(X, X #> 3, L).              % L = [_A].
?- findall(X, freeze(X, true), L).     % L = [_A].
?- findall(X, dif(X,a), [Y]), Y = a.   % Y = a.
?- findall(X, X #> 3, [Y]), Y = 1.     % Y = 1.
?- findall(X, freeze(X, fail), [Y]), Y = 1.   % Y = 1.
?- bagof(X, dif(X,a), L).              % L = [_A].
```

Trealla 2.92.3 drops `dif/2` and `freeze/2` the same way
(`findall(X, dif(X,a), [Y]), Y = a` succeeds); its `X #> 3` case did not
finish within 20 s, so it is unmeasured.  SWI-Prolog is not installed on
this machine, so its behaviour is not measured; it needs measuring before
the ruling, as it may be the system that keeps them.

So Clausal's current behaviour, option (a), is what Scryer and Trealla
do.  Clausal agrees with Scryer on all seven goals above.

## Workaround today

Turn the residual into data inside the goal:
`findall(I-D-Dom, (Goal, fd_dom(I, Dom)), L)` gives
`L = [_A-high-1000..100000, _B-low-0..999]`.

More generally, with `copy_term/3` (added 2026-11-04), collect each answer
with its residual goals, and call them to put the constraints back:
`findall(X-Gs, (dif(X,a), copy_term(X,X,Gs)), L)` gives
`L = [_A-[dif(_A,a)]]` (Scryer: `L = [_A-[dif:dif(_A,a)]]`), and
`findall(X-Gs, (X #> 3, copy_term(X,X,Gs)), L)` gives
`L = [_A-[_A in 4..sup]]`.  This is option (c) without a new collector.

Related: `copy-term-attributes-freeze-clpz-and-copy-term-3-2026-09-30.md`
(`copy_term/2` drops `freeze` and CLP(Z) domains),
`done/copy-term-3-attribute-goals-2026-09-08.md`,
`tabled-answers-drop-their-constraints-on-replay-2026-07-05.md`.
