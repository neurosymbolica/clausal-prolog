# Bug: `maplist/foldl/...` at the wrong arity still blames a missing argument

**Reported:** 2026-07-29, found while fixing
[`arity-mismatch-reports-a-missing-trail-argument.md`](done/arity-mismatch-reports-a-missing-trail-argument.md)

---

## Symptom

```clausal
-private([art_1_2, meta])

citation(art_1_2, "EUMR Article 1(2)", meta),

Test("maplist wrong arity") <- maplist(citation, [art_1_2]),
```

reports:

```
  ho.clausal:5 :: maplist wrong arity — citation__3() missing 2 required positional arguments: 'arg2' and 'trail'
```

The same three faults the sibling fix removed from the direct-call case: the
mangled internal name, an argument (`trail`) the author cannot supply, and no
mention of arity.  `maplist(citation, L)` calls `citation` with one argument;
`citation` takes three.

## Why the sibling fix does not cover it

The fix routes every wrong-arity call through `_dispatch_at(callee, arity)` (and
so `PredicateMeta._get_dispatch(arity)`), which needs the caller to say how many
arguments it will supply.  The compiled call sites pass it (the emitters know),
and `call/N` passes it (`_make_call_goal_trampoline` knows `extra_n`).  The rest
of the higher-order family calls the shared funnel
`_registry._ensure_trampoline_dispatch(goal_val)` with no arity, so the check is
skipped and the goal runs on into the old `TypeError`.

## What is *not* left (this note used to be wrong)

The first version of this todo said the remaining sites were "all in
`clausal/logic/builtins/higher_order.py`".  They were not.  Two other runtime
funnels resolved a goal without an arity, and unlike the higher-order family
both knew theirs exactly, so both were fixed rather than filed:

- `builtins/control.py::_goal_dispatch_and_args` (`time_goal/1,2`) — a bare name
  is called with no arguments at all (arity 0); a term instance with one per
  field.
- `builtins/dcg.py` (`phrase/2`, `phrase/3`) — `len(user_args) + 2`, because
  `phrase` supplies the difference-list pair itself, so a nonterminal's called
  arity is never the arity written in the source.  See `_DCG_ARITY_NOTE` there
  for why `len(fields)` is not the same expression.

## Requested fix

`_ensure_trampoline_dispatch` already takes an optional `arity`.  There are
16 remaining call sites (`grep -c '_ensure_trampoline_dispatch(' ` reports 17 in
that file, one of which is `call/N` and already passes `extra_n`), each of which
knows its own effective arity — but not uniformly, which is why this was left
out of the sibling fix rather than swept:

- `maplist/2..5` call the goal at `len(lists)`, i.e. arity − 1;
- `foldl/4..6` at `len(lists) + 2` (element(s), accumulator in, accumulator out);
- `include/exclude/partition` at 1;
- `aggregate_all` and friends call a goal that takes no extra arguments.

So the change is one argument per site, but the *value* has to be read off each
builtin's own contract; a single mechanical sweep would get some of them wrong,
and a wrong value here turns working code into a refusal.  Do them
deliberately, with a test per family.

`tests/test_predicate_arity_mismatch_diagnostic.py::TestOtherGoalPositions` is
where the coverage goes — it already pins negation, `findall/3` and `call/N`.
