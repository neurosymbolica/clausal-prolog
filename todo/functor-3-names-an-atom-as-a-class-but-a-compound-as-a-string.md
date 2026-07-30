# `functor/3` names an arity-0 atom as itself but a compound's functor as a string

**Filed:** 2026-07-30, split out of
[[internal-unify-typeerror-reaches-the-user-as-error-text]] while fixing the
crash that was hiding it. **Status: OPEN DESIGN QUESTION, no crash behind it.**

## The asymmetry

`clausal/logic/builtins/_helpers.py`, `_functor_name_py`:

```python
if is_term_instance(term):
    return type(term).__name__          # a str
...
if isinstance(term, PredicateMeta) and not term._fields:
    return term                          # the class itself
```

So the same predicate answers in two different types depending on the arity of
its argument, and only the arity-0 answer round-trips:

```clausal
-private([zed, cite(KEY)])

functor(zed, N, A), N is zed            # succeeds — N is the atom class
functor(cite(K), N, A), N is cite       # fails    — N is the string "cite"
```

Compounds behave like the second case too (`Compound.functor` is a `str`), so
"str" is the majority answer and the arity-0 class is the odd one out — but the
arity-0 answer is the one that round-trips, which is what an author writing
`functor/3` in a test is checking for.

## Why it matters

It is what the author in the originating todo was actually reaching for. Their
test read

```clausal
CITE_TERM is cite(eu_reg_2016_399_art_6_1),
functor(CITE_TERM, FUNCTOR_NAME, ARITY),
FUNCTOR_NAME is cite,
ARITY == 1
```

which is exactly the shape that works for an arity-0 atom and cannot work for
anything else. Until 2026-07-30 that goal *crashed*; it now fails cleanly with
the binding shown (`FUNCTOR_NAME = 'cite'`), which is honest but still tells an
author that a reasonable-looking symmetry does not hold.

## The question

Pick one, deliberately:

1. **Leave it.** `functor/3` is ISO-named and ISO says the name of a compound is
   an atom, which Clausal spells as a `str` at the surface. The arity-0 arm is
   then the anomaly and the docs should say so out loud.
2. **Make arity-0 answer a `str` too.** Consistent, ISO-shaped, and it makes
   `N is zed` stop working — a behaviour change with corpus reach, since
   `functor/3` over declared atoms is a real pattern. Needs a corpus sweep first.
3. **Make with-fields terms answer the class.** Makes the author's expectation
   true and keeps atom round-tripping, but diverges from ISO, breaks
   `functor(f(1), N, A), N == "f"`, and forces the same decision on `unpack/2`
   (`=..`) and `arg/3`'s neighbours to stay coherent.

Whichever wins has to move `functor/3`, `unpack/2` and the `_functor_name_py` /
`_arity_py` pair together — they share the helper — so this is not a one-line
change and should not be done opportunistically.

Not urgent: nothing crashes, and the failure mode is a clean goal failure with
the offending binding printed.
