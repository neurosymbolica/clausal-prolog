# `functor/3` can surface a raw internal `__unify__()` TypeError as the error text

**Filed:** 2026-07-30, from run logs from a measured authoring study, preserved
in an external harness's scratch archive.
**Status: REPRODUCED AND FIXED**, 2026-07-30, branch
`fix/internal-unify-typeerror`. It was *not* already fixed: it reproduced at
`7a432659` on the first attempt from the preserved scratch tree. The trigger is
neither `functor/3` nor the package boundary — both were red herrings, which is
why the three minimal repros below all passed. See **Resolution** at the bottom;
the original report is preserved unchanged above it.

(Module paths and error transcripts below are paraphrased with invented,
neutral names — the error class and structure are reproduced exactly.)

## What was seen

```
FAILURES:
  test_load.clausal:57 :: cite term constructs correctly — _make_unify.<locals>.__unify__() missing 1 required positional argument: 'trail'
    goal 2 of 2 raised:
      functor(CITE_TERM, rulebase.rolling_window_rule.citations.cite, 1)
      TypeError: _make_unify.<locals>.__unify__() missing 1 required positional argument: 'trail'

4 tests: 3 passed, 1 failed [FAILED]
```

The authored source of that test (model-written, so treat the *input* as
arbitrary — the complaint is about the *output*):

```clausal
Test("cite term constructs correctly") <- (
    CITE_TERM is cite(reg_x_2016_art_6_1),
    functor(CITE_TERM, FUNCTOR_NAME, ARITY),
    FUNCTOR_NAME is cite,
    ...
```

Note the rendered goal is post-binding — the diagnostic substitutes the values
live at the raise, so `FUNCTOR_NAME`/`ARITY` appear filled in. The call in
source is decomposition mode (both free), not verification mode. Don't chase
the wrong mode on the strength of the rendered line.

`cite` here is a package-qualified atom
(`rulebase.rolling_window_rule.citations.cite`) imported into the test module,
so the call crosses a package boundary. That is the one feature the failing
case has that none of my repros did — start there.
Related: [[functor-identity-leaks-across-modules-in-one-process]].

## Why it is worth fixing regardless of the trigger

`_make_unify.<locals>.__unify__() missing 1 required positional argument:
'trail'` names a closure inside the engine and a parameter the user cannot see,
has never written, and cannot act on. Whatever the caller did wrong, an
internal Python `TypeError` is not an acceptable user-facing error — and
clausal already has the right shape of error for the neighbouring case
(`PredicateArityMismatchError: score_profile takes 6 arguments, but this call
passes 3` appears in the same corpus). Either the call is legal and this is an
engine bug, or it is illegal and it should raise a named clausal error.

Cost of the current behaviour, measured: **10 attempts across 2 runs, neither
recovering.** One domain's authoring study burned 7 attempts over 89
minutes on it and terminated stuck; a second domain's authoring study burned 3
more. A local 27B model given this message has nothing to act on, so it edits at
random until the attempt budget runs out.

## What I could not reproduce

Three minimal repros, all **PASS** at pin `9f3f0720`:

1. `-private([cite(X)])` + `functor(T, cite, 1)` (construction mode)
2. `-module(cits, [cite])` + `-import_from(cits, [cite])` + `functor(T, cite, 1)`
3. `T is cite(1), functor(T, NAME, ARITY)` (decomposition mode, private atom)

A fourth attempt at the package-qualified form was blocked by an unrelated
`strict_atoms` error on the test harness scaffolding I wrote, so the actual
distinguishing case is still untested.

The run predates the `clausal_sha` provenance field on the formalizer side, so
the exact engine revision it ran against is **unrecorded**. `/workspace/clausal`
was at `297e506f` (2026-07-24) around the study and `9f3f0720` by 2026-07-30, so
the fix may already be in. First step for whoever picks this up is to reproduce
against the scratch tree preserved in the external harness's archive, which
still holds the failing `rulebase/rolling_window_rule/tests/test_load.clausal`
and its package. If it passes there at HEAD, close this as already-fixed and
say which commit did it.

---

## Resolution (2026-07-30)

### It reproduced

At `7a432659`, running the preserved tree verbatim:

```
$ python -m clausal.testing rulebase/rolling_window_rule/tests/test_load.clausal
  test_load.clausal:57 :: cite term constructs correctly — _make_unify.<locals>.__unify__() missing 1 required positional argument: 'trail'
    goal 3 of 4 raised:
      FUNCTOR_NAME is rulebase.rolling_window_rule.citations.cite
      TypeError: _make_unify.<locals>.__unify__() missing 1 required positional argument: 'trail'
```

