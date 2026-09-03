# HAND-OFF: design the token-layer formalism for the Phase 3 Prolog parser

> **DONE 2026-09-04.** Design: `toklex-token-formalism-design.md` (+ external version &
> PDF, shared with Markus Triska/Ulrich Neumerkel). Implementation:
> `toklex-implementation-plan.md`, executed on branch feat/toklex — compiler, ISO +
> clausal dialect specs, incremental driver with UTF-8 stage, DCG rendering verified
> under Scryer, and the hand-written tokenizer swapped for the generated one
> (empty full-suite name-diff).

**For the next Claude instance.** The user will direct you to design a formalism based on
this plan. Read this file, then `implementation_plans/tagged-tuple-term-representation.md`
§1b (atom/functor rulings) and §1c (the parser output interface contract) before doing
anything. This is DESIGN work first — present the design and get approval before
implementation. CLONE ONLY (/workspace/clausal-bug-fix); never touch /workspace/clausal.

## The task

Design a **formalism for writing the TOKEN layer** of a Prolog reader — something a
tokenizer can be *written in* and then *compiled to a DCG* — satisfying the requirements
below, and satisfying (or refining, with the user's approval) the L0 contract in §1c.
The TERM layer needs no formalism: ISO term syntax's variable part is precedence-shaped,
`op/3` is its grammar, and the existing runtime-mutable Pratt core handles it (see §1c).
Do not design a CFG/DCG for terms.

## Markus Triska's requirements (verbatim, via the user, 2026-09-03)

> "we need to find a good formalism to write it, something that is then complied to a DCG.
> it must be able to "peek ahead" to see whether the current token will be extended
>
> and be able to push characters to the stream, or remember that they were present, for
> the next token.
>
> it must be able to be used from streams that are not repositionable, like user input:
>
> in this case, it must be able to wait for more input"

Context: the user asked him whether a Prolog parser written in Prolog exists; he said it
is something that needs to be worked on. The formalism you design should therefore be
suitable for a Prolog-hosted implementation (compiled to a DCG) even though Clausal's
first implementation is the Python Pratt stack — the §1c contract is deliberately
formalism-agnostic so both can sit behind it.

## What exists (all paths in the clone)

- `clausal/tools/prolog_tokenizer.py` (487 ln) — hand-written, batch (whole source →
  token list). The thing the formalism would replace/generate.
- `clausal/tools/prolog_parser.py` (446 ln) — Pratt/precedence-climbing;
  `_maybe_apply_op_directive` mutates the op table mid-parse. Keep.
- `clausal/tools/prolog_operators.py` — mutable `OperatorTable`, ISO op/3 semantics
  (incl. op(0,·) removal, ISO 8.14.3.4), dialect defaults (SWI; check for Scryer).
- `clausal/tools/prolog_ast.py` — current P-node output (to be superseded by §1c's
  ReaderItem/cells contract).
- `tests/test_prolog_parse.py` — existing coverage; your design must not regress it.
- A Scryer checkout at /workspace/scryer-prolog — its reader is a reference for ISO
  tokenizing edge cases and for the char-list/String conventions (see the
  scryer-cell-interchange-codec todo).

## Design constraints and hints

1. **The maximal-munch invariant is the heart of it** (§1c L0): never emit a token that
   could still be extended by unseen input — `=` vs `=..`, `1` vs `1.5` vs `1.0e7`,
   `0'c`, quoted atoms with escapes and line continuations, block comments. The formalism
   must make this invariant *derivable from the token definitions* (e.g. via
   follow-set/extension annotations), not hand-maintained.
2. **Pushback must be expressible**: "push characters to the stream, or remember that
   they were present" — e.g. reading `1.` then seeing a non-digit means the `.` was
   end-of-clause, not a decimal point: two tokens, one char returned. The formalism needs
   a principled way to say this (bounded pushback? mark/commit?).
3. **Incrementality is a contract, not a stream capability**: NEED_MORE propagates when
   input is exhausted mid-token; no seeking ever. A DCG compilation target implies the
   formalism's state must be reifiable (freeze the lexer state between chunks —
   Triska-style DCG with explicit state threading, or a pure DCG over a partial list
   whose var tail IS the wait-for-more-input mechanism — note the elegance: a partial
   list with an unbound tail is exactly "a stream that can wait"; freezing on the tail
   var is the classic Prolog-native answer and worth first-class consideration).
4. **Phase 3 surface specifics** the token definitions must cover: bare + single-quoted
   atoms (quoted may contain anything writable — but NOT the reader-unwritable `-hide`
   separator, §1b: the reader REJECTS that character inside any atom token, quoted or
   not); double-quoted = char lists; `-hide`/`-tagged_terms`-style directive syntax as
   used in .clausal files (check how current .clausal directives are tokenized —
   `-module(...)` style, not `:- module(...)`; confirm against real fixtures).
5. **Deliverables of YOUR task**: (a) the formalism's design document (notation, semantics,
   the compilation scheme to a DCG, the incremental-state story, worked examples for the
   nasty tokens in #1/#2); (b) a decision on where it lives (Clausal-side generator vs a
   spec shared with the Prolog-in-Prolog effort); (c) an implementation plan. Get user
   approval between (a) and (c). The user may share the design with Markus Triska —
   write it to be readable outside this codebase.

## Process expectations (this project's established discipline)

- SDD with worktrees, task briefs, per-task review + final whole-branch review; baseline
  failure-set name-diffs (capture with `pytest tests/ -q --tb=no
  --continue-on-collection-errors` from the worktree, /workspace/clausal/venv/bin/python);
  build_ext --inplace in fresh worktrees AND in the clone root after merging C changes.
- NEVER `git add -A`; NEVER `git stash` (three violations logged; it keeps happening —
  put the prohibition in every dispatch and check `git stash list` after implementers).
- Commit trailer: Co-Authored-By + Claude-Session lines (see any recent commit).
- Memory index (MEMORY.md) has the standing rulings: clone-only, parser is user-owned,
  Phases 0–2 status, the Compound-is-a-dataclass funnel trap.

## Why this matters (one paragraph of context)

Phases 0–2 of the term-representation program are merged: construction fast path (7.3×
micro, 1.54× on the walker-heavy macro), funnel refactor, and the dual-representation
bridge — tagged cells beat even the fast-pathed class representation (B/A = 0.561,
~1.8×) with zero C changes. Phase 3 (compiler flip + atom pivot: global str atoms,
`-hide` with a reader-unwritable separator, cons rule retired, double-quotes → char
lists) is specified in §1b/§1c and gated on the user's parser. Your formalism is the
front door of that parser: the token layer is the only part of Prolog reading that
genuinely wants a formalism, and it is the part Markus Triska identifies as the open
problem for Prolog-in-Prolog parsing.
