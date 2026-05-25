# String Implementation Audit — Design Spec

**Date:** 2026-05-25
**Author:** Michael Amy (with Claude)
**Status:** Draft — pending user review before plan-writing

---

## Goal

Audit the Clausal string implementation under the contract *"a string is a list
of single-character strings"*, find the places where the implementation
diverges from that contract, and remediate them. Cover the core unification
surfaces, the `SegList` / `SegString` partial-string machinery, and the
integration points (polymorphic builtins, higher-order, DCG, term inspection,
indexing).

This is an audit-and-remediate effort: the deliverables include a written
findings ledger, an adversarial test suite, and per-class fix commits — not
just a report.

---

## Background

The strings-as-lists work landed in seven phases (see commits `b8d3038`
through `82ecc96`):

1. C-level `str ↔ list` element-wise unification (`_variables.c`).
2. `SegList` accepts strings as unification targets.
3. (Implied by phase numbering — not enumerated separately in commits.)
4. Polymorphic list builtins accept strings.
5. Higher-order predicates accept strings.
6. *(SegList-vs-SegList unification — not yet implemented; documented as
   "Phase 6" in code comments. Out of scope for this audit; if a finding
   depends on it, it's deferred.)*
7. `SegString` and string-preserving head pattern matching.

A follow-up fix commit (`82ecc96`) addressed two `SegString` bugs found during
review. The user's stated suspicion is that more bugs of similar character
exist, and that the unhappy-path / edge-case coverage is thin.

The audit scope and methodology are this spec's substance.

---

## Scope

### Core surfaces (in)

- `clausal/logic/variables/_variables.c` — the C `do_unify` `str ↔ list`
  branches and the `__unify__` protocol-hook ordering.
- `clausal/terms.py` — `SegList`, `SegString`, `VarSeg`, `ConcreteSeg` and
  their dunder methods (`__walk__`, `__unify__`, `__eq__`, `__hash__`,
  `__occurs_check__`, `__contains__`, `__add__`, `__radd__`), the generator
  helpers `_seglist_unify_gen` / `_segstring_unify_gen`, and
  `_multi_star_splits`.
- `clausal/logic/runtime/list_unify.py` — `_head_list_unify_input_py`,
  `_head_list_unify_output_py`, and the C-accelerated overrides exported by
  `clausal/logic/runtime/_list_unify.c`.
- `clausal/logic/runtime/body_star_unify.py` — `_body_star_unify`,
  `_body_multi_star_unify`, `_build_star_list`, `_build_multi_star_list`,
  `_in_iter`.
- `clausal/logic/compiler/head_match.py` — `head_to_match_pattern`,
  `_compile_multi_star_guard`, and the str/SegList normalisation gates inside
  the multi-star guard AST.
- `clausal/logic/compiler/goal_shallow.py` — `_head_has_deferred_pattern`
  (which drives whether continuation-TCO is safe for string-pattern clauses)
  and any body-path star handling in this file.

### Integration surfaces (in)

- `clausal/logic/builtins/lists.py` — every `was_str = isinstance(_, str)`
  site, plus the `_seq_result` helper. Covers `append`, `length`, `member`,
  `reverse`, `nth/get_item`, `take`/`drop`/`split_at`, `msort`, `last`,
  `select`, `permutation`, `flatten`, etc.
- `clausal/logic/builtins/higher_order.py` — `maplist`, `foldl`, `include`,
  `exclude`, `partition`, and any other predicates with `was_str` branches.
- `clausal/logic/builtins/dcg.py` — `phrase/2,3`, the `>>` expansion, and
  terminal/non-terminal handling of strings vs char-lists.
- `clausal/logic/builtins/chars.py` + `_chars_core.c` — `char_type`,
  `char_code`, single-char-str vs int representation of characters.
- `clausal/logic/builtins/type_checks.py` — `is_list/1`, `string/1`,
  `atom/1`, `var/1`, `ground/1` answers over strings / SegStrings.
- `clausal/logic/builtins/inspection.py` — `functor`, `arg`, `=..`,
  `copy_term` over strings.
- Compiler first-arg indexing — first-arg bucket assignment for clauses with
  string-shaped head args (file location to be found during Phase 0).

### Past-issue sources (in)

- `git log` filtered to commits touching the in-scope files (especially
  `fix(...)` commits and the `Phase N:` series).
- In-repo planning documents at the repo root: `todo/`,
  `implementation_plans/`, `MIGRATION_STATUS.md`, `MIGRATION_TODOS.md`,
  `MIGRATION_CANDIDATES.md`, `DUPLICATE_TESTS.md`.

### Out of scope

- REPL printing / portray / listing format (consulted only if a finding
  traces back to a representation invariant violation).
- `tools/`, `prolog_emit`, `pythonic_ast`, `prolog_backends/`,
  `clausal-*` extension packages.
- Performance work beyond what a correctness fix incidentally requires.
- API redesign or rename of `SegList`/`SegString`.
- New strings-as-lists features (e.g. `SegList`-vs-`SegList` unification —
  if it surfaces as a missing feature it gets a `wontfix: deferred` ledger
  entry, not a fix).

---

## Issue-class taxonomy

The audit hunts for instances of these classes. Each Phase 0 finding is
tagged with one class + a severity (`bug` / `design-gap` / `smell` /
`doc-only`).

### C1 — Type preservation across the str↔list boundary

Operations that consume a `str` should return a `str` (or vice versa) when
the contract demands it; the implementation often returns `list` instead.
Concrete suspects already visible in source:

- `_head_list_unify_output_py` (list_unify.py:165) builds `result` as a
  `list` unconditionally, even when the deferred-output target was a string.
- `_build_star_list` (body_star_unify.py:50–126) falls back to `list`
  whenever any element isn't a 1-char str — possibly too conservative.
- `SegList.__walk__` (terms.py:227–234) expands a VarSeg-bound substring
  into a char list, losing the str-ness of the binding.
- `SegList.__unify__` against `str` (terms.py:320–322) compares
  `walked == list(other)`, discarding str-ness.
- Class-wide question: what is the *rule* — input-type wins, ground-input
  wins, or "str iff every element is a 1-char str"? Inconsistency is itself
  a bug.

### C2 — Non-deterministic unification collapsed to first solution

`_seglist_unify_gen` and `_segstring_unify_gen` enumerate all valid splits,
but `SegList.__unify__` / `SegString.__unify__` consume only the first
(`for _ in ...: return True`). So `[*A, *B] = "ab"` succeeds with `A=""` /
`B="ab"` and never offers the two other splits. Compare with the head/body
multi-star unification paths, which *do* backtrack via compiled for-loops.
This is a logic-semantics violation, not a type bug.

### C3 — SegString blind spots vs SegList

Codepaths that handle `SegList` don't have a `SegString` twin. Suspects:

- `_head_list_unify_input_py` walks SegList (list_unify.py:114–117) but
  doesn't walk SegString.
- `_compile_multi_star_guard` emits a SegList-normalise branch
  (head_match.py:857–872) but no SegString-normalise branch.
- `SegString.__unify__(list)` only works when the SegString is ground;
  `SegList.__unify__(str)` handles non-ground.
- SegList-vs-SegList and SegString-vs-SegString both return `NotImplemented`
  (terms.py:328–329, 574–575). Per scope, this is `wontfix: deferred`.

### C4 — Head-pattern literal mismatch

A clause `Foo("abc")` compiles to `MatchValue(Constant("abc"))`, which only
matches the *exact* string `"abc"`. A caller invoking `Foo(['a','b','c'])`
— which unifies with `"abc"` elsewhere in the system — silently misses
this clause. Symmetric concern for `Foo(['a','b','c'])` heads called with
`"abc"`. Possibly the largest-blast-radius finding; needs probe before any
fix is attempted.

### C5 — Hash / equality / identity asymmetries

- `SegList.__hash__` raises `TypeError` unconditionally (terms.py:376–378).
- `SegString.__hash__` returns `hash(walked)` when ground, `id(self)`
  otherwise (terms.py:589–591).
- `SegList.__eq__` rejects `str` (terms.py:366–374); `SegString.__eq__`
  accepts `str` (terms.py:581–587).
- Cross-type equality: `"abc" == ['a','b','c']` at Python level vs `unify`
  level vs Prolog `==` — what are the answers, and are they internally
  consistent?

### C6 — Hashable vs unhashable bridges

Strings are hashable, lists are not. Anywhere a builtin uses `set` / `dict`
keyed on terms (memoisation, `setof`/`bagof`/`distinct`, tabling, dict
literals), a string and the equivalent char-list become distinct keys even
when they unify. Tabling is the high-impact case: a tabled predicate
called once with `"abc"` and once with `['a','b','c']` — one subgoal or
two?

### C7 — Unicode / multi-codepoint corner cases

C-level unify uses `PyUnicode_GET_LENGTH` (code-point count) and
`PyUnicode_READ_CHAR` (one code point at a time). Behaviour to confirm:

- Grapheme clusters (base+combining vs precomposed `"é"`).
- Surrogate halves in str (invalid but constructable).
- Multi-codepoint emoji (`"👍🏽"` has multiple code points).
- Zero-width joiners.
- List element that is itself a multi-codepoint string (e.g.
  `["ab", "c"]` vs `"abc"`) — currently rejected; document the rule.

Likely correct at the code-point level but possibly surprising; the audit
documents the contract and ensures it's consistent.

### C8 — Partial-term short-circuits / silent failure

Code paths that meet a non-ground SegList/SegString return `False` or
`NotImplemented` instead of constraining or suspending. Examples:

- `_head_list_unify_input_py` returns `False` on non-ground SegList
  (list_unify.py:116–117).
- `SegString.__unify__(list)` returns `NotImplemented` for non-ground
  (terms.py:565–573).
- `_in_iter` calls `iter(collection)`, which routes through
  `SegList.to_list()` (terms.py:285–292) and raises `TypeError` on
  non-ground.

These create *quiet* logical incompleteness — programs produce fewer
answers than they should without an error.

### C9 — Mode / direction asymmetry in polymorphic builtins

Every polymorphic builtin (`append/3`, `length/2`, `member/2`, `reverse/2`,
`nth/3`, `take/3`, etc.) has multiple modes. Audit the matrix:

- `(str, str, str)`, `(str, str, Var)`, `(Var, str, str)`,
  `(str, list, ?)`, `(list, str, ?)`, etc.
- `length(L, 5), L = "hello"` — does L get bound to a 5-element list of
  vars first, then re-unified with `"hello"`?
- `(Var, int)` modes have no input type to switch on — what does the
  builtin return?

The audit enumerates the modes for each builtin and tests the mode matrix.

### C10 — DCG / `phrase` interaction

DCGs thread a difference-list through goals. With strings, the threading
variable can be Var, str, or list at different points.

- `phrase(g, "input", Rest)` — is `Rest` a str or a list? Is the type
  preserved across the threading?
- `phrase(g, S0, S)` with `S0` a Var — what gets bound?
- Pushback `[X | S]` semantics over a string-mode input.
- Terminal `[a, b]` in a DCG rule matched against a string body.
- The `dcg.py` `isinstance(..., str)` branches (lines 18, 49, 81, 85,
  89–100) cover the easy cases — confirm they cover all cases.

### C11 — Trail / backtracking around partial structures

`_seglist_unify_gen` marks the trail before each yield and undoes after,
but `SegList.__unify__` returns on the first yield without undoing,
leaving the first split's bindings on the trail. This is intentional (the
chosen split becomes the result), but fragile: a caller that re-unifies
the same SegList against another value while still holding the first
split exercises a code path that assumes a fresh trail mark. Audit
whether the caller contract is sound and whether any builtin violates it.