Two things the original report guessed wrong, both of which explain why the
three minimal repros passed:

* **The failing goal is not `functor/3`.** It is `FUNCTOR_NAME is cite`, one
  goal later. `functor/3` succeeded and did its job. (The field log said
  "goal 2 of 2" against "goal 3 of 4" here — a compiler difference between the
  two revisions, not a different bug; the reduced form below still renders
  "goal 2 of 2".)
* **The package boundary is irrelevant.** One file with no imports reproduces:

```clausal
-private([cite(KEY)])

Test("bare functor name as a value") <- (
    NAME is "cite",
    NAME is cite
)
```

The three repros in the original report all missed it because none of them put
a *bare, with-fields functor name* on a unification side against a
non-identical value. Repro 3 came closest but compared two variables.

### Root cause

Not in `functor/3`, and not specific to unification of any particular shape.
`clausal/logic/variables/_variables.c` reaches every Python term type through a
plain `PyObject_GetAttrString(t, "__unify__")` and then calls `hook(other,
trail)`. On an *instance* the lookup binds and the call matches the generated
`__unify__(self, other, trail)`. On a **class** — and a bare functor name is a
class used as a term value — the same lookup returns the *unbound* function, so
`other` lands in `self` and `trail` is never filled in. Hence the message,
which names the engine's own closure and a parameter the author never wrote.

`__occurs_check__` had the identical shape and the identical break
(`occurs_check(V, cite)` raised too).

Arity-0 atoms were immune only because `PredicateMeta` deliberately installs no
hooks on them at all ("the class IS the value"). Any declared functor of arity
≥ 1, used bare as a value against a non-identical operand, raised — so the true
blast radius was much wider than `functor/3`: head matching (`p("cite")`
against a clause `p(cite)`) raised as well.

### Fix

`clausal/logic/predicate.py` — `_make_unify` / `_make_occurs_check` now take a
`_CLASS_CALL` sentinel as the default of their last parameter. Only a
two-argument call can leave it in place, and a two-argument call is by
construction the class-side one, so the branch is a decision rather than a
guess. The class arm answers identity and otherwise returns `NotImplemented`,
which is exactly what an arity-0 atom's *absent* hook produces: the C unifier
falls through to the symmetric hook and then to rich compare. The change
therefore cannot alter *whether* any two terms unify.

A descriptor that gives each caller its own signature is the tidier way to say
this and was written first, then thrown away: it puts a Python frame on every
*instance*-side hook lookup, taking `t.__unify__` from 35ns to 103ns and showing
up end-to-end on term head matching. The sentinel version benchmarks inside the
noise of `main` on both.

After:

```
  test_load.clausal:57 :: cite term constructs correctly
    goal 3 of 4 failed:
      FUNCTOR_NAME is rulebase.rolling_window_rule.citations.cite
    bindings at failure: CITE_TERM = cite(reg_x_2016_art_6_1), FUNCTOR_NAME = 'cite', ARITY = 1
```

The author is now shown `FUNCTOR_NAME = 'cite'` — the string — next to the atom
it was compared against. That is the whole content of their mistake, on one
line, in their own vocabulary.

Tests: `tests/test_predicate_class_as_term_value.py` (19).

### What this deliberately did *not* decide

The reduced goal still *fails*, and reasonable people would expect it to
succeed: `functor/3` decomposition hands back the functor name of a with-fields
term as a **string**, but hands back an arity-0 atom as the **class**. So
`functor(cite(K), N, A), N is cite` cannot succeed while
`functor(some_atom, N, A), N is some_atom` can. That asymmetry is very likely
what the test's author was relying on, and it is a semantics question, not a
crash. Changing it would move `functor/3`, `unpack/2` and ISO conformance
together, so it is filed separately as
[[functor-3-names-an-atom-as-a-class-but-a-compound-as-a-string]] rather than
guessed at here.

### Second sighting

[[done/arity-mismatch-reports-a-missing-trail-argument]] (fixed 2026-07-29) was
the same sentence — `citation__3() missing 1 required positional argument:
'trail'` — from a completely different seam: a wrong-arity *call* rather than a
class-valued *term*. Two independent engine faults have now surfaced as "a
missing `trail`". Worth treating any user-visible Python `TypeError` that names
`trail` as an engine fault by default, since `trail` is not a word the surface
language has.
