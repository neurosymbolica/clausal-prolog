# ISO comparison and unification builtins in canonical form — design

**Status:** DESIGN, awaiting the operator's review. No code. Written 2026-09-08 by the
engine lane after the operator's direction: "as we move toward ISO Prolog, with Clausal
more as a seam language, we can expand the use of standard ISO operators such as `=:=`;
in Python the syntactic mechanism is the canonical form with quoted atoms, `'=:='(lhs,
rhs)`; the syntax trade-off occurs in few `.clausal` files, with `.pl` files interpreted by
Clausal using ISO syntax and semantics."

Companion: `implementation_plans/prolog-eq-mode-lowering.md` (the translator-side
diagnosis this design dissolves rather than patches). Every claim marked *probed* was
run on canonical 7d8a4889 on 2026-09-08.

## 1. The problem, in one paragraph

Clausal's `==` is `nodes.ArithEq`: a CLP(FD) equality **constraint** that binds an unbound
side, degrades to a ground structural test on non-numbers, and raises
`type_error(evaluable, …)` when one side is unbound and the other a ground non-number.
ISO has three different things where Clausal has one: `=:=` (evaluate both sides,
never binds), `==` (structural identity, `1 == 1.0` is false), `=` (unification). The
translator (`clausal/tools/clausal_to_prolog.py::_convert_compare`) therefore has to
GUESS which one a `==` site meant, by operand shape; the guess is wrong on 4 of 7 measured
shapes and produces the live G3 red `type_error(evaluable, date/3)` on every domain that
compares dates with `==`. An author who could say which comparison they mean would remove
the guess entirely.

## 2. What already exists (probed)

- **The canonical-form sugar is already in the rewriter.** `'name'(args)` — a call whose
  callee is a single-quoted string literal — is "sugar for a name reference whose
  identifier is that string" (`clausal/templating/term_rewriting.py`, `visit_Call`); a
  DOUBLE-quoted callee is refused in every mode with a located error (ISO 6.3.3, strings
  design §7). So `'=:='(X, Y)` already parses to a call of the predicate named `=:=`.
- **The predicates do not exist.** `'=:='(1, 1.0)` → `PredicateNotFoundError: =:=/2`;
  likewise `==/2`, `@</2`, `=/2`; `'=..'` reaches Python name resolution and fails with
  `NameError`. Only `structural_eq/2` and `dif/2` exist under Clausal names.
- **A `Name` whose id is a Python keyword compiles from the AST** (`ast.Name('is')` inside a
  `Call` compiles under CPython 3.13), so `'is'(R, E)` is not blocked by the code generator;
  whether the compiler's name→builtin lookup (`_registry.get_builtin_class`) sees it before
  any Python-level binding is a Task 1 verification, not an assumption.
- Clausal `is` is unification (`nodes.Unify`, ISO `=`); Clausal's ISO-`is/2` role is
  played by `eval_/2`, which downstream code never calls, and in practice by `==` (826 goal
  positions corpus-wide, per the eq-mode note §2.1).

## 3. Design

### 3.1 Admitted spellings and their meanings

Register these predicates under their ISO names, callable ONLY through the canonical
form in `.clausal` files (Python syntax has no infix for them) and natively in `.pl`:

