# listing/1's clause-BODY display leaks the raw -hide separator (pre-existing, general)

**Found:** P3-1 Task 6 fix round (write/1, term_to_string/2, print_term/1,
portray_clause/1, and listing/1's own fact-argument formatting all now
render a mangled (`-hide`) atom's human `module.name` form — see
`clausal/logic/builtins/io.py`'s `_format_term_for_io`/`_format_clause_term`
and `clausal/terms.py`'s `term_str` str branch).

**Gap:** `listing/1`'s clause-BODY rendering (`_format_clause`'s
`body_strs = [str(g) for g in clause.body]`) still leaks the raw U+E000
separator for a rule-shaped clause. Root cause, confirmed by probe: a
ground-argument FACT compiles into `head(V) <- V is <value>` internally
(`Clause(head=holds(V), body=[Unify(left=V, right=<value>)])` — this is a
PRE-EXISTING compiler normalization, unrelated to atoms/hiding), and
`Unify`'s `__str__` (inherited from `pythonic_ast.nodes.BinOp.__str__`,
`f"{left} {op} {right}"`) plain-interpolates its `right` operand via
Python's own `str()` rather than routing through `term_str`. This is a
GENERAL gap: it never called `term_str` for ANY string leaf (atom or not),
hidden or not — Task 6 did not introduce it, only exposed it (a hidden
atom's raw separator is simply more visible/jarring than a normal string
would have been in the same spot).

**Why not fixed in Task 6:** the fix would mean touching `BinOp`/`UnaryOp`/
sibling `__str__` methods across `clausal/pythonic_ast/nodes.py` broadly
(every operator node's leaf-str interpolation), which is a materially
larger, more architectural change than the two funnels the fix-round
review scoped ("if cheap" was the bar for the listing/portray spot-check;
this isn't). `portray_clause/1` and every other display funnel
(`write/1`, `writeln/1`, `write_to_string/2`, `print_term/1`,
`term_to_string/2`) are confirmed clean; only `listing/1`'s RULE-shaped
(non-fact) clause bodies are affected.

**Repro:**
```python
owner.holds._clauses[0]
# Clause(head=holds(arg_0=AttVar(_2)), body=[Unify(left=AttVar(_2), right='hide_ownerhide_secret')])
# listing(owner.holds) prints:  holds(_2) <- _2 is hide_ownerhide_secret.
```

**Next step (not scoped here):** decide whether `Node.__str__`'s leaf-str
interpolation should route through `term_str` generally (fixes this AND
every other str-quoting inconsistency in AST-level `__str__`), or whether
`_format_clause`'s body-goal formatting specifically should switch from
`str(g)` to a `term_str`-aware equivalent. Either is a bigger surface than
one function; needs its own design pass, likely outside P3-1.

## Closed 2026-09-30 (stale)

No longer reproduces on f84633ea: with `-hide([secret])`, `listing(holds/1)`
and `listing(r/1)` for `r(X) <- (X is secret)` both print `lsh.secret`, and
`writeq` prints `f(lsh.secret)` -- no raw U+E000 separator.
