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

## Resolution — 2026-07-30

**None of the three options. The question was mis-framed, and measuring it said so.**

The asymmetry above is real but harmless. What was actually broken sat one step
later: **construction never rebuilt a declared term at all.** With arity > 0,
both `functor/3` and `unpack/2` reduced a `PredicateMeta` name to
`name.__name__` and built a generic `Compound` — discarding the class even when
the caller handed it over directly. Since a Compound never unifies with a
declared term-class instance of the same name and arity, decompose-then-
reconstruct could not round-trip, and neither could `functor(T, cite, 1)`.

Two pieces of evidence redirected the fix:

- A downstream helper library had already hit this and written it down as settled
  behaviour rather than a defect — its own "ATTR-LIST
  BRANCH — VERIFIED SEMANTICS (2026-07-19 interpreter probe)" note, including the
  consequence that "after a kit `world_set` on an attr-list world the entry is
  a generic Compound — the domain's class-constructor read will NOT see it".
- The corpus sweep's headline risk was backwards. `key_string/2` was read as
  depending on decomposition yielding the *class*; its own docstring says the
  opposite — "atom-shaped KEY -> its functor-name string, via a build-then-
  decompose roundtrip". It needs the **string** arm. Option 3 would have broken
  the kit; option 2 would have broken 3 ISO golden tests and contradicted the
  recorded A09-F027 round-trip principle.

**Fixed** in `clausal/logic/builtins/inspection.py::_construct_named`, shared by
both construction sites: a `PredicateMeta` name whose field count matches the
requested arity now builds that class's instance. Everything else is untouched —
a `str` name still builds a Compound and is deliberately not resolved back to a
class (which module's `cite` a bare string names is ambiguous under module-local
atom identity), and an arity that disagrees with the class falls through to the
Compound rather than raising, which is what keeps the kit's
`functor(PROBE, KEY, 1)` over an arity-0 schema atom working.

Decomposition is unchanged, so the type asymmetry this todo was named for still
stands — deliberately. It is documented rather than removed.

Verified: 11 new tests in `tests/test_functor_construction_declared_term.py`;
full suite 10771 passed; the investment-screening domain's 123 tests, the tax-credit
domain's 41, and the downstream helper library's own `planner_tests.clausal` 49 +
demos + gap-wave2 all green against the branch.

The diagnosability half — a generic Compound *renders identically* to the
declared term it will not unify with, so the failure reads as a contradiction —
is split out to
[[a-generic-compound-renders-identically-to-a-declared-term]].
