# `:- .` reads as a fact whose head is the atom `':-'`

**Status: open, waiting on an operator ruling (2026-11-03).** The reader is
right. The open question is whether a Prolog text may define `(:-)/0`. See
"Findings 2026-11-03" below.

**Filed:** 2026-09-04 (second item of
`todo/done/toklex-unclosed-block-comment-silent-eof-2026-09-04.md`), split
out 2026-09-30 when that file's first item was resolved.

`read_module(":- .\n")` returns `[Clause(term=':-', ...)]`: the Pratt
parser's bare-operator-atom leniency accepts a prefix operator with no
operand before `.`. The original note said ISO calls that a syntax error, and
gave two options: downgrade the `PClause` to a `SyntaxIssue` in
`PrologReader._classify_pitem`, or validate clause shape in the consumer.
Full write-up in the done file.

## Findings 2026-11-03

**The reading is ISO's and Scryer's. The reader must not change.**

- Ulrich Neumerkel's conformity suite, #224: `\ .` is expected to give
  `existence_error`. So the text is read as the atom `\` and then called, not
  refused as a syntax error. A prefix operator followed by a token that
  cannot start a term is an atom (ISO 6.3.4.2). Scryer carries this row as
  `test_224` in `tests-pl/iso-conformity-tests.pl`. `:- .` is the same case,
  read as the atom `:-`.
- The priority-1201 rule (ISO 6.3.1.3) applies only where the operator
  atom is an *operand*. #76 `:- = :- .`, #77 `- = - .` and #78 `* = * .`
  are syntax errors, and the reader already refuses them.
- Scryer's `read_term/3` reads `:- .` as `:-`.
  `tests/iso/test_prefix_op_atom_scryer.py` (commit 434a135a) already pins
  this through both readers, the native `PrologReader` and the translator's
  `parse_term`, and against Scryer: row `":- ."`.

**Concern 1, the item silently becoming a fact, does not happen in the
native front end.** `iso_l3.lower_clause` refuses any head named `:-` of any
arity. A `.pl` or `.clausal` file containing `:- .` does not load:
`cannot define the control construct :-/0 (ISO permission_error(modify,
static_procedure, :-/0))`. The translator front end
(`CLAUSAL_PL_FRONTEND=translator`) also refuses it, because `:-` is not a
Python identifier. The seam has no such syntax. So the consumer-side
validation that option 2 asked for already exists.

**What is left is a divergence over `(:-)/0`:**

| Text | Scryer | Trealla | Clausal (native) |
|---|---|---|---|
| file `:- .` | defines the fact `(:-)/0`; `call((:-))` succeeds | `permission error modifying user:(:-)/0` | refused at load: "control construct :-/0" |
| file `?- .`, `--> .` | defines `(?-)/0`, `(-->)/0` | n/a | defines them (same as Scryer) |
| `assertz((:-))` | succeeds | n/a | succeeds |
| file `((:- a) :- true).` | `permission_error(modify,static_procedure,(:-)/1),load/1` | n/a | refused (same as Scryer) |

`(:-)/0` is neither an ISO control construct nor an ISO built-in, so the
refusal message is wrong in any case ("control construct"). Clausal is also
inconsistent with itself: `assertz((:-))` defines what loading `:- .`
refuses.

## Options (ruling needed)

1. **Follow Scryer (recommended):** in `iso_l3.lower_clause`, refuse a `:-`
   head only for arities 1 and 2, so that `:- .` defines `(:-)/0`, as
   `assertz((:-))` already does. This agrees with Scryer, with
   `?- .`/`--> .`, and with assertz.
2. **Keep the refusal and fix the message:** refuse `(:-)/0` at load as
   Trealla does, without calling it a control construct. For consistency,
   `assertz((:-))` would then have to refuse it too.
3. **Leave as is:** close this todo as resolved (the reader is right) and
   accept that `:- .` is refused with an inaccurate message.

Related, filed separately:
`todo/assertz-accepts-colon-dash-1-and-2-heads-2026-11-03.md`. `assertz/1`
accepts `(:-)/1` and `(:-)/2` heads, which Scryer refuses.
