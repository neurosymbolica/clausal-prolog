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

## Roadmap

- **Phase 1.1** (done): Prolog AST nodes, operator table, dialect config
- **Phase 1.2** (done): Clausal → Prolog text emission
- **Phase 1b**: AST ↔ runtime bridge (Database/PredicateMeta ↔ Prolog AST)
- **Phase 2**: Dialect-specific emission (SWI/Scryer library maps, untranslatable handling)
- **Phase 3**: Prolog → Clausal (tokenizer, Pratt parser, Prolog AST → `.clausal` text)
- **Phase 4**: Roundtrip validation (golden files, property tests)
