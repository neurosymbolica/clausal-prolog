# `clause body must be parenthesized` names no line, and the line is in hand

Found 2026-08-08 by a measured authoring study, which burned four authoring
attempts and blocked on this one diagnostic.

## What the author sees

    eu_dimension.clausal FAILED TO LOAD:
      eu_dimension.clausal :: <load> — clause body must be parenthesized or a single
      call: write  head <- (body)  or  head <- goal(X)

That is the whole message. The file has 20 clauses and six *legal* nested `<-` forms
(`filter_map(L, ((true, true) <- true), OUT)` and friends), so "one of these twenty is
wrong, and six of them look like the thing you are warning me about" is the entire
signal. The producer re-emitted the same file shape four times, the driver's
`repair_stall_repeats` terminator fired on the identical error signature, and the run
ended. No attempt was wasted on a bad guess about the *rule* — the cheat-sheet in
`auto/phases.py` teaches `head <- (body)` correctly. They were wasted guessing WHERE.

## The location exists at the raise site

`clausal/templating/term_rewriting.py` raises `_ARROW_BODY_ERROR` from three places —
lines 272, 318 and 3423 — and every one is holding an AST node when it does:

| line | node in scope | has `.lineno` |
|---|---|---|
| 272 | `usub_node` (and `left`) | yes |
| 318 | `inner`, `first_comp`, `usub_node` | yes |
| 3423 | `head`, `value.elts[0]`, `expr_stmt` | yes |

All three raise `SyntaxError(_ARROW_BODY_ERROR)` — the one-argument form, which leaves
`filename`, `lineno`, `offset` and `text` set to `None`.

## This is the outlier, not the norm

Python's own parser errors on a `.clausal` file arrive fully located. Probe: give a
clause a trailing `.` instead of `,` and the loader reports

    msg='invalid syntax'  filename='.../bad.clausal'  lineno=3  offset=27
    text='good_one(X) <- (thing(X)).\n'

So the surrounding machinery already propagates location faithfully, and consumers
already know how to read it. Only the hand-raised arrow-body error drops it.

## Minimal reproduction

    # bad2.clausal — the offending clause is on line 7
    # line 2
    good_one(X) <- (thing(X)),

    good_two(X) <- thing(X),

    bad_clause(X) <- thing(X), other(X),

    import clausal, bad2
    # SyntaxError: clause body must be parenthesized or a single call: ...
    # e.filename is None; e.lineno is None; e.offset is None; e.text is None

## Fix

Raise the two-argument form at all three sites:

    raise SyntaxError(_ARROW_BODY_ERROR, (filename, node.lineno, node.col_offset + 1,
                                          source_lines[node.lineno - 1]))

Sites 318 and 3423 already receive `source_lines` / `transformer._source_lines`; site
272 needs the filename and lines threaded in, or the location attached one frame up by
whoever owns the source text.

Do NOT settle for adding the line number to the message string. The structured
attributes are what a downstream loader and any other reader can key on without
parsing prose, and the located parser errors above already set the precedent.

## Why it is worth doing now

This is the same species this project keeps meeting: a channel that reports the fault
and silently drops the part that makes it actionable. The `clip()` fix (three attempts,
2026-08-03) was the same shape — the diagnostic survived, the ACTUAL VALUE did not.
Here the diagnostic survives and the LOCATION does not. A weak producer cannot bisect a
twenty-clause file from a message with no coordinates, so the cost lands as burned
attempts and a blocked run that reads like a capability wall.

Related: a handoff note from the external authoring harness's own docs
("when a run stalls on a diagnostic, suspect the diagnostic before the model").