### C12 — `char` representation drift (1-char str vs int code)

Strings-as-lists fixes the *container*; the *element* type also matters.
`member(C, "abc")` binds `C` to a 1-char str. Then `C + 1` (arithmetic)
fails. Then `[C] = "a"` works. Audit which char-aware builtins assume
int codes vs 1-char strs, and whether the boundary is consistent.

### C13 — Type-check predicates returning surprising answers

The strings-as-lists contract commits us to specific answers for type
checks; audit what they actually return:

- `is_list("abc")` — true or false?
- `string([a,b,c])` — true or false?
- `atom("abc")` — Prolog ambiguity (SWI says yes, others no).
- `ground(SegString_with_bound_vars)` — true.
- `var(C)` after `member(C, "abc")` — false.

### C14 — Term inspection drift

- `functor("abc", F, A)` — `F="abc", A=0` (atom-like) or `F=., A=2`
  (cons-cell view)?
- `"abc" =.. L` — what is `L`?
- `copy_term("abc", X)` — shares or copies?

Each builtin has a defensible answer; the audit documents what it actually
does and aligns with the contract.

### C15 — Indexing / dispatch on string head args

The compiler's first-argument indexing routes calls by clause head shape.
If `Foo("abc")` and `Foo(['a','b','c'])` end up in different buckets, a
call with the "wrong" container misses half the clauses. This is the
dispatch-time analogue of C4.

