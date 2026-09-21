# The same name in both `-module` and `-private` is accepted silently

**Found:** 2026-07-30, while deciding
[[done/private-atoms-are-importable-contra-spec]]. Split out of it because it
is a *different* rule (mutual exclusion, not visibility) and deciding it was
not in that todo's scope.
**Severity:** low. Nothing is broken; the question is whether the permissive
behaviour should be blessed, warned about, or enforced.

## What the docs said, and what happens

`implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md` and
`docs/directives.md` both said:

> An atom may not appear in both `-module` and `-private` (mutually exclusive
> points on the same axis); the compiler rejects this with a hard error.

It does not. `_process_declarations` walks `module_items` in order and only
mints a fresh class when the existing binding is absent or is the process-global
default; the first listing therefore wins and the second is a no-op. The name
gets exactly one module-local class either way, and load order does not change
the outcome. No error, no warning.

Measured with `-module(dbl, [tag_x])` + `-private([tag_x])` and with the two
directives in the opposite order; both load clean and yield a single
module-local class.

Both docs were corrected on 2026-07-30 to describe what happens. They no longer
claim an error that does not exist — but nobody has decided whether the
*silence* is right.

## Who relies on it

A downstream helper library lists eight names in both lists on
purpose: `absent`, `assessment`, `attribute`, `item`, `labels`, `unknown`,
`unmet`, `value`. Its own comment explains why:

> These same functors are ALSO in the `-module` export list (they are the library's
> public data vocabulary ...). Declaring them here lets this library build them
> and match works across modules.

Vendored into a second downstream repo as well, so two copies. Plus a second
downstream helper module (`flip`) in both repos, and the in-repo fixture
`tests/fixtures/functor_reexport_vocab.clausal` (`flip`). Five files total.

## The question

Given that `-private` is now settled as an advisory surface marker and not a
barrier ([[done/private-atoms-are-importable-contra-spec]]), listing a name in
both lists is *contradictory documentation* rather than a semantic conflict:
the module is telling a reader both "this is my public vocabulary" and "this is
internal". The compiler cannot resolve that, but it could point at it.

1. **Bless it.** State that the second listing is a no-op and move on. Cheapest,
   but leaves five files saying two opposite things about the same names.
2. **Warn.** A one-line diagnostic naming the module and the overlapping names,
   suggesting the author drop whichever listing is wrong. Would fire on five
   known files, all of which look like they *meant* the `-module` listing and
   added `-private` to get the signature pre-registered — which suggests the
   real answer might be (3).
3. **Find out what the authors wanted.** The downstream helper library's comment implies the
   `-private` listing was added for a reason the author believed was necessary
   ("declaring them here lets this library build them"). If `-module` alone
   already gives signature pre-registration — it should, both lists go through
   the same `_register_functor` path — then the `-private` listings are
   redundant and can simply be deleted, and the question dissolves. **Check this
   first**; it may make the whole todo moot.
4. **Enforce.** Rejected pre-emptively: it breaks five shipped files for a rule
   with no semantic teeth.

## Not to be confused with

Whether `-private` names are importable. That was decided (they are) in
[[done/private-atoms-are-importable-contra-spec]].
