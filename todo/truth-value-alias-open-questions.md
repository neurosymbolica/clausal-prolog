# Open questions from the truth-value alias + `Undefined` rename

Landed (uncommitted, this clone): `true`/`false`/`undefined` are parse-time
aliases for `True`/`False`/`Undefined`, and the Kleene singleton was renamed
`Unknown` -> `Undefined` to match XSB/SWI. Full suite green against baseline.

These are the decisions the work surfaced but did not settle.

## 1. Should `clausal-fmt` normalise the spelling?

`clausal/fmt` is a stdlib-`ast` formatter and never sees the alias fold, so it
emits whatever the author wrote. Options: leave it (two spellings persist in
source), normalise to `True`/`False`/`Undefined` (one house style, but a
formatter that renames identifiers is a new class of edit for this tool), or
normalise the other way for Prolog-facing files.

Note the arrow-spelling precedent: fmt already cannot see `<-` vs `:-` in the
AST and needs a ledger. An alias normaliser would need the same treatment.

## 2. Should `prolog_to_clausal` stop rewriting inbound `true`/`false`?

`clausal/tools/prolog_to_clausal.py:607-613` maps inbound `true`/`false` to
`True`/`False`. Now that the lowercase spellings are legal, leaving them alone
would keep converted source closer to its Prolog original. Kept as-is for now
because it is the canonicalising choice and nothing depends on the difference.

Inbound `unknown` is still deliberately *not* rewritten to the builtin (the
asymmetry documented at `clausal_to_prolog.py:707`). Outbound now emits
`undefined`, so a round trip through Prolog no longer returns the builtin — the
same one-way behaviour as before the rename, but worth a decision.

## 3. Is `unknown` the right thing to leave as a diagnostic?

`unknown` is not an alias: it was the pre-rename name, and binding it would
restore the ambiguity the rename removed. `clausal/atom_diagnostics.py` catches
it and points at `Undefined`. If external corpora carry `unknown` heavily, that
trade could go the other way.

## 4. Should the reserved names have an escape hatch?

All six spellings (`True`/`False`/`Undefined` and the three aliases) are now
refused in declaration lists, clause heads and directive targets. The in-tree
corpus (1768 `.clausal` files) defines none of them, so nothing broke, but
there is no `-implicit_atoms`-style opt-out the way strict atoms have one.
Probably fine; unverified against out-of-tree corpora.

Two definition sites are still guarded only by incidental Python errors rather
than by the diagnostic, because the name never survives parsing as an
identifier: `True(1),` as a clause head raises `TypeError: 'bool' object is not
callable`, and `-dynamic(True/1)` raises a malformed-spec `SyntaxError`. Both
refuse the definition, so the behaviour is right and only the message is poor.
Catching them would mean a check on the raw Python AST before term rewriting.

## 5. RESOLVED — no `Unknown` alias is kept

`clausal.terms.Unknown` is gone, and so is the `_get_unknown` pickle shim.
Nothing in the repo references the old name any more (the remaining `Unknown`
hits are all prose in error messages). All ~22 out-of-tree implementors under
`packages/` were checked and none referenced the truth value.

The only theoretical loss is a pickle written before the rename whose reduce
payload names `clausal.terms._get_unknown`. The value shipped 2026-07-17 and is
used in two downstream `.clausal` files; no such pickle is known to exist. If
one turns up, `_get_unknown = _get_undefined` restores it in one line.

## 6. Pre-existing: bare-atom dict keys do not resolve injected builtins

Noticed while wiring key-position aliasing. A bare `Name` dict key goes through
`_visit_dict_key` -> `$intern_atom("<name>")`, which interns an atom by name
rather than resolving a binding. `{Undefined: 3}` therefore keys on an interned
atom named `Undefined`, not on the singleton — and yet `T[Undefined] == 3`
succeeds, so the two paths agree by construction somewhere. Worth understanding
properly: if they ever diverge, `{Undefined: 3}` silently stops matching. This
predates the rename and is not caused by it.

## 7. Cosmetic: `evaluation_error(undefined)` now collides in Prolog output

ISO's arithmetic `evaluation_error(undefined)` (`builtins/arithmetic.py:627`)
and the truth value now share the atom `undefined` in emitted Prolog. Different
concepts, same spelling, no code path confuses them. Flagged, not fixed.
