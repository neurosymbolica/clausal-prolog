# `in_/2` does not accept a DictTerm, while the `in` operator does

**Filed:** 2026-07-30, splitting the last live item out of
`todo/done/dict-key-membership-in-operator.md` before archiving it.

The `in` **operator** is done and tested for dicts: `foo in {foo: 1, bar: 2}`
succeeds, `findall(K, K in {foo: 1, bar: 2}, KS)` enumerates the keys. That
todo's acceptance criteria were all written in operator form, so it is closed.

The **predicate** spelling is not there:

```
in_(foo, {foo: 1, bar: 2})     % FAILS
in_(foo, [foo, bar])           % succeeds
```

So the two spellings disagree on dicts, and the failure is silent — `in_/2`
fails rather than raising, so a rule written with the predicate form just yields
no solutions.

The archived todo's "Where" section proposed dispatching `in_/2` on the right
operand's type, which is still the obvious fix (`clausal/logic/builtins/` —
`in_/2` currently goes through the list path). Decide as part of it whether
`in_/2` on a dict should enumerate keys in the same order as the operator.

Not urgent: no corpus file uses `in_/2` against a dict (it would have failed
loudly in a gold if it did). It is filed because a silent disagreement between
two spellings of the same operation is the kind of thing that costs an hour when
someone finally hits it.
