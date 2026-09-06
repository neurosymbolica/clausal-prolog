# Importing Prolog Code

Clausal can import `.pl` (Prolog) files directly. drop a `.pl` file on
`sys.path` and `import` it — Clausal translates, compiles, and caches it
automatically.

```python
import clausal              # installs the import hook

import my_prolog_module     # translates my_prolog_module.pl on the fly
```

The result is a normal Clausal module: predicates are `PredicateMeta` classes,
dispatch is compiled, and everything works exactly as if you had written the
code in `.clausal` syntax.

---

## Quick example

Given a file `graphs.pl`:

```prolog
edge(1, 2).
edge(2, 3).
edge(3, 4).

path(X, Y) :- edge(X, Y).
path(X, Z) :- edge(X, Y), path(Y, Z).
```

Import and query from Python:

```python
import clausal
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

import graphs  # finds and translates graphs.pl

x, y = Var(), Var()
for _ in call("Path", x, y, module=graphs.__clausal_module__):
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
:- use_module(helpers, [double/1]).
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
- Unification (`=` becomes `is`, `\=` becomes `is not`)
- Lists (`[H|T]` becomes `[H, *T]`)
- DCG rules (`-->` becomes `>>`)
- Directives (`dynamic`, `discontiguous`, `table`, `module`, `use_module`)
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

P("ab"),

Q(red),

R('hello world'),
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
- `true`, `false` and `fail` map to Python `True`/`False`.

A `:- double_quotes(Mode)` directive in the source is carried across in
place, where it governs the clauses below it: `atom` becomes
`-double_quotes(atom)`; `chars` is already what the emitted header says, so
it is not written twice; `codes` has no Clausal mode (codes are spelled
`b"…"` at the literal) and is emitted as a comment.

!!! warning "`set_prolog_flag` is not translated"
    Only the bare `:- double_quotes(Mode)` spelling is carried across. The
    ISO/SWI form `:- set_prolog_flag(double_quotes, Mode)` is **not**
    recognised today: it falls through to the generic directive emitter as
    `-SetPrologFlag(double_quotes, atom)`, which is not a Clausal directive,
    so the import fails with `SyntaxError: Unknown directive:
    -SetPrologFlag(...)`. It is a loud failure, not a silent mistranslation —
    but if your `.pl` file sets the flag that way, rewrite it as
    `:- double_quotes(Mode)`.

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

The default dialect is SWI-Prolog.

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
| `\=` | `is not` |
| `is` | `eval_/2` |
| `=:=` | `==` |
| `=\=` | `!=` |
| `=<` | `<=` |
| `\+` | `not` |
| `;` | `or` |
| `-->` | `>>` |
| `member(X, L)` | `X in L` |

Predicate names are converted from `snake_case` to `PascalCase`:
`foo_bar/2` becomes `FooBar/2`.

Variables keep their Prolog names if single-letter (`X`, `Y`), otherwise
get a trailing underscore: `Head` becomes `head_`, `Result` becomes `result_`.

---

## Caveats

- **The `.pl` extension is also used by Perl.** If a Perl script ends up
  on `sys.path`, the import hook will attempt to parse it as Prolog and
  raise a `SyntaxError`.
- **All `.pl` files must be UTF-8 encoded.** Non-UTF-8 files raise a
  `SyntaxError` at import time.
- **Avoid naming `.pl` files after standard modules.** A file like `json.pl`
  on `sys.path` could shadow `clausal.modules.json`.

---

*See also: [For Prolog Programmers](for_prolog_programmers.md) — syntax
mapping and conceptual guide for Prolog users.*

*See also: [Prolog Translation](prolog_translation.md) — CLI tools and
full translation reference.*

*See also: [Module System](import.md) — Clausal's import directives and
cross-module calls.*

*See also: [Trealla Prolog Embedding](trealla.md) — fast, lightweight in-process Prolog via C · [Scryer Prolog Embedding](scryer.md) — strict ISO conformance with tabling support. Both run Prolog on actual ISO engines alongside the native engine.*