| canonical form | ISO meaning | engine implementation |
|---|---|---|
| `'=:='(A, B)`, `'=\\='(A, B)` | evaluate both sides as arithmetic; compare; never binds; `instantiation_error` if a side is unbound; `type_error(evaluable, F/N)` for a non-evaluable term (a `date/3` IS such a term — the G3 red is ISO-correct behaviour for `=:=`, which is why dates need `@<`/`compare/3`, §3.3) | new; reuse the arithmetic evaluator behind `eval_/2` |
| `'<'(A, B)`, `'>'(A, B)`, `'=<'(A, B)`, `'>='(A, B)` | arithmetic ordering, same evaluation rules | new aliases; note ISO spells less-or-equal `=<`, not `<=` |
| `'=='(A, B)`, `'\\=='(A, B)` | structural identity / non-identity: `1 == 1.0` false; variables identical only if the same variable | alias `structural_eq/2` + its negation |
| `'@<'`, `'@>'`, `'@=<'`, `'@>='`, `compare(Order, A, B)` | ISO standard order of terms: Var < Number < Atom < String < Compound; compounds by arity, then name, then args left to right | new; one comparator, five entry points |
| `'='(A, B)`, `'\\='(A, B)` | unify / not unifiable | aliases of unification and `dif`-free negation-of-unify |
| `'=..'(T, L)` | univ | new (or alias if a `univ` exists under another name — verify) |
| `'is'(R, E)` | ISO `is/2`: evaluate `E`, unify with `R` | alias of `eval_/2` with ISO argument order |
| `'#='(A, B)`, `'#\\='(A, B)`, `'#<'`, `'#=<'`, `'#>'`, `'#>='` | CLP arithmetic CONSTRAINT: binds an unbound side, propagates, valid in every mode | **what `==` already is** — `nodes.ArithEq` IS a CLP(FD) equality constraint; alias it under its established name |

**`#=` is not ISO, and is in this design anyway.** It is not an addition: it is the
correct name for what `==` does today. `==` compiles to `nodes.ArithEq`, a CLP(FD)
equality constraint that binds and propagates, which is precisely what `#=` has meant
since CHIP. Registering it is naming an existing behaviour, not inventing one, and using
`#=` for a genuine arithmetic constraint is the CLP tradition used correctly rather than
overloaded (contrast: overloading it for dimensioned quantities, which was considered and
declined 2026-09-09).

It is REQUIRED by the measurement. `clausal/tools/eq_analysis/instrument.py` recorded
430,945 executions over 1933 corpus+library sites (log: trunk
`docs/eq-measurement-2026-09-09-f5ad9a5d.log`). **33 sites take two arithmetic modes** —
every one `{BIND, TEST}`, the same site binding on one call and testing on another. For
those no single ISO spelling is correct: `'is'` errors when both sides are ground under
some paths, `'=:='` raises `instantiation_error` on the binding call. `#=` is the only
spelling valid in every mode, so without this row those 33 sites have nowhere to go.
Static analysis called 28 of them `ARITH_SHAPE`, indistinguishable from single-mode — a
shape-based migration writes `=:=` there and ships `instantiation_error` into working
code, silently.

CONSEQUENCE FOR THE TRANSLATOR (Task 4): a `'#='` site emits `#=` into `.pl`, which is
`library(clpz)` in Scryer, not ISO. The exported file therefore needs its `use_module`,
and a domain using one is no longer pure-ISO. That is a real narrowing of the export
claim and belongs in a downstream exporter's documentation, not silently in a header.

Everything else ISO defines by an operator (`\\+`, `->`, `;`, `,`) is OUT of scope: those
already have Clausal spellings (`not`, if/else, `or`, conjunction) and the translator maps
them today.

### 3.2 What happens to bare `==`, `!=`, `<`, … in `.clausal` files

**Nothing, in this design.** `==` stays `ArithEq` with its current binding semantics;
existing files keep their meaning; the ratchet is not re-scored. What changes:

1. A **lint** (in `clausal-fmt`/`clausal-rewrite`'s lint family, or the strictness lint
   family — Task 3 decides which) flags a bare `==` whose ISO meaning is ambiguous: an
   operand that is not provably numeric (a date, an atom, a string, a compound) or a mode
   the eq-mode note's rules 1–2 cannot settle. The fix-it text names the canonical
   spelling: `'=:='` for a numeric test, `'is'` for evaluate-and-bind, `'=='` for
   identity, `'='` for unification.
2. The **translator** emits a canonical-form call 1:1 (`'=:='` → `=:=`, `'@<'` → `@<`, …)
   with no mode inference, and keeps its existing (guessing) path for bare `==` so that
   an unmigrated file translates exactly as today. Progress is then measured by the count
   of bare `==` sites the lint still flags — a number that only goes down.
3. The a downstream user migrates sites to the canonical spelling domain by domain, using the
   lint's classification; that is corpus work, sequenced by the operator.

### 3.3 Dates and the two-spelling pairs, settled by standard order

