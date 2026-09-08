# An atom-declared name applied with arguments compiles to `Call(func=<str>)` and fails SILENTLY

**Status: OPEN.** Severity: high (silent) — the two silent classes the P3-1/P3-2
reviews promised were fail-loud both show up here.

Found 2026-09-05 while probing a downstream peer's question (keyword-field matching
after the cell flip — that WORKS; see the peer's findings note).
Observed on `feat/p33-state-reloc` @ `0b8c2937` = clone main `d0f2bad5` + P3-3 T1/T2
(neither task touches this path). Almost certainly a P3-1 artifact: before the pivot a
`-private` atom was a class and applying it raised; now it is a `str`, and the compiler
emits `Call(func='bound2', …)` with a bare string func that nothing downstream refuses.

## Reproduction

```
-module(p2, [c(X), wrap(G)])
-private([bound2])          # bound2 is an ATOM, not a functor

c(wrap(G))   <- (G is 1)    # declared functor → ('wrap', 1)         OK
c(bound2(G)) <- (G is 2)    # atom applied as 1-ary functor → NO SOLUTION, no error
c(4)
c(Y) <- (Y is bound2(5))    # body position → Y = Call(func='bound2', args=[5])  LEAKS the AST node
```

`call("c", X)` yields `[('wrap', 1), 4, Call(func='bound2', args=[5], kwargs=[])]`.
Compare `c(undeclared(G))` (name declared nowhere): loud `NameError: Predicate
'undeclared/1' is not in scope as a term class` — the right behavior, one row over.

Compiled clause (from `db._clauses[("c",1)]`):
`Clause(head=c(X=Call(func='bound2', args=[AttVar(_1)], kwargs=[])), …)` — `func` is the
plain atom string where the declared-functor row has `LoadName(name='wrap')`.

## Why it matters

- Head position: the clause is present, indexes, and never matches → a "total" predicate
  silently loses a case. This is exactly the silent-flip class the answer-level A/B was
  built to catch, and it is one typo away from any domain file (`verdict` declared as an
  atom in one module, used as `verdict(...)` in another).
- Body position: a compiler AST node escapes into user data.

## Proposed fix (decide, then do)

Compile-time error in the head_match/term_to_ast placer when a name resolves to an ATOM
(registry says arity 0 / `-private`/`-module` bare entry) but is applied with N>0 args:
"`bound2` is declared as an atom; to use it as a functor declare `bound2(G)` in `-module`
(or enable `-implicit_functors`)". Under `-implicit_functors` it should instead lower to a
cell `('bound2', G)` like any OWA functor. Either way `Call(func=<str>)` must never be
emitted. Pin both positions (head + body) and the `-implicit_functors` variant.

Natural home: P3-3 T4 (closure/head_match code is open) or a standalone hotfix if a
domain hits it first. Probe files: scratchpad `n3probe/p2.clausal` + `run2.py` (session
ff7d2f98).

## Resolution (2026-09-05, P3-3 Task 4)

**Status: CLOSED — fail-loud at load time.** Fixed under the controller's
cheap-pass ruling for Task 4 (≤ ~30 lines including its test; the fix is 20
lines of implementation plus 2 tests).

`TermTransformer._visit_call_func` (`clausal/templating/term_rewriting.py`) —
the ONE place a Call's func position is visited, which is why the check lives
there and not at each of the several `visit_Call` branches — now raises a
`SyntaxError` when the func is a bare `Name` whose identifier is a declared
atom (`transformer.atoms`, i.e. a bare name in `-module` or a `-private`
entry, or `transformer._hidden_atoms` for a `-hide`-en one). The message names
the atom, its site, and the remedy: declare it with arguments in the `-module`
functor list.

Refusing in the func-position visitor is what makes `Call(func=<str>)`
unconstructible rather than merely diagnosed downstream: `visit_Name`'s atom
branch still answers a declared atom with its `str` spelling everywhere else,
which is correct in every position but this one.

Both positions from the repro are pinned:
`tests/test_atom_diagnostics.py::test_an_atom_applied_as_a_functor_is_refused_at_load`
(head position — the silently unmatchable clause) and
`::test_an_atom_applied_as_a_functor_in_a_body_is_refused_too` (body position
— the AST node leaking into user data).

Not done, deliberately: the `-implicit_functors` variant this todo proposed
("lower to a cell `('bound2', G)` like any OWA functor"). The transformer
carries no `-implicit_functors` state — the directive compiles to a
module-level `__clausal_implicit_functors__` the COMPILER reads — so threading
it into `TermTransformer` is a larger change than the cheap pass allowed, and
raising is strictly better than the silent behaviour either way. Whoever wants
that lowering has a loud error pointing at the exact site to start from.

## Fix round 1 amendment (2026-09-05) — scope of the closure, stated exactly

Two corrections to the Resolution above, both from the Task 4 review.

**1. A dual-declared name applies as the FUNCTOR (review I-1).** The first cut
refused on atom-set membership alone, which broke a legal and live
configuration:

```
-module(c2, [dual, dual(G), c(X)])   # 'dual' declared as BOTH atom and functor
dual(1),
c(X) <- dual(X),                     # refused, prescribing the declaration line 1 has
```

