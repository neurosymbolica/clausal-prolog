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

Clausal registers three import finders, checked in this order:

| Priority | Finder | Extension | Loader |
|---|---|---|---|
| 1 | `PredicateFinder` | `.clausal` | `PredicateLoader` |
| 2 | `PrologFinder` | `.pl` | `PrologLoader` |
| 3 | `ModulesFinder` | *(bare names)* | redirects to `clausal.modules.*` |

If both `foo.clausal` and `foo.pl` exist in the same directory, the `.clausal`
file wins. This means you can keep the original `.pl` alongside a
hand-optimized `.clausal` version and the right one is always loaded.

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
imported predicates into the calling module's namespace.

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

### Unsupported constructs

The translator **rejects** programs containing:

- **Cut (`!/0`)** — raises `SyntaxError`. Use `once/1`, `dif/2`, first-argument
  indexing, or constraints instead.
- **If-then-else (`(C -> T ; E)`)** — raises `SyntaxError`. Use reified
  if-then-else, separate clauses with `dif/2` guards, or constraints.

These are rejected rather than silently mistranslated, because their semantics
cannot be faithfully represented in Clausal's pure core.

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

A `:- double_quotes(Mode)` directive in the source — or the ISO spelling
`:- set_prolog_flag(double_quotes, Mode)` — is carried across in place,
where it governs the clauses below it: `atom` becomes
`-double_quotes(atom)`; `chars` is already what the emitted header says, so
it is not written twice; `codes` has no Clausal mode (codes are spelled
`b"…"` at the literal) and is emitted as a comment.

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

---

## Bytecode caching

Translated `.pl` files are cached as `.pyc` bytecode in `__pycache__/`, just
like `.clausal` files. Cache invalidation is automatic — if you modify the
`.pl` file, the next import re-translates and recompiles.

The `.pyc` is keyed on the `.pl` file's mtime and size, so:

- **Editing the `.pl` file** invalidates the cache (triggers re-translation)
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

Predicate names cross unchanged: `foo_bar/2` stays `foo_bar/2`. A name
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
  such as `findall(X, counter(X), L)`), when the engine knows it as a
  builtin or evaluable, or when it is used as data at two arities (a
  `-private` entry declares field names, which belong to one arity; a
  PREDICATE may have several arities in one file, as in ISO -- a file
  defining `call_goal/1` .. `call_goal/8` imports).  A data term under such a
  name that nothing
  else declares raises the ISO error term
  `error(existence_error(procedure, f/1), f/1)` when it is built (a
  `catch/3` sees it; from Python it is also a `NameError`).
- **Arithmetic follows today's Clausal operators, not ISO's.** `Y is X / 2`
  becomes `eval_(X / 2, Y)`, and `=:=` becomes the constraint `==` (see
  [Operators](operators.md)).
- **No cut, no if-then-else** (above), and no streams or `op/3`. The ISO
  flags are there ([Prolog Flags](flags.md)), but `unknown` can only be
  `error`.

## Caveats

- **The `.pl` extension is also used by Perl.** If a Perl script ends up
  on `sys.path`, the import hook will attempt to parse it as Prolog and
  raise a `SyntaxError`.
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