ISO standard order compares compounds by arity, then name, then arguments left to right,
so `date(Y, M, D)` terms order chronologically under `@<` with no date-specific code —
the eq-mode note's §6 "date ordering" defect has a spelling (`'@<'(D1, D2)`,
`compare(O, D1, D2)`) that is correct in both engines. The engine's standard-order
comparator must place a `date` value (a `datetime.date` behind the term) where the term
`date(Y, M, D)` would sit, which is the ONE representation-specific rule in this design
(Task 2 pins it against Scryer with the eq-mode note's §6.2 rows).

The open ruling from the `==`-on-strings fix ("ordering operators on str vs char list")
closes the same way: under `-double_quotes(chars)` a string IS its char list, one term, so
`'=='("ab", [a, b])` is true and neither side is `@<` the other; under atom mode `"ab"`
is the atom `ab` and orders as an atom. No new rule, just ISO order over the term the
literal denotes.

### 3.4 Errors

ISO error terms exactly, as `atom_chars/2` and `global_atom/2` already do:
`instantiation_error` for an unbound arithmetic operand, `type_error(evaluable, F/N)` for
a non-evaluable one, `type_error(list, L)` in `=..`. Scryer is the reference for every
error shape (the eq-mode note §1.3 shows the invocation form).

## 4. Tasks (for the writing-plans step, after review)

1. **Harness first** (the eq-mode note's own rule 1): a test that runs a `.clausal`
   predicate on the engine AND its translation in Scryer and compares answers, seeded
   with the note's §1.2/§1.3 matrices. Nothing else lands before it is red for the right
   reasons. Includes the `'is'`-name lookup verification (§2).
2. **The builtins** of §3.1, each with Scryer-pinned rows: arithmetic comparison family,
   structural family, standard-order family + `compare/3`, `=`/`\\=`, `=..`, `'is'`.
3. **The lint** of §3.2 (1), with the classification borrowed from the eq-mode note's
   Option B rules 1–2; counts reported per file.
4. **The translator**: canonical-form calls emitted 1:1; bare `==` path untouched.
5. **Docs**: `docs/builtins.md` (a new "ISO comparison" section), `docs/syntax.md` (the
   canonical form, single quotes only, and why), `docs/python_integration.md` (nothing —
   the seam is unaffected: `--'=:='(X, 1)` builds the cell as any functor).

## 5. Explicitly not in this design

- Infix ISO operators in `.clausal` source (Python's grammar; the `.pl` reader is the
  operator surface and is the operator's own project).
- Changing bare `==`'s meaning, now or on a flag. The lint plus the canonical spelling is
  the migration; a semantic flip would silently re-score the ratchet (eq-mode note §4.5).
- `\\+`, `->`, `;` canonical forms — already spelled in Clausal.
- **Python's `is`, `is not`, `in`, `not in`.** Untouched, in either context, and this
  design cannot reach them: the ONLY entry point it adds is the quoted canonical form,
  and Python has no syntax for writing `'is'(X, E)` as an infix operator. Measured
  2026-09-09 inside a `.clausal` file: in HOST Python code (`def` blocks) `a is b`,
  `a is not c`, `2 in [1, 2]`, `9 not in [1, 2]` all behave exactly as Python; in a
  CLAUSE BODY `X is 3 + 4` is unification and gives the term `Add(3, 4)`. Those two
  meanings for `is` are pre-existing and are NOT changed here — registering `'is'` as
  ISO `is/2` adds a third construct that is syntactically distinct from both. The
  clause-body/Python divergence is its own question, filed separately in
  `todo/is-and-eq-are-swapped-relative-to-iso-2026-09-09.md`.

## 6. Risks

- A predicate named `is`/`=`/`<` collides with nothing today (probed: none registered),
  but every one of these names is also a Python operator or keyword; the ONLY entry
  point is the quoted canonical form, and `clausal-fmt` must never "simplify" it back to
  an infix form.
- Standard order for engine-native values that ISO does not have (Decimal, Quantity,
  dict terms, Python objects): rule them into the Var < Number < Atom < String < Compound
  lattice explicitly (Task 2), or refuse with `type_error` rather than order arbitrarily.
