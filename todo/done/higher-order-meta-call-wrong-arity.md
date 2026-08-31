# Bug: `maplist/foldl/...` at the wrong arity still blames a missing argument

**Reported:** 2026-07-29, found while fixing
[`arity-mismatch-reports-a-missing-trail-argument.md`](arity-mismatch-reports-a-missing-trail-argument.md)

---

## Symptom

```clausal
-private([art_1_2, meta])

citation(art_1_2, "Example Reg Article 1(2)", meta),

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

---

## Fixed (2026-08-31)

Done as requested: one arity argument per site, each value read off the
builtin's own goal invocation (the `StepGenerator` / `_run_goal_once` call a
few lines below each funnel call, which lists the exact arguments the goal
receives).  The counts, audited site by site:

- **1** (the element alone): `maplist/2`, `include/3`, `exclude/3`,
  `partition/4`, `take_while/3`, `drop_while/3`, `span/4`
- **2** (element + output/key/truth slot): `maplist/3`, `group_by/3`,
  `sort_by/3`, `max_by/3`, `min_by/3`, `filter_map/3`, `tfilter/3`,
  `tpartition/4`
- **3** (element + both accumulators): `foldl/4`

Two corrections to this note's own framing, discovered while fixing:

- The family list above ("maplist/2..5, foldl/4..6, aggregate_all") was
  SWI-shaped; this codebase registers only `maplist/2,3` and `foldl/4`, and
  has no `aggregate_all`.  The 16 sites in `higher_order.py` were the whole
  set.
- Nothing needed changing in `_ensure_trampoline_dispatch` or below it:
  `_dispatch_at` forwards the arity only to a `PredicateMeta`, and
  `_refuse_call_at` declines quietly when heads are unreadable or disagree, so
  closures, foreign implementors and stale-`_arity` predicates are untouched
  by construction.

Coverage: `TestHigherOrderFamily` in the same test file — the 16 mismatch
shapes parametrized against `citation/3` (a `/2` callee for `foldl`, whose
count agrees with `/3`), plus one correct-arity guard per count, because a
wrong count here refuses working code.  Full suite diffed against a stashed
baseline: failure sets identical (the pre-existing `test_clpsat.py` /
`test_clportools.py` / doc-snippet failures, nothing new).

Files: `clausal/logic/builtins/higher_order.py`,
`tests/test_predicate_arity_mismatch_diagnostic.py` (+19 tests).
