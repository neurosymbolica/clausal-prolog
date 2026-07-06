# investigate-A05: two parked constraints-core design decisions (needs USER, not Opus)

**Parked per the standing user instruction 2026-07-05** (design questions are
recorded, not asked interactively). These are policy calls that shape fix
todos; do not implement the affected fixes in a direction-sensitive way
before they are answered. Full context:
`docs/superpowers/audits/2026-07-05-fable-partition/05-constraints-core/design-questions.md`.

## 1. A05-D001 — cross-type truth in the dif/reify layer (blocked on A01-D001)

Because `unify` uses Python `==` for atomics, the whole constraint layer
inherits cross-type equality: `dif(1, 1.0)` and `dif(1, True)` are False
("cannot be different"), `reify_eq(1, True)` is True, `eq(1,1,1)` and
`eq(1,2,0)` succeed (the truth var unifies with 1/0), and
`structural_eq(1, 1.0)` / `structural_eq(True, 1)` are True even though
`docs/constraints.md` calls structural_eq "Prolog ==/2".

Options: (a) keep strict unify-consistency and fix the docs (structural_eq
= "unifiable with zero bindings"); (b) strict identity in dif/structural_eq
— **unsound**, dif would call terms "different" that the engine unifies;
(c) endorse Python `==` everywhere and rename structural_eq.
**Recommendation: (a) now**; the only real decision is A01-D001's (what
unify itself does) — dif/reify_eq must inherit it verbatim either way.
Whatever A01-D001 decides for bool/int, re-run
`tests/audit_2026_07_05/test_05_constraints_core.py` — the reif truth-var
tests encode the current behaviour.

## 2. A05-D002 — engine-reserved attribute keys are user-writable

`put_attr/3` / `put_attrs/2` accept keys `"dif"`, `"fd"`, `"clpb"`,
`"real"`, `"units"` with arbitrary values, which then reach the solver
hooks. This is the direct trigger for the A05-F002 segfault, and even
after F002's validation it remains a silent-corruption channel (a
well-formed-but-bogus pair list changes dif's meaning). SWI avoids this by
module-scoping attributes; Clausal keys are global strings.

Options: (a) defensive validation in every hook + document keys as
reserved; (b) make put_attr/3 fail on hook-registered keys; (c) namespace
user attrs (`user.<key>`). **Recommendation: (a)** — (b) breaks
hand-posting constraints (legitimate advanced use), (c) is a breaking
rename. Validation is required anyway to close F002.
