# A qualified unit in `-constant_number_units` records nothing for `/3`

Filed 2026-09-11, found while answering "how do we reliably tell euro cents from dollar
cents?" — the disambiguating spelling was the one that lost the record.

**Today.** `_units_ast_to_term` (`clausal/templating/term_rewriting.py`, ~519) lowers a unit
expression to the term `constant_number_units/3` answers with. It handles `Name`, integer
`Constant` and `BinOp`, and returns **`None` for `Attribute`** — at which point
`_handle_constant_value_directive` skips the registration entirely. Measured:

    -constant_number_units(a, 5000, eur_cent)             /3 -> 5000, eur_cent
    -constant_number_units(b, 5000, united_states.usd_cent)   /3 -> NO ANSWER AT ALL

Not "answers without the qualifier" — the constant is absent from `/3`, so a gate enumerating
united constants silently does not see it. The VALUE is correct either way
(`constant_value/2` gives the right Quantity); only the declared-pair channel is empty.

**Why it stopped being urgent, and why it is still a defect.** The minor-unit naming rule
(same day) means the qualified form is no longer needed to disambiguate a minor unit: `cent`
is shared, so it is not bound bare, and `eur_cent`/`usd_cent` say which at the site. But the
qualified form remains the documented way to write a currency where two jurisdictions share a
word, and the corpus vocabulary has 25 such names —

    dollar x22   franc x17   pound x12   dinar x10   peso x10   rupee x7

— so `-constant_number_units(levy, 5, bahrain.dinar)` has no `/3` answer today, and that is
exactly the declaration whose unit most needs recording.

**Ask.** Lower an `Attribute` to a term that keeps the qualification. Shape to decide, and it
is the only real question here:

    ('.', ('bahrain',), ('dinar',))     structured, matches how a compound unit already
                                        lowers (('/', ('metre',), ('second',)))
    ('bahrain.dinar',)                  one atom, simpler to match, loses the parts

The structured form is consistent with what `/3` already does for `metre / second`, and a
caller that wants the flat spelling can rebuild it. Whichever is chosen, the existing tests in
`tests/test_constants.py` that assert `('euro',)` for a bare name must keep passing —
qualification changes only the qualified case.

**Related but NOT the same, and still open.** `-import_from(bahrain, [dinar])` followed by
`-import_from(kuwait, [dinar])` binds `dinar` twice, silently, last-one-wins, with no warning.
Pre-existing and general to every shared currency word. Arithmetic catches it the moment the
amount meets a differently-dimensioned one, and the message now says `dinar (BHD) vs
dinar (KWD)` — but a rulebase computing entirely in the wrong one never raises. The
minor-unit naming rule removed this hazard for minor units by construction; currencies still
have it.