### C16 — Free-threaded build safety

`_variables.c` uses `FT_CS_*` critical-section macros in places. The
str↔list unify path (lines 1127–1179) doesn't acquire any visible. PyUnicode
is immutable so reads are safe, but `var_deref` and `do_unify` recursion
follow the bind chain — confirm the str↔list addition didn't open a hole
under the FT model. Limited to static review + targeted stress; residual
uncertainty documented.

---

## Methodology

### Phase 0 — Read-only audit + class enumeration

For each in-scope file, walk every relevant function and tag each finding
with `(class, severity, file:line, one-line reproducer)`. Findings go into
a single ledger at
`docs/superpowers/audits/2026-05-25-string-implementation/findings.md`,
grouped by class, sorted by severity within class.

Severity vocabulary:

- `bug` — the code produces a wrong answer, crashes, or silently drops
  solutions in a way the contract forbids. Must be fixed unless `wontfix`
  with rationale.
- `design-gap` — the contract itself is under-specified for this case; the
  code's current behaviour is defensible but inconsistent with sibling
  cases. Fix usually means picking a consistent rule and aligning all
  sites.
- `smell` — code that works but invites future bugs (asymmetric handling,
  duplicated invariants, magic-number splits). Optional fix.
- `doc-only` — the implementation is correct; `docs/strings_as_lists.md`
  or a code comment is wrong or missing.

