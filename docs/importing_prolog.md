# Importing Prolog Code

!!! warning "Experimental in 1.0"
    `.pl` import is **experimental** and outside the 1.0 compatibility
    promise (see [Public API](public-api.md)). It translates Prolog source
    into Clausal's own syntax with an older translator; it is not an ISO
    Prolog system. Programs that use cut or if-then-else are refused (see
    [Known limitations](#known-limitations)).
    For running real ISO Prolog alongside Clausal, use the
    [Scryer](scryer.md) or [Trealla](trealla.md) embeddings.

Clausal can import `.pl` (Prolog) files directly. drop a `.pl` file on
`sys.path` and `import` it — Clausal translates, compiles, and caches it
automatically.

```python
import clausal              # installs the import hook

import my_prolog_module     # translates my_prolog_module.pl on the fly
```

The result is a normal Clausal module: each predicate is bound to its handle,
dispatch is compiled, and everything works exactly as if you had written the
code in `.clausal` syntax — including querying it from Python with a goal cell
and `module=`.

---

## Quick example

Given a file `edges.pl`:

```prolog
edge(1, 2).
edge(2, 3).
edge(3, 4).

path(X, Y) :- edge(X, Y).
path(X, Z) :- edge(X, Y), path(Y, Z).
```

Import and query it from a `.seam` file like any Clausal module:

```python
# app.seam
-module(app, [])
-import_from(edges, [path])

def main():
    for X in --path(1, X):
        print("path", 1, X)      # path 1 2, path 1 3, path 1 4
```

From a plain `.py` file, where `--` is not available, use the lower-level
`solve` with a goal cell:

```python
import clausal
from clausal import solve, Var
from clausal.logic.variables import deref

import edges  # finds and translates edges.pl

x, y = Var(), Var()
for _ in solve(("path", x, y), module=edges):
    print(f"path({deref(x)}, {deref(y)})")
```

Output:

```
path(1, 2)
path(2, 3)
path(3, 4)
path(1, 3)
path(1, 4)
path(2, 4)
```

---

## How it works

The translation pipeline runs inside Python's import machinery:

```
.pl source
  → prolog_to_clausal()    # Prolog text → Clausal text
  → EmbedTransformer       # Clausal text → Python AST
  → compile()              # Python AST → bytecode
  → .pyc cache             # bytecode cached in __pycache__/
```

On the first import, the full pipeline runs. On subsequent imports, the cached
`.pyc` is loaded directly — no translation or parsing.

---

## Finder priority

Clausal registers two import finders ahead of Python's own, checked in this
order:

| Priority | Finder | Extensions | Loader |
|---|---|---|---|
| 1 | `PredicateFinder` | `.clausal`, `.seam`, then `.pl` | `PredicateLoader`; `.pl` via `PrologLoader` or `NativePrologLoader` (`CLAUSAL_PL_FRONTEND`) |
| 2 | `ModulesFinder` | *(`py.X` names)* | redirects to `clausal.modules.py.*` |

`PredicateFinder` resolves per `sys.path` entry, in path order, as Python
does: the first entry that holds the module wins, whatever its extension.
Only within one entry does the extension decide: a flat `foo.clausal`, then
`foo.seam`, then a `foo/__init__.clausal` or `foo/__init__.seam` package,
then a flat `foo.pl`, then a `foo/__init__.pl` package. So if both
`foo.clausal` and `foo.pl` exist in the same directory, the `.clausal` file
wins -- you can keep the original `.pl` alongside a hand-optimized
`.clausal` version and the right one is always loaded -- but a `foo.pl` in an
earlier `sys.path` entry beats a `foo.clausal` in a later one.

A plain Python module is found by Python's `PathFinder`, which runs after
these finders: a `.clausal`, `.seam` or `.pl` module anywhere on `sys.path`
still wins over a `.py` module of the same name in an earlier entry.

---

## Importing data names from a `.pl` module

A `.pl` module's export list holds only `name/arity` predicates, and data
needs no declaration. So a seam `-import_from` of a name that the `.pl`
module neither defines as a predicate (at any arity) nor binds gives you
the ATOM of that name:

```prolog
% citations.pl
:- module(citations, [citation/2]).
citation(art1, [label-'Art 1']).

% rules.pl
:- module(rules, [verdict/2]).
verdict(P, v(ok, [cite(art1)])) :- P = p.
```

```python
# score.seam
-import_from(citations, [citation, cite])   # citation: the predicate
                                             # cite: the atom cite
-import_from(rules, [verdict, v, ok, p])

match(K, C) <- (verdict(p, T), T is v(ok, [cite(K)]), C is cite(K))
```

The query `match(K, C)` answers `K = art1, C = cite(art1)`.

An atom is global by spelling, so the `cite` you import is the same atom
the `.pl` rulebase writes in `cite(art1)`: the term built from it
(`('cite', 'art1')`) is `==` to the rulebase's.

- A name the module binds keeps its ordinary meaning: an exported
  predicate imports the predicate, and a data atom the file itself uses
  imports that atom. A predicate the module defines but does not export
  is an error (see
  [Unexported predicates in Clausal code](#unexported-predicates-in-clausal-code)).
- A `name/N` entry names a predicate, so it never resolves to data: with
  no `name/N` in the module it is still an `ImportError`.
- The imported name also builds terms at any arity, positionally:
  `--cite(++k)` and a clause's `cite(K)` are `('cite', K)`, the rulebase's
  `cite(k)`. So does a data functor the `.pl` module uses and you import
  (`v` above), under either front end.
- A typo can no longer fail the import, so a name within a small edit
  distance of one of the module's predicates (`citaton` for `citation`)
  warns once, with `ClausalImportedDataNameWarning`, naming the predicate.
- Only `.pl` targets: a `.clausal`/`.seam` module exports its data in its
  `-module(...)` list, and a name missing there is still an `ImportError`.

### Reading a data name as an attribute

The same rule answers attribute access from Python (ruled 2026-10-01).
`getattr(mod, 'employment')` or `mod.employment` on a module loaded from
`.pl` (either front end, including a package's `__init__.pl`) is the atom
`'employment'` when the module neither defines `employment` as a predicate
(at any arity) nor binds it:

```python
import citations                   # citations.pl
citations.cite                     # 'cite', the atom
citations.citation                 # the predicate's handle, as before
```

- Only an atom-shaped name is answered: a lowercase identifier that is no
  Python keyword and no reserved name (`true`, `false`, `undefined`). A
  dunder or private name (`__wrapped__`, `_x`), a TitleCase name and a
  non-identifier still raise `AttributeError`.
- Tooling gets no answer: importlib's submodule probe, the Python standard
  library (`unittest`'s `load_tests`, `doctest`, `pickle`, `inspect`) and
  tools such as pytest and Sphinx still see `AttributeError`, so their
  hook lookups (`getattr(mod, 'load_tests', None)`) behave as before.
  Only your own code gets the atom.
- A submodule of a `.pl` package that is not imported yet is not data:
  `from pkg import sub` still imports it.
- In Python code, `from mod import name` is `getattr(mod, 'name')`, so an
  unbound atom-shaped name imports its atom too (ruled 2026-10-01: in
  Python code, Python semantics apply). That includes a name that is not a
  submodule of a `.pl` package: `from pkg import nosuchsub` gives the atom
  `'nosuchsub'`. In Clausal code the same name goes through the seam
  `-import_from` rules above.
- A near miss of a predicate (`citations.citaton`) warns once per module
  and name, with `ClausalImportedDataNameWarning`.
- `.clausal`/`.seam` and Python modules are unchanged.

**`getattr`/`hasattr` on a `.pl` module no longer signals absence; use
`clausal.has_predicate` / `clausal.defines_predicate` /
`clausal.module_binds`.** `clausal.has_predicate(mod, name, arity=None)`
asks whether `name` is a predicate you can call through the module (defined
there or imported, as in a thin facade), `clausal.defines_predicate` whether
the module itself defines it, and `clausal.module_binds(mod, name)` whether
the name is a real attribute of the module (a predicate or data).

### Unexported predicates from Python

In Python code there is no export privacy (ruled 2026-10-01: in Python
code, Python semantics apply). A predicate a `.pl` module defines but does
not list in its `module/2` export list is still an attribute of the module,
so Python reaches it like any module attribute:

```python
import citations                   # :- module(citations, [citation/2]).
citations.helper                   # helper/1 is not exported: its handle
from citations import helper       # the same handle
solve(("helper", X := Var()), module=citations)   # runs
```

!!! warning "Possible, but not supported long-term and not advisable"
    Reaching an unexported predicate from Python works today, under both
    front ends, but it is **not supported long-term** and may stop working
    in a future release. Python callers should use the module's exported
    predicates. There is no runtime warning.

Clausal code gets no such access: a seam `-import_from(citations, [helper])`
(or `helper/1`, or `alias(helper, h)`) and a `.pl`
`:- use_module(citations, [helper/1])` of a predicate the module defines
but does not export are load-time errors (see
[Unexported predicates in Clausal code](#unexported-predicates-in-clausal-code)).

---

## Importing between `.pl` files

Prolog's `:- use_module` directive is translated to Clausal's import system.
when one `.pl` file imports another, the import hook handles both files:

```prolog
% helpers.pl
double(X, Y) :- Y is X * 2.

% main.pl
:- use_module(helpers, [double/2]).
quad(X, Y) :- double(X, T), double(T, Y).
```

The `use_module` with an explicit import list is the recommended form — it
maps directly to Clausal's `-import_from` directive, which injects the
imported predicates into the calling module's namespace. The list keeps its
indicators, so `[double/2]` imports `double/2` only, as in Scryer; a
`library(...)` list is imported by bare name (a library may be a Python
module, which has no arities). `use_module/1`
imports every predicate the `.pl` module's `module/2` directive exports
(`-import_module` plus an `-import_from` of that list); for a `.clausal` or
`.seam` module it is `-import_module`, whose predicates are reached
qualified.

An EMPTY import list, `:- use_module(m, []).`, is a translation error naming
the line: Scryer reads it as `remove_module/2` (it drops `m`'s imports and
does not load `m`, so `m:p(X)` is an `existence_error`), while Trealla and
SWI load `m` and import nothing. Write `use_module(m)` or
`use_module(m, [p/1])` instead; after either, `m:p(X)` reaches every
predicate `m` exports, in Clausal, Scryer and Trealla alike.

### Unexported predicates in Clausal code

In Clausal code, importing a predicate that a `.pl` module defines but does
not list in its `module/2` export list is a load-time `ImportError` carrying
`permission_error(access, private_procedure, Name/Arity)` (ruled
2026-10-01). That covers a seam `-import_from(m, [p])`, `[p/N]` and
`[alias(p, q)]`, and a `.pl` `:- use_module(m, [p/N])`, under both front
ends:

```prolog
% m.pl
:- module(m, [rate/1]).
rate(X) :- helper(X).
helper(5).
```

```python
-import_from(m, [helper])   # ImportError: ... permission_error(access,
                            #   private_procedure, helper/1) -- m defines
                            #   helper/1 but does not export it
```

- A bare name is refused when the module exports it at no arity; a `p/N`
  entry when the module defines `p/N` and does not export it. A bare name
  exported at one arity binds the NAME, so it also reaches the module's
  other, unexported arities; import `p/N` to take only the exported one.
- A circular import is not checked (the exporter is still loading).
- A `.pl` file with no `module/2` directive exports everything.
- A name the module does not define as a predicate is unaffected: a data
  name still imports its atom (above).
- Scryer accepts `use_module(m, [helper/1])` for an unexported `helper/1`
  silently and imports nothing, so the later call raises
  `existence_error(procedure, helper/1)`; Clausal refuses at load time
  instead. The error term is provisional.
- Python code is not affected (see
  [Unexported predicates from Python](#unexported-predicates-from-python)).

### `end_module`: closing a module

A `.pl` module file may end with the ISO 13211-2 directive
`:- end_module(Name).` Both `.pl` front ends check it:

- `Name` names the module the file's `:- module(Name, Exports).` opened;
- it is the last item of the file: only comments may follow it.

Anything else is a load-time `SyntaxError` naming the line and carrying the
ISO error term (the ISO 13211-2 text is not in this repository; the terms
are Clausal's, in Scryer's `error(E, Context)` shape):

| The file | The error |
|---|---|
| `:- end_module(other).` in module `m` | `error(existence_error(module, other), end_module/1)` |
| `end_module` with no `module/2`, or a second `end_module` | `error(existence_error(module, Name), end_module/1)` |
| a clause or directive after `end_module(m)` | `error(permission_error(modify, module, m), end_module/1)` |
| `end_module(X)` / `end_module(f(x))` | `instantiation_error` / `type_error(atom, f(x))` |

**Requiring it.** In a `.pl` file end_module is optional. When it is
REQUIRED, a module file without it fails to load with
`error(existence_error(directive, end_module(m)), load/1)`, naming the file
and the module. Most specific first:

1. the file's own `:- set_prolog_flag(require_end_module, true).` (or
   `false`) -- it governs that file only;
2. the process-wide setting: `CLAUSAL_REQUIRE_END_MODULE=1` (or `0`) in the
   environment, `clausal.end_module.set_require_end_module(True | False |
   None)` from Python, or `set_prolog_flag(require_end_module, V)` run as a
   goal (`V` is `true`, `false` or `default`); `current_prolog_flag/2` reads
   it;
3. the surface's default: `.pl` does not require it; the Clausal Prolog
   surface will (it has no file extension of its own yet).

A seam file (`.seam`, and `.clausal` today) is never affected, and has no
`end_module`.

Scryer does not accept `end_module/1` (`domain_error(directive,
end_module/1)`, and the file fails to load): a file meant for Scryer as well
leaves it out, or has it removed on the way
(`clausal.end_module.strip_end_module`).

### Importing a Python-backed module

Under the native front end (`CLAUSAL_PL_FRONTEND=native`) a `.pl` file can
import an engine module whose predicates are written in Python, such as
`py.datetime`:

```prolog
:- use_module(py/datetime, [date_add/3, timedelta/3, days_between/3]).
due(D) :- timedelta(30, 0, TD), date_add(date(2026, 1, 15), TD, D).
```

`py/X` names the same module as `-import_from(py.X, ...)` in a `.seam`
file. Each `name/N` entry is checked against the module's predicates (see
`clausal.module_signatures` in [the public API](public-api.md)): a name the
module does not have, or an arity it does not register, is a load-time
`SyntaxError` that names the line and lists what the module offers.
`use_module(py/datetime)` with no list imports every predicate the module
has. A Python predicate is one object for all its arities, so importing
`p/N` also makes `p`'s other registered arities callable. A bare atom in
the list imports nothing, as for any module.

### Module paths

A module is named by an atom (`helpers`), a quoted or unquoted path
(`'sub/helpers'`, `sub/helpers`, `'../shared/helpers'`, with or without a
`.pl` suffix), or `library(Name)`. As in Scryer, a path is resolved against
the **importing file's own directory** first; the file found there is
imported under its dotted module name (relative to the importer's package
root, or else to a `sys.path` entry). A path with no such file beside the
importer is read as a dotted module on `sys.path` (`a/b` is `a.b`), which is
how a bare name has always been resolved.

A module spec that names no importable module — a variable, a compound that
is not an `a/b` path, `'../../x'` with no such file and no dotted reading, or
a file outside every `sys.path` entry — is a load-time `SyntaxError` that
names the directive and its line. Until 2026-09-29 an unquoted `a/b` path
became a comment and the import vanished, and a quoted one failed with
"argument must be a dotted module path".

### Name clashes: qualified calls

When two modules export the same name, import them without a list (or
without that name) and call each one **module-qualified**, as in ISO and
Scryer: `m:p(X)` crosses as Clausal's qualified call `m.p(X)`.

```prolog
:- use_module(small_sizes).
:- use_module(big_sizes).

both(A, B) :- small_sizes:size(x, A), big_sizes:size(x, B).
```

Renaming an import with `as` (`use_module(m, [p/2 as q])`) is not
accepted: neither ISO nor Scryer has it, and the reader refuses the
directive. (A `.clausal`/`.seam` file has its own rename,
[`alias(p, q)`](import.md#aliases).)

### Library imports

Standard Prolog library imports are mapped to Clausal built-in modules:

| Prolog | Clausal equivalent |
|---|---|
| `:- use_module(library(clpfd), [...])` | `-import_from(clausal.logic.clpfd, [...])` |
| `:- use_module(library(clpz), [...])` | `-import_from(clausal.logic.clpfd, [...])` |
| `:- use_module(library(clpb), [...])` | `-import_from(clausal.logic.clpb, [...])` |
| `:- use_module(library(tabling), [...])` | `-import_from(clausal.logic.tabling, [...])` |
| `:- use_module(library(lists))` | *(built-in — no import needed)* |
| `:- use_module(library(apply))` | *(built-in — no import needed)* |
| `:- use_module(library(L))`, L one of `dif`, `between`, `error`, `pairs`, `when`, `freeze`, `iso_ext` | *(built-in — no import needed)* |
| `:- use_module(library(L), [...])`, every listed name an engine builtin | *(built-in — no import needed)* |

Any other `library(Name)` is read as the module `Name` (a missing one is an
`ImportError` at load). A predicate of a built-in library that the engine
lacks raises the ISO `existence_error` when it is called.

### Constants, units and dicts (native front end)

With `CLAUSAL_PL_FRONTEND=native`, a `.pl` file declares constants and units
with the same directive family as the seam
([Constants Directive](directives.md#constants-directive)), in ISO syntax:

```prolog
:- use_module(european_union, [euro, eur_cent]).   % a unit is a Python value
:- constant_value(max_retries, 3).
:- constant_number_units(max_fine, 5000, euro).
:- constant_number_units(one_euro, 1, euro).
:- constant_number_currency(fee, "292.00", euro).  % exact decimal: a string
:- constants_number_currency(snap_max/2, [[1, 29200], [2, 53600]],
                             eur_cent, money_at(2)).

next_try(X) :- X is constant(max_retries) + 1.
fine(N, Q)  :- Q is N * constant(one_euro), Q > constant(max_fine).
declared(N, U) :- constant_number_units(max_fine, N, U).  % 5000, euro
value(V)    :- constant_value(max_fine, V).               % program-wide
```

* `constant(Name)` is replaced at **compile time** (term expansion), as in the
  seam; it is not an evaluable functor. The name must be declared above the
  clause (or imported); anything else, including `constant(X)` or
  `constant(f(a))`, is a load error naming the `.pl` line.
* Units come **only** from these declarations. `5*euro` is the ordinary ISO
  term `'*'(5, euro)`; `make_quantity/3` stays available. Comparing a
  quantity with a plain number or another unit raises
  `system_error(units_mismatch)`, as in the seam; units that cancel give a
  plain number.
* `use_module(M, [name])` on a **Python** module (a currency jurisdiction
  such as `european_union`) imports the value `name`, as `-import_from` does;
  on a Prolog module a bare name imports nothing (D11).
* A value is ISO data: `:- constant_value(k, 2*3).` holds the term
  `'*'(2, 3)` (which `is/2` evaluates to 6), an atom is that atom, and
  `"..."` follows the `double_quotes` flag in force (chars by default).
  Under a units directive the number is a number or a double-quoted
  decimal string (`"292.00"`, exact), never an atom.
* Dicts are predicate forms only (no literal, no subscript): `dict_pairs/2`
  builds, `get/3` reads softly (fails on a missing key), `get_strict/3` reads
  strictly (`existence_error(dict_key, Key)`), `dict_put/4` and
  `dict_put_pairs/3` update.

---

## What translates and what doesn't

### Supported constructs

Most standard Prolog translates cleanly:

- Facts and rules (`:- body` becomes `<- (body)`)
- Arithmetic (`is`, comparison operators)
- Unification (`=` becomes `is`; `\=` becomes the quoted ISO builtin
  `'\\='(X, Y)`, a test run once, and `\==` becomes `'\\=='(X, Y)` --
  not the delayed `is not` (`dif/2`) and `!=` (CLP) constraints, which answer
  differently when an argument is unbound)
- Lists (`[H|T]` becomes `[H, *T]`)
- DCG rules (`-->` becomes `>>`)
- Directives (`dynamic`, `discontiguous`, `table`, `module`, `use_module`),
  in the ISO call form `:- dynamic(foo/1).`
- Negation as failure (`\+` becomes `not`)
- Standard order of terms: `X @< Y` (and `@>`, `@=<`, `@>=`) becomes the
  quoted ISO builtin `'@<'(X, Y)`; `compare/3` crosses unchanged. (Refused
  until 2026-09-29, when the engine had had them for weeks.)
- One name at several arities: `p(1).` and `p(1, 2).` define `p/1` and
  `p/2`, two procedures, as in ISO; `use_module(m, [p/1])` imports one of
  them.
- `bagof/3` and `setof/3` with the existential quantifier: `Y^Goal` becomes
  `Y ^ (Goal)` (nested to the right, `A ^ (B ^ (Goal))`), so the solutions
  group by the free variables as in ISO (8.10):
  `setof(X, Y^p(X, Y), L)` answers one list.

### Unsupported constructs

The translator **rejects** programs containing:

- **Cut (`!/0`)** — raises `SyntaxError`. Use `once/1`, `dif/2`, first-argument
  indexing, or constraints instead.
- **If-then-else (`(C -> T ; E)`)** — raises `SyntaxError`. Use reified
  if-then-else, separate clauses with `dif/2` guards, or constraints.

These are rejected rather than silently mistranslated, because their semantics
cannot be faithfully represented in Clausal's pure core.

A **query in program text** (`?- Goal.`) is refused too: it is not run on
load, and until 2026-09-29 it was silently turned into a comment. An
`:- op/3` directive is applied by the reader to the terms below it (its
effect on the program's text); Clausal has no run-time operator table, so
the directive itself is kept as a comment.

### Atoms and strings

The translator preserves the ISO distinction: a Prolog **atom** loads as a
Clausal atom, and a Prolog **double-quoted string** loads as a Clausal string.

```prolog
p("ab").          % a STRING -- the list ['a','b']
q(red).           % the ATOM red
r('hello world'). % the ATOM 'hello world'
```

translates to:

```
-double_quotes(chars)
-private([red])

p("ab"),

q(red),

r('hello world'),
```

- A **bare atom** (`red`) is emitted as a bare name and collected into an
  auto-generated `-private([...])` list, so it compiles under strict atoms
  with no work from you.
- A **quoted atom** (`'hello world'`), or one whose spelling is not a plain
  lowercase identifier or that collides with a Python keyword, is emitted
  single-quoted — `'…'` is an atom in every
  [`-double_quotes`](directives.md#-double_quotes) mode, so it stays an atom
  no matter what the engine default becomes.
- A **double-quoted string** is emitted double-quoted, and the generated
  module carries `-double_quotes(chars)` (written above every other directive,
  because it governs the literals below it) so the literal re-reads as the
  string it was. The directive is written only when the file actually
  contains a string.
- `true`, `false` and `fail` map to Python `True`/`False` (`a :- true.`
  becomes `a() <- (True)`).
- The atom `undefined` is emitted quoted (`'undefined'`): bare `undefined`
  is Clausal's truth value `Undefined`, which `-private` cannot declare
  (until 2026-09-29 a file holding the atom failed to load).

The ISO directive `:- set_prolog_flag(double_quotes, Mode)` (or the short
`:- double_quotes(Mode)`) governs every `"…"` below it, as in Scryer, and the
translator applies it at each literal: under `chars` (the default) `"ab"` is
the string `"ab"` (the chars `[a, b]`), under `codes` it is the list
`[97, 98]`, and under `atom` it is the atom `'ab'`. The module's own mode
follows for `chars` and `atom` (`-double_quotes(atom)`), so
`current_prolog_flag(double_quotes, M)` reports it; Clausal has no `codes`
module mode, so that directive becomes a comment while its literals are
still emitted as codes. Any other value is refused, naming the line (Scryer:
`domain_error(flag_value, double_quotes+Value)`). Until 2026-09-29 `codes`
was only a comment and the strings below it stayed chars.

Any other `:- set_prolog_flag(Flag, Value).` is carried across as the
directive [`-set_prolog_flag(Flag, 'Value')`](directives.md#-set_prolog_flag)
(the value quoted, so `fail` stays an atom). A setting the engine refuses
(`unknown` = `fail`, say) is then a load-time error; see [Prolog Flags](flags.md).

### ISO assert: `assert_creates_dynamic` is on

Every imported `.pl` module starts with the flag
[`assert_creates_dynamic`](flags.md#assert_creates_dynamic) set to `true`, so
the imported code gets ISO's assert (7.5.2(2)): `assertz(counter(0))` creates
`counter/1` as a dynamic procedure the first time, with no `:- dynamic`
declaration. A static predicate, a builtin and a declared data functor are
still refused with `permission_error(modify, static_procedure, PI)`.
`.clausal` and `.seam` modules keep the declare-first default (`false`).

The default is set by the loader, not written into the translation. A
`:- set_prolog_flag(assert_creates_dynamic, false).` in the file turns it
off for that module.

### Singletons: `_Name` is deliberate

A `.pl` file follows the Prolog convention (ISO, Scryer): a variable whose
name starts with `_` (`_Y` in `g(L) :- setof(X, p(X, _Y), L).`) is used
once on purpose, so the load does not warn about it. Any other variable
used once still gets `ClausalSingletonWarning`. This is the `.pl` loader's
rule only: in `.clausal` and `.seam` source every named variable used once
warns, whatever its spelling (see
[singleton variables](syntax.md#singleton-variables-and-_unused)).

---

## Loading `.pl` files programmatically

For tests and scripts that need to load a specific `.pl` file by path (rather
than relying on `sys.path` discovery):

```python
from clausal.import_hook import _load_prolog_module

mod = _load_prolog_module("my_module", "/path/to/my_module.pl")
logic_module = mod.__clausal_module__
```

You can also specify a Prolog dialect:

```python
from clausal.tools.prolog_dialect import Dialect

mod = _load_prolog_module("my_module", "/path/to/my_module.pl",
                          dialect=Dialect.scryer())
```

The default is Scryer's operator table (`Dialect.scryer_reader()`): ISO's
Table 7 plus Scryer's own defaults, prefix `+` (200, fy) and the infix `div`
and `rdiv` (400, yfx) -- what Scryer reports with no library loaded. It
replaced SWI's table on 2026-09-28. SWI's extra operators are therefore not
operators here, as they are not in Scryer: the prefix directive forms
(`:- dynamic foo/1.` -- write `:- dynamic(foo/1).`), `*->`, `=@=`, `\=@=`,
`xor`, and the dict operators `:<` and `>:<`. A file that needs one declares
it with `:- op/3`, which the reader applies as it goes, or pass
`Dialect.swi()` to read SWI source.

---

## Running a `.pl` file's tests

`test/1` clauses in a `.pl` file are tests, as in a `.clausal` file: the
translator keeps the `test` name, so `test('name') :- Body.` is the runner's
`test/1`. Both runners collect `.pl` files:

```bash
python -m clausal.testing path/to/rules.pl      # or a directory holding .pl files
python -m pytest path/to/rules.pl
```

A `.pl` file that fails to translate is reported as a failing `<load>` test
carrying the translator error (exit 1), never skipped. A `.pl` file with no
`test/1` clauses exits 5 ("no tests collected") unless `--allow-empty` is
given. See [Testing](testing.md).

---

## Error handling

Translation and parse errors are surfaced as `SyntaxError`, which Python's
import machinery displays clearly:

```
SyntaxError: Cannot import foo.pl: Cut (!/0) cannot be translated to Clausal.
```

| Error type | Cause | Exception |
|---|---|---|
| Prolog parse error | Invalid Prolog syntax | `SyntaxError` |
| Translation error | Unsupported construct (cut, if-then-else) | `SyntaxError` |
| Encoding error | Non-UTF-8 `.pl` file | `SyntaxError` |
| Import error | Missing module in `use_module` | `ImportError` |
| Unmappable module spec | `use_module(M)`, a path with no module | `SyntaxError` naming the directive and line |
| Empty import list | `use_module(M, [])` (Scryer and Trealla disagree on it) | `SyntaxError` naming the directive and line |

A translation error names the `.pl` line it comes from
(`Cannot import foo.pl: line 12: Cut (!/0) ...`).

---

## Bytecode caching

Translated `.pl` files are cached as `.pyc` bytecode in `__pycache__/`, just
like `.clausal` files. Cache invalidation is automatic — if you modify the
`.pl` file, the next import re-translates and recompiles.

The `.pyc` is keyed on the `.pl` file's mtime and size, and on a
fingerprint of the engine, including the translator itself (see
[Caching](caching.md)), so:

- **Editing the `.pl` file** invalidates the cache (triggers re-translation)
- **Upgrading or editing the engine** invalidates it too
- **Restarting Python** loads from cache (no re-translation)
- **`sys.dont_write_bytecode = True`** suppresses cache writes

---

## Translation reference

For the full mapping between Prolog and Clausal syntax, see
[Prolog Translation](prolog_translation.md).

The key operator mappings:

| Prolog | Clausal |
|---|---|
| `:-` | `<-` |
| `=` | `is` |
| `\=` | `'\\='(X, Y)` (ISO "not unifiable", a test; not `is not`, which is the delayed `dif/2`) |
| `\==` | `'\\=='(X, Y)` (ISO term non-identity, a test; not `!=`, which is the CLP disequality) |
| `is` | `eval_/2` |
| `=:=` | `==` |
| `=\=` | `!=` |
| `=<` | `<=` |
| `\+` | `not` |
| `;` | `or` |
| `-->` | `>>` |
| `member(X, L)` | `X in L` |
| `X // Y`, `mod`, `rem`, `div`, `^`, `**`, `<<`, `>>`, `/\`, `\/`, `\` | the quoted ISO evaluable: `'//'(X, Y)`, `'^'(X, Y)`, ... |
| `max(X, Y)`, `abs(X)`, `sqrt(X)`, ... (any ISO evaluable) | the same name |

Predicate names cross unchanged: `foo_bar/2` stays `foo_bar/2`. A few
library predicates that Clausal spells differently are renamed to the
Clausal predicate that answers the same (`memberchk/2` → `in_check/2`,
`nth0/3` → `list_item/3`, `time/1` → `time_goal/1`, `all_distinct/1` →
`all_different/1`, ...), but never a name the program defines, declares or
imports from its own modules — a file's own `time/1` stays `time/1` — and
never a name the engine already has (`atomic/1`). Until 2026-09-29
`profile_get/3` was renamed to Clausal's `get/3` and `atomic/1` to an
`is_atomic/1` that does not exist; both now cross unchanged. A name
that collides with a Python keyword gets a trailing underscore (`not/1`
becomes `not_/1`), and a quoted functor whose name is not a plain lowercase
name is refused rather than translated — `'Foo'`, `'FOO'` and `'_foo'` would
each be emitted as a name Clausal reads as something other than a predicate
(a TitleCase identifier is a load-time error; the other two are logic
variables).

Variables keep their Prolog names — all of them, not just single letters.
`X` stays `X`, `Head` stays `Head`, `_Ignored` stays `_Ignored`: a
capital-initial identifier is a logic variable in Clausal exactly as it is in
ISO Prolog. Until 2026-09-10 a multi-letter variable was lowercased and given
a leading underscore (`Head` became `_head`), which was not injective —
`Head` and `HEAD` both became `_head` — so a clause using both silently
merged them into one variable.

One spelling does not survive, and is refused rather than translated:
`__Foo`, because a leading double underscore is excluded from the variable
class. It is a legal ISO variable; the refusal names the Prolog variable and
suggests a spelling that works.

`_PI_` was a second such case until 2026-09-11, when Clausal read one leading
and one trailing underscore as a [module constant](syntax.md#constants)
rather than a variable. Constants are spelled like atoms now, so `_PI_` is an
ordinary variable and crosses untouched. (Before 2026-09-10 it was silently
renamed to `_pi`.)

---

## Known limitations

- **Some compound data terms are not declared.** The translator declares a
  program's bare atoms and the functors of its data terms (`p(f(1)).` and
  `q(X) :- X = g(2).` add `f(_)` and `g(_)` to the `-private([...])` list).
  A name is left undeclared when the program defines, declares, imports or
  calls it as a predicate (including in a meta-predicate's goal argument,
  such as `findall(X, counter(X), L)`), or when the engine knows it as a
  builtin or evaluable at that arity.  A name used as data at two arities
  is declared at both (`box(1)` and `box(1, 2)` add `box(_)` and
  `box(_, _)`: a `-private` entry's field names are per arity).  A data term
  under a name that nothing
  else declares raises the ISO error term
  `error(existence_error(procedure, f/1), f/1)` when it is built (a
  `catch/3` sees it; from Python it is also a `NameError`).
- **Arithmetic.** `+ - * /` cross as Clausal's operators (`Y is X / 2`
  becomes `eval_(X / 2, Y)`), and `=:=` becomes the constraint `==` (see
  [Operators](operators.md)). The ISO operators Python spells differently
  (`//`, `mod`, `rem`, `div`, `^`, `**`, the bit operators) cross as the
  quoted ISO evaluable (`'^'(2, 3)`), and every ISO evaluable function keeps
  its name, so these answer as in ISO: `2 ** 3` is `8.0` and `2 ^ -1` is
  `type_error(float, 2)`. Until 2026-09-29 `max`/`min`/`abs` were renamed to
  `max_`/`min_`/`abs_` (a `type_error(evaluable, max_/2)`), `^` became Python
  `**` (`2 ^ -1` answered `0.5`) and `<<`, `/\`, `\/`, `\` were not
  evaluated at all.
- **A renamed library name is renamed in data position too.** The few
  renames that remain (`memberchk` → `in_check`, `float/1` → `float_/1`,
  ...) apply wherever the name appears as a functor, because a meta-call's
  goal argument is emitted as a term; `X = memberchk(a, L)` builds
  `in_check(a, L)`.
- **`use_module/1` of a `.clausal`/`.seam` module** gives qualified access
  only (`-import_module`); name the predicates with `use_module/2`.
- **No cut, no if-then-else** (above), and no streams or `op/3`. The ISO
  flags are there ([Prolog Flags](flags.md)), but `unknown` can only be
  `error`.

## Caveats

- **The `.pl` extension is also used by Perl.** If a Perl script ends up
  on `sys.path`, the import hook will attempt to parse it as Prolog and
  raise a `SyntaxError` -- even when a `.clausal` or `.seam` module of the
  same name sits in a later `sys.path` entry, since the earlier entry wins.
  `sys.path[0]` is the script directory or the current directory, so a
  stray `foo.pl` there shadows an installed `foo.clausal`.
- **All `.pl` files must be UTF-8 encoded.** Non-UTF-8 files raise a
  `SyntaxError` at import time.
- **Avoid naming `.pl` files after standard modules.** A file like `json.pl`
  on `sys.path` could shadow `clausal.modules.json`, and in the other
  direction `-import_from(graphs, [...])` in a Clausal module finds the
  standard `graphs` module before a `graphs.pl` of yours.

---

*See also: [For Prolog Programmers](for_prolog_programmers.md) — syntax
mapping and conceptual guide for Prolog users.*

*See also: [Prolog Translation](prolog_translation.md) — CLI tools and
full translation reference.*

*See also: [Module System](import.md) — Clausal's import directives and
cross-module calls.*

*See also: [Trealla Prolog Embedding](trealla.md) — fast, lightweight in-process Prolog via C · [Scryer Prolog Embedding](scryer.md) — strict ISO conformance with tabling support. Both run Prolog on actual ISO engines alongside the native engine.*
