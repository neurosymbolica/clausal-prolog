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

- **A bare `/` in evaluation is Python's true division.** In `eval_/2`,
  `'is'/2` and the ISO comparisons, `7 / 2` is 3.5 and `6 / 2` is 3.0 (a
  float for two integers); a `Fraction` or `Decimal` operand stays exact, as
  in Python. Write `rdiv(7, 2)` for the exact rational 7/2. Inside a
  constraint (`==`, `!=`, `<`, ...) `/` stays rational. See
  [docs/operators.md](docs/operators.md).
- **Bare operators keep Python's meaning; quoted ones follow Scryer.** In
  `.clausal`/`.seam` source, clause bodies and `--` expressions alike,
  `-7 // 2` is -4 and `2 ** 3` is the integer 8. A quoted or runtime-built
  cell follows Scryer and ISO: `'//'(-7, 2)` truncates to -3, `'**'(2, 3)`
  is the float 8.0, `'/'(7, 2)` is 3.5.
- **A zero divisor is ISO's `evaluation_error(zero_divisor)`** in plain
  arithmetic on every spelling (`eval_(1 // 0, X)` raises
  `error(evaluation_error(zero_divisor), (//)/2)`), never a raw Python
  `ZeroDivisionError`. Inside a constraint it **fails** instead, in every
  goal order: `X == 1 // 0` has no solutions, as in Scryer.
- **A non-arithmetic term in an arithmetic constraint** raises Scryer's
  clpz error: `X == foo(1)` raises
  `error(domain_error(clpz_expression, foo(1)), (==)/2)`.
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
- **A pair is `Key-Value`, as in Scryer's `library(pairs)`.**
  `pairs_keys_values/3`, `pairs_keys/2`, `pairs_values/2` and
  `group_pairs_by_key/2` take and build `'-'(K, V)` pairs instead of
  `[K, V]` lists (a `[K, V]` element now fails), and follow Scryer's
  definitions in every mode. `group_pairs_by_key/2` groups only ADJACENT
  pairs with identical keys and returns `K-Values` groups: sort first to
  collect every occurrence of a key. See [docs/pairs.md](docs/pairs.md).
  `dict_pairs/2`, `dict_put_pairs/3` and `zip_/3` use the same `'-'(K, V)`
  pairs (a `[K, V]` element now fails).
