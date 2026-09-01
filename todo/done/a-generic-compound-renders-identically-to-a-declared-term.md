# A generic `Compound` renders identically to the declared term it will not unify with

**Filed:** 2026-07-30, split out of
[[functor-3-names-an-atom-as-a-class-but-a-compound-as-a-string]] while fixing
the construction half. **Status: OPEN, no crash behind it.**

## What it looks like

A goal that fails on a Compound-vs-declared-term mismatch reports a binding that
is character-for-character what the author asked for:

```
goal 4 of 4 failed:
  T2 is cite(_)
bindings at failure: T = cite(art), N = 'cite', A = 1, T2 = cite(_)
```

`T2 = cite(_)` and the goal `T2 is cite(_)` — and it failed anyway. Everything a
reader can see says it should have succeeded. The renderer is telling the truth
about the *shape* and hiding the only thing that matters, which is that one side
is a `clausal.terms.Compound` and the other a `PredicateMeta` instance.

Confirmed at the Python level:

```python
str(cite(1))                    # 'cite(k=1)'
str(Compound('cite', [1]))      # 'cite(1)'
unify(cite(1), Compound('cite', [1]))   # False
```

(The two differ slightly here because the declared term shows its field name;
at the `.clausal` surface with a `Var` argument both render `cite(_)`.)

## Why it is worth fixing separately

The `functor/3` construction fix (2026-07-30) removed the most common *source*
of a stray Compound, but it did not remove the class of confusion. Any path that
produces a generic Compound alongside a declared term of the same name — the
string arm of `functor/3` construction, `unpack/2` from a string functor, terms
crossing a module boundary where the declared class differs — lands the reader
in the same place: a diagnostic that reads as a contradiction.

This is the same family as [[internal-unify-typeerror-reaches-the-user-as-error-text]]
and the `trail` leak: an engine-level distinction escaping into user-facing text
with no vocabulary to describe it. Here the failure is worse than a bad message,
because it looks like a *correct* message.

## The question

Where should the distinction be drawn, and how loudly?

1. **Only in failure diagnostics.** When a unification failure involves a
   Compound and a declared term-class instance of the same name/arity, say so
   explicitly — "`T2` is a generic compound `cite/1`, not the declared
   `cite/1` from `<module>`". Narrow, and the reader only pays when confused.
2. **In the term renderer generally.** Give a generic Compound a distinguishing
   mark wherever it prints. Consistent, but noisy, and it changes a lot of
   expected output across the corpus and docs.
3. **At the point of construction.** Warn when a Compound is built whose
   name/arity matches a declared class in scope. Catches it earliest, but "in
   scope" is exactly the ambiguity that kept the string arm of `functor/3`
   unresolved — see the sibling todo.

Option 1 is the cheapest and fits the house pattern of a `*_diagnostics.py`
module that only runs once something has already failed.

## Notes

- The reified-term renderer landed 2026-07-20 (see the memory note on auditor
  engine prereqs); whatever is chosen should go through it rather than around it.
- Not urgent: nothing crashes, and after the construction fix the common
  round-trip path no longer produces the mismatch at all.
