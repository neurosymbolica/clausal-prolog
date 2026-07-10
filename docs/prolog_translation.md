# Prolog Translation

Clausal includes a bidirectional translator between `.clausal` and `.pl` (Prolog) source files. This enables exporting clausal programs for use in SWI-Prolog or Scryer Prolog, and importing existing Prolog code into clausal — either via the CLI tools or directly at import time (see [import.md](import.md#importing-pl-prolog-files-directly)).

---

## Clausal → Prolog

Translate a `.clausal` source string to Prolog text:

```python
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

source = '''
Edge(1, 2),
Edge(2, 3),
Reach(X, Y) <- Edge(X, Y)
Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
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

# SWI-Prolog output (e.g. all_different, library(clpfd))
print(clausal_source_to_prolog(source, dialect=Dialect.swi()))

# Scryer Prolog output (e.g. all_distinct, library(clpz))
print(clausal_source_to_prolog(source, dialect=Dialect.scryer()))

# Trealla Prolog output (same as Scryer — all_distinct, library(clpz))
print(clausal_source_to_prolog(source, dialect=Dialect.trealla()))
```

### Intermediate Prolog AST

For programmatic access, stop at the AST stage:

```python
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog_ast

pmodule = clausal_source_to_prolog_ast("Edge(1, 2),\n")
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

| Clausal | Prolog | Rule |
|---|---|---|
| `FooBar` | `foo_bar` | PascalCase → snake_case |
| `all_different` | `all_different` | PascalCase → snake_case |
| `DCGRule` | `dcg_rule` | Acronym runs split correctly |
| `findall` | `findall` | Builtin name map overrides |
| `time_goal` | `time` | Builtin name map (SWI/Scryer) |

### Variable names

| Clausal | Prolog | Rule |
|---|---|---|
| `_x` | `X` | Strip leading underscore, uppercase |
| `_head` | `Head` | Strip underscore, capitalize |
| `RESULT` | `Result` | ALLCAPS → titlecase |
| `X` | `X` | Single uppercase stays |
| `_` | `_` | Anonymous stays |

### Operators

| Clausal | Prolog | Notes |
|---|---|---|
| `X is Y` | `X = Y` | Unification |
| `X is not Y` | `dif(X, Y)` | Disequality ([dif/2](constraints.md)) |
| `Y == X * 2` | `Y =:= X * 2` | Arithmetic equality (compound arithmetic operand) |
| `X == Y` | `X == Y` | Structural equality |
| `X != Y` | `X \== Y` | Structural inequality |
| `X <= Y` | `X =< Y` | ISO `=<` |
| `not G` | `\+ G` | Negation as failure |
| `A and B` or `A, B` | `A, B` | Conjunction |
| `A or B` | `(A ; B)` | Disjunction |

Note: on import, Prolog `=:=` with *atomic* operands (`X =:= Y`) still
becomes structural `X == Y` — a known lossy case pending decision A11-D008.

### Lists

| Clausal | Prolog |
|---|---|
| `[]` | `[]` |
| `[1, 2, 3]` | `[1, 2, 3]` |
| `[H, *T]` | `[H\|T]` |

### Directives

| Clausal | Prolog |
|---|---|
| `-module(name, [Foo(X)])` | `:- module(name, [foo/1]).` |
| `-import_from(mod, [Pred])` | `:- use_module('mod', [pred]).` |
| `-dynamic(Color(N, V))` | `:- dynamic(color/2).` |
| `-private([...])` | *(omitted — Prolog visibility is module-based)* |

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
- `OperatorTable.scryer_default()` — ISO + Scryer CLP(Z) operators (`#=`, `#<`, etc.)
- `OperatorTable.trealla_default()` — ISO + Trealla CLP(Z) operators (same as Scryer)

The emitter uses the operator table to decide when to parenthesize subexpressions.

---

## Prolog → Clausal

Translate a `.pl` (Prolog) source string to clausal text:

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
Edge(1, 2),

Edge(2, 3),

Reach(X, Y) <- (Edge(X, Y))

Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
```

### Dialect selection

```python
from clausal.tools.prolog_dialect import Dialect

# Parse SWI-Prolog source (uses SWI operator table)
print(prolog_to_clausal(source, dialect=Dialect.swi()))

# Parse Scryer Prolog source
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

### Emitting clausal from Prolog AST

```python
from clausal.tools.prolog_to_clausal import prolog_ast_to_clausal, emit_clausal_item

clausal_text = prolog_ast_to_clausal(pmodule)
```

### reverse translation rules

| Prolog | Clausal | Rule |
|---|---|---|
| `foo_bar(X)` | `FooBar(X)` | snake_case → PascalCase |
| `findall(...)` | `findall(...)` | reverse builtin name map |
| `X = Y` | `X is Y` | Unification |
| `X \= Y` | `X is not Y` | Disequality |
| `Y is X * 2` | `Y := X * 2` | Arithmetic evaluation |
| `Y =:= X * 2` | `Y == X * 2` | Arithmetic equality (atomic-operand `X =:= Y` imports as structural `==`; pending A11-D008) |
| `X == Y` | `X == Y` | Structural equality |
| `X \== Y` | `X != Y` | Structural inequality |
| `X =< Y` | `X <= Y` | ISO `=<` → `<=` |
| `\+ G` | `not G` | Negation as failure |
| `(A , B)` | `(A, B)` | Conjunction |
| `(A ; B)` | `(A or B)` | Disjunction |
| `(C -> T ; E)` | **Rejected** | Not supported — use [reified ITE](reified_ite.md) or [dif/2](constraints.md) guards |
| `!` (cut) | **Rejected** | Not supported — use [once/1](control.md), dif/2, [indexing](indexing.md) |
| `[H\|T]` | `[H, *T]` | List cons |
| `member(X, L)` | `X in L` | Membership |
| `head :- body.` | `Head() <- (body)` | Rules |
| `head.` | `Head(),` | Facts (trailing comma) |
| `head --> body.` | `Head() >> (body)` | [DCG](dcg.md) rules |
| `:- module(...)` | `-module(...)` | [Module directive](directives.md) |
| `:- use_module(library(L), [...])` | `-import_from(L, [...])` | Import directive |
| `:- dynamic(p/N)` | `-dynamic(P/N)` | Dynamic directive |
| `:- op(P, T, N)` | `# operator: op(P, T, N)` | Comment (no clausal equivalent) |
| `X` (variable) | `X` (single letter) or `_x` (leading underscore) | Variable naming |

### User-defined operator mappings

For projects with custom operators, provide a JSON mapping file:

```json
{
  "operator_mappings": {
    "<>":  {"clausal": "NotEqual", "arity": 2},
    "==>": {"clausal": "Implies", "arity": 2}
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
# Clausal → Prolog (auto-detected from .clausal extension)
python -m clausal.tools.translate input.clausal -o output.pl

# Prolog → Clausal (auto-detected from .pl extension)
python -m clausal.tools.translate input.pl -o output.clausal

# Explicit target format
python -m clausal.tools.translate input.clausal --to swi -o output.pl
python -m clausal.tools.translate input.clausal --to scryer -o output.pl
python -m clausal.tools.translate input.pl --to clausal -o output.clausal

# Pipe mode (stdin/stdout)
echo 'Foo(1, 2),' | python -m clausal.tools.translate --to swi
echo 'foo(1, 2).' | python -m clausal.tools.translate --to clausal

# Roundtrip check (exit 0 if roundtrip reproduces the original)
python -m clausal.tools.translate --roundtrip input.clausal --dialect swi
python -m clausal.tools.translate --roundtrip input.pl --dialect swi
```

Options:

| Flag | Description |
|---|---|
| `--to clausal\|iso\|swi\|scryer` | Target format; auto-detected from extension if omitted |
| `--dialect iso\|swi\|scryer` | Prolog dialect (default: iso for clausal→prolog, swi for prolog→clausal) |
| `-o FILE` | Output file (stdout if omitted) |
| `--roundtrip` | Translate there and back; exit 0 if output matches input |

### Single-direction tools

The individual tools are still available:

```bash
python -m clausal.tools.clausal_to_prolog input.clausal -o output.pl --dialect swi
python -m clausal.tools.prolog_to_clausal input.pl -o output.clausal --dialect swi
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

In the reverse direction (Clausal → Prolog), Clausal's reified if-then-else (`THEN if COND else ELSE`) is also rejected because its monotonic three-valued semantics cannot be faithfully represented by Prolog's committed-choice `(C -> T ; E)`.

### Known roundtrip limitations

- **DCG rules**: Prolog `-->` ↔ clausal `>>` roundtrip can produce syntax that doesn't re-parse in the second leg (comma-in-pushback-list edge cases).
- **Arity-indicator directives**: `:- dynamic foo/2.` → `-dynamic(Foo/2)` → the `/2` arity indicator doesn't re-parse as clausal in the return leg. Single-leg translation works correctly in both directions.
- **Whitespace/formatting**: Exact text match is not guaranteed; structural equivalence is.

---

## Golden test files

Golden snapshot files live in `tests/fixtures/prolog_golden/`:

| Direction | Files | Purpose |
|---|---|---|
| Clausal → Prolog | `*.pl` (11 files) | Checked-in expected Prolog output |
| Prolog → Clausal | `*.clausal` (11 files) | Checked-in expected clausal output |

To regenerate golden files after changing translation logic:

```bash
# Clausal → Prolog
python -m clausal.tools.clausal_to_prolog SOURCE.clausal -o tests/fixtures/prolog_golden/NAME.pl

# Prolog → Clausal
python -m clausal.tools.prolog_to_clausal SOURCE.pl -o tests/fixtures/prolog_golden/NAME.clausal
```

---

## Tier 3: Scryer Prolog embedding

The translation pipeline feeds directly into the [Scryer Prolog embedding](scryer.md) — an in-process Scryer engine accessible from Python via PyO3. `.clausal` files are translated to Prolog with `Dialect.scryer()` and loaded into the embedded machine:

```python
from clausal.scryer import Scryer

with Scryer() as s:
    s.consult_file("clausal/examples/fibonacci.clausal")
    s.query_one("fib(10, R).")
    # {'R': 55}
```

See the [Scryer Prolog Embedding](scryer.md) documentation for the full API.

---

## Roadmap

- **Phase 1.1** (done): Prolog AST nodes, operator table, dialect config
- **Phase 1.2** (done): Clausal → Prolog text emission
- **Phase 2** (done): Dialect-specific emission, golden tests, CLI
- **Phase 3** (done): Prolog → Clausal (tokenizer, Pratt parser, Prolog AST → `.clausal` text)
- **Phase 4** (done): Roundtrip validation, golden Prolog→Clausal files, unified CLI
- **Phase 5** (done): Import-time `.pl` translation — `PrologFinder`/`PrologLoader` in the import hook translate `.pl` files on the fly, with `.pyc` caching and recursive `use_module` support (see [import.md](import.md#importing-pl-prolog-files-directly))
- **Phase 6** (stretch, not started): Self-hosted DCG translator — rewrite the Prolog parser as a clausal DCG operating on a token stream, using the state-threading DCG pattern for dynamic `op/3` handling
- **Phase 7** (stretch, not started): Additional dialects — GNU Prolog (`fd_*` constraints), ECLiPSe (`lib(ic)`, `do/2`), XSB Prolog (HiLog, tabling differences), Tau Prolog (JavaScript-hosted); each as a `Dialect` subclass
