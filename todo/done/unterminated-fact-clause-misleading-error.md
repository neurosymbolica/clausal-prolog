STATUS: DONE (2026-07-20). Fixed: trailing comma made optional for declared
bodyless facts (Part A) + terminator-specific diagnostic for the undeclared
case (Part B). `EmbedTransformer.visit_Expr` now rewrites a bare declared
`Call`/`Name` into a fact (gated on `_seen_functors` AND module-compile mode),
and wraps an undeclared bare call so an undefined functor raises a
"missing trailing ','" hint via `$unterminated_fact_error`. This also fixed a
latent silent-drop: a comma-less FINAL fact in a block (`counter(2)` etc.) was
silently discarded in ≥9 corpus fixtures — those clauses now land.
Feature commits 351222ee..1102171d (merge 498c1614); Fable-review follow-up
dbc90856 confined the rewrites to module compilation (REPL echo regression) and
bumped CLAUSAL_BYTECODE_TAG. Design: docs/superpowers/specs/2026-07-20-optional-fact-comma-design.md.

---

# Bug: un-terminated bodyless fact clause reports a misleading `name '<x>' is not defined`

**Filed:** 2026-07-20 (from clausify-domains work; run under `PYENV_VERSION=3.13.3`)
**Severity:** DX / error-reporting (no incorrect results — it fails to load, but with a message that points at the wrong thing)

## Summary

A **bodyless fact clause** (a head with no `<- (...)` body) that is **not terminated with a trailing `,`** causes the loader to mis-parse, and the reported error names an arbitrary token from the mis-parse — typically `name '<variable>' is not defined` or `name '<predicate>' is not defined` — instead of a clear "unterminated clause" diagnostic. Rules (`head <- (body)`) do **not** need a terminator, so mixing an un-terminated fact in among rules is an easy and very confusing mistake.

Note: `_`, named-underscore variables (`_ATOM`), and Python-style booleans (`True`/`False`) all work **correctly** in fact-head position once the clause is comma-terminated — so this is NOT an underscore/variable/boolean bug. It is purely the missing-terminator parse + misleading error.

## Repro (canonical)

```
-module(r1, [ p(A, B), q(A) ])
-strict_atoms
p(_, 1)
q(X) <- ( p(X, 1) )
Test("t") <- ( q(9) )
```
Run: `PYENV_VERSION=3.13.3 python3 -m clausal.testing r1.clausal`
**Actual:** `r1.clausal::<load> — name '_' is not defined`
**Expected:** either accept it, or report something like `unterminated clause near 'p(_, 1)' — add a trailing ','`.

Adding the comma fixes the parse:
```
p(_, 1),
q(X) <- ( p(X, 1) )
```

Variant (un-terminated fact before a `Test`) reports the *predicate* name instead:
```
-strict_atoms
p(_ATOM, 1)
Test("t") <- ( p(9, 1) )
```
→ `name 'p' is not defined`.

## Confirming the three sub-behaviors are fine (all pass with the comma)

```
-strict_atoms
f(_, 1),        Test("bare _ in fact head")        <- ( f(9, R), R == 1 )   # PASS
g(_ATOM, 1),    Test("_ATOM is a variable")         <- ( g(9, R), R == 1 )   # PASS
b(True),        Test("Python True literal")         <- ( b(X), X == True )   # PASS
```

## Why it matters

Facts and rules routinely coexist in one module (e.g. a lookup fact beside its accessor rule). Because rules need no terminator but bodyless facts do, dropping the fact's comma is a natural slip — and the resulting `name '_' is not defined` sends you hunting for an atom-declaration / variable problem that does not exist. This cost multiple debugging cycles in the clausify-domains `resolve.clausal` work (and independently tripped a second author on a `..._profile({...})` fact).

## Suggested fix

Detect an un-terminated bodyless clause at parse time and emit a terminator-specific diagnostic (clause text + "add trailing ','"), rather than letting the mis-parse surface as a downstream `name '…' is not defined`. (Alternatively: accept a newline/EOF-terminated bodyless fact the way rules are accepted, making the terminator optional and symmetric.)
