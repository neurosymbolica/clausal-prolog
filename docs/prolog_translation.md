# Prolog Translation

Clausal includes a bidirectional translator between `.clausal` and `.pl` (Prolog) source files. This enables exporting clausal programs for use in SWI-Prolog or Scryer Prolog, and (in future phases) importing existing Prolog code into clausal.

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

Pass a `Dialect` to control SWI-specific or Scryer-specific output:

```python
from clausal.tools.prolog_dialect import Dialect

# SWI-Prolog output (e.g. all_different, library(clpfd))
print(clausal_source_to_prolog(source, dialect=Dialect.swi()))

# Scryer Prolog output (e.g. all_distinct, library(clpz))
print(clausal_source_to_prolog(source, dialect=Dialect.scryer()))
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
| `AllDifferent` | `all_different` | PascalCase → snake_case |
| `DCGRule` | `dcg_rule` | Acronym runs split correctly |
| `FindAll` | `findall` | Builtin name map overrides |
| `TimeGoal` | `time` | Builtin name map (SWI/Scryer) |

### Variable names

| Clausal | Prolog | Rule |
|---|---|---|
| `X_` | `X` | Strip trailing underscore |
| `head_` | `Head` | Strip underscore, capitalize |
| `RESULT` | `Result` | ALLCAPS → titlecase |
| `X` | `X` | Single uppercase stays |
| `_` | `_` | Anonymous stays |

### Operators

| Clausal | Prolog | Notes |
|---|---|---|
| `X is Y` | `X = Y` | Unification |
| `X is not Y` | `dif(X, Y)` | Disequality |
| `Y := X * 2` | `Y is X * 2` | Arithmetic evaluation |
| `X == Y` | `X == Y` | Structural equality |
| `X != Y` | `X \== Y` | Structural inequality |
| `X <= Y` | `X =< Y` | ISO `=<` |
| `not G` | `\+ G` | Negation as failure |
| `A and B` or `A, B` | `A, B` | Conjunction |
| `A or B` | `(A ; B)` | Disjunction |

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

### Reverse translation rules

| Prolog | Clausal | Rule |
|---|---|---|
| `foo_bar(X)` | `FooBar(X)` | snake_case → PascalCase |
| `findall(...)` | `FindAll(...)` | Reverse builtin name map |
| `X = Y` | `X is Y` | Unification |
| `X \= Y` | `X is not Y` | Disequality |
| `Y is X * 2` | `Y := X * 2` | Arithmetic evaluation |
| `X == Y` | `X == Y` | Structural equality |
| `X \== Y` | `X != Y` | Structural inequality |
| `X =< Y` | `X <= Y` | ISO `=<` → `<=` |
| `\+ G` | `not G` | Negation as failure |
| `(A , B)` | `(A, B)` | Conjunction |
| `(A ; B)` | `(A or B)` | Disjunction |
| `(C -> T ; E)` | `(C -> T or E)` | If-then-else |
| `[H\|T]` | `[H, *T]` | List cons |
| `member(X, L)` | `X in L` | Membership |
| `head :- body.` | `Head() <- (body)` | Rules |
| `head.` | `Head(),` | Facts (trailing comma) |
| `head --> body.` | `Head() >> (body)` | DCG rules |
| `:- module(...)` | `-module(...)` | Module directive |
| `:- use_module(library(L), [...])` | `-import_from(L, [...])` | Import directive |
| `:- dynamic(p/N)` | `-dynamic(P/N)` | Dynamic directive |
| `:- op(P, T, N)` | `# operator: op(P, T, N)` | Comment (no clausal equivalent) |
| `X` (variable) | `X` (single letter) or `x_` (multi-letter) | Variable naming |

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

### Clausal → Prolog

```bash
python -m clausal.tools.clausal_to_prolog input.clausal -o output.pl --dialect swi
```

### Prolog → Clausal

```bash
python -m clausal.tools.prolog_to_clausal input.pl -o output.clausal --dialect swi
```

Both tools support pipe mode (stdin/stdout) when file arguments are omitted.

---

## Roadmap

- **Phase 1.1** (done): Prolog AST nodes, operator table, dialect config
- **Phase 1.2** (done): Clausal → Prolog text emission
- **Phase 2** (done): Dialect-specific emission, golden tests, CLI
- **Phase 3** (done): Prolog → Clausal (tokenizer, Pratt parser, Prolog AST → `.clausal` text)
- **Phase 4**: Roundtrip validation & unified CLI
