# `@<`, `compare/3` and `=..` are still missing — date sites have nowhere to go

Found 2026-09-09. `feat/iso-compare-builtins-2026-09-09` delivers the ISO
arithmetic comparisons (`=:=`, `=\=`, `<`, `>`, `=<`, `>=`), unification and
identity (`is`, `=`, `\=`, `==`, `\==`) and the CLP family (`#=` …). It does
NOT deliver the standard-order comparators `@<`, `@>`, `@=<`, `@>=`,
`compare/3`, or `=..`.

That matters more than a scoping note usually would, because spec §3.3
designates exactly those as the answer to the defect that motivated the whole
line of work: the G3 red is `type_error(evaluable, date/3)`, and the spec's
words are "which is why dates need `@<`/`compare/3`".

## Consequences, concretely

- A date-comparing corpus site has NO correct spelling to migrate to yet.
  The branch's goal line ("so the measured `==` sites have spellings to
  migrate to") is true for the NUMERIC subset only.
- The spec §4 Task 3 lint must NOT be built to emit `@<` fix-its until this
  lands, or it will point sites at a predicate that does not exist.

## Why it was deferred, legitimately

Spec §6 flags a real design question: standard order over Decimal, Quantity
and DictTerm is not settled, and `compare/3` forces an answer for every pair
of types the engine can hold. That is a design decision, not an
implementation gap, and it deserves its own spec round rather than being
improvised inside a comparison-operators branch.

Next step: a spec round on standard order for the non-ISO term types, then a
plan. Until then, describe the comparison work as unblocking numeric
migration, not corpus migration.
