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

- **`arg/3` with an unbound `N` raises `instantiation_error`** (ISO 8.5.2.3,
  as Scryer). It used to enumerate the `(N, Arg)` pairs, SWI's extension.
- **The clpz `#` family refuses a non-arithmetic operand.** `'#='`, `'#\='`,
  `'#<'`, `'#>'`, `'#=<'` and `'#>='` raise clpz's
  `domain_error(clpz_expression, Culprit)` for an atom, a string, a list, a
  compound that is not evaluable, or a Python `bool` anywhere in an operand
  (Scryer's clpz treats the atom `true` the same). A ground one used to fail
  (`'#='(1, foo)`), succeed (`'#\='(1, foo)`), raise
  `type_error(orderable, foo)` (`'#<'`), or count a bool as 0/1. Floats are
  unchanged. Infix `==` is unchanged.
- **`number_chars/2` and `number_codes/2` read their text as Scryer does**
  (ISO 8.16.7) and raise `syntax_error(unexpected_end_of_file)` or
  `syntax_error(unexpected_char)` for text that is not a number. They used to
  parse it with Python's `int()`/`float()` and fail, accepting `"1 "`,
  `"+1"`, `"1e5"` and `"inf"` besides; `"0x1A"` and `"0'a"` now read. With
  both arguments bound the text is read (`number_chars(1, ['0', '1'])`
  holds), and a float's text always carries its fraction (`1.0e+22`), so it
  reads back. `atom_number/2` still fails on a non-number, as Scryer's
  library does.
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
- **An empty test run fails.** `python -m clausal.testing` exits 5 ("no
  tests collected", pytest's number) when it collects no `test/1` clause; it
  exited 0. Pass `--allow-empty` when an empty run is expected. `--strict`
  is now the default and changes nothing. See [docs/testing.md](docs/testing.md).

### Added

- **`abolish/1` (ISO 8.9.4).** `abolish(Name/Arity)` removes a dynamic
  procedure: its clauses and the procedure itself, so a later call is
  `existence_error(procedure, Name/Arity)` (a procedure emptied by
  `retract/1` fails instead). A static procedure, user-defined or builtin,
  is `permission_error(modify, static_procedure, Name/Arity)`; a procedure
  that does not exist is no error; the indicator's errors are ISO's
  (instantiation, `type_error(predicate_indicator, PI)`, `type_error(atom,
  Name)`, `type_error(integer, Arity)`, `domain_error(not_less_than_zero,
  Arity)`). It was an existence error. The database has a matching
  `Database.abolish(functor, arity)`.

- **clpz's `sum/3` and `global_cardinality/3` on the native `.pl` front
  end.** `sum(Vs, Op, Value)` (Op one of `#=`, `#\=`, `#<`, `#>`, `#=<`,
  `#>=`; Value a clpz expression) and `global_cardinality(Vs, Pairs,
  Options)` with Scryer's options `consistency(value)` and `cost(Cost,
  Matrix)`, answering and raising as Scryer's clpz does. `sum/3` is not a
  global builtin (a global `sum` would shadow Python's `sum` inside a seam
  `++` escape): it resolves only in a `.pl` file that imports
  library(clpz), from `clausal.stdlib.clpz_sum`; a file that defines its
  own `sum/2` still loads.

- **automaton/8** (clpz, Scryer's signature): automaton/3 with counters.
  An arc `arc(From, Label, To, Exprs)` sets each counter to its
  expression, where a variable of `Counters` is that counter's previous
  value and a variable of `Template` the matching part of the current
  element; an arc without `Exprs` leaves the counters. Scryer's own
  library raises `instantiation_error` for every counter expression with a
  variable (its `template_var_path/3` calls `arg/3` with an unbound
  index); Clausal gives the documented relation (the documentation's
  `sequence_inflexions` example answers `N = 3`).
- **append/2, list_max/2 and list_min/2** (Scryer's library(lists)).
  `append(ListOfLists, List)` answers as its two-clause definition does,
  in the same order and with the same non-termination (`append([A,B],
  [1,2])` enumerates the three splits; `append(foo, L)` fails).
  `list_max/2` and `list_min/2` fold with `max/2` / `min/2` through `is/2`
  (`list_max([2, 2.0], M)` is `M = 2.0`; the first element is taken
  unevaluated, so `list_max([1+1], M)` is `M = 1+1`).

- **Native `.pl` front end: meta-predicates, library(reif) and the
  transition constructs.** `findall/4` (the list ends in a given tail, as in
  Scryer), `maplist/4..9` (every answer, like `maplist/2,3`) and `call/9`
  are new builtins, for `.seam` as well. After `:- use_module(library(reif))`
  a `.pl` goal `if_(If_1, Then, Else)` has Scryer's meaning: `If_1` is
  called with one more argument, the truth value (`X = Y` and `dif(X, Y)`
  are reified in place, `(A, B)` and `(A ; B)` unfolded), and an unbound or
  non-boolean truth value raises `instantiation_error` /
  `type_error(boolean, T)`. The rest of Scryer's reif export list is there:
  `(=)/3` and `dif/3` are engine builtins (Scryer's answer orders),
  `tmember/2`, `tmember_t/3` and `cond_t/3` are in `clausal.stdlib.reif`,
  and so are `tfilter/3` and `tpartition/4` with EVERY answer, which a
  `.pl` file importing library(reif) takes instead of the engine's
  committed-choice builtins of the same name. `\+`, `once/1`, `forall/2`,
  `memberchk/2`, the `findall(_, G, [])` backdoor and `make_quantity/3` are
  accepted and counted: `l3_stats["transition_constructs"]` holds the goal
  sites per construct, and a load with any logs one INFO line on the
  `clausal.pl_frontend` logger.

- **Constants, units and dicts on the native `.pl` front end.** A `.pl`
  file declares constants with the seam's directive family in ISO syntax
  (`:- constant_value(max_retries, 3).`, `:- constant_number_units(max_fine,
  5000, euro).`, `constant_number_currency/3` and the `constants_number_*`
  tables), runs through the seam's own handlers, and reads a value with
  `constant(Name)`, folded at compile time as in the seam; an undeclared
  name is a load error naming the `.pl` line. `constant_number_units/3` is
  module-scoped as in the seam. `use_module(european_union, [euro])` imports
  a unit (a bare name on a Python module imports its value). `5*euro` stays
  an ordinary ISO term. `is/2` and the ISO comparisons now accept a quantity
  (`Q is 100 * constant(one_euro)` answers 100 euro) instead of raising
  `type_error(evaluable, ...)`; comparing across units (or with a plain
  number) raises `system_error(units_mismatch)`, as the seam does.
- **`get_strict/3`: the strict dict read as a predicate.**
  `get_strict(Dict, Key, Value)` (get/3's argument order) raises
  `existence_error(dict_key, Key)` on a missing key, with the subscript
  `V is D[K]`'s other errors, where `get/3` fails. It is the strict read ISO
  syntax can spell; from `.seam` it is an ordinary call.
- **Native `.pl` front end: declarations (`CLAUSAL_PL_FRONTEND=native`).**
  A `.pl` file is not strict: every atom and data functor it uses is
  declared for it, so a `.seam` file can `-import_from` those names, and
  each load logs the count as one INFO line on the `clausal.pl_frontend`
  logger (the names at DEBUG). A data functor declared this way has no field
  names, and `assertz` of its term still creates a dynamic procedure. The
  optional `:- constructors([pt(x, y)]).` gives a data functor field names
  (`signature/3`, `unbound_keys/2`). Listed as `pt/2` in `module/2`, it is
  exported as data with those fields. There is no `atoms/1` directive.
  Not declared: a constant's name (`constant(Name)` is a fold, not data), a
  constants table's predicate, an imported name (a Python module's value
  such as `euro` included) and the engine's own names (clpz, clpq). A bare
  entry of a `use_module/2` list imports nothing and is a use of its atom,
  unless the module offers that name as `name/N` (a module/2 export, a
  Python module's predicate): then it is not declared either.
- **A set literal in goal position is a CLP(Q) constraint set.** In
  `.clausal`/`.seam` source, `two(N, Q) <- {Q == N * 2}` and
  `within(X) <- {0 <= X <= 10}` post exact rational constraints: the twin
  of clpq's `{C}` and the short spelling of `clpq.rational((...))`, which
  it lowers to (one goal, identical answers). Elements are comparisons
  (`==`, `!=`, `<`, `<=`, `>`, `>=` or a chain); any other element is a
  load-time error naming it. A set in data position is still a set and
  `{}` is still a dict. The constraint block now runs the units side
  channel, so a `-constant_number_units` constant folded in through
  `constant(Name)` keeps its unit: `{Q == 100 * constant(one_euro)}` gives
  `100 euro` (before, `clpq.rational` refused a Quantity as non-linear).
  See [docs/clpq.md](docs/clpq.md).
- **library(lambda) as builtins: `(\)/1..8`, `(^)/3..10`, `(+\)/2..9`.**
  Ulrich Neumerkel's lambdas (`maplist(\X^Y^(Y is 2*X), Xs, Ys)`,
  `Free+\X^Goal`) run through call/N with Scryer's answers: `\` copies the
  lambda before each call so no binding leaks between calls, `+\` shares the
  variables of its left side, and a parameter no argument reaches raises
  `existence_error(lambda_parameter, _)`. The native `.pl` front end accepts
  `use_module(library(lambda)[, List])` and adds its `op(201, xfx, +\)`.
  The procedures are global, as the list builtins are: unlike Scryer, a
  module that does not import the library can still call them, and
  `call(Y^G, A)` is library(lambda)'s `(^)/3` rather than an
  existence_error.
- **clpz's predicates under Scryer's names: `in/2`, `ins/2`, `labeling/2`,
  and the reified connectives `#<==>`, `#==>`, `#<==`, `#\/`, `#/\`, `#\`.**
  Domains are written `1..3`, `inf..sup`, `1..3 \/ 5..7` or an integer;
  `labeling/2` takes Scryer's options (`leftmost`/`ff`/`ffc`/`min`/`max`,
  `up`/`down`, `step`/`enum`/`bisect`) and answers in Scryer's order; a
  reified comparison or `in/2` keeps its 0/1 variable linked. Errors carry
  Scryer's formal terms (`domain_error(clpz_domain, D)`, ...). They are
  builtins, so they work from `solve()` and, quoted, from the seam; a
  module's own definition of the name answers first. The engine's
  `label/1` is unchanged (first-fail); a native `.pl` file that imports
  library(clpz) gets Scryer's `label/1` (`labeling([], Vs)`).
