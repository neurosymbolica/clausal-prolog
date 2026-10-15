# ISO Prolog Conformity

Clausal Prolog measures itself against the ISO/IEC 13211-1 standard, and
specifically against the conformity-testing work published by
**Ulrich Neumerkel**, the editor of ISO/IEC 13211-1 (the core standard) and
convenor of ISO/IEC JTC1/SC22 WG17, the working group that maintains it.
Where our behavior and his published tables disagree, we treat that as a bug
in Clausal Prolog, not as a difference of opinion. His
[conformity testing](https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing)
pages — syntax, DCGs/`phrase`, and the rest — are our **primary reference**
for what ISO actually requires in cases the bare standard text leaves hard to
pin down. They exist precisely because the standard alone under-determines
some answers; a test suite maintained by the person who wrote and still
edits the standard is the closest thing to ground truth a conformance effort
can ask for.

## Why ISO adherence matters

A language standard is a boring thing to get excited about until you need
one. For Prolog, ISO/IEC 13211-1 is what lets code, documentation, teaching
material, and programmer experience move between implementations instead of
being locked to one. That matters for reasons beyond taste:

- **Interoperability is the whole point.** The Prolog ecosystem is a
  federation of independent, long-lived implementations — SWI-Prolog, GNU
  Prolog, SICStus, Scryer, Ciao, ECLiPSe, and others — each with its own
  strengths and its own community. No single one of them "wins"; the
  standard is what lets a predicate written against the standard run the
  same way everywhere, and lets knowledge ("how does `sub_atom/5` behave at
  its edges?") transfer between systems instead of having to be relearned
  for each one. A new implementation that conforms adds to that shared
  ground instead of fragmenting it further. This is Clausal Prolog's main
  rationale for caring about ISO at all: conformance work here is not just
  self-interest, it is a (small) contribution back to interoperability that
  benefits every conformant Prolog, not only this one.
- **Conformance is falsifiable; vibes are not.** "Behaves like a real
  Prolog" is not a testable claim. "Behaves as ISO 13211-1 §8.6.1 specifies
  for `is/2`" is — you can write the test, run it against the standard's own
  worked examples or against Ulrich Neumerkel's tables, and get a yes or no.
  That is what makes a conformance effort an actual engineering activity
  rather than an aspiration.
- **It disciplines error handling, not just happy paths.** Most of what the
  standard pins down precisely is *failure* behavior: which exact error term
  a given misuse raises, in which argument-checking order, with which
  culprit. That is exactly the part of a language implementation that is
  easiest to get subtly wrong and hardest to notice getting wrong, because
  the "normal" cases keep working regardless. Chasing ISO conformance is, in
  large part, a forcing function for getting that long tail right.
- **It is a form of respect for the people who did the hard part already.**
  Decades of implementation experience and committee work went into
  resolving the standard's edge cases (what should `char_code(X, -1)` raise?
  does `[a|b|c]` mean anything?). Reinventing those answers from scratch
  invites reinventing their mistakes too. Conforming where ISO has already
  decided something lets Clausal Prolog spend its own design effort on
  problems ISO genuinely doesn't cover.

## What this applies to, and what it deliberately doesn't

Clausal Prolog's native `.pl` front end is the part of the engine this effort
is about: a reader, writer, and solver aiming to behave as ISO 13211-1
specifies for every builtin it offers, and — where ISO itself is silent or
leaves something implementation-defined — to make a documented, deliberate
choice rather than an accidental one.

`.clausal` (Clausal Prolog proper) uses ISO Prolog *syntax* but is a
**deliberately restricted** dialect: no cut, no if-then-else, no committed
choice. That restriction is not a conformance gap to be closed — it is a
considered design decision (see [Purity and Monotonicity](purity.md)) in
service of a different goal: keeping every `.clausal` predicate monotonic,
so that formalized rules (law, policy, business logic) compose safely and
stay explainable under the guarantees described in the project's
[goals](goals.md). `.clausal` and `.pl` share the same ISO-grammar parser and
writer, so syntax-level conformance work on one benefits the other, but a
`.clausal` program will never gain `!/0` by design, regardless of how
conformant the underlying reader becomes.

For the detailed, continuously-updated list of what conforms today and what
doesn't, see the
[ISO Prolog Compatibility Report](iso_prolog_compatibility_report.md). This
page is about *why* and *against what*; that one is about *where things
stand right now*.

## How we measure it

In rough order of authority:

1. **Ulrich Neumerkel's conformity-testing pages** — the primary reference,
   described above. When a page gives a definitive expected answer ("Codex"
   column), that answer wins, full stop.
2. **The ISO/IEC 13211-1 standard text itself** (plus its corrigenda),
   for anything the conformity pages don't cover directly.
3. **[Scryer Prolog](https://www.scryer.pl)**, a modern, actively-maintained
   ISO-conformant Prolog, as a practical, runnable cross-check — useful for
   confirming exact behavior (does this really raise an error, and which
   one?) and, where ISO leaves something genuinely open, as one example of a
   reasonable, real-world answer. Scryer is a tool for checking our work,
   not an oracle: where its behavior and Ulrich Neumerkel's own tables
   disagree, the tables win. (SWI-Prolog is popular but takes enough
   deliberate liberties with the standard that it is not used as a
   reference here.)
4. **Other published ISO-conformance test suites**, such as the one the
   [Ciao Prolog](https://github.com/ciao-lang/iso_tests) project maintains —
   genuinely useful for coverage (they test far more of the standard than
   any one hand-maintained page can), but treated as a secondary source: a
   good way to *find* candidate gaps, cross-checked against the standard
   text and, where it exists, Ulrich Neumerkel's own judgment before acting
   on them.

When these disagree, the order above is the tie-break, not a vote.
