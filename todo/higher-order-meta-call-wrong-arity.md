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

The fix routes every wrong-arity call through
`PredicateMeta._get_dispatch(arity)`, which needs the caller to say how many
arguments it will supply.  The compiled call sites pass it (the emitters know),
and `call/N` passes it (`_make_call_goal_trampoline` knows `extra_n`).  The rest
of the higher-order family calls the shared funnel
`_registry._ensure_trampoline_dispatch(goal_val)` with no arity, so the check is
skipped and the goal runs on into the old `TypeError`.

## Requested fix

`_ensure_trampoline_dispatch` already takes an optional `arity`.  There are
17 remaining call sites, all in `clausal/logic/builtins/higher_order.py`, each
of which knows its own effective arity — but not uniformly, which is why this
was left out of the sibling fix rather than swept:

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