- **foldl/4 backtracks into every call**, as maplist does (it committed to
  each call's first solution), and maplist, foldl and the `X in L` goal
  enumerate an OPEN list as the ISO prologue's definitions do.
- **`call(Y^G)` is `existence_error(procedure, (^)/2)`**, as in ISO and
  Scryer (it was `type_error(callable, ...)`); bagof/setof still read `^`.
- **`clausal.__all__` is smaller.** `make_predicate` and
  `MakePredicateRetiredError` are gone. `Database`, `Clause`,
  `structural_unify` and `get_builtin_class` are internal and no longer
  listed (they stay attributes of `clausal`). The builtin objects whose names
  are not Python identifiers (`'#='`, `'=..'`, `'@<'`, `is`, …) and the
  dotted solver predicates (`z3.*`, `clpq.*`, `ortools.*`, …) are no longer
  listed either. They stay attributes of `clausal` and callable from
  `.clausal` source; only `from clausal import *` stops binding them.
- **At the 1.0 release, the packages under `packages/` pin an exact Clausal
  minor** (`clausal>=1.0,<1.1`), because some of them use internal helpers.
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
- **Arithmetic is exact where it can be:** `Decimal` is a number, `+ - *`
  stay exact, `rdiv` and `/` inside a constraint are rational, an integral
  rational is presented as an `int`, and a float mixed with a `Decimal`
  raises.
- **Standard order:** `Quantity` sorts in the number band. `sort/2` no longer
  treats `1`, `1.0` and an equal `Decimal` as duplicates, and it no longer
  crashes on mixed units.
- **`sort/2`, `msort/2` and `compare/3` agree with `term_key`.**
- **The bytecode cache is keyed by an engine fingerprint.** Caches from
  earlier versions are ignored and rebuilt.

### Added

- **Negative tests: `test(Name, fail)`.** plunit's `test/2` with the option
  `fail` passes iff its goal has no solution; a solution fails it and an
  exception is an error, as for `test/1`. The seam spelling is the same term,
  `test("name", fail) <- Goal`, and `.pl` files write it as plunit does. Any
  other option (`throws(E)`, `nondet`, `true(C)`, ...) is a collection error
  naming it (`clausal.testing.TestCollectionError`; one failing `<collect>`
  item for the file), never ignored. As in plunit, `test/2` is reserved: a
  file defining its own `test/2` predicate with other second arguments now
  fails collection (none of 1,450 `.clausal`/`.seam`/`.pl` files in the repo
  and a corpus checkout does). In a `.pl` file an atom second argument of
  `test/2` stays that atom (`fail`/`false` no longer fold to `False` there),
  in heads, calls and data alike. See [docs/testing.md](docs/testing.md).
- **`-import_from(m, [p/1])` imports one arity of `p`**, as Scryer's
  `use_module(m, [p/1])` does (`s//1` is `s/3`). A bare `p` still imports
  every arity; the forms mix in one list, and `alias(p/1, q)` renames one
  arity. An indicator the exporter lacks is a load-time `ImportError`
  (`existence_error(procedure, p/N)`, with the file, line and the arities
  the module has). A call at an arity that was not imported is refused like
  any missing arity, and the message names the entry to add. A `p/N` entry
  names a predicate, so `clausal.imported_atoms` does not count it. See
  [docs/import.md](docs/import.md#importing-one-arity-namen).
- **A repeated `-import_from` entry is one import.** `[baz, baz]`,
  `[baz/1, baz/1]` and `[baz, baz/1]` load as one entry (the `.pl`
  translator no longer emits `[baz, baz]` for `[baz/1, baz/2]`). Binding ONE
  local name to two different predicates (`[alias(f, x), alias(g, x)]`) is
  now a `SyntaxError`; Python kept the last one silently before.
- **A `.pl` file's `use_module(file, [p/1])` imports `p/1` only**, as in
  Scryer; it imported every arity of `p` before. A `library(...)` list is
  still imported by bare name.
- **`clausal.declared_atoms(module_or_package)`.** The `frozenset` of atom
  names declared in the `-module`/`-private` lists of a module's own files,
  or, for a package, of its `__init__` and its loaded submodules. An
  `-import_from`ed atom is not included, and the answer does not depend on
  import order. See
  [docs/python_integration.md](docs/python_integration.md#listing-the-atoms-a-module-declares-declared_atoms).
- **`clausal.imported_atoms(module_or_package)`.** A `dict` from atom name to
  exporter module name for the atoms a module's own files (or a package's
  `__init__` and loaded submodules) bring in via `-import_from` without
  re-declaring them. It counts only atoms the exporter declares, so imported
  predicates are left out, and it never overlaps `declared_atoms`. A package
  `__init__` with no `-module` list can now list its imported atoms without
  reading internal namespace keys. See
  [docs/python_integration.md](docs/python_integration.md#listing-the-atoms-a-module-imports-imported_atoms).
- **CLP(ℝ) `inf/2` and `sup/2`**: the bounds of an expression over real
  variables, read from the store without changing it; they fail when
  unbounded. (They used to reach the CLP(ℚ) solver, which knew nothing of
  a real variable: `in_real(X, 0.0, 10.0), X >= 2.5, inf(X, I)` gave
  `I = 0`.) See [docs/clpr.md](docs/clpr.md).
- **`Module.declare_dynamic(name, arity)`**, the Python spelling of
  `-dynamic(name/arity)`, so a `Module` built from Python can take an
  `assertz`. Idempotent; its errors are ISO `dynamic/1`'s. See
  [docs/database_ops.md](docs/database_ops.md).
- **Prolog flags.** `set_prolog_flag/2` and `current_prolog_flag/2` with the
  ISO flags (`bounded`, `max_integer`, `min_integer`,
  `integer_rounding_function`, `char_conversion`, `debug`, `max_arity`,
  `unknown`, `double_quotes`) and ISO's error terms, and the directive
  `-set_prolog_flag(Flag, Value)`. `double_quotes` is the module's
  `-double_quotes` mode. `unknown` can only be `error`. See
  [docs/flags.md](docs/flags.md).
- **The `assert_creates_dynamic` flag** (module-scoped, default `false`).
  With it `true`, `assertz`/`asserta` of a procedure that does not exist
  creates it as dynamic (ISO 7.5.2(2)), instead of raising
  `permission_error(modify, static_procedure, PI)`. A static predicate, a
  builtin and a declared data functor are still refused. An imported `.pl`
  module starts with it `true`, and `:- set_prolog_flag(F, V).` in a `.pl`
  file now carries across for any flag.

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
- **The rest of ISO's evaluables:** `sign/1`, `+/1`, `rem/2`, `gcd/2`,
  `truncate/1`, `round/1`, `ceiling/1`, `floor/1`, `float/1`,
  `float_integer_part/1`, `float_fractional_part/1`, `sqrt/1`, `sin/1`,
  `cos/1`, `tan/1`, `asin/1`, `acos/1`, `atan/1`, `atan2/2`, `atan/2`,
  `exp/1`, `log/1`, `pi`, `e` and the bitwise `'>>'`, `'<<'`, `'/\\'`,
  `'\\/'`, `'\\'`, `xor`, with Scryer's kinds and errors. See
  [docs/arithmetic.md](docs/arithmetic.md).
- **`foldl/5`, `foldl/6` and `map_list_to_pairs/3`**, as Scryer's
  `library(lists)` and `library(pairs)`.
- **`'^'/2`**, ISO integer power: `'^'(2, 3)` is 8, and a negative
  exponent on an integer base other than 1 is `type_error(float, B)`.
- **`rdiv/2` as an evaluable functor**, the exact rational division:
  `rdiv(7, 2)` is 7/2 and `rdiv(6, 2)` is 3, in every arithmetic context.
- **The evaluable functors are builtins in scope in every module**
  (`+ - * / // div mod ** ^ rdiv` and unary `-`), strict or not, with no
  declaration: `'is'(X, rdiv(7, 2))` and `'//'(A, B)` are written as in
  Prolog. As data they stay ordinary terms.
- **[docs/operators.md](docs/operators.md)**: what each operator spelling
  means bare, quoted, and in the planned Prolog syntax.
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
    - `ClausalExportArityMismatchWarning`: a `name/N` export entry for an
      arity the module neither defines nor declares, while it has clauses
      for `name` at another arity (`-module(m, [base/9])` over `base/2`
      clauses). The export stays legal; the warning names both arities.
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
- **`Test/1`** test clauses: a TitleCase name is a logic variable, so
  `Test("…") <- …` is a load-time error. Use `test/1`.
- **The `-implicit_atoms` directive**, with its deprecation warning
  (`ClausalImplicitAtomsDeprecationWarning`) and the
  `tools/codemods/add_implicit_atoms.py` codemod. A file that carries it
  does not load: `SyntaxError: -implicit_atoms was removed; declare atoms
  with -private([...]) or quote them`.

### Fixed

- **`:- use_module(m, []).` in a `.pl` file is a located translation
  error**, not a loader crash (`ValueError: empty names on ImportFrom`).
  Scryer reads it as `remove_module/2` (drops the imports, never loads
  `m`), Trealla and SWI as "load `m`, import nothing", so the error names
  both and points at `use_module(m)` / `use_module(m, [p/1])`. See
  [docs/importing_prolog.md](docs/importing_prolog.md).
- **An imported `.pl` file's `_Name` variable is no singleton.** By the
  Prolog convention (ISO, Scryer) `_Y` in `setof(X, p(X, _Y), L)` is used
  once on purpose; the `.pl` load warned "rename to `_Y_UNUSED`". The
  `.clausal`/`.seam` rule is unchanged: every named variable used once
  warns.
- **`python -m clausal.testing` skips what the pytest plugin skips.** A
  directory scan honours `collect_ignore`/`collect_ignore_glob` from the
  `conftest.py` files under it, so `tests/` no longer reports the golden
  translator inputs as failing loads, and the Prolog files shipped as
  package data (the toklex specs and the constants preludes) carry the
  `% clausal: no-collect` marker.
- **A lambda called with the wrong number of arguments** raises an ISO
  error term instead of a Python `TypeError`: too many arguments extend the
  body goal (`maplist((S) <- (S > 0), [1, 2], R)` is
  `existence_error(procedure, (>)/3)`, as Scryer's library(lambda)), too
  few are `existence_error(lambda_parameter, Lambda)`.
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
- **A bare builtin name in a data position is the atom** (`integer`,
  `assertz`, `in_`), as in every Prolog: `must_be(integer, 3)` succeeds
  (it raised `type_error(atom, <builtin integer/1>)`), `X is assertz` binds
  the atom `assertz`, and `call(in_, X, [1])` answers `X = 1` instead of
  leaking a Python `TypeError`. A meta-argument (`call/N`, `maplist`'s
  closure) receives the atom and resolves it when called.
- **A package whose `__init__` is a `.clausal` file** loads as a Clausal
  package even when it is imported before `clausal.import_hook`; it used to
  become an empty namespace package, and its `-import_from` of sibling
  files never ran.
- **A top-level `--goal` over a predicate of the same file** (which runs
  before the file's clauses are compiled) raises
  `existence_error(procedure, p/1)` with a message giving the file and
  line and the fix, instead of a bare "not defined".
- **sqlite: TEXT columns are strings in every row shape.** A multi-column
  row from `query/3,4` used to carry its TEXT columns as atoms (so
  `SELECT name, age` gave `('alice', 30)`, which is also the compound
  `alice(30)`); it is now `("alice", 30)`, as a single-column row already
  was.
- **`.clausal` bytecode is written atomically.** The loader wrote a cached
  `.pyc` in place, so a process sharing the `__pycache__` could read a torn
  file; it now writes a temp file beside it and `os.replace`s it in, as
  CPython does, and removes the temp file if the write fails.
- **The Prolog exporter keeps `!=` a constraint.** It wrote `X != Y` as the
  plain test `\==` (or `=\=` beside arithmetic), which differs whenever an
  argument is unbound. A numeric `!=` (a side that exports as an integer --
  including `-3`, a quantity literal such as `5000(euro)` and a constant
  folded to an integer -- or as arithmetic) is now clpz's `#\=`, imported
  beside `#=`; any other, including a float, is `dif/2`. `is not` stays `dif/2`. See
  [docs/prolog_translation.md](docs/prolog_translation.md).

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
| `[K, V]` pairs for `pairs_*` / `group_pairs_by_key` | `'-'(K, V)` |
| `-implicit_atoms` | list the atoms in `-private([...])` / `-module(name, [...])`, or quote them |
| `X := Expr` in a body | `eval_(Expr, X)` |
| `Compound(f, args)` / `KWTerm(...)` | the cell `(f, *args)` |
| `exc.term` read as an object (`.args`, `.functor`) | `cell_functor(exc.term)`, `cell_args(exc.term)` |
| matching the context text in `error(_, Context)` | match the culprit indicator, or `_`; the prose is `exc.message` |
| `assertz` into an undeclared predicate | declare it `-dynamic` first |

## 0.4.0

See the `v0.4.0` tag.
