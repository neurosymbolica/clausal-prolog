# `{}`/1 is not callable: `call({X > 1})` is an existence error

Found 2026-10-11.

```prolog
:- use_module(library(clpq)).
```

    clausal -g "{X > 1}" lin.clausal     ->  error(existence_error(procedure,{}/1),{}/1)
    G = {X > 1}, call(G)                 ->  the same

Both `.pl` front ends and Clausal Prolog lower `{C}` written in a clause body
to `clpq.rational(C)` at compile time; nothing defines `{}`/1 as a
predicate, so a brace goal built at run time (a toplevel goal, a meta-call,
`findall/3` over a brace goal held in a variable) has no definition.  Scryer
defines `{}/1` in library(clpq), so `G = {X > 1}, call(G)` answers `G = {X>1}, X>1.` (checked 2026-10-11).

Fix shape: a `{}`/1 builtin that posts its argument through the same path as
the compiled form, visible when the calling module imports library(clpq)
(without the import, `{}`/1 stays an ordinary undefined goal, as the native
front end rules today).
