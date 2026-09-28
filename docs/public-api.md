# Public API (1.0)

From 1.0.0, Clausal follows [semantic versioning](https://semver.org/). A
change that breaks anything in the **covered** surface below needs a major
release (2.0). Anything **internal** may change in any minor release.

"Stable" here means two things together: the covered API is frozen, and
downstream code built on it keeps working. A release candidate has to go
through a 7-day stability window, with no behaviour changes, before it is
tagged 1.0.0.

Deprecated forms keep working, with a warning, for the whole 1.x series.
They are removed in 2.0.

---

## 1. Covered

### 1.1 The surface language

- The `.clausal` file format and its alias `.seam`: the same syntax,
  found, loaded and cached the same way. Where both `name.clausal` and
  `name.seam` exist, `.clausal` wins. See [Syntax](syntax.md).
- The clause forms: facts (`head,`), rules (`head <- body`), and test
  clauses (`test("description") <- body`, the `test/1` predicate). See
  [Testing](testing.md).
- The directives documented in [Directives](directives.md): `-module`
  (including `-private` and `-hide`), `-import_from`, `-import_module`,
  `-strict_atoms`, `-implicit_functors`, `-dynamic`,
  `-table`, `-discontiguous`, `-meta_predicate`, `-shallow`,
  `-set_prolog_flag`, the
  `-constant_value` / `-constant_number_units` family, `-allow_singletons`,
  `-specialize` and the EDCG directives. `-double_quotes` is **transitional**
  (see 2).
- Export lists: `name/arity` exports a **procedure**. A fielded entry
  `edge(A, B)` exports a **data functor** (a term constructor). A fielded
  entry with no clauses stays data, and calling it raises an
  `existence_error` that says so. A bare `name` exports the atom.
- The dynamic database is **declare-first**: `assertz/1` and its kin add
  clauses only to a predicate declared `-dynamic`. Asserting into any other
  predicate raises `permission_error(modify, static_procedure, Name/Arity)`.
  The module flag `assert_creates_dynamic` (below) selects ISO 7.5.2(2)
  instead: an assert into a procedure that does not exist creates it as
  dynamic. It is `false` in a `.clausal`/`.seam` module and `true` in an
  imported `.pl` module.
- Literal semantics:
    - `'x'` and bare `x` are the **atom** `x`.
    - `"…"` is a **string**, which is a char list, by default (as in
      Scryer and Trealla).
    - `b"…"` is a list of byte codes.
    - Lists accept both `[H, *T]` and ISO `[H|T]`, which are the same term.
    - Arithmetic on exact numbers stays exact: `+ - *` on integers,
      rationals and `Decimal` are exact, `/` of two exact numbers is
      rational (`7 / 2` is `7/2`), and an integral rational is presented as
      an `int` (`4 / 2` is `2`). Mixing a float with a `Decimal` raises.
    - Arithmetic written as a plain cell, such as `('+', 1, 2)`, evaluates
      wherever an arithmetic expression does (`eval_/2`, the arithmetic
      comparisons, `between/3`, `#=`, `==`/`!=` constraints, CLP(Q) and
      CLP(R)). The evaluable functors form one closed, static table; any
      other compound raises `type_error(evaluable, Name/Arity)`.
    - Units and currencies: `Quantity` values with dimension checking.
      See [Units](units.md) and [Currency](currency.md).
- Name classes: a name with a capital initial, or one that starts with `_`,
  is a logic variable. A TitleCase name used as a functor is a load-time
  error.
- The Python seams in hosted code: `++expr` (a Python escape) and `--term`
  (a term, or a goal in goal position). Their boundary rules are in 1.4.

### 1.2 Builtins and error terms

- The ISO builtins and the error terms they throw, as documented in
  [Builtins](builtins.md) and the
  [ISO compatibility report](iso_prolog_compatibility_report.md). The quoted
  ISO names (`'is'`, `'='`, `'=='`, `'=:='`, `'@<'`, `compare/3`, `'=..'`,
  and the rest) are part of this.
- **Prolog flags:** `set_prolog_flag/2` and `current_prolog_flag/2`, the
  directive `-set_prolog_flag/2`, and the flag names and values documented
  in [Prolog Flags](flags.md): the ISO flags `bounded`, `max_integer`,
  `min_integer`, `integer_rounding_function`, `char_conversion`, `debug`,
  `max_arity`, `unknown`, `double_quotes`, and `assert_creates_dynamic`.
  Which flags are module-scoped is covered too. The set of values a flag
  can be SET to may grow (`unknown` = `fail`, say) in a minor release.
- The builtin predicates in the Clausal standard library, by name and
  arity, as documented under [Builtins](builtins.md) and the library pages.
  They are covered as **predicates**, called from `.clausal` source or as a
  goal cell. The Python objects `clausal` exports under the same names are
  not (see 3).
- **Error terms are Scryer's.** An error is the plain cell
  `error(Formal, Culprit)`: `Formal` is the ISO formal term
  (`type_error(atom, 1)`, `existence_error(procedure, foo/1)`, …) and
  `Culprit` is the predicate indicator of the culprit, or an unbound
  variable when there is no single culprit. The names inside `Formal` are
  atoms. Both the `Formal` and the `Culprit` are covered.
- The explanatory prose that accompanies an error is **not** part of the
  term. It is `LogicException.message` (or `None`) and is printed after the
  term. Its text is not covered: messages can improve in a minor release.
  After a Prolog catch-and-rethrow (`catch(G, E, throw(E))`) the prose is
  recovered on a best-effort basis only.

### 1.3 Python entry points

All of these import from `clausal`:

```python
from clausal import (
    solve, call, once, query,            # the query API
    query_wfs, Solutions,
    declared_atoms,                      # module introspection
    Var, Trail, Module,                  # runtime objects
    deref, unify,                        # term access
    cell_functor, cell_args, make_cell,  # reading and building a cell
    to_python, to_clausal, term_key,     # the converters
    LogicException, UnboundVarCoercionError,
    Quantity, UnitsMismatch,
)
```

| Name | Signature | Notes |
|---|---|---|
| `solve` | `solve(goal, module=None, trail=None) -> Iterator[Trail]` | `goal` is a cell; `module=` is required for an unqualified cell. Read bindings inside the loop. |
| `call` | `call(functor, *args, module=None, trail=None) -> Iterator[Trail]` | Drives one predicate directly. `module=` and `trail=` are keyword-only. |
| `once` | `once(goal, module=None, trail=None) -> Trail \| None` | The first solution, or `None`. |
| `query` | `query(goal, variables, module=None, trail=None) -> Iterator[dict]` | **Deprecated** (`DeprecationWarning`). Covered through 1.x, removed in 2.0. |
| `query_wfs` | `query_wfs(goal, variables, module=None, trail=None) -> list[dict]` | Well-founded semantics: each answer dict carries `"_truth"` (`True` or `Undefined`) and `"_delays"`. See [WFS](wfs.md). |
| `Solutions` | `Solutions(goal, module=...)` | The interactive (REPL/notebook) solution iterator and display. |
| `declared_atoms` | `declared_atoms(module_or_package) -> frozenset[str]` | The atoms the module's own files declare in their `-module`/`-private` lists; for a package, also its **loaded** submodules. Excludes `-import_from`ed atoms and does not depend on import order. Takes a module, a `Module` or a dotted name (lookup-only, like `module=`). See [Python integration](python_integration.md#listing-the-atoms-a-module-declares-declared_atoms). |
| `cell_functor`, `cell_args`, `make_cell` | `cell_functor(c)`, `cell_args(c) -> tuple`, `make_cell(functor, *args) -> tuple` | Read and build a compound term (a cell). |
| `to_python` | `to_python(val)` | Deep conversion out. |
| `to_clausal` | `to_clausal(value) -> Any` | Deep conversion in. Raises `TypeError` for an unregistered class. |
| `term_key` | `term_key(term) -> tuple` | The standard order of terms, as a sort key. |
| `Var` | `Var()` | `.value`, and `int()` / `float()` / `bool()` / `str()` / f-string coercion. |
| `Trail` | `Trail()` | Pass one explicitly to keep a residual constraint store. |
| `Module` | `Module(name)` | A logic module. `module=` also accepts an imported `.clausal` module or a dotted name. |
| `deref`, `unify` | `deref(term)`, `unify(a, b, trail) -> bool` | |
| `LogicException` | `.term` is the thrown term; `.message` is the prose or `None` | Every `throw/1` and ISO error that reaches Python. |
| `UnboundVarCoercionError` | subclass of `TypeError` | |
| `Quantity`, `UnitsMismatch` | | The units value and its error. |

`module=` accepts a `Module`, an imported `.clausal` module, or the module's
dotted name as a string. An unqualified cell with no module raises ISO
`existence_error(module, …)`.

A module attribute for a predicate (`fibonacci.fib`) is the predicate's
**handle**, a `str`. Compare handles with `==` and never parse them; the
spelling is opaque (see 3). A handle is not callable. Build the cell and pass
the module.

Also covered:

| Import | Names |
|---|---|
| `clausal.logic.atoms` | `mint`, `is_atom`, `spelling`, `char_atom` (the Python atom API) |
| `clausal.logic.cells` | `chars`, `is_chars`, `chars_text` (the string carrier) |
| `clausal.logic.seam` | `UndefinedAnswer`, `ResidualConstraints` |
| `clausal.logic.solve` | `query_wfs` (the same function as `clausal.query_wfs`) |
| `clausal.testing` | `load_clausal_module` |
| `clausal.import_hook` | `enable_ipython` |
| `clausal.lint_warnings` | the warning classes in 1.6 |

### 1.4 The term representation and the Python boundary

- **An atom is a Python `str`.** `'bar'` is the atom `bar`. Compare atoms
  with `==`, never with `is`.
- **A string is the carrier `('$chars', text)`.** Build one with
  `clausal.logic.cells.chars(text)`.
- **A compound is a plain cell:** a tuple whose first element is the functor
  name and whose remaining elements are the arguments. For example,
  `('edge', 'a', 'b')`. There is no compound class.
- The 1-tuple `('x',)` is **reserved**. It is not an atom and must not be
  built.
- A list is a Python `list`.
- A dict term or a set term reaches Python as an internal object. The
  covered way to read one is `to_python`, which gives a `dict` or a
  `frozenset`; the classes themselves (`DictTerm`, `SetTerm`) are not
  covered.
- A goal from Python is a cell run against a module:
  `solve(('fib', 10, F := Var()), module=m)`.

The boundary does no conversion unless you ask for it (the "dumb seam"):

- A goal-position `--` seam (`if --g(X):`, `for X in --g(X):`,
  `while --g(X):`) hands back the engine's **raw** term: an atom as its
  `str`, a string as its carrier, a compound as its cell.
- `++` passes a value in **unconverted**. A Python `str` that comes in
  through `++` is an atom.
- To convert, call the converters by name: `to_python` (deep, out),
  `to_clausal` (deep, in), and `term_key` (the sort key).

See [Python integration](python_integration.md) for the full rules.

### 1.5 The `_get_dispatch` protocol

Any Python object with a `_get_dispatch()` method can stand as a predicate
(for `call/N`, as a goal object, or as a `py.*` module predicate). This
protocol is duck-typed and has out-of-tree implementors, so **its signature
is frozen**:

```python
class MyPredicate:
    def _get_dispatch(self):          # no parameters, ever
        return self._dispatch

    def _dispatch(self, this_generator, proceed, fail, catcher, *args):
        trail = args[-1]              # the arguments, then the trail
        ...
        yield (proceed, None)         # once per solution
        yield (fail, DONE)            # when exhausted
```

`DONE` is `clausal.logic.trampoline.DONE`. The engine never passes an extra
argument to `_get_dispatch()`. When it needs more information, it routes
around the method instead.

### 1.6 Lint warnings

The warning **classes** and their hierarchy are covered, so a
`warnings.filterwarnings(…, category=…)` keeps working. The message text is
not covered. All the classes live in `clausal.lint_warnings`, and every one
is a `UserWarning` through `ClausalLintWarning`, so they show by default:

`ClausalLintWarning`, `ClausalSingletonWarning`,
`ClausalCrossModeLiteralWarning`, `ClausalDeprecatedSpellingWarning`,
`ClausalTitleCaseIdentifierWarning`, `ClausalKeywordArgumentWarning`,
`ClausalCurrencyLiteralWarning`, `ClausalScaleInNameWarning`,
`ClausalShadowedVariableWarning`, `ClausalBooleanSeamWarning`,
`ClausalAtomExportDefinedAsPredicateWarning`,
`ClausalExportArityMismatchWarning`, `ClausalRetiredQuasiQuoteWarning`, `ClausalAtomClassDeprecationWarning`,
`ClausalSeamTextCompareWarning`, `ClausalStringInCatchPatternWarning`.

**The lint rule for 1.x:** a minor release may add a new lint, but a new
lint may only **warn**. Turning a lint into a load-time error, so that code
which loaded before is refused, needs a major release.

### 1.7 The import hook

- `import clausal` installs the import hook. After that, a plain `import`
  loads a `.clausal` or `.seam` file on `sys.path` as a Python module.
- Each predicate is bound to its handle, and `$module` holds the logic
  `Module`.
- Bytecode is cached in `__pycache__/`. The cache **format** is internal
  (see 3).
- `CLAUSAL_IPYTHON=1` enables the IPython integration eagerly.

---

## 2. Deprecated: works through 1.x, removed in 2.0

| Form | Replacement | Warning |
|---|---|---|
| `clausal.logic.atoms.atom('x')` (the boundary class) | `'x'`; test with `type(v) is str` or `is_atom(v)` | `ClausalAtomClassDeprecationWarning`, once per call site |
| `-double_quotes(atom)` / `-double_quotes(chars)` | Drop it: `'x'` for a symbol, `"x"` for text | Per-module ratchet. The directive is deleted once no module needs it. |
| TitleCase unit names (`Metre`) and the old physical-constant spellings | The lowercase / snake_case spelling (`metre`) | `ClausalDeprecatedSpellingWarning` |
| `query(goal, variables, module)` | `solve(...)`, reading `Var.value` | `DeprecationWarning` |

Two known gaps in the atom-class deprecation:

- `isinstance(v, atom)` does **not** warn. It is now `False` for every value
  the engine produces, so a filter built on it goes silently empty.
- Unpickling a pickled `atom` instance warns once, attributed to the
  `pickle.loads` call site.

---

## 3. Internal (may change in a minor release)

- Compiler internals (`clausal.logic.compiler`, `clausal.templating`,
  `clausal.pythonic_ast`), the `Database`, `Clause` and `PredRow` internals,
  and the trampoline and drive-loop internals, apart from the protocol in 1.5.
- The spelling of a mangled predicate handle. It is opaque.
- The C extension ABI.
- Cache formats, including the `.clausal` bytecode cache.
- The Prolog exporter (`clausal.tools.clausal_to_prolog`,
  `clausal.tools.prolog_dialect`), `clausal-fmt` and `clausal-rewrite`.
- Everything under `clausal.tools`, `clausal.reflection`, and any name that
  starts with `_`.
- `DictTerm` and `SetTerm` (`clausal.terms`); read them through `to_python`
  (1.4).

### Experimental in 1.0

- **Importing `.pl` files** (a plain `import` of a Prolog source file, see
  [Importing Prolog](importing_prolog.md)). It goes through a translator that
  is being replaced, and what it accepts and how it names things may change
  in a minor release.

### Exported by `clausal` but not covered

The builtin objects with a Python-identifier name (`append`, `between`,
`length`, …) are in `clausal.__all__` for convenience. Each builds the goal
cell for its builtin (`between(1, 3, X)` is `('between', 1, 3, X)`). The
predicates are covered by 1.2; the Python objects are internal and may
change in a minor release.

### Attributes of `clausal` that are internal

These are attributes of the `clausal` module but are not in
`clausal.__all__` and are not covered:

| Name | What it is | Use instead |
|---|---|---|
| `Database` | the clause store | `Module` |
| `Clause` | a stored clause record | |
| `structural_unify` | the unifier behind `=`, taking a `trail` | `unify` |
| `get_builtin_class` | looks up a builtin's object by functor | |

A builtin whose name is not a Python identifier (`'#='`, `'=..'`, `'@<'`, …)
and the dotted solver predicates (`z3.*`, `ortools.*`, `pysat.*`, `clpq.*`,
`clpr.*`) are not in `clausal.__all__`. They are still attributes of the
`clausal` module (`getattr(clausal, '#=')`) and are callable from `.clausal`
source as before.

### The packages under `packages/`

The packages under `packages/` are versioned independently. Some of them use
internal helpers (`clausal.modules.py.ModulePredicate`,
`simple_to_trampoline`, `clausal.logic.builtins._helpers`, the exporter), so
at the 1.0 release each one pins an exact **minor** release of Clausal: a
package built for 1.0 requires `clausal>=1.0,<1.1`, and is re-released for
each Clausal minor.

### Not part of 1.0

These were removed before 1.0 (see `CHANGELOG.md` in the repository):

- **`Compound`** and **`KWTerm`** (`clausal.terms`), with `compound_as_cell`,
  `list_to_cons`, `cons_to_list` and the builtin `extend/3`. A compound term
  is the plain cell `(functor, *args)`.
- **`make_predicate`** and **`MakePredicateRetiredError`**. A predicate is
  a row in its module's database. Write it in a `.clausal` module, or
  implement `_get_dispatch` (1.5).