- **The native `.pl` front end: clpq's `{C}` and ops by import.** After
  `use_module(library(clpq))`, `{C}` is lowered to `clpq.rational(C)`. An import installs the operators Scryer
  installs: `use_module/1` every op the module exports; an import list the
  exported ops it names, plus the exported ops the module also declares
  with a top-level `op/3` (so `use_module(library(clpz), [label/1])` still
  makes `#=` an operator, while `use_module(library(lambda), [(\)/2])` no
  longer makes `+\` one).
- **`member/2` and `memberchk/2` are builtins under their ISO names.** They
  were registered only as `in_/2` and `in_check/2`, so a `.pl` file read by
  the native front end, or a goal handed to `solve()`, found no procedure.
  The same builtins answer both spellings; a module's own or imported
  `member/2` still answers first.
- **Negative tests: `test(Name, fail)`.** plunit's `test/2` with the option
  `fail` passes iff its goal has no solution; a solution fails it and an
  exception is an error, as for `test/1`. The seam spelling is the same term,
  `test("name", fail) <- Goal`, and `.pl` files write it as plunit does. Any
  other option (`throws(E)`, `nondet`, `true(C)`, ...) is a collection error
  naming it (`clausal.testing.TestCollectionError`; one failing `<collect>`
  item for the file), never ignored. As in plunit, `test/2` is reserved: a
  file defining its own `test/2` predicate with other second arguments now
  fails collection (no file in this repository defines one). In a `.pl` file an atom second argument of
  `test/2` stays that atom (`fail`/`false` no longer fold to `False` there),
  in heads, calls and data alike. See [docs/testing.md](docs/testing.md).
- **One name at several arities in one file**, as in ISO: `p(1),` and
  `p(1, 2),` define `p/1` and `p/2`, two unrelated procedures (a DCG
  `s//1` is `s/3`); neither is padded into the other. A bare `p` in a data
  position is still the atom, `p(1, 2)` is the compound at the arity
  written, and a call at an arity that has no clauses is still an
  arity-mismatch error. See [docs/predicates.md](docs/predicates.md).
- **Declared fields per arity.** A name may carry declared fields at
  several arities, each with its own field names, in `-module` and
  `-private` lists and across directives: `-module(lib, [q(X), q(X, Y)])`
  loads. A clause head of a declared name must be at a declared arity
  (write `f/2`, an indicator, to add an arity without fields). A term built
  from Python by field name uses the written arity, else the one declared
  arity its keywords fit, else raises `AmbiguousArityConstructionError`.
  An `-edcg_pred` name keeps one arity.
- **`.pl` files are test files.** `python -m clausal.testing` and the
  pytest plugin load a `.pl` file through the `.pl` importer and run its
  `test/1` clauses; a `.pl` file that fails to translate is a failing
  `<load>` item. A file opts out with a `% clausal: no-collect` comment. A
  directory scan lists the files it skipped, with the reason. See
  [docs/testing.md](docs/testing.md).
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
- **`clausal.module_signatures(module)`.** A `dict` from predicate name to
  the `frozenset` of its arities, for the predicates a module offers to
  `-import_from`. It answers for a Python-backed engine module (`py.datetime`,
  `currency`, `units`, ...), which has no Clausal source to read a signature
  from, as well as for a Clausal module. A module name is spelled and
  resolved as `-import_from` resolves it, and is imported if needed. See
  [docs/public-api.md](docs/public-api.md#13-python-entry-points).
- **A native `.pl` file can import a Python-backed module.**
  `:- use_module(py/datetime, [date_add/3, timedelta/3]).` works under
  `CLAUSAL_PL_FRONTEND=native`: `py/X` is redirected to the engine's
  `py.X` module as `-import_from(py.X, ...)` is, and each `name/N` entry is
  checked against `clausal.module_signatures`. A name the module lacks, or
  an arity it does not register, is a load error that names the `.pl` line
  and lists the predicates the module offers. `use_module(py/datetime)`
  imports every predicate the module has. See
  [docs/importing_prolog.md](docs/importing_prolog.md#importing-a-python-backed-module).
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

### Changed

Where there is a choice, ISO 13211-1 is the reference, and Scryer Prolog
where ISO is silent; SWI-Prolog is not a reference.

- **The Prolog exporter prefers ISO/Scryer spellings.** The default (`iso`)
  dialect writes `all_different` as `all_distinct/1` and `time_goal` as
  `time/1`, Scryer's names; `in_domain` and `divmod_` are unchanged. The
  default CLP(ℤ) library is `clpz` (`Dialect.swi()` keeps `clpfd`). Every
  dialect writes a prefix-operator directive in functional notation
  (`:- discontiguous(p/1).`), which both Scryer and SWI read. See
  [docs/prolog_translation.md](docs/prolog_translation.md).
- **Tests never drive Scryer's toplevel from stdin.** The oracle build hangs
  when its interactive toplevel reads a pipe or `/dev/null`, and when a `-g`
  goal raises with no separate `-g halt` after it. `tests/_oracles.py`
  `run_scryer(program, goals)` now asks each query with `-g` (stdin
  `/dev/null`, a trailing `-g halt`) and prints the answer with the
  toplevel's own printers (`tests/_scryer_toplevel.pl`), so `   X = 1.`,
  `   false.` and `   error(...).` read exactly as before. Every test that
  fed Scryer queries uses it; `tests/test_oracle_paths.py` guards that no
  direct Scryer call reads stdin.
- **`.pl` import renames nothing silently.** The ISO evaluables keep their
  names and ISO meaning (`max`, `min`, `abs`, `sqrt`, ...; `max` used to
  become `max_`, which is not evaluable); `//`, `mod`, `rem`, `div`, `^`,
  `**` and the bit operators cross as the quoted ISO evaluables
  (`'^'(2, -1)` is `type_error(float, 2)`, not `0.5`); `profile_get/3`,
  `atomic/1` and a program's own or imported names cross unchanged.
- **`.pl` import: `use_module` resolves paths as Scryer does.** A quoted or
  unquoted slash path (`sub/helpers`, `'../shared/helpers'`, with or without
  `.pl`) is resolved against the importing file's directory; an unquoted
  one used to become a comment and the import vanished. A spec that names
  no module is a `SyntaxError` naming the directive and its line. The
  built-in libraries (`dif`, `between`, `error`, ...) are explicit no-op
  imports. Every translation error names the `.pl` line.
- **`.pl` import: `set_prolog_flag(double_quotes, Mode)`** governs every
  `"…"` below it: `chars`, `codes` (`[97, 98]`) or `atom`. `codes` used to
  be ignored.
- **`.pl` import: the standard-order comparisons** `@<`, `@>`, `@=<`,
  `@>=` cross as the quoted ISO builtins (they were refused).
- **`.pl` import refuses what it cannot keep.** A query in program text
  (`?- G.`) is refused (it used to become a comment); the atom `undefined`
  is written quoted.
- **`.pl` import: a name clash between modules** is resolved with a
  module-qualified call, `m:p(X)` (which becomes `m.p(X)`). Renaming an
  import with `as` is not accepted, as neither ISO nor Scryer has it. See
  [docs/importing_prolog.md](docs/importing_prolog.md#name-clashes-qualified-calls).

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

- **A test clause whose body is exactly `true`, or a test fact, keeps its
  name and option.** Such a clause is stored like a fact, with its head
  arguments moved into leading unifications, and the test runner read the
  bare head: `test(name) :- true.` was reported as `_0` and run as
  `test(_)`, and `test(name, fail) :- true.` failed collection with
  "unknown test option `'fail'`". The runner now reads the moved arguments
  back. This affected both `.pl` front ends and `.clausal`/`.seam`
  (`test("name") <- True`), and a compound description on any seam test
  clause (`test(case(2)) <- ...`), which was run as `test(_)` and so could
  pass on the strength of another test's clause.
- **`findall/4` inside a `findall/3` goal no longer raises "findall/3 not
  found".** When a clause set called both `findall/3` (the compiler special
  form) and `findall/4`, the compiled clause could bind the name to a
  dispatch stand-in fixed at arity 3 and route the `findall/4` goal through
  it. Whether this happened depended on hash order, so it failed only on some
  runs. It affected `.pl` and `.seam` source alike.
- **`{}` in goal position is now a clear load-time error.** In `.seam`
  source `{}` is the empty dict, not an empty constraint set. As a goal it
  used to surface an internal `NotImplementedError` ("goal shape not yet
  supported (DictTerm)"). It now raises `DictGoalError`: "`{}` is an empty
  dict, not a goal in predicate p/1 (line N)". A non-empty set of
  comparisons in goal position is still the CLP(Q) constraint set.
- **`assertz((foo :- X))` with `X` unbound raises the runtime rule refusal.**
  An unbound body is a rule body (ISO converts it to `call(X)`), so it now
  gets `permission_error(assert, rule, foo)` like every other rule assert
  instead of `instantiation_error`. With `X` bound to `true` it still asserts
  the fact `foo`. The same applies to `asserta/1`.

- **An improper list read from a `.pl` file is the ISO cons cell, not a
  list of characters.** The native `.pl` front end read `[b|foo]` as
  `[b,f,o,o]` (the atom's characters spliced in), so `msort([b|foo], L)`
  answered `L = [b,f,o,o]`. A tail that is neither a list nor a variable
  now makes the compound `'.'(H, T)`: `sort/2`, `msort/2`, `keysort/2` and
  `atom_chars/2` raise `type_error(list, [b|foo])`, `is_list/1`, `length/2`
  and `append/3` fail, `member/2` finds the heads, `X = [b|foo], X = [H|T]`
  binds `H = b, T = foo`, and `writeq/1` prints `[b|foo]`, as Scryer does.
  A clause HEAD `[H|T]` does not yet match an improper list.
- **The native `.pl` front end resolves a `use_module` path beside the
  importing file first.** Inside a `.pl` package `pk`, `use_module(sib, ...)`
  now imports `pk.sib` when `pk/sib.pl` (or `.clausal`, `.seam`, `.py`, a
  package) exists, and a slash path `a/b` names `a/b` beside the importer;
  only a path with nothing beside the importer is read as a dotted module on
  `sys.path`. This is Scryer's rule and the translator's. Before, the native
  front end read the path as a top-level module only: a same-named module
  later on `sys.path` answered silently, and without one the import was
  refused.
  In both front ends a plain directory beside the importer (one with no
  `__init__` file) is no module: Scryer opens only the file, and the
  translator used to take such a directory and never fall back to
  `sys.path`.
- **The bytecode cache key includes the source suffix.** A same-directory
  `twin.pl` and `twin.clausal` share one `__pycache__` file; with equal size
  and modification time each was served the other's bytecode. `.pl` and
  `.seam` caches are rebuilt once; `.clausal` caches are unaffected.
- `_load_module` and `_load_prolog_module` accept a `pathlib.Path` on a warm
  bytecode cache too (it raised `TypeError`).
- A non-`str` `sys.path` entry (`None`, `bytes`, an `int`, a `Path`) is
  skipped by the source finder, as CPython's `PathFinder` skips it, instead
  of raising `TypeError` out of every import.
- **clpz global constraints follow Scryer's clpz contract.**
  `global_cardinality(Vs, Pairs)` now requires every element of `Vs` to be
  one of the keys: it counted per key only, so an element free to take an
  off-key value satisfied every count (`X in 0..2,
  global_cardinality([X], [1-0])` labelled X = 0 and 2; clpz has no
  answer). Its counts and elements must be integers or variables (`[1-a]`
  succeeded; now `type_error(integer, a)`), and a repeated key is
  `domain_error(gcc_unique_key_pairs, Pairs)`. `zcompare/3` raises
  `domain_error(order, O)` for a bound Order other than `<`, `=`, `>` (it
  failed) and `type_error(integer, X)` for a non-arithmetic operand.
  `element/3` raises `type_error(integer, I)` for a non-integer index (it
  failed). `scalar_product/4` takes any clpz expression as its fourth
  argument (`Y*Y`, `4/2`), as `#=` does; every compound was refused.
- **`compare/3` checks its Order argument (ISO 8.4.2.3).** An Order that is
  neither a variable nor an atom is `type_error(atom, Order)`; an atom other
  than `<`, `=` and `>` is `domain_error(order, Order)`.  `compare(foo, a, b)`
  used to fail silently.

- **`succ/2` and `numlist/3` raise Scryer's errors instead of failing.**
  `succ(X, Y)` with both unbound is an instantiation error, a non-integer
  argument `type_error(integer, A)` and a negative one
  `domain_error(not_less_than_zero, A)`; `numlist(a, 3, L)` is
  `type_error(integer, a)`.  All of these used to fail silently.
  (`numlist/3` with an unbound bound still fails; Scryer enumerates.)
- **CLP(R) reads a united variable's interval.** The units side channel
  posts a physical quantity's constraint on a shadow variable; `inf/2`,
  `sup/2` and `label_real/1,2` read the user's variable instead, so after
  `clpr.real((X >= constant(one_metre), X <= 2 * constant(one_metre)))`,
  `inf(X, L)` answered `0 metre` (from CLP(Q)) and `sup(X, H)` failed. They
  now read the shadow and answer with the expression's dimension (`1.0
  metre`, `2.0... metre`), the same numbers as the unit-free twin. Money is
  still refused by CLP(R) (`units_unsupported`).

  A clause head list pattern takes the cell apart too: `p([H|T], H, T)`
  called with `[b|foo]` answers `H = b, T = foo`, `[a, b|T]` walks nested
  cells, and a proper pattern such as `[a, b]` matches only a chain that
  ends in `[]` (the head matcher, C and Python, shares the body's code).
- **`clause/2`, `retract/1` and `retractall/1` answer every clause when the
  pattern holds a frozen variable.** A `freeze/2` goal woken while a clause
  head was tested left its bindings behind, so
  `freeze(Y, Y = X), clause(p(Y), true)` found only the first clause, with no
  error.
- **`assertz(M:C)`, `asserta(M:C)`, `retract(M:C)` and `retractall(M:H)` act
  on module M.** Before, the assert stored a clause for `(:)/2` in the
  calling module, where nothing could reach it, and the retracts removed
  nothing and gave no error. An unbound `M` is an `instantiation_error`.
- **`retract/1` raises ISO's errors.** `retract(1)`, `retract("ab")` and
  `retract([a])` raise `type_error(callable, _)`, and a control construct
  (`retract((a, b))`, `retractall(true)`) raises
  `permission_error(modify, static_procedure, _)`, as in Scryer. Before,
  `retract/1` failed and `retractall/1` succeeded. `retract((p(_) :- 1))`
  now fails, as in ISO 8.9.3 and Scryer, instead of raising.
- **`retract/1` no longer recompiles the predicate for each clause it
  removes.** The next call recompiles it, once. A drain of 1,000 clauses
  took over a minute and now takes a few hundredths of a second.
- **`copy_term/2`, `term_variables/2`, `ground/1`, `numbervars/3`,
  `bagof/3`, `setof/3` and `findall/3` see the variables of a partial list
  nested in a term.** The C term walkers treated a partial list (`[A|T]`), a
  partial string or byte string, and a dict term as a leaf below the top
  level: `term_variables(f([A|T]), Vs)` gave `[]`, `copy_term(f([A|T]),
  f([B|U]))` left `A == B`, `ground(f([a|T]))` succeeded, and the free
  variables of a bagof/setof goal and the per-solution copy of findall/3
  missed them too. The walkers now read through these shapes at any depth,
  in C (no slowdown for proper terms), with the Python twins in step. A dict
  term's values are walked the same way (its keys are ground).
  `numbervars/3` numbers every variable except one in the hole of a partial
  list or string (the `T` of `[A|T]`), which it leaves unbound at any depth:
  `[A|'$VAR'(1)]` has no representation and could not be printed (ISO
  numbers it too; this follows the `[a|b]` gap).
- **`copy_term/2` copies `dif/2` constraints.** `dif(A, a), copy_term(A, B),
  B = a` now fails, as in Scryer: the copy carries the constraint, over
  copies of the constraint's other variables. `freeze/2` goals and CLP
  constraints are still not copied (their attribute is a compiled goal or a
  propagator network, not a term); findall/3 and bagof/3 copy no
  attributes, as in Scryer.

- **A `.pl` module in an earlier `sys.path` entry is no longer shadowed by a
  `.clausal` or `.seam` module of the same name in a later one.** The import
  hook now resolves source modules per `sys.path` entry, in path order: the
  first entry that holds the module wins, and the extension priority
  (`.clausal`, `.seam`, then `.pl`) decides only within one entry. Before,
  `.clausal`/`.seam` and `.pl` were found by two finders that each scanned
  the whole path, so a `.pl` package could load a same-named `.clausal`
  sibling from another tree and answer from it without any error.
  `PrologFinder` is no longer installed on `sys.meta_path`; `PredicateFinder`
  finds `.pl` too. The other side of the same rule: a stray `foo.pl` in an
  earlier entry (such as the script directory, `sys.path[0]`) now shadows a
  `foo.clausal` or `foo.seam` in a later one. See
  [docs/importing_prolog.md](docs/importing_prolog.md).

- **A partial list is `instantiation_error` in the clpz globals.**
  `tuples_in/2`, `global_cardinality/2`, `lex_chain/1`, `automaton/3` and
  the other clpz predicates that read a list raised
  `type_error(list, [1|_])` for a partial list; Scryer's `must_be/2` gives
  `instantiation_error`.
- **subtract/3, intersection/3 and union/3 compare elements by `==/2`.**
  Python's `==` made `1` and `1.0` (and `f(1)` and `f(1.0)`) one element:
  `subtract([1, 2, 1.0], [1.0], D)` gave `[2]`, now `[1, 2]`.
- **CLP(Q) accepts quantities.** `{Q = 100 * constant(one_euro)}` in a
  `.pl` file, `clpq.rational(Q == 100 * constant(one_euro))`, `in_q/3` with
  quantity bounds, `entailed/1` and the objectives of `maximize/2`,
  `minimize/2`, `sup/2`, `inf/2` and `bb_inf/3` go through the units side
  channel the CLP(FD) comparators already use: dimensions are inferred and
  checked first (a disagreement is `system_error(units_mismatch)`), the
  tableau solves on exact magnitudes in the base unit, and the answer is a
  quantity — `100 euro`, `3/2 euro`, and `N = 300` for
  `{Q = N * constant(one_euro)}, Q = 300 euro`. Every such post used to
  raise a raw `TypeError: CLP(Q) requires linear constraints`. A quantity
  leaf inside an arithmetic cell built at run time (`Q = 6000 * constant(c)`
  in ISO syntax) is evaluable in a post too, instead of
  `type_error(evaluable, ...)`. See [docs/clpq.md](docs/clpq.md#units).
- **`true` in a `.pl` data position is the truth value.** The native front
  end left `true`/`false`/`undefined` as atoms where the seam folds them to
  `True`/`False`/`Undefined`, so `memberd_t(b, [a, b], true)` FAILED (the
  reified `T` is `True`). They fold now, as in the seam; `True`/`False`
  written in a `.pl` file stay ordinary variables. Known divergence (as in
  the seam): the engine treats the folded values as bools, not atoms, so
  `atom(true)` fails, `atom_length(false, N)` and `functor(F, true, 1)`
  raise `type_error(atom, _)`, `true = 1` succeeds and `compare(O, true, a)`
  gives `<` (Scryer: yes, 5, `true(_)`, no, `>`).
- **A user-defined `true/N` or `false/N` (N >= 1) loads,** in `.seam` and
  `.pl` alike (ISO and Scryer allow it): the seam refused it as a "reserved
  truth value name", and `call(true, X)` now reaches it. `true/0` and
  `false/0` stay the truth values; `undefined/N` stays reserved.
- **A listless `use_module/1` of a `.seam` module imports its export list**
  on the native front end: the bare names of its `-module` list were
  skipped, so the module's predicates were not in scope; a module exporting
  nothing is still loaded, so `m:G` reaches it.

- **A procedure `assertz` creates is no longer shadowed by an atom of the
  same name some other module declared.** Module dicts are seeded from the
  process-wide atom pool, so the body goal `note(X)` of a later,
  assert-created `note/1` bound to the atom `note` and raised
  `existence_error(procedure, note/1)`, depending on what the process had
  loaded first. The call now re-resolves in the calling module (its own
  row, then a builtin) and raises the same error only when nothing answers.
- **`:- use_module(m, []).` in a `.pl` file is a located translation
  error**, not a loader crash (`ValueError: empty names on ImportFrom`).
  Scryer reads it as `remove_module/2` (drops the imports, never loads
  `m`), Trealla and SWI as "load `m`, import nothing", so the error names
  both and points at `use_module(m)` / `use_module(m, [p/1])`. See
  [docs/importing_prolog.md](docs/importing_prolog.md).
- **A tail-recursive clause keeps its effects on caller variables.**
  Tail-recursion optimisation restarted the clause after undoing its whole
  trail segment, so a `dif` or CLP constraint on a caller variable
  (`K is not H`, `K != 3`), a binding of one (`K is foo`) and a binding
  nested in a tail argument were silently lost:
  `findall(1, (ka(K, [a, b]), K is a), R)` gave `R = [1]` for
  `ka(K, [H, *T]) <- (K is not H, ka(K, T))`. The restart is now taken only
  when the clause touched nothing but variables it created; otherwise it
  makes the ordinary recursive call. See
  [docs/compiler.md](docs/compiler.md#tail-recursion-optimization-tro).
- **`==` and `!=` see through bound variables.** A variable bound inside a
  list, cell or dict reads as its value, as ISO `==/2` dereferences every
  subterm: `X is [Y], Y is 1, X == [1]` failed silently.
- **`.pl` import: `bagof/3` and `setof/3` keep `Y^Goal`.** The quantifier
  was stripped, so `setof(X, Y^p(X, Y), L)` answered once per `Y`.
- **`.pl` import declares a program's data functors.** `p(f(1)).` in an
  imported `.pl` file answers `p(f(1))` instead of raising
  `existence_error(procedure, f/1)`; a name used as data at two arities is
  declared at both.
- **The native ISO reader keeps the last clause** of a text with no
  trailing newline (`clausal.tools.iso_l3.read_iso`, internal; not yet the
  `.pl` import path), and its `lower_items` raises on a refusal by default.
- **The bytecode cache key covers everything that decides the emitted
  code**: the evaluable table, the units and countries tables, the term
  helpers and the `.pl` translator with its tokenizer, as well as the
  compiler. Editing any of them used to leave stale cached bytecode.
- **The Prolog exporter names each import and export once.** A `-module`
  export list is deduplicated by `Name/Arity`, and so is an import list
  whose arities are known (`[helper/1, helper/1]`, `helper(X)` beside
  `helper/1`, `sent//1` beside `sent/3`). An import list holding a bare
  name, with no module signatures to give its arity, is written as a
  listless `use_module(lib)`: Scryer refuses a bare atom in an import list
  and Trealla imports nothing.
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
  folded to an integer -- or as arithmetic, including a clpz evaluable
  such as `abs(X)`) is now clpz's `#\=`, imported beside `#=`; any other,
  including a float, is `dif/2`. `is not` stays `dif/2`. See
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
