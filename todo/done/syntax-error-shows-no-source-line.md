# Bug: `invalid syntax (file.clausal, line N)` shows no source line and no reason

**Reported:** 2026-07-29, from an external authoring harness
**Severity:** high for machine authors — third-ranked defect by attempts burned,
80% unrecovered.

---

## STATUS: FIXED at the parse site (2026-07-29)

Implemented in `clausal/syntax_diagnostics.py`, hooked into both parses of a
`.clausal` source in `clausal/import_hook.py` (`_parse_clausal_source` and the
cache-hit `_extract_module_items`), and into `reify_source` in
`clausal/reflection.py` so `reify_file` reports the same thing.
Tests: `tests/test_syntax_error_diagnostic.py` (24). Docs: `docs/syntax.md`,
"When the syntax is wrong".

The reproduction below now prints:

```
  test_load.clausal :: <load> — invalid syntax (m.clausal, line 6)
    3 | f(X) <- (
    4 |     X > 1,
    5 |     Y is
      |         ^ `is` has no right-hand side
    6 | )
      | ^ parse gave up here
  -> complete the expression, or delete the goal — a Clausal goal cannot end
     on an operator.
```

Decisions, and why:

* **A window, not just the reported line.** Priority 1 was the offending source
  and caret; rendering only line 6 would have shown correct code and left the
  author no better off. Three preceding lines is the smallest window covering
  the observed defect-to-give-up distance (one or two goals), and it is
  bounded, so a long body cannot become a wall. The enclosing clause head is
  added when it falls outside the window — one row, with `...N lines omitted` —
  so the author always knows which clause is broken.
* **The reported line is labelled `parse gave up here`,** not blamed, whenever
  an earlier culprit was identified. The off-by-some-lines behaviour is now
  stated rather than left for the author to discover.
* **Constructs are named only when confident** (priority 2): a dangling
  operator with no RHS, an unparenthesised `<-` body, a goal missing its `,`
  (CPython finds this one; it is restated in Clausal's terms), an unclosed
  bracket, an unterminated string, and the two Prolog habits `:-` and `).`.
  With no confident guess the source and caret are still rendered and no guess
  is offered — a wrong construct name would cost more than none.
* **Nothing is swallowed.** `msg`, `lineno`, `offset`, `text`, `filename` and
  the exception class are all preserved; the report is added via `str` and a
  PEP 678 note. Genuine `.py` files, and `.pl` files (whose line numbers refer
  to the *translated* Clausal text), are left to CPython.

---

## Symptom

The complete engine output for a syntax error is two lines:

```
FAILURES:
  test_load.clausal :: <load> — invalid syntax (m.clausal, line 6)

1 tests: 0 passed, 1 failed [FAILED]
```

No offending source text, no caret, no explanation of what is wrong. Python's own
`SyntaxError` carries `text` and `offset` and renders both; that detail is being
dropped somewhere between the parse failure and this message.

This is engine-side, not a harness truncation — reproduced directly with
`python -m clausal.testing`, output quoted verbatim above.

## Reproduction

`m.clausal`:
```clausal
-module(m, [f(A)])

f(X) <- (
    X > 1,
    Y is
)
```
`test_load.clausal`:
```clausal
-import_from(m, [f])

Test("t") <- (
    f(2)
)
```
```
PYTHONPATH=. python -m clausal.testing test_load.clausal
```

Note the mistake is on **line 5** (`Y is` with no right-hand side); the message
reports **line 6**, the closing paren where the parse actually gave up. That is
normal parser behaviour, but combined with no source text it points the author at
a line that is perfectly correct. Every study instance showed this: the reported
line was a `)`, a `).`, or the last body goal, while the real defect was earlier.

## Measured impact

25-run census, local 27B authoring five domains, ranked by repair attempts burned
and whether the *next* attempt escaped:

| failure mode | attempts | runs | recovered | stuck | stuck% |
|---|---|---|---|---|---|
| `cannot import name X from M` | 133 | 25 | 6 | 106 | 95% |
| **`invalid syntax (file, line N)`** | **18** | **4** | 3 | 12 | **80%** |
| undeclared atom(s) in module | 15 | 7 | 4 | 8 | 67% |

Affected files were spread across the whole package — `computation.clausal` (16),
`decision.clausal` (14), and single-digit counts in `queries`, `fixtures`,
`test_public_interface` — so this is not one bad template.

## Requested fix

Render the source line and caret, as Python does, and name the construct when it
can be inferred:

```
invalid syntax (m.clausal, line 6)
    5 |     Y is
      |          ^ `is` has no right-hand side
    6 | )
      | ^ parse gave up here
```

Priority order:

1. **The offending source text and caret.** On its own this likely resolves most
   of the 80% — the author can see the file, but not which construct the parser
   objected to, and the reported line is usually not the faulty one.
2. **The Clausal-level construct name** where recoverable (`is` with no RHS, a
   rule body missing its `)`, a fact missing its trailing comma). Clausal already
   does exactly this well elsewhere — the "looks like a bodyless fact missing its
   trailing comma" message was hit once in the census and **recovered on the next
   attempt** (0% stuck). That is the standard to match.

## Related

Same family as
[`import-error-should-list-module-exports.md`](import-error-should-list-module-exports.md),
[`functor-field-name-mismatch-diagnostic.md`](functor-field-name-mismatch-diagnostic.md)
and [`test-failure-goal-level-diagnostics.md`](test-failure-goal-level-diagnostics.md):
an error that states a fact without the context needed to act on it. The census
shows the pattern holds across all of them — **every message that named its
subject was fixed on the following attempt; every message that did not burned the
author's whole repair budget.**
