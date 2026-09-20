# The two-package-copy diagnostic after the cell flip — a design question

**Status:** open (parked for the operator). Found 2026-09-20 during the P2
Task 4 sweep, on `feat/predmeta-p2-head-cells-2026-09-19`.
Test parked as `xfail(strict=True)`:
`tests/test_second_package_copy_term_identity.py::
test_term_crossing_between_copies_is_refused_with_a_precise_message`.

## What changed, and it is a genuine improvement first

`describe_term_identity_mismatch` exists because `is_term_instance` is
NOMINAL: with two copies of the package live, a term minted by one is not a
term to the other, and the old message said "expected a functor dataclass
instance" while holding one. It fires on a foreign `PredicateMeta`-minted
HEAD INSTANCE.

**P2 removes that failure mode.** A head is a CELL now, and a plain tuple
crosses between package copies perfectly well — there is no nominal identity
to lose. So the check never runs, and the rulebase in that test compiles
further than it used to.

## What it hits instead

It dies in the `pythonic_ast` NODE layer:

    NotImplementedError: terms_to_goalop: goal shape not yet supported
    (ArithEq): ArithEq(left=AttVar(_1), right=1)

preceded by the real clue, already emitted as a `RuntimeWarning`:

    dollar_ref: <class 'clausal.pythonic_ast.nodes.ArithEq'> is spelled like
    the twinned runtime name 'ArithEq' but is not the registered
    <class 'clausal.pythonic_ast.nodes.ArithEq'>

Two `ArithEq` classes, so every `isinstance` in `terms_to_goalop` misses and
it falls to `_not_yet`. Still a refusal — but from a layer the diagnostic
does not cover, with exactly the uninformative message this test file exists
to prevent.

## The question

Should the precise diagnostic be generalised to the AST-node layer?

* **(a) Yes — generalise.** `_not_yet` (and the other nominal checks) consult
  a copy-crossing describer. Cost: `_describe_term_identity_mismatch` is
  written for `PredicateMeta` specifically — it checks
  `foreign.__name__ != PredicateMeta.__name__` and its wording says "head
  class". A node class is neither a head nor PredicateMeta-minted, so this is
  a generalisation of both the TEST and the WORDING, not a call-site change.
  The existing test's assertions (`"decision/2"`, `"PredicateMeta id=0x"`
  twice) would all be rewritten.
* **(b) No — accept the coarser refusal.** Two copies in one process is
  documented as unsupported
  (`todo/term-identity-cannot-cross-two-package-copies.md`), and P2 has
  already removed one of its two failure modes. Re-point the test at the
  node-layer refusal and assert the `dollar_ref` warning is what names the
  cause.
* **(c) Make the warning an error.** The `dollar_ref` RuntimeWarning already
  detects the duplicate class precisely and by name, at the point where it
  can still say something useful. Promoting it for this case would give a
  good message with no new describer at all — probably the cheapest of the
  three, and the one worth costing first.

**Engine-lane recommendation: (c), then (b) for the test.** (a) buys a better
message for a scenario that is unsupported anyway, and it widens a diagnostic
whose narrowness is deliberate — its own comments record that a `namedtuple`
once made it fire "confident, specific and entirely wrong".

## Not to be confused with

The sibling test in the same file,
`test_first_copy_keeps_term_identity_after_second_copy_is_imported`, is NOT
affected and is fixed rather than parked: it builds a term instance directly,
and it only needed the P2 bridge flag (`_clausal_instances`) so that it mints
the instance its name is about.
