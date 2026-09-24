# Constructing a predicate term with too FEW positional args pads with fresh variables

**Found:** 2026-09-24, dropping the vocabulary-implements idiom.
**Pre-existing.**

`impclob_verdict/2` (tests/fixtures/impclob_implements.clausal): measured
`impclob_verdict('solo')` gives `('impclob_verdict', 'solo', AttVar)` with no
error, where too MANY args raises `ClausalTermConstructionError`
(`TestGenuineArityDisagreementStillRaises`).

Seen end to end on main before the refusal landed: a module exporting
`impclob_verdict(ONLY)`, importing `impclob_verdict` (declared /2) and writing
`impclob_verdict(solo),` loaded, and stored the clause
`('impclob_verdict', _, _)` (`solo` dropped, both slots fresh); the arity
error only came at CALL time. That load is now refused (the new step-3d
refusal names it `/2`, because that is what the head compiled to), but the
construction itself still pads silently wherever else it is reached (a body
term, an `assertz`).

Question: should a short positional construction raise like a long one? Check
for callers that rely on the padding before changing it.
