# `clausal rewrite` — open questions after the head-fold landing

**Status:** v1 shipped (`clausal/rewrite/`, `clausal-rewrite` CLI,
`tests/rewrite/`).  One rule class — the head-fold — plus the driver, the CLI,
a corpus sweep, and a negative control proving the legality checks are
load-bearing.  57 folds fire across the in-repo corpus.

These are the calls v1 made or deferred.

## 1. Rules cannot invent goals

The splice reuses the original `ast` node for every goal the rule kept, which
is exactly why comments survive without a heuristic.  A goal the rule INVENTED
has no node to reuse and no comments to inherit, so the driver refuses by name
rather than mis-splice.

Whole classes of rewrite want to invent goals — lambda elimination lifts a
lambda body into a new predicate, tell-don't-ask replaces a getter chain with a
call.  Supporting them needs two decisions, not one: how to render a new goal
(`render_ast` can do it) and where its comments come from — nowhere, from the
goal it replaced, or from the rule itself.  The third option means rules would
have to be able to say something about comments, which is a much bigger change
to the rule contract than the rendering is.

## 2. `RewriteClause/2` only, and only over clauses

Directives, facts and Python items pass through untouched.  A rule cannot see
the file it is in, so nothing cross-clause is expressible: no "rename this
predicate everywhere", no "these two clauses are one clause with an or".  The
spec's `RewriteClause/3` (with a module argument) is the shape that would open
that up.

## 2b. A comma-separated clause series is exempt

The driver rewrites a statement that IS one clause.  `p(..) <- (..), q(..),` is
one statement holding several items, and splicing into it would mean rebuilding
the series and re-deriving which comma belongs to which clause.  It is left
byte-stable, with a test pinning that.  No file in this repo's corpus writes
clauses that way (checked: zero statements), so it costs nothing today -- but
the exemption is silent, and a `--check` run would report such a file clean
whether or not a rule would have fired in it.

## 3. Folding interacts with the formatter's missing width engine

`NatnumProgram(PROGRAM) <- (PROGRAM is [ ...five lines of list... ])` folds to
a fact whose argument is that whole list — and v1 of the formatter does not
wrap, so it lands on one very long line.  The fold is right; the line is worse
than what it replaced.  This is the same deferral as
[clausal-fmt-open-style-questions.md](clausal-fmt-open-style-questions.md) §1,
and it argues for doing the width engine before running the rewriter over
anything wide.

## 4. Operator terms are refused, though they would be sound

`S is A + B` is unification like any other `is`, so folding it into the head is
sound in the same way `S is tag(A)` is.  v1 refuses everything that is not
constructor-shaped rather than argue term by term.  Lifting that restriction is
a one-line change to `Foldable/1` plus refusal tests turning into fold tests —
worth doing deliberately, with the behavioral evidence in hand, not as a tweak.

## 5. The caveat the tests cannot close

Folding moves a binding from body time to head-unification time.  Those differ
only to a caller that inspects bindings between goals — coroutining, a
`when/2`-style suspension, a debugger stepping the body.  No test in this repo
distinguishes them, and the corpus sweep cannot: it checks that unfired
statements are untouched, not that folded ones behave identically.  What backs
the claim is running a rewritten tree through its own test suite, which is what
the invariance run does and what any adopter should do before keeping the
output.

## 6. Three reflection gaps the build ran into

Recorded separately in
[reflection-gaps-found-by-the-rewriter.md](reflection-gaps-found-by-the-rewriter.md):
an occurs check cannot see into a term a rule just built (so legality must be a
pre-condition), `[*XS]` matches strings as well as lists, and reification drops
a head's keyword-argument names.  The first of the three produced a real unsound
fold before the suite run caught it.

## 7. Decided in v1, recorded so it is not re-litigated by accident

- **Refusal is failure.** A rule that does not apply simply fails; there is no
  "declined because" channel.  The CLI reports firings, not refusals.
- **First rule wins.** `RewriteClause` is asked of each module in order and the
  first solution is taken; rules are not scored or combined.
- **Fixpoint bound 20 per clause**, and exceeding it is an error naming the
  rule, not a silent stop at 20.
- **A rewrite run also formats.**  `--check` therefore reports a change on an
  unformatted file with zero firings; the CLI help says so.
- **Leading-underscore rule files are test assets**, excluded from the default
  rule set, because one of them is deliberately unsound.