Mine `git log` for `fix(...)` and `Phase N:` commits touching the in-scope
files; pull unresolved items from `todo/`, `implementation_plans/`, and
the `MIGRATION_*.md` files. Cross-reference these as "prior-known"
findings in the ledger.

Phase 0 exit criteria:

- Every in-scope file has been walked.
- The ledger is cross-referenced (no duplicate findings).
- Every class has at least one verdict — including "no instances found".

### Phase 1 — Adversarial tests per class

One new test file per class with findings:
`tests/audit_2026_05_25/test_class_C<N>_<topic>.py`. Each test names the
ledger finding it covers.

Test pattern:

- Wrong-output finding → assert the *correct* output, mark
  `xfail(strict=True, reason="ledger F<N>")`.
- Crash/exception finding → same, with `raises=...`.
- Silent-incompleteness finding → enumerate all solutions, assert the
  expected count, `xfail` on the count.

A `tests/audit_2026_05_25/conftest.py` documents that pre-fix every
test here is intentionally failing.

Phase 1 exit criteria:

- Every `bug` / `design-gap` ledger finding has at least one test.
- `smell` findings get tests when cheap; otherwise stay ledger-only.

### Phase 2 — Fix class-by-class

One commit per class (or per subclass if a class fragments). Order by
fix-blast-radius ascending — self-contained classes first (C2
non-determinism, C5 hash/eq asymmetry), cross-cutting ones last (C4
head literals, C9 polymorphic mode matrix). Each commit:

