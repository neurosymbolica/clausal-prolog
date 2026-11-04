# Asserting a cyclic term stores it, and the predicate then fails to compile

Filed 2026-11-04 (found in review of the fact-load work; the behaviour
predates it). Severity: low-medium: one cyclic assert makes the whole
predicate unusable until the clause is retracted.

## What / Repro

```prolog
:- dynamic(c/1).
go1 :- X = f(X), assertz(c(X)).
```

* `assertz(c(0)), c(0), go1` succeeds: the cyclic clause is STORED (the
  dispatch was compiled already, so the assert only invalidates it).  The
  next call, `c(_)`, recompiles and raises
  `error(resource_error(finite_memory), _)`, and so does every later call.
* `go1` with no compiled dispatch yet: the assert compiles at once and
  raises `resource_error(finite_memory)` from `assertz/1`, but the clause
  stays stored; `c(1)` then raises `existence_error(procedure, c/1)`.
* `retract(c(_))` removes it, and the predicate works again.

ISO 13211-1 has no cyclic terms, so it does not define this; other systems
were not checked.

## Options

* Refuse the assert before storing: `resource_error`/`representation_error`
  from `assertz/1`, nothing stored (an acyclicity check on the clause
  term; the clause is copied there anyway).
* Or store it and answer it: the clause table holds a fact as a term, and
  its head walk (`clause_table._plain`) is already bounded, so a cyclic
  fact could be kept as data and unified (the unifier is cycle-safe for
  eq/neq, see `l3-cyclic-unify-fix-covers-only-eq-neq-is-2026-10-15.md`).
