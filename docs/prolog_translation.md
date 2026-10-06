# Prolog Translation

Clausal Prolog includes a bidirectional translator between seam (`.seam`) and Prolog source (`.pl`, or a `.clausal` [Clausal Prolog](clausal_prolog.md) file read as Prolog). This enables exporting seam programs for use in Scryer, Trealla or SWI-Prolog, and importing existing Prolog code as seam source — either via the CLI tools or directly at import time (see [Importing Prolog Code](importing_prolog.md)).

!!! warning "Experimental in 1.0"
    The Prolog → seam direction, and `.pl` import built on it, is
    **experimental** in 1.0 (see [Public API](public-api.md) and the known
    limitations in [Importing Prolog Code](importing_prolog.md#known-limitations)).
    Where the two languages differ, Clausal Prolog follows ISO first and Scryer where
    ISO is silent; SWI is a supported export dialect, not a reference.

---

## Seam → Prolog

Translate a seam (`.seam`) source string to Prolog text:

```python
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

source = '''
edge(1, 2),
edge(2, 3),
reach(X, Y) <- edge(X, Y)
reach(X, Y) <- (edge(X, Z), reach(Z, Y))
'''

print(clausal_source_to_prolog(source))
```

Output:

```prolog
edge(1, 2).

edge(2, 3).

reach(X, Y) :-
    edge(X, Y).

reach(X, Y) :-
    edge(X, Z),
    reach(Z, Y).
```

### Dialect selection

Pass a `Dialect` to control dialect-specific output:

```python
from clausal.tools.prolog_dialect import Dialect

# The default: ISO, with Scryer's names where ISO has none
# (all_distinct, time, library(clpz))
print(clausal_source_to_prolog(source))

# SWI-Prolog output (all_different, library(clpfd))
print(clausal_source_to_prolog(source, dialect=Dialect.swi()))

# Scryer Prolog output (e.g. all_distinct, library(clpz))
print(clausal_source_to_prolog(source, dialect=Dialect.scryer()))

# Trealla Prolog output (same as Scryer — all_distinct, library(clpz))
print(clausal_source_to_prolog(source, dialect=Dialect.trealla()))
```

Where the dialects differ, the default follows ISO first and Scryer where
ISO is silent: its CLP(ℤ) library is `clpz` (only `Dialect.swi()` uses
`clpfd`), and it writes `all_different` as `all_distinct/1` and `time_goal`
as `time/1`. `in_domain` and `divmod_` keep their names, because Scryer's
`ins` is binary and it has no `divmod/4`.

### Intermediate Prolog AST

For programmatic access, stop at the AST stage:

```python
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog_ast

pmodule = clausal_source_to_prolog_ast("edge(1, 2),\n")
# PModule(items=(PClause(head=PCompound('edge', (PNumber(1), PNumber(2)))),))
```

The Prolog AST can be inspected, transformed, and emitted separately:

```python
from clausal.tools.clausal_to_prolog import emit_term, emit_item, emit_module
from clausal.tools.prolog_operators import OperatorTable

op_table = OperatorTable.iso_default()
for item in pmodule.items:
    print(emit_item(item, op_table))
```

---

## Translation rules

### Naming conventions

| Seam | Prolog | Rule |
|---|---|---|
| `all_different` | `all_different` | names cross unchanged |
| `dcg_rule` | `dcg_rule` | names cross unchanged |
| `findall` | `findall` | Builtin name map overrides |
| `time_goal` | `time` | Builtin name map (every dialect) |
| `all_different` | `all_distinct` | Builtin name map (`iso`, Scryer, Trealla; `all_different` under SWI) |

### Variable names

Variable names cross unchanged, in both directions.

| Seam | Prolog | Rule |
|---|---|---|
| `_x` | `_x` | names cross unchanged |
| `Foo` | `Foo` | names cross unchanged |
| `FOO` | `FOO` | names cross unchanged |
| `N0` | `N0` | names cross unchanged |
| `X` | `X` | names cross unchanged |
| `_` | `_` | Anonymous stays anonymous |

A capital-initial identifier names a logic variable in the seam exactly as it
does in ISO Prolog, and `_x` is a variable on both sides too, so a round trip
returns the spelling you wrote.

Until 2026-09-10 the translator renamed: `_head` → `Head`, `RESULT` →
`Result` outbound, `Foo` → `_foo` inbound. That rule was not injective —
`_result` and `RESULT` both became `Result` — so a per-clause table numbered
the second arrival (`Result2`) to stop two variables merging into one. Both
are gone. If you are comparing exported `.pl` against output from before that
date, expect **every** variable to differ, and expect a variable that used to
carry a disambiguating numeric suffix to lose it.

Two consequences worth knowing:

- One legal ISO variable spelling has no seam variable spelling and is
  **refused** by the importer rather than translated: `__Foo`, a dunder,
  excluded from the variable class. Refusing is not renaming, so injectivity
  is unaffected; the message names the Prolog variable and offers a spelling
  that works. `_PI_` was refused for the same reason until 2026-09-11, when
  the [module-constant](syntax.md#constants) spelling was retired; it now
  crosses like any other variable.
- The singleton post-pass still runs, so a variable occurring exactly once in
  an exported clause is emitted with a leading underscore (`RESULT` →
  `_RESULT`) to silence the ISO singleton warning. A seam `_x`-style name
  already has one and is left alone.

### Operators

What the exporter emits (Scryer dialect shown; `==` is the seam's arithmetic
constraint, see [Operators](operators.md)):

| Seam | Prolog | Notes |
|---|---|---|
| `X is Y` | `X = Y` | Unification |
| `X is not Y` | `dif(X, Y)` | Disequality ([dif/2](constraints.md)) |
| `Z == X * 2` | `#=(Z, X * 2)` | CLP(ℤ) constraint; the module gets `:- use_module(library(clpz), [(#=)/2])` |
| `X == Y` | `#=(X, Y)` | The same constraint |
| `'=='(X, Y)` | `X == Y` | Structural identity (the quoted spelling) |
| `X != 3`, `X + 1 != Y`, `X != 5000(euro)` | `#\=(X, 3)`, `#\=(X + 1, Y)`, `#\=(X, 5000)` | CLP(ℤ) disequality when a side exports as an integer or arithmetic; the module imports `(#\=)/2` from clpz |
| `X != Y`, `X != foo` | `dif(X, Y)`, `dif(X, foo)` | Otherwise (not numeric, or not known to be) — see the note below |
| `X <= Y` | `X =< Y` | ISO `=<` (evaluates; not a constraint) |
| `eval_(X * 2, Z)` | `Z is X * 2` | Eager evaluation |
| `not G` | `\+ G` | Negation as failure |
| `A and B` or `A, B` | `A, B` | Conjunction |
| `A or B` | `(A ; B)` | Disjunction |

!!! note "`!=` stays a constraint"
    In the seam `X != Y` is a disequality **constraint**: it waits for its
    arguments rather than testing them now, so it is never exported as the
    plain tests `\==` or `=\=`, which differ from it whenever an argument is
    unbound. The exporter decides "numeric" from the source alone, on the
    term each side EXPORTS AS: a side that becomes an integer (an integer
    literal, `-3`, a quantity literal such as `5000(euro)`, a constant
    folded to an integer) or an arithmetic expression (including a clpz
    evaluable call such as `abs(X)`) gives clpz's `#\=`;
    anything else, including a variable, a float (literal, `2.5(euro)`, or
    a folded float constant: CLP(ℤ) is over the integers) and a constant
    folded to an atom, gives `dif/2`, which is sound for numbers too but
    does not propagate over a finite domain. The decision looks only at the
    two operands: `X != Y` between two variables is `dif/2` even when both
    are CLP(ℤ) variables elsewhere in the clause (the answers are the same;
    only the pruning is weaker). Write `'\\=='(X, Y)` in the seam
    when you mean the structural test -- which is what Prolog `\==` imports
    as.

### Lists

| Seam | Prolog |
|---|---|
| `[]` | `[]` |
| `[1, 2, 3]` | `[1, 2, 3]` |
| `[H, *T]` | `[H\|T]` |

### Directives

| Seam | Prolog |
|---|---|
| `-module(name, [foo(X)])` | `:- module(name, [foo/1]).` |
| `-module(name, [foo(X), foo/1])` | `:- module(name, [foo/1]).` (each `Name/Arity` once) |
| `-import_from(mod, [pred/2])` | `:- use_module('mod', [pred/2]).` |
| `-import_from(mod, [pred])` | `:- use_module('mod').` (a bare name has no arity to list) |
| `-dynamic(color(N, V))` | `:- dynamic(color/2).` |
| `-discontiguous(p/1)` | `:- discontiguous(p/1).` |
| `-private([...])` | *(omitted — Prolog visibility is module-based)* |

A prefix-operator directive (`dynamic`, `discontiguous`, `table`, ...) is
written in functional notation, `:- dynamic(color/2).`, which Scryer, Trealla
and SWI all read. An import list names each `Name/Arity` once. When the
exporter knows the exporting module's signatures (the export pipeline always
passes them), a bare name in an import list is written as the indicators it
stands for; without them it cannot give the arity, and Scryer refuses a bare
atom in an import list, so the directive is written without a list.

---

## Prolog AST nodes

All nodes are frozen dataclasses in `clausal.tools.prolog_ast`:

| Node | Description |
|---|---|
| `PAtom(name, quoted)` | Atom: `foo`, `'hello world'` |
| `PVar(name)` | Variable: `X`, `_` |
| `PNumber(value)` | Integer or float |
| `PString(value)` | Double-quoted string |
| `PCompound(functor, args)` | Compound term / operator |
| `PList(elements, tail)` | List with optional tail |
| `PCurly(body)` | `{Goal}` curly-bracketed term |
| `PClause(head, body)` | Clause: `head :- body.` |
| `PDCGRule(head, body)` | DCG rule: `head --> body.` |
| `PDirective(body)` | Directive: `:- body.` |
| `PModule(items)` | Complete Prolog source file |

Builder helpers: `atom()`, `var()`, `compound()`, `op()`, `prefix()`, `plist()`, `cons()`, `fact()`, `rule()`, `dcg_rule()`, `directive()`.

Introspection: `variables()`, `functors()`, `is_ground()`, `term_size()`, `subterms()`.

Visitor/transformer: `PrologVisitor`, `PrologTransformer` (same pattern as `ast.NodeVisitor`/`ast.NodeTransformer`).

---

## Operator table

`OperatorTable` in `clausal.tools.prolog_operators` tracks operator precedence and associativity. Factory methods:

- `OperatorTable.iso_default()` — ISO 13211-1 operators
- `OperatorTable.swi_default()` — ISO + SWI extensions (`xor`, dict operators, etc.)
- `OperatorTable.scryer_builtin_default()` — ISO + Scryer's own defaults (prefix `+`, `div`, `rdiv`): what Scryer's toplevel has with no library loaded. **The `.pl` translator reads with this table by default** (`Dialect.scryer_reader()`, ruling of 2026-09-28; it read with the SWI table before).
- `OperatorTable.scryer_default()` — ISO + Scryer CLP(Z) operators (`#=`, `#<`, etc.)
- `OperatorTable.trealla_default()` — ISO + Trealla CLP(Z) operators (same as Scryer)

The emitter uses the operator table to decide when to parenthesize subexpressions.

---

## Prolog → Seam

Translate a `.pl` (Prolog) source string to seam text:

```python
from clausal.tools.prolog_to_clausal import prolog_to_clausal

source = '''
edge(1, 2).
edge(2, 3).
reach(X, Y) :- edge(X, Y).
reach(X, Y) :- edge(X, Z), reach(Z, Y).
'''

print(prolog_to_clausal(source))
```

Output:

```python
edge(1, 2),

edge(2, 3),

reach(X, Y) <- (edge(X, Y))

reach(X, Y) <- (edge(X, Z), reach(Z, Y))
```

### Dialect selection

```python
from clausal.tools.prolog_dialect import Dialect

# The default: Scryer's operator table (ISO + prefix +, div, rdiv)
print(prolog_to_clausal(source))

# Parse SWI-Prolog source (SWI operator table: `:- dynamic foo/1.`, `*->`, ...)
print(prolog_to_clausal(source, dialect=Dialect.swi()))

# Scryer with library(clpz)'s operators (`#=`, `#<`, ...)
print(prolog_to_clausal(source, dialect=Dialect.scryer()))
```

### Parsing Prolog to AST

For programmatic access, parse to the intermediate Prolog AST:

```python
from clausal.tools.prolog_parser import parse, parse_term

pmodule = parse("edge(1, 2).\n")
# PModule(items=(PClause(head=PCompound('edge', (PNumber(1), PNumber(2)))),))

term = parse_term("X + Y * 2")
# PCompound('+', (PVar('X'), PCompound('*', (PVar('Y'), PNumber(2)))))
```

The parser is a Pratt (top-down operator-precedence) parser that:

- Uses `OperatorTable` for dynamic operator lookup
- Handles `op/3` directives mid-file (operators defined in earlier directives affect later parsing)
- Correctly resolves all Prolog associativity specifiers (`xfx`, `xfy`, `yfx`, `fx`, `fy`, `xf`, `yf`)
- Parses lists, curly braces, parenthesized terms, negative numbers, and quoted atoms

### Emitting seam text from Prolog AST

```python
from clausal.tools.prolog_to_clausal import prolog_ast_to_clausal, emit_clausal_item

clausal_text = prolog_ast_to_clausal(pmodule)
```

### reverse translation rules

| Prolog | Seam | Rule |
|---|---|---|
| `foo_bar(X)` | `foo_bar(X)` | names cross unchanged |
| `findall(...)` | `findall(...)` | reverse builtin name map |
| `X = Y` | `X is Y` | Unification |
| `X \= Y` | `'\\='(X, Y)` | ISO "not unifiable": a test, not the delayed `dif/2` |
| `Y is X * 2` | `eval_(X * 2, Y)` | Eager arithmetic evaluation |
| `Y =:= X * 2` | `Y == X * 2` | Arithmetic equality (a constraint in the seam) |
| `X =\= Y` | `X != Y` | Arithmetic disequality |
| `X == Y` | `'=='(X, Y)` | Structural identity |
| `X \== Y` | `'\\=='(X, Y)` | Structural non-identity: a test, not the CLP `!=` |
| `X =< Y` | `X <= Y` | ISO `=<` → `<=` |
| `\+ G` | `not G` | Negation as failure |
| `(A , B)` | `(A, B)` | Conjunction |
| `(A ; B)` | `(A or B)` | Disjunction |
| `(C -> T ; E)` | **Rejected** | Not supported — use [reified ITE](reified_ite.md) or [dif/2](constraints.md) guards |
| `!` (cut) | **Rejected** | Not supported — use [once/1](control.md), dif/2, [indexing](indexing.md) |
| `[H\|T]` | `[H, *T]` | List cons |
| `member(X, L)` | `X in L` | Membership |
| `foo(X) :- body.` | `foo(X) <- (body)` | Rules |
| `head.` | `head(),` | Facts (trailing comma) |
| `head --> body.` | `head() >> (body)` | [DCG](dcg.md) rules |
| `:- module(...)` | `-module(...)` | [Module directive](directives.md) |
| `:- use_module(library(L), [...])` | `-import_from(L, [...])` | Import directive; `clpfd`/`clpz` map to `clausal.logic.clpfd` |
| `:- use_module(sub/helpers, [p/1])` | `-import_from(sub.helpers, [p/1])` | A path resolves against the file's directory; `p/1` imports one arity |
| `:- use_module(m)` | `-import_module(m)` (plus an `-import_from` of a `.pl` module's export list) | Whole-module import |
| `m:p(X)` | `m.p(X)` | Module-qualified call |
| `X @< Y` | `'@<'(X, Y)` | Standard order (and `@>`, `@=<`, `@>=`) |
| `setof(X, Y^G, L)` | `setof(X, Y ^ (G), L)` | The `^` quantifier is kept |
| `X // Y`, `X mod Y`, `X ^ Y`, ... | `'//'(X, Y)`, `'mod'(X, Y)`, `'^'(X, Y)`, ... | Quoted ISO evaluables; `max`, `abs`, ... keep their names |
| `:- dynamic(p/N)` | `-dynamic(p/N)` | Dynamic directive |
| `:- op(P, T, N)` | `# operator: op(P, T, N)` | Comment (no clausal equivalent) |
| `X` (variable) | `X` | Variable names cross unchanged |

### User-defined operator mappings

For projects with custom operators, provide a JSON mapping file:

```json
{
  "operator_mappings": {
    "<>":  {"clausal": "not_equal", "arity": 2},
    "==>": {"clausal": "implies", "arity": 2}
  }
}
```

Use with the CLI:

```bash
python -m clausal.tools.prolog_to_clausal input.pl --operator-map ops.json
```

---

## CLI tools

### Unified translator

The recommended entry point for all translation tasks:

```bash
# Seam → Prolog (auto-detected from the .seam extension)
python -m clausal.tools.translate input.seam -o output.pl

# Prolog → seam (auto-detected from the .pl or .clausal extension)
python -m clausal.tools.translate input.pl -o output.seam

# Explicit target format
python -m clausal.tools.translate input.seam --to swi -o output.pl
python -m clausal.tools.translate input.seam --to scryer -o output.pl
python -m clausal.tools.translate input.pl --to clausal -o output.seam

# Pipe mode (stdin/stdout)
echo 'foo(1, 2),' | python -m clausal.tools.translate --to scryer
echo 'foo(1, 2).' | python -m clausal.tools.translate --to clausal

# Roundtrip check (exit 0 if roundtrip reproduces the original)
python -m clausal.tools.translate --roundtrip input.seam --dialect swi
python -m clausal.tools.translate --roundtrip input.pl --dialect swi
```

Options:

| Flag | Description |
|---|---|
| `--to clausal\|iso\|swi\|scryer` | Target format; auto-detected from extension if omitted. `clausal` means seam text (Prolog → seam); it does not produce a `.clausal` Clausal Prolog file. A `--to` that contradicts the input file's extension (`--to swi` on a `.clausal` or `.pl` file, `--to clausal` on a `.seam` file) is a usage error (exit 2) |
| `--dialect iso\|swi\|scryer` | Prolog dialect (default: iso for seam→prolog, Scryer's operator table for prolog→seam) |
| `-o FILE` | Output file (stdout if omitted) |
| `--roundtrip` | Translate there and back; exit 0 if output matches input |

### Single-direction tools

The individual tools are still available:

```bash
python -m clausal.tools.clausal_to_prolog input.seam -o output.pl --dialect swi
python -m clausal.tools.prolog_to_clausal input.pl -o output.seam --dialect swi
```

### Python API

```python
from clausal.tools.translate import translate, roundtrip
from clausal.tools.prolog_dialect import Dialect

# One-step translation
prolog = translate(clausal_src, direction="clausal_to_prolog", dialect=Dialect.swi())
clausal = translate(prolog_src, direction="prolog_to_clausal", dialect=Dialect.swi())

# Roundtrip check
ok, first_leg, second_leg = roundtrip(source, direction="clausal_to_prolog", dialect=Dialect.swi())
```

---

## Roundtrip properties

The roundtrip validation (Phase 4) verifies these properties when translating there and back:

| Property | Status |
|---|---|
| Clause count preserved | Verified for all non-DCG fixtures |
| Head functor/arity preserved | Verified |
| Variable identity preserved | Variables that co-occur in source still co-occur |
| Clause order preserved | Predicate clause order is semantic in Prolog |
| Operator precedence preserved | `a + b * c` stays `a + b * c` |
| Directive preservation | One-leg verified (dynamic, module, use_module) |

### Unsupported constructs

The translator **rejects** Prolog programs containing cut or if-then-else with a `PrologTranslationError`, rather than producing semantically incorrect output:

- **Cut (`!/0`)** — breaks declarative semantics. Use `once/1`, `dif/2`, indexing, or constraints.
- **If-then-else (`(C -> T ; E)`)** — defined in terms of cut in ISO. Use reified if-then-else (`THEN if COND else ELSE`), separate clauses with `dif/2` guards, or constraints.
- **Bare if-then (`(C -> T)`)** — same as above.

In the reverse direction (seam → Prolog), the seam's reified if-then-else (`THEN if COND else ELSE`) is also rejected because its monotonic three-valued semantics cannot be faithfully represented by Prolog's committed-choice `(C -> T ; E)`.

### Known roundtrip limitations

- **DCG rules**: Prolog `-->` ↔ seam `>>` roundtrip can produce syntax that doesn't re-parse in the second leg (comma-in-pushback-list edge cases).
- **Arity-indicator directives**: `:- dynamic(foo/2).` → `-dynamic(foo/2)` (the bare prefix form `:- dynamic foo/2.` needs `Dialect.swi()`: it is not an operator in Scryer's table); check the return leg with `--roundtrip` before relying on it.
- **Whitespace/formatting**: Exact text match is not guaranteed; structural equivalence is.

---

## Golden test files

Golden snapshot files live in `tests/fixtures/prolog_golden/`:

| Direction | Files | Purpose |
|---|---|---|
| Seam → Prolog | `*.pl` (11 files) | Checked-in expected Prolog output |
| Prolog → seam | `*.seam` (11 files) | Checked-in expected seam output |

To regenerate golden files after changing translation logic:

```bash
# Seam → Prolog
python -m clausal.tools.clausal_to_prolog SOURCE.seam -o tests/fixtures/prolog_golden/NAME.pl

# Prolog → seam
python -m clausal.tools.prolog_to_clausal SOURCE.pl -o tests/fixtures/prolog_golden/NAME.seam
```

---

## Tier 3: Scryer Prolog embedding

The translation pipeline feeds directly into the [Scryer Prolog embedding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) — an in-process Scryer engine accessible from Python via PyO3, shipped as the optional `clausal-scryer` package (`packages/clausal-scryer`; not part of the core install, so this example is not run by the core test suite). `.seam` files are translated to Prolog with `Dialect.scryer()` and loaded into the embedded machine:

```python
from clausal.scryer import Scryer

with Scryer() as s:
    s.consult_file("clausal/examples/fibonacci.seam")
    s.query_one("fib(10, R).")
    # {'R': 55}
```

See the [Scryer Prolog Embedding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) documentation for the full API.

---

## Roadmap

- **Phase 1.1** (done): Prolog AST nodes, operator table, dialect config
- **Phase 1.2** (done): seam → Prolog text emission
- **Phase 2** (done): Dialect-specific emission, golden tests, CLI
- **Phase 3** (done): Prolog → seam (tokenizer, Pratt parser, Prolog AST → seam text)
- **Phase 4** (done): Roundtrip validation, golden Prolog→seam files, unified CLI
- **Phase 5** (done, experimental in 1.0): Import-time `.pl` translation — `PrologFinder`/`PrologLoader` in the import hook translate `.pl` files on the fly, with `.pyc` caching and recursive `use_module` support (see [Importing Prolog Code](importing_prolog.md))
- **Phase 6** (stretch, not started): Self-hosted DCG translator — rewrite the Prolog parser as a seam DCG operating on a token stream, using the state-threading DCG pattern for dynamic `op/3` handling
- **Phase 7** (stretch, not started): Additional dialects — GNU Prolog (`fd_*` constraints), ECLiPSe (`lib(ic)`, `do/2`), XSB Prolog (HiLog, tabling differences), Tau Prolog (JavaScript-hosted); each as a `Dialect` subclass
