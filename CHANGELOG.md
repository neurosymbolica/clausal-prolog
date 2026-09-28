# Changelog

All notable changes to Clausal are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). From 1.0.0 onwards
the project follows [semantic versioning](https://semver.org/) over the
surface described in [docs/public-api.md](docs/public-api.md).

## Unreleased (1.0.0)

This is the first release with a public-API promise. Most of the changes
since 0.4.0 finish three moves:

- Terms are plain Python values: an atom is a `str`, a compound is a tuple
  `(functor, *args)` (a "cell"), and a string is the carrier
  `('$chars', text)`. There is no compound class any more.
- A predicate is a row in its module's database, named by a handle. It is
  no longer a Python class.
- The language moves towards ISO Prolog: the ISO builtin names, ISO error
  terms, and `"…"` as a string by default.

### Breaking

> **TODO (coordinator, before release):** add the entries for the ISO/Scryer
> arithmetic alignment once it has landed on main (the `//`, `**` and `^/2`
> rulings, the CLP(FD) error for a non-arithmetic term, and the zero-divisor
> error), including the rule that a bare Python operator inside a `--` seam
> keeps Python's meaning. Do not describe them here before they land.

- **Error terms are Scryer's, and are plain cells.** An error is
  `error(Formal, Culprit)`, where `Culprit` is the culprit's predicate
  indicator (`atom_length/2`) or an unbound variable. The explanatory prose
  that used to sit in the second argument is now `LogicException.message`,
  printed after the term. A catcher that matched on the old context text
  must match on the indicator, or on `_`. Read an error term from Python
  with `cell_functor` / `cell_args`.
- **`Compound` and `KWTerm` are gone.** A compound term is always the plain
  cell `(functor, *args)`; see Removed.
- **The dynamic database is declare-first.** `assertz/1` and its kin add
  clauses only to a predicate declared `-dynamic`; asserting into any other
  predicate raises `permission_error(modify, static_procedure, Name/Arity)`.
- **`eval_/2` is stricter.** It now evaluates an operand bound in a
  variable, raises `type_error(evaluable, Name/Arity)` for a compound that
  is not arithmetic, and raises `instantiation_error` for an unbound
  operand. A Python `str` reached through a variable is an atom there and
  raises; write `X is ++(expr)` to evaluate Python.
- **`clausal.__all__` is smaller.** `make_predicate` and
  `MakePredicateRetiredError` are gone, and the builtin objects whose names
  are not Python identifiers (`'#='`, `'=..'`, `'@<'`, `is`, …) and the
  dotted solver predicates (`z3.*`, `clpq.*`, `ortools.*`, …) are no longer
  listed. They stay attributes of `clausal` and callable from `.clausal`
  source; only `from clausal import *` stops binding them.
- **The packages under `packages/` pin an exact Clausal minor**
  (`clausal>=1.0,<1.1`), because some of them use internal helpers.
- **An atom is a Python `str`, and a string is the carrier
  `('$chars', text)`.** Answers, `++` arguments and the converters all follow
  this. The 1-tuple `('x',)` is reserved.
- **`"…"` is a string (a char list) by default**, as in Scryer and Trealla.
  A module that relied on the old atom reading needs `'…'` for its symbols,
  or `-double_quotes(atom)` as a stop-gap.
- **A module attribute for a predicate is the predicate's handle** (a `str`),
  not a callable class. `m.pred(X)` no longer runs anything. Write
  `solve(("pred", X), module=m)`.
- **Predicates defined as Python classes are gone.** `PredicateMeta` and
  `make_predicate` have been deleted, and a Python-made predicate class is
  refused at load. Implement `_get_dispatch()` instead (see the public API).
- **Goal-position `--` seams hand back raw terms** (the "dumb seam"). An
  atom comes back as its `str`, a string as its carrier, a compound as its
  cell. `++` passes values in unconverted. Convert with `to_python` /
  `to_clausal` where you need a Python value.
- **Name classes:** a name with a capital initial is a logic variable, and a
  TitleCase name used as a functor is a load-time error. The SI unit names
  are now lowercase, and the old spellings are warned aliases.
- **Keyword-argument terms** (`point(x=1, y=2)`) are refused at load. Build
  terms positionally.
- **No implicit arity padding:** a term is built at the arity it is written
  with, and a partial keyword-only construction is refused.
- **Constants were respelled** as the `-constant_value(name, value)` family.
  A bare name is the atom, and `constant(name)` retrieves the value.
- **`q(...)` quasi-quotation is retired.** `q` is an ordinary name.
  `ClausalRetiredQuasiQuoteWarning` flags old `term_expansion/4` rules that
  still use it.
- **ISO behaviour at the call boundary:**
    - A direct call to an unknown procedure raises
      `existence_error(procedure, Name/Arity)`.
    - `call/N` runs `findall`, `once`, `catch` and module-qualified cells.
    - A call at a different arity resolves under the name it used.
- **Module rules:**
    - A load may not add clauses to another module's predicate.
    - An imported name that clashes with a local definition is refused.
    - `-import_from` binds the names it lists, not the module.
- **Arithmetic is exact:** `Decimal` is a number, `+ - *` stay exact, `/`
  of exact numbers is rational, an integral rational is presented as an
  `int`, and a float mixed with a `Decimal` raises.
- **Standard order:** `Quantity` sorts in the number band. `sort/2` no longer
  treats `1`, `1.0` and an equal `Decimal` as duplicates, and it no longer
  crashes on mixed units.
- **`sort/2`, `msort/2` and `compare/3` agree with `term_key`.**
- **The bytecode cache is keyed by an engine fingerprint.** Caches from
  earlier versions are ignored and rebuilt.

### Added

- **`.seam`** as an alias extension for `.clausal` files.
- **Goal-position seams in hosted Python:** `if --g(X):`, `for X in --g(X):`,
  `while --g(X):` and `not --g(...)`, plus comprehensions whose first `for`
  is a seam, and the dotted form `--m.pred(X)`. Conditional (WFS-undefined)
  answers raise `UndefinedAnswer`, and unbound constrained exports raise
  `ResidualConstraints`.
- **Converters exported from `clausal`:** `to_python` (deep, out),
  `to_clausal` (deep, in) and `term_key` (the standard order as a sort key).
- **Cell helpers exported from `clausal`:** `cell_functor`, `cell_args` and
  `make_cell`, to read and build a compound term. `query_wfs` is exported
  from `clausal` too.
- **Arithmetic written as a plain cell evaluates.** `('+', 1, 2)` evaluates
  in `eval_/2`, the arithmetic comparisons, `between/3`, `#=`, `==`/`!=`
  constraints and CLP(Q)/CLP(R), through one closed table of evaluable
  functors.
- **A public API promise:** `docs/public-api.md` lists what semantic
  versioning covers from 1.0.0. A new lint in a minor release may only warn.
- **Error messages print the term the way Scryer does**
  (`error(type_error(atom,1),atom_length/2)`), then the prose.
- **ISO builtins under their ISO names:** `'is'`, `'='`, `'\='`, `'=='`,
  `'\=='`, `'=:='` and the arithmetic comparisons, `'@<'` and its family,
  `compare/3`, `'=..'`, `'#='`, `clause/2`, and `writeq/1` and
  `write_canonical/1`.
- **ISO error terms**, pinned against Scryer, and a `system_error/2` helper.
- **`test/1`** is the test-clause predicate.
- **Units and CLP:** quantities and united variables take part in CLP
  comparisons, `in_domain/3`, and `label/1`. Added the `percent` and
  `basis_point` ratio units. `str(Quantity)` now round-trips.
- **Currency:** the full ISO 4217 vocabulary, including historical
  currencies; minor units such as `cent`; `money/3` and `money_round/3` with
  the other money builtins; and a construction-time precision check.
- **Constants:** lexical scope, `constant_number_units/3`,
  `module_constant_units/4`, and exact decimal strings.
- **Types:** `quantity/1`. `number/1` accepts a quantity, and `sum_list/2`
  sums every numeric kind.
- **Well-founded semantics:** `query_wfs` reports truth values and delays
  for every goal shape. Answers use the strong-Kleene `Undefined` value.
- **Dict dot access** (`P.key`), and `is`-chains (`A is B is C`) for naming
  a term inline.
- **New load-time lints:**
    - `ClausalStringInCatchPatternWarning`: a double-quoted string naming
      the type, domain or kind of an error in a catch pattern
      (`catch(G, error(domain_error("date", _), _), R)`), which never
      matches because the engine's error terms carry atoms. Write `'date'`.
    - `ClausalBooleanSeamWarning`: a seam read as a boolean.
    - `ClausalSeamTextCompareWarning`: a seam answer compared with a
      Python `str` literal.
    - `ClausalAtomExportDefinedAsPredicateWarning`: an exported atom that
      is also a predicate.
    - `ClausalScaleInNameWarning`, `ClausalCurrencyLiteralWarning`,
      `ClausalTitleCaseIdentifierWarning`, `ClausalKeywordArgumentWarning`.
- **Diagnostics:**
    - Syntax errors show the source line and a caret.
    - Arity mismatches name the arity.
    - Undefined predicates list their candidates.
    - The test runner descends into a failing goal's clauses.

### Deprecated

These keep working, with a warning, through 1.x. They are removed in 2.0.

- **The `clausal.logic.atoms.atom` boundary class.** Constructing one emits
  `ClausalAtomClassDeprecationWarning`. It is a `UserWarning`, so it is shown
  by default, once per call site. Write `'x'`, and test with
  `type(v) is str` or `is_atom(v)`. Known gaps:
    - `isinstance(v, atom)` does **not** warn. It is now `False` for every
      engine value, so filters built on it go silently empty.
    - Unpickling an old instance warns once, at the `pickle.loads` call
      site.
- **`Test/1`** test clauses. Use `test/1`.
- **`-double_quotes/1`.** It is a temporary per-module ratchet, and it will
  be deleted once no module needs it.
- **TitleCase unit names** (`Metre` for `metre`) **and the old
  physical-constant spellings.** They are warned aliases
  (`ClausalDeprecatedSpellingWarning`).
- **`query()`.** Iterate `solve(...)` and read `Var.value`.

### Experimental

- **Importing `.pl` files** is experimental in 1.0: it goes through a
  translator that is being replaced, and it is outside the semantic
  versioning promise.

### Removed

- `PredicateMeta`, `make_predicate` and `MakePredicateRetiredError`.
- `clausal.terms.Compound` and `clausal.terms.KWTerm`, with
  `compound_as_cell`, `list_to_cons`, `cons_to_list` and the builtin
  `extend/3` (only a keyword term could satisfy it). Keyword-argument terms
  stay a load-time `SyntaxError`.
- The `CLAUSAL_NO_FLIP` environment switch.
- The `:=` walrus form in clause bodies (`X := Expr`), which is now a
  `SyntaxError`. It was never deprecated. Use `eval_(Expr, X)` for eager arithmetic, `==` for arithmetic
  constraints, and `is` for unification.
- `q(...)` quasi-quotation.

### Fixed

- **Indexing:** clause selection no longer drops answers when:
    - an argument slot holds a variable bound to a structure,
    - a structured head was asserted at runtime,
    - a keyword data head is called positionally.
- **WFS:**
    - A clause-prefix delay covers every answer.
    - A detached judging leader no longer loses the outer loop's answers.
- **Exceptions:** `catch/3` works around a trampolined subgoal, and
  `throw/1` raises a copy of the ball (ISO 7.8.10).
- **Crashes:**
    - A crash on garbage collection of a `Trail` (weakref ordering).
    - A reference-counting bug in CLP(B) node construction.
- **CLP(FD):** crashes and unsound saturation on bignum bounds past float
  range.
- **Arithmetic:** `5 + money` raises what `money + 5` raises.
- **ISO equality:** `'=='` is an equivalence relation, and it distinguishes
  `1` from `1.0`.
- **Validation:** `global_atom/2` raises `type_error(atom, Name)` instead of
  failing silently.

### Migration guide: 0.x to 1.0

| 0.x | 1.0 |
|---|---|
| `m.pred(X)` | `solve(("pred", X), module=m)` |
| `make_predicate(...)` / a Python predicate class | a `.clausal` module, or an object with `_get_dispatch()` |
| `atom("x")` | `"x"` |
| `isinstance(v, atom)` | `type(v) is str` |
| comparing a seam answer with `"text"` | `v == --"text"` or `to_python(v) == "text"` |
| `"sym"` used as a symbol in a `.clausal` file | `'sym'` or bare `sym` |
| `Test("…") <- …` | `test("…") <- …` |
| `X := Expr` in a body | `eval_(Expr, X)` |
| `Compound(f, args)` / `KWTerm(...)` | the cell `(f, *args)` |
| `exc.term` read as an object (`.args`, `.functor`) | `cell_functor(exc.term)`, `cell_args(exc.term)` |
| matching the context text in `error(_, Context)` | match the culprit indicator, or `_`; the prose is `exc.message` |
| `assertz` into an undeclared predicate | declare it `-dynamic` first |

## 0.4.0

See the `v0.4.0` tag.
