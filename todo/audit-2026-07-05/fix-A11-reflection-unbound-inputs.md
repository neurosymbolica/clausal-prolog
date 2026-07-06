# fix(A11-F014): reflection builtins — silent failure on unbound inputs; raw ReifyError escape

`modules/reflection.py:96-120, 158-183`: unbound SOURCE/PATH → silent 0
solutions (house style raises instantiation_error, chars.py:161); docs
(reflection.md:114-115) claim clause_head/clause_body are "equivalent to
matching Clause(HEAD, GOALS, _) directly" — direct unification against an
unbound var BINDS, so the claim is false in that mode. Malformed source:
`reified_item("((broken", I)` → raw ReifyError escapes solve() (catch/3
bypass family, see fix-A11-module-pred-error-protocol.md).

**Fix**: instantiation_error on unbound source/path; convert ReifyError to a
catchable logic exception; fix the equivalence claim in docs.

**Test**: test_F014_reified_item_unbound_source_instantiation_error (xfail).
