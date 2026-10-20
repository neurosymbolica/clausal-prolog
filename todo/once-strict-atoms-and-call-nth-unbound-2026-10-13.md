# `call(once, G)` in seam needs `-private([once])` under strict atoms (2026-10-13)

A bare builtin name works as an atom closure: `call(atom_length, 'abc', X)` loads and answers 3.
A bare SPECIAL-FORM name does not: `call(once, g(X))` and `maplist(once, [...])` fail to load
with `strict_atoms: undeclared atom 'once'`, because special forms have no binding in the module
namespace. Scryer needs no declaration. The same probably holds for the other special forms (catch,
findall, forall, ...) used as bare closures.

Fix: treat special-form names as known atoms for the strict-atoms check (they are engine-defined).
Test: maplist/call with each bare special-form name.

# Also: `call_nth(G, N)` with N unbound raises (2026-10-13)

Clausal raises `type_error(positive_integer, _)`, at full arity as well. Scryer and Trealla
enumerate instead: N = 1, then N = 2, … over G's answers. Make an unbound N enumerate.

When N enumerates, call_nth(G, N) with N unbound keeps G's choice points: the
cut-over-a-table rule then needs a run-time-N case. Today
`compiler/cut_scope._COMMITS` lists `("call_nth", "inner")` (every call_nth
stops at its Nth answer, 2026-10-20), and the lowering's commit check
(`control_constructs._compile_call_nth`) sits on that stop.