`_visit_call_func` now bypasses the atom branch for a name that is also
declared as a functor — locally (the EmbedTransformer's live `_seen_functors`,
threaded into `TermTransformer` as `_declared_functors`) or by `-import_from`
(`_import_remap`, emitting the DOTTED reference) — and emits the functor
reference `visit_Name` cannot reach, because its atom test runs before its
import-remap and fallthrough branches. The refusal is left for a name declared
as an atom and NOT as a functor. A `-hide`-en name can never be dual-declared
(`_register_functor` refuses that collision head-on), so it always refuses.

The `-import_from` half fixes a second live instance of this same silent bug:
`-private([wrap])` + `-import_from(owner, [wrap])` + `c(wrap(1))` emitted
`Call(func='wrap', …)` before and emits `LoadName(name='owner.wrap')` now
(verified against the branch base `dd0a8ad2`).

**2. What is NOT closed (review M-1).** The todo's headline CROSS-MODULE case
is still open:

```
owner:     -module(owner, [verdict, …])          # 'verdict' is an atom here
importer:  -import_from(owner, [verdict])
           c(verdict(1)),
```

The importer's own atom set does not contain `verdict` (an `-import_from`
records the name in `_import_remap`/`_imported_functors`, never in `_atoms`),
so this check cannot see it. The importer LOADS and fails at the first call
with `TypeError: 'str' object is not callable` raised from `<template>` —
verified on this branch after the fix. That is LOUD, so it is out of the silent
class this todo was filed for, but it is unlocated: no file, no line, no name
of the offending declaration.

So, precisely:

* **Covered:** same-module declarations — `-module` bare entries, `-private`,
  `-hide` — in head and body position, plus the dual-declared lowering above.
  An **import-shadowed** name is covered only when the imported name is a
  FUNCTOR in its owner: that case lowers to the owner's dotted reference and
  answers. When the imported name is an ATOM in its owner too, nothing
  declares it with arguments anywhere and it is a located refusal — see the
  fix-round-2 amendment below, which corrects this bullet's first wording.
* **Not covered:** applying an atom imported from another module. Loud but
  unlocated; would need the importer to consult the OWNER's registry (the
  signature registry knows `verdict` has no functor signature) at the
  `-import_from` site or at the call site. Filed here rather than reopened,
  since the silent-failure class the todo names is closed.
  **Superseded by fix round 2** — see below: this IS now covered, at compile
  time, with file:line, *when the file is loaded as a module*. Still NOT
  covered on the IPython/interactive entry path, which never reaches the pass
  that settles it — see the fix round 3 note at the end of this file.

## Fix round 2 amendment (2026-09-06) — the last two gaps

**Declaration order no longer decides (review O1).** The round-1 check read
the WALK-TIME functor set, so a functor established by a clause BELOW its
first use was invisible and a legal program was refused:

```
-module(ordA, [dual, c(X)])
c(X) <- dual(X),      # refused in round 1
dual(1),              # the functor, one line later
```

The decision is now deferred: `_visit_call_func` records the candidate and
emits the functor reference, and `EmbedTransformer.visit_Module` settles it
once the whole file has been walked. Both statement orders load and answer.

**The import bypass consults the OWNER (review O2).** Round 1 took the dotted
bypass on `_import_remap` membership alone, so a name that is an atom in its
owner TOO got the dotted lowering, loaded, and died at the first call with the
unlocated `TypeError: 'str' object is not callable`. The deciding fact is
whether the imported name carries a functor SIGNATURE — `-import_from` copies
the owner's registry entry across under the local spelling for a functor and
has nothing to copy for an atom — so the remaining candidates travel to
`compiler_v2._check_atoms_applied_as_functors`, which runs after the module
body (and therefore after the import and the signature copy) and raises the
located message built at the call site.

So the cross-module case listed as "not covered" above IS now covered, at
compile time, naming the owner:

```
tests/fixtures/t4f2_import_atom_shadow.clausal:9: `verdict` is declared as an
atom in `tests.fixtures.t4f2_owner_atom` and locally, but is applied as a
functor here.  Nothing declares `verdict` with arguments: declare it as
`verdict(X)` in `tests.fixtures.t4f2_owner_atom`'s -module functor list, or
reference it bare as the atom it is.
```

Pinned end-to-end with real owner + importer fixtures
(`tests/fixtures/t4f2_owner_functor.clausal`,
`t4f2_owner_atom.clausal`, `t4f2_import_functor_shadow.clausal`,
`t4f2_import_atom_shadow.clausal`) in
`tests/test_atom_diagnostics.py`, both directions.

## Fix round 3 note (2026-09-06) — one more entry path the imported half misses

Filed by the round-3 review; **no fix now**, recorded so nobody reads the
round-2 amendment as "closed everywhere".

The IPython/interactive entry path (`clausal/import_hook.py`,
`_FreshEmbedTransformer.visit`, ~1047-1051) runs a fresh `EmbedTransformer`
over each cell and returns the rewritten tree. It never reads
`_module_items` and never calls `compile_module`, so
`compiler_v2._check_atoms_applied_as_functors` — the pass that settles the
IMPORTED half of this check — does not run for an interactive cell.

Consequence, in a notebook/REPL session only:

```
-private([x])
-import_from(m, [x])
x(1)                  # still the unlocated runtime TypeError
```

The LOCAL half does fire there, because `EmbedTransformer.visit_Module`
raises during the rewrite the cell itself performs — so a cell applying a
plain `-private` atom that no clause declares as a functor is refused with
its line, exactly as in a file. Only the imported case is missed.

Fixing it means giving the interactive path somewhere to settle deferred
items after the cell's imports have run, which is a change to how the
interactive path works rather than to this check.
