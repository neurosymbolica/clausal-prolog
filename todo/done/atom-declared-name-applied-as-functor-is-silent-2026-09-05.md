# An atom-declared name applied with arguments compiles to `Call(func=<str>)` and fails SILENTLY

**Status: OPEN.** Severity: high (silent) — the two silent classes the P3-1/P3-2
reviews promised were fail-loud both show up here.

Found 2026-09-05 while probing the clausify peer's N3 question (keyword-field matching
after the cell flip — that WORKS; see /workspace/clausify/ATOM-FINDINGS-FOR-clausal-c3.md).
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
