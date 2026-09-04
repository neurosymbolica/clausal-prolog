# Global-vocabulary collision tooling (parked design question)

Raised by the user 2026-09-04 while reviewing the P3-2 plan's R5 (cross-module
cell exchange): unease, from a large-system-maintenance background, about
globally-agreed atom/functor meanings post-P3-1 — "Python without imports."

## Assessment recorded at the time

- The declaredness half of Python's import guarantee SURVIVES the pivot:
  strict-atoms (undeclared bare atom = compile error), `-module` signatures,
  and checked construction (OWA off by default). Only spelling-identity went
  global. Erlang (global atoms + tagged tuples + structural match) is the
  industrial precedent that this scales under maintenance.
- Collisions manifest only as accidental unification where same-spelled data
  actually MEETS; predicates (behavior) stay module-local through P3-3.
  Residual real risk: generic/meta code over heterogeneous terms.
- A "default-local atoms" switch was considered and rejected: it is the
  pre-P3-1 design (measured footguns: -private double-declaration identity
  break, Phenomena A/B, unpicklable terms), it regresses to
  import-the-atom-everywhere the moment local atoms must cross a boundary,
  a switchable MODE would force every library to be correct under both
  semantics, and it breaks the ISO-compatibility driver (and, post-R2,
  literally means module-local string literals).

## Parked follow-ups (tooling, not semantics)

1. **Cross-module vocabulary lint**: warn when two modules declare the same
   functor spelling with different arities or field-name tuples.
   `Database.register_signature` (database.py:166) already warns on
   within-module signature conflicts — this generalizes it across module
   Databases (needs a process-wide registry or a post-load sweep; decide
   whether it runs at import time or as a `clausal-lint` pass).
2. **Vocabulary report tool**: enumerate a module's declared atoms/functors
   and every other module declaring the same spelling — makes the global
   namespace auditable the way an import list is.
3. **Convention doc**: `-hide` internal tokens (state-machine tags, sentinel
   atoms) by default; prefix vocabulary that deliberately crosses module
   boundaries (the Erlang convention). Belongs in the strict-atoms /
   `-hide` user docs shipped in P3-1 Task 8.

None of this blocks P3-2; item 1 is the highest-value and could ride any
later phase or land standalone.
