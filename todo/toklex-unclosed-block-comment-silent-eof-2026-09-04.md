# PrologReader loses an unterminated block comment silently at EOF

**Filed:** 2026-09-04, from the final whole-branch review of the prolog-reader
L1/L2 plan (`feat/prolog-reader`). Severity: real corpus symptom (Scryer's
`crypto.pl`), no code change proposed here — parked, needs a parity re-check
first.

## The gap

`PrologReader`'s recovery contract (Task 5, `clausal/tools/prolog_reader.py`)
promises a `SyntaxIssue` for every damaged item, including EOF with an
unterminated one (`resumable=False`). That promise depends on the L0 layer
producing an `error` Tok for anything it cannot finish. It does not for an
unclosed `/* ...` block comment: both `IncrementalLexer._nest_step`
(`clausal/tools/toklex/driver.py`, the "EOF with depth > 0 -- leave nest mode
silently" branch, ~line 489) and `RegexLexer._nest_step`
(`clausal/tools/toklex/regex_target.py`, the "EOF with depth > 0: lenient
silent exit" branch, ~line 528) consume the remaining input as trivia and
hand back a plain `EOF` sentinel — no `error` Tok, no signal of any kind.

Probe (run against this branch):

```python
>>> from clausal.tools.prolog_reader import read_module
>>> read_module("foo(a).\n/* never closed")
[Clause(term=('foo', 'a'), spans=((0, 6), (4, 5)), var_names={})]
```

One item back, not two — the entire unterminated comment (and whatever real
code might have followed it, had the file continued) vanishes with no trace.
`PrologReader.read_term()` never sees an `error` Tok to turn into the
guaranteed EOF `SyntaxIssue`; it just sees `EOF` with an empty item buffer,
which is indistinguishable from a genuinely clean end of file.

This is not hypothetical: `tests/toklex/test_reader_corpus.py`'s docstring
already documents the real-world trigger — Scryer's
`/workspace/scryer-prolog/src/lib/crypto.pl` opens with a comment containing a
stray `/*`, which (read with `nested_comments=True`, clausal's own dialect
default) swallows the entire rest of the file the same way. The corpus test
works around it by reading that file (and the corpus generally) with
`nested_comments=False` — a call-site choice, not a fix for the underlying gap
in the reader's guarantee.

## Proposed fix (future task)

Have the L0 layer emit an `('unterminated', <comment text>)` `error` Tok when
`close()` is reached with nest depth > 0, instead of exiting silently. That
gives `PrologReader._handle_error_tok`'s existing `"unterminated"` branch
(added in Task 5) something to catch, and the EOF path already knows how to
turn a pending `_item_error` into a `resumable=False` `SyntaxIssue`.

Two things this needs, not just a one-line change:

1. **A parity re-check.** The silent lenient exit is a *deliberate* choice,
   not an oversight — it is locked design decision #4 in
   `implementation_plans/toklex-implementation-plan.md` ("Lenient nest-at-EOF:
   an unterminated block comment at true EOF ends the trivia silently (parity
   with the current tokenizer's documented behavior)"). Changing it changes
   observable L0 behavior for every consumer, not just `PrologReader` —
   `tests/toklex/test_parity.py` and the old-tokenizer parity suite need a
   fresh look before this ships, not just the reader's own tests.
2. **`_lex_error_message` needs a new arm.** Today (`clausal/tools/
   prolog_reader.py`) `_lex_error_message` maps `reason == "unterminated"` to
   either `"unterminated string"` or `"unterminated quoted atom"` based on
   `t.lexeme.startswith('"')` — it has no case for an unterminated *comment*
   and would mislabel one as a quoted atom. Needs its own reason value (or a
   lexeme-based check) so the message doesn't lie about what was left open.

## Second parked item, same seam: `:- .` silently classifies as a fact

Separate but adjacent gap, same review pass. `PrologParser._parse_atom_or_compound`'s
existing "does the next token look like it can start a term?" leniency (used
so a bare operator atom like `-` can stand alone as a value) also accepts
`:-` on its own before a `.`:

```python
>>> from clausal.tools.prolog_reader import read_module
>>> read_module(":- .\n")
[Clause(term=':-', spans=(0, 2), var_names={})]
```

`:-` is a prefix operator (`fx`, 1200) with nothing following it to be its
operand; `_can_start_term()` sees the `.` next and correctly refuses to treat
`:-` as prefix, so it falls back to parsing `:-` as a bare atom and the item
becomes an ordinary fact whose head is the atom `':-'`. ISO calls a lone
prefix-operator-with-no-operand a syntax error (`:-` immediately followed by
`.` should not parse), so this is at minimum a divergence from strict ISO
syntax checking — and it means `PrologReader`'s `Clause` items are not
guaranteed to be well-formed clause terms just because they came back as
`Clause` rather than `SyntaxIssue`.

This is pre-existing Pratt-parser behavior (not something Task 4/5 introduced
or could fix locally in the reader), and it is unclear whether it should be
tightened at all — `:-` used as a bare atom is legal ISO Prolog in contexts
where it is not being read as a clause item (e.g. as a list element or an
argument). Two options for whoever picks this up:

- Tighten L1: have `PrologReader._classify_pitem` special-case a `PClause`
  whose head is exactly the atom `':-'` (or `'?-'`, `'-->'`, by the same
  leniency) and downgrade it to a `SyntaxIssue`.
- Leave L1 alone and put the guard in the Phase 3 compiler instead: it must
  not assume every `Clause.term` it receives from the reader is a
  well-formed clause (functor/arity sane, not a bare directive-operator
  atom) — validate on the way in rather than trusting the reader's
  classification.

No preference recorded here; parking the decision rather than picking one
under review-fix-wave time pressure.
