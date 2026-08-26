# The EDCG body rewriter's if-then-else case is unreachable

**Filed:** 2026-08-26, found while renaming `If/3` → `if_/3`.
**Status: OPEN.**

## What

`_rewrite_edcg_body` in `clausal/templating/term_rewriting.py` has an
if-then-else case (`case Call(func=Name(id=name), args=[cond, then_, else_])
if name in _ITE_NAMES`) that threads each accumulator through the condition
and both branches. It never runs: the generic
`case Call(func=Name(id=name), args=args, keywords=kwargs)` a few dozen lines
above it matches *any* call, so the ITE falls in there first.

Consequence: an ITE inside an EDCG body is rebuilt as an opaque call whose
arguments are never visited, so the branches get no accumulator threading and
no DCG state args. The branch goals then reach the compiler as bare terms.

## Repro (verified 2026-08-26 against `/workspace/clausal` main, i.e. this is
not a regression from the rename)

```clausal
-module(pe, [pick(_cnt0, _cnt)])
-edcg_acc(counter, _x, _in, _out, {_out == _in + _x})
-edcg_pred(inc, 0, [counter])
-edcg_pred(pick, 0, [counter])
inc >> ([1] // counter)
pick >> (if_(inc, inc, inc))
```

Loading raises

```
NotImplementedError: terms_to_goalop: goal shape not yet supported
(LoadName): LoadName(name='inc')
```

— `inc` stayed a bare 0-arity name instead of becoming `inc(_in, _out)`.

## Fix

Move the ITE case above the generic `Call` case (and above
`case Call(... ) if name in edcg_preds`, since an EDCG predicate named `if_`
would otherwise shadow it — or reject that name outright). Then write the
EDCG-body test that `tests/test_if_spelling.py` had to drop:

```clausal
pick >> (if_(<ground cond>, inc, (inc, inc)))
```

and assert the counter comes out as 1 (then branch), not 2.

Check the DCG rewriter (`_rewrite_dcg_body`) for the same ordering bug — its
ITE case *is* reachable (`tests/test_dcg.py::TestIfThenElse` passes), so the
two functions have diverged and it is worth knowing why.

Related: [[rename-If-3-to-if_-3]].
