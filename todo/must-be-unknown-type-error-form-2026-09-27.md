# `must_be/2` with an unknown type raises `domain_error(type, T)`; Scryer raises `type_error(type, T)`

**Status: OPEN. Found 2026-09-27 during Compound retirement slice 2; not fixed.**

## Measured

    t(R) <- (catch((must_be(foo, 1), R is no_error), E, R is E)),

    Clausal (main 03f70a71):  R = error(domain_error(type, foo), must_be/2)
    Scryer:                    error(type_error(type,foo),must_be/2)

Scryer command (`library(error)` loaded):

    t(G) :- catch((G, write(no_error)), E, writeq(E)), nl.
    ?- t(must_be(foo, 1)).

## Notes

`must_be/2` is not in ISO 13211-1 core; it comes from `library(error)`. ISO
is silent, so the house rule is to follow Scryer. SWI answers
`existence_error(type, foo)`, a third form; it is not the reference.

Changing the error form changes what an existing `catch/3` pattern matches, so
grep for `domain_error(type` in catchers and tests before switching.