1. Implements the fix.
2. Flips xfails for that class to passing (remove `xfail` markers, keep
   tests).
3. Runs the full pre-existing test suite — zero regressions.
4. Updates `docs/strings_as_lists.md` if the user-visible contract moved.
5. Updates the ledger entry: `open` → `fixed in <sha>` or
   `wontfix: <reason>`.

`wontfix` is reserved for findings where the audit concludes the current
behaviour is correct (e.g. a C7 grapheme finding where code-point
semantics are intentionally retained). Every `wontfix` carries a
one-paragraph rationale.

### Phase 3 — Sweep

Re-run Phase 0 (read-only) on the now-fixed code. New findings get
appended to the ledger as Phase 3 items, triaged into fix vs todo. Then a
cross-class consistency pass: did any class-N fix break a class-M
assumption?

### Tooling and verification

- `pytest tests/` (existing) plus `pytest tests/audit_2026_05_25/`.
- Rebuild C extensions (`pip install -e . --no-build-isolation`) whenever
  `_variables.c`, `_list_unify.c`, or `_chars_core.c` change.
- Optional property-based reinforcement (time permitting): hypothesis
  strategies for `(str, list)` round-trips on each builtin, generated
  from the C9 mode matrix.

### When the auditor pauses for user input

- Before any change that alters a user-visible Clausal contract (e.g.
  "we're deciding to make `[H|T] = "abc"` bind `T` to `"bc"` instead of
  `['b','c']`").
- Before any `wontfix` decision on a finding the user might disagree
  with.
- If C4 confirms with large blast radius — escalate to a separate spec
  rather than rolling it into this audit.

Otherwise: proceed without per-step gates.

---

## Deliverables

- `docs/superpowers/specs/2026-05-25-string-implementation-audit-design.md`
  — this spec.
- `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
  — the ledger (built in Phase 0, updated through Phase 3).
- `tests/audit_2026_05_25/test_class_C<N>_*.py` — adversarial test files
  (one per class with findings).
- One commit per fix in Phase 2; one summary commit at the end of Phase 3.
- Updates to `docs/strings_as_lists.md` wherever contract clarifications
  land.

## Success criteria

- Every in-scope source file has been read and tagged in the ledger.
- Every `bug` or `design-gap` finding has either a green test + a fix
  commit, or a `wontfix` entry with rationale.
- The full pre-existing test suite passes after each Phase 2 commit.
- Phase 3 sweep finds zero new `bug`-severity items.
- `docs/strings_as_lists.md` reflects the post-fix reality on every
  contract it documents.

## Risks

- *Ledger growth.* 50+ items plausible. Mitigation: class-grouping keeps
  reading tractable; per-class commits are individually reviewable.
- *Cross-class regression.* A class-N fix may break a class-M assumption.
  Mitigation: Phase 3 cross-class consistency pass; every Phase 2 commit
  runs the full suite.
- *C4 blast radius.* Head-literal mismatch fix may touch the compiler
  and thousands of existing clauses. Mitigation: confirm with a probe
  first; if large, escalate to a separate spec rather than rolling it
  in.
- *Contract drift vs user intent.* Audit conclusions may disagree with
  the user's intended contract. Mitigation: the "pause before user-visible
  contract change" rule in Phase 2.
- *FT safety hard to test.* Free-threaded build (C16) is hard to stress
  on a single-threaded harness. Mitigation: static review + targeted
  stress; document residual uncertainty.

---

## Non-goals (explicit)

- No API or naming changes to `SegList` / `SegString`.
- No performance work beyond what a correctness fix incidentally requires.
- No new strings-as-lists features; `SegList`-vs-`SegList` unification
  (the documented "Phase 6") is `wontfix: deferred` if it surfaces.
- No remediation of issues outside the in-scope file list beyond ledger
  notes.
