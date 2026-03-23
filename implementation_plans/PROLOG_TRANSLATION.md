# Bidirectional Clausal ↔ Prolog Translation

## Context

Clausal uses Python's parser and therefore has a different surface syntax from ISO Prolog. A bidirectional translator enables:

- **Clausal → Prolog:** export clausal programs for use in Scryer/SWI-Prolog
- **Prolog → Clausal:** import existing Prolog libraries and textbook examples
- **Dialect awareness:** SWI-Prolog and Scryer Prolog differ in library paths, operator defaults, dict syntax, CLP library names, and tabling directives
- **Programmatic bridge:** the Prolog AST is a first-class public API, enabling direct AST-to-AST and runtime-to-runtime interop without text round-trips

---

## Three-Tier Bridge Architecture

The translator is designed around a shared **Prolog AST** that serves as the interchange hub. This enables three tiers of integration, from simple text translation to live runtime bridges:

```
Tier 1: Text ↔ Text         Translate .clausal ↔ .pl source files
Tier 2: AST ↔ AST           Programmatic: build/consume Prolog AST without parsing
Tier 3: Runtime ↔ Runtime   Direct term/clause exchange with a running Prolog engine
```

### Tier 1 — Text ↔ Text

The basic use case: translate source files between clausal and Prolog syntax.

```
.clausal source ──→ pythonic_ast ──→ Prolog AST ──→ .pl source
.pl source ──→ tokens ──→ Pratt parser ──→ Prolog AST ──→ .clausal source
```

### Tier 2 — AST ↔ AST (programmatic, no parsing/emitting)

The Prolog AST is a public API. Code can construct, inspect, transform, and convert
Prolog AST nodes without ever touching source text.

```
clausal Database/PredicateMeta ──→ Prolog AST ──→ (emit to text, or hand to Tier 3)
Prolog AST ──→ clausal Database/PredicateMeta     (load without .clausal file)
Prolog AST ──→ transform/optimize ──→ Prolog AST  (rewrite passes)
```

Entry points:
- `db_to_prolog_ast(db, dialect)` — walk a Database's clause store → `PModule`
- `pred_to_prolog_ast(pred_cls, dialect)` — single PredicateMeta class → `[PClause]`
- `prolog_ast_to_db(module, db)` — load a `PModule` into a clausal Database
- `clausal_term_to_pterm(term)` / `pterm_to_clausal_term(pterm)` — convert individual terms

### Tier 3 — Runtime ↔ Runtime (live Prolog engine bridge)

Exchange terms and clauses with a running Prolog process. The Prolog AST is the
serialization boundary — each side converts between its native representation and
the shared AST.

```
clausal runtime                                   Prolog engine
    │                                                  │
    ▼                                                  ▼
clausal terms ──→ Prolog AST ──→ serialized ──→ Prolog terms
clausal terms ◄── Prolog AST ◄── serialized ◄── Prolog terms
```

Serialization options (Tier 3 detail, Phase 3b):
- **Text:** emit/parse Prolog source (simplest, works with any Prolog)
- **Prolog term_to_atom:** exchange via `term_to_atom/2` (SWI/Scryer)
- **SWI-Prolog C FFI:** via `pyswip` or `janus` — pass terms directly
- **Scryer Rust FFI:** via `scryer-prolog` Python bindings (when available)
- **JSON interchange:** SWI's `library(http/json)` ↔ Python `json` for ground terms

### Full Architecture Diagram

```
                         ┌──────────────────────┐
                         │   Operator Table     │
                         │  (ISO + dialect)     │
                         └──────┬───────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
         ▼                      ▼                      ▼
  .clausal source         Prolog source          Dialect config
         │                      │                      │
         ▼                      ▼                      │
  pythonic_ast             Tokenizer                   │
  (existing pipeline)           │                      │
         │                      ▼                      │
         │                Token stream                 │
         │                      │                      │
         │                      ▼                      │
         ├─────────────►  Pratt parser ◄───────────────┘
         │                      │
         │               ┌──────┴──────┐
         ▼               ▼             │
    ┌─────────────────────────┐        │
    │      Prolog AST         │◄───────┘
    │   (public API / hub)    │
    └──┬──────┬──────┬────────┘
       │      │      │
       ▼      │      ▼
  .pl source  │  .clausal source          ← Tier 1: text ↔ text
              │
       ┌──────┴──────┐
       ▼             ▼
  clausal DB    clausal terms             ← Tier 2: AST ↔ AST
  (Database,    (Compound, Var,
  PredicateMeta) PredicateMeta instances)
       │
       ▼
  Prolog engine                           ← Tier 3: runtime ↔ runtime
  (pyswip / janus / text pipe)
```

All tiers share:
- The **Operator Table** (knows what operators exist, their precedence and associativity)
- The **Prolog AST** (intermediate representation — the central hub)
- The **Dialect** configuration (operator defaults, library mappings, syntax variants)

---

## Prolog AST (Intermediate Representation) — Public API

The Prolog AST is a **first-class public API**, not just an internal detail of the text
translator. It is the central hub through which all three tiers communicate. Code can
construct, inspect, transform, and convert Prolog AST nodes programmatically.

All nodes are plain frozen dataclasses in `clausal/tools/prolog_ast.py`. The module
also provides visitor/transformer base classes and builder helpers.

### Node definitions

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Union

# ── Terms ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class PAtom:
    """Atom: foo, 'hello world', +, =.."""
    name: str
    quoted: bool = False          # True if needs quoting in output

@dataclass(frozen=True, slots=True)
class PVar:
    """Variable: X, _Y, _"""
    name: str                     # "_" for anonymous

@dataclass(frozen=True, slots=True)
class PNumber:
    """Integer or float literal."""
    value: int | float

@dataclass(frozen=True, slots=True)
class PString:
    """Double-quoted string (SWI: string; Scryer: char list)."""
    value: str

@dataclass(frozen=True, slots=True)
class PCompound:
    """f(a, b, c) — also used for operators: +(1, 2)"""
    functor: str
    args: tuple[PTerm, ...]

@dataclass(frozen=True, slots=True)
class PList:
    """[H|T] or [a, b, c]"""
    elements: tuple[PTerm, ...]
    tail: PTerm | None = None     # None means proper list

@dataclass(frozen=True, slots=True)
class PCurly:
    """{Goal} — DCG inline goals, set notation."""
    body: PTerm

PTerm = Union[PAtom, PVar, PNumber, PString, PCompound, PList, PCurly]

# ── Clauses & directives ──────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class PClause:
    """head :- body.  (body=None for facts)"""
    head: PTerm
    body: PTerm | None = None

@dataclass(frozen=True, slots=True)
class PDCGRule:
    """head --> body."""
    head: PTerm
    body: PTerm

@dataclass(frozen=True, slots=True)
class PDirective:
    """:- directive."""
    body: PTerm

@dataclass(frozen=True, slots=True)
class PQuery:
    """?- query."""
    body: PTerm

PItem = Union[PClause, PDCGRule, PDirective, PQuery]

@dataclass(frozen=True, slots=True)
class PModule:
    """A complete Prolog source file."""
    items: tuple[PItem, ...]
    source_path: str | None = None
```

### Visitor and Transformer

Following the pattern of Python's `ast.NodeVisitor` / `ast.NodeTransformer`:

```python
class PrologVisitor:
    """Walk a Prolog AST without modifying it.

    Subclass and override visit_PAtom, visit_PCompound, etc.
    Default visit methods recurse into children.
    """
    def visit(self, node: PTerm | PItem | PModule) -> None:
        method = f"visit_{type(node).__name__}"
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node) -> None:
        """Recurse into child nodes."""
        for child in _children(node):
            self.visit(child)


class PrologTransformer:
    """Walk and rebuild a Prolog AST, replacing nodes.

    Return the node unchanged to keep it, or return a new node to replace it.
    Return None from visit_PItem to delete an item.
    """
    def visit(self, node: PTerm | PItem | PModule):
        method = f"visit_{type(node).__name__}"
        transformer = getattr(self, method, self.generic_visit)
        return transformer(node)

    def generic_visit(self, node):
        """Rebuild node with transformed children."""
        # Recursively transform children, reconstruct with dataclasses.replace
        ...
```

### Builder helpers

Convenience functions for constructing AST nodes without verbose dataclass calls:

```python
# Atoms & variables
def atom(name: str) -> PAtom: ...
def var(name: str) -> PVar: ...
def anon() -> PVar: return PVar("_")

# Compound terms (the workhorse)
def compound(functor: str, *args: PTerm) -> PCompound: ...
def op(name: str, left: PTerm, right: PTerm) -> PCompound:
    """Binary operator as compound: op('+', a, b) → +(a, b)"""
    ...
def prefix(name: str, arg: PTerm) -> PCompound:
    """Prefix operator: prefix('\\+', g) → \\+(g)"""
    ...

# Lists
def plist(*elements: PTerm, tail: PTerm | None = None) -> PList: ...
def cons(head: PTerm, tail: PTerm) -> PList:
    """[H|T] shorthand."""
    return PList((head,), tail=tail)

# Clauses
def fact(head: PTerm) -> PClause: return PClause(head)
def rule(head: PTerm, body: PTerm) -> PClause: return PClause(head, body)
def dcg_rule(head: PTerm, body: PTerm) -> PDCGRule: ...
def directive(body: PTerm) -> PDirective: ...

# Module
def module(*items: PItem, source_path: str | None = None) -> PModule: ...
```

### Introspection utilities

```python
def variables(term: PTerm) -> set[str]:
    """Collect all variable names in a term (excluding '_')."""

def functors(term: PTerm) -> set[tuple[str, int]]:
    """Collect all functor/arity pairs in a term."""

def is_ground(term: PTerm) -> bool:
    """True if the term contains no variables."""

def term_size(term: PTerm) -> int:
    """Number of nodes in the term tree."""

def subterms(term: PTerm) -> Iterator[PTerm]:
    """Yield all subterms in depth-first order."""
```

---

## Tier 2: AST ↔ Clausal Runtime Conversions

`clausal/tools/prolog_bridge.py`

These functions convert between clausal's native runtime representations and the
Prolog AST, enabling programmatic interop without text round-trips.

### Clausal runtime → Prolog AST

```python
def clausal_term_to_pterm(term, dialect: Dialect | None = None) -> PTerm:
    """Convert a clausal runtime term to a Prolog AST node.

    Handles:
    - Var          → PVar (name from var._name or generated)
    - int/float    → PNumber
    - str          → PAtom (or PString depending on dialect)
    - bool         → PAtom('true') / PAtom('false')
    - None         → PAtom('none')  [with warning — no Prolog equivalent]
    - list         → PList (recursively convert elements; detect [H, *T] tails)
    - tuple        → PCompound(',', ...) [Prolog tuple convention]
    - Compound     → PCompound(functor, converted args)
    - PredicateMeta instance → PCompound(snake_name, converted fields)
    - KWTerm       → PCompound with keyword-ordered args [with metadata]
    - DictTerm     → SWI dict or assoc list (dialect-dependent)
    - SetTerm      → ordset list (dialect-dependent)
    """

def pred_to_prolog_ast(
    pred_cls: type,  # PredicateMeta class
    dialect: Dialect | None = None,
) -> list[PClause]:
    """Convert all clauses of a PredicateMeta class to Prolog AST clauses.

    Reads pred_cls._clauses, converts each Clause(head, body) to PClause.
    Handles:
    - Clause heads with pattern matching → PClause head
    - Clause bodies (goal chains) → PClause body with conjunction
    - DCG rules (detected by hidden state args) → PDCGRule
    """

def db_to_prolog_ast(
    db: Database,
    dialect: Dialect | None = None,
    include_directives: bool = True,
) -> PModule:
    """Convert an entire Database to a Prolog AST module.

    Walks db._clauses for all predicates, emitting:
    - Module directive (if db has module metadata)
    - Import directives (from db._imports or module_dict inspection)
    - Dynamic/discontiguous/table directives (from predicate metadata)
    - Clauses in definition order
    - DCG rules (detected and re-sugared)
    """

def module_dict_to_prolog_ast(
    module_dict: dict,
    dialect: Dialect | None = None,
) -> PModule:
    """Convert a loaded .clausal module's globals dict to Prolog AST.

    This is the most convenient entry point — given a module loaded via
    import hook, extract all PredicateMeta classes and their clauses.
    Preserves clause order and predicate grouping.
    """
```

### Prolog AST → Clausal runtime

```python
def pterm_to_clausal_term(pterm: PTerm, var_map: dict[str, Var] | None = None):
    """Convert a Prolog AST node to a clausal runtime term.

    var_map tracks variable identity: same PVar name → same Var instance.
    Pass a shared var_map across related terms to preserve variable sharing.

    Handles:
    - PAtom        → str (Python atom) or known functor class
    - PVar         → Var (fresh or from var_map)
    - PNumber      → int/float
    - PString      → str
    - PCompound    → Compound(functor, args) or PredicateMeta instance if known
    - PList        → Python list (proper) or cons structure (partial)
    - PCurly       → Compound('{}', [body])
    """

def prolog_ast_to_db(
    module: PModule,
    db: Database | None = None,
) -> Database:
    """Load a Prolog AST module into a clausal Database.

    Creates/updates predicate entries from PClause/PDCGRule items.
    Processes PDirective items for metadata (dynamic, table, etc.).
    Returns the populated Database.

    This enables: parse a .pl file → Prolog AST → load into clausal runtime
    without ever generating .clausal source.
    """

def prolog_ast_to_module_dict(
    module: PModule,
    module_name: str = "__prolog_import__",
) -> dict:
    """Load a Prolog AST module into a Python module-like dict.

    Creates PredicateMeta classes, compiles dispatch functions,
    and populates a dict suitable for use as module globals.

    This is the programmatic equivalent of importing a .clausal file:
    the caller gets back a dict with predicate classes ready for query.
    """
```

### Term conversion details

The conversion handles the full operator mapping at the term level:

Prolog AST | Clausal runtime | Notes
---|---|---
`PCompound('=', (X, Y))` | `Unify(X, Y)` | Becomes `is` in clausal syntax
`PCompound('is', (R, E))` | `AugAssign(R, E)` | Becomes `:=` in clausal syntax
`PCompound('\\+', (G,))` | `Not(G)` | Becomes `not` in clausal syntax
`PCompound(',', (A, B))` | `And(A, B)` | Becomes `,` in clausal syntax
`PCompound(';', (A, B))` | `Or(A, B)` | Becomes `or` in clausal syntax
`PCompound('dif', (X, Y))` | `IsNot(X, Y)` | Becomes `is not` in clausal syntax
`PCompound('-->', (H, B))` | DCG rule | Becomes `>>` in clausal syntax
`PCompound('.', (H, T))` | Cons cell | Becomes `[H, *T]` in clausal syntax
`PCompound(f, args)` | `Compound(f, args)` or `PredCls(*args)` | PascalCase functor class if known

---

## Tier 3: Runtime Bridge (Live Prolog Engine)

`clausal/tools/prolog_runtime.py` (Phase 3b)

Exchange terms and queries with a running Prolog engine. The Prolog AST is the
serialization boundary.

### Abstract bridge interface

```python
class PrologBridge(ABC):
    """Abstract interface for communicating with a running Prolog engine."""

    def __init__(self, dialect: Dialect): ...

    @abstractmethod
    def assert_clause(self, clause: PClause) -> None:
        """Assert a clause into the running Prolog engine."""

    @abstractmethod
    def retract_clause(self, clause: PClause) -> bool:
        """Retract a matching clause. Returns True if found."""

    @abstractmethod
    def query(self, goal: PTerm) -> Iterator[dict[str, PTerm]]:
        """Execute a query, yielding variable bindings as dicts.

        Each yielded dict maps variable names to their bound Prolog AST terms.
        Use pterm_to_clausal_term() to convert bindings to clausal runtime terms.
        """

    @abstractmethod
    def consult_module(self, module: PModule) -> None:
        """Load an entire module into the Prolog engine."""

    @abstractmethod
    def call(self, goal: PTerm) -> bool:
        """Call a goal, returning True if it succeeds (ignoring bindings)."""

    def query_clausal(self, goal: PTerm) -> Iterator[dict[str, object]]:
        """Like query(), but converts bindings to clausal runtime terms."""
        var_map = {}
        for bindings in self.query(goal):
            yield {k: pterm_to_clausal_term(v, var_map) for k, v in bindings.items()}
```

### SWI-Prolog bridge (via janus / pyswip)

```python
class SWIPrologBridge(PrologBridge):
    """Bridge to SWI-Prolog via janus-swi (preferred) or pyswip.

    janus-swi (SWI 9.1+) provides direct in-process term exchange.
    pyswip uses the SWI C foreign interface via ctypes.
    """

    def __init__(self, use_janus: bool = True):
        super().__init__(Dialect.swi())
        if use_janus:
            import janus_swi as janus
            self._engine = janus
        else:
            from pyswip import Prolog
            self._engine = Prolog()

    def query(self, goal: PTerm) -> Iterator[dict[str, PTerm]]:
        # Serialize goal to text, send to engine, parse bindings back
        goal_text = emit_term(goal, self._dialect.operator_table)
        for solution in self._engine.query(goal_text):
            yield {k: self._parse_binding(v) for k, v in solution.items()}
```

### Scryer Prolog bridge (via subprocess / text pipe)

```python
class ScryerPrologBridge(PrologBridge):
    """Bridge to Scryer Prolog via subprocess.

    Scryer doesn't have a Python FFI yet, so we communicate via
    stdin/stdout text interchange. The Prolog AST is serialized to
    Prolog source, sent as queries, and results are parsed back.
    """

    def __init__(self, scryer_path: str = "scryer-prolog"):
        super().__init__(Dialect.scryer())
        self._process = subprocess.Popen(
            [scryer_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
```

### Bridge usage examples

```python
# Example 1: Query SWI-Prolog from clausal
bridge = SWIPrologBridge()
bridge.consult_module(db_to_prolog_ast(my_db, Dialect.swi()))
for bindings in bridge.query_clausal(compound("member", var("X"), plist(atom("a"), atom("b")))):
    print(bindings["X"])  # clausal Var/str/int values

# Example 2: Load a Prolog library into clausal
from clausal.tools.prolog_parser import parse_file
from clausal.tools.prolog_bridge import prolog_ast_to_db

ast = parse_file("library.pl", dialect=Dialect.swi())
db = prolog_ast_to_db(ast)
# Now query db using clausal's solve/query API

# Example 3: Translate individual terms programmatically
from clausal.tools.prolog_bridge import clausal_term_to_pterm, pterm_to_clausal_term
from clausal.logic.variables import Var

x = Var("X")
pterm = clausal_term_to_pterm(Compound("member", (x, [1, 2, 3])))
# pterm = PCompound('member', (PVar('X'), PList((PNumber(1), PNumber(2), PNumber(3)))))
```

---

## Operator Table

`clausal/tools/prolog_operators.py`

### Data model

```python
@dataclass(frozen=True, slots=True)
class OpEntry:
    precedence: int       # 1–1200
    specifier: str        # xf, yf, xfx, xfy, yfx, fy, fx
    name: str             # operator name (atom)

class OperatorTable:
    """Mutable operator table with ISO defaults + dialect extensions."""

    def __init__(self):
        self._ops: dict[str, list[OpEntry]] = {}  # name → entries (can have prefix + infix)

    def define(self, prec: int, spec: str, name: str) -> None: ...
    def lookup_infix(self, name: str) -> OpEntry | None: ...
    def lookup_prefix(self, name: str) -> OpEntry | None: ...
    def lookup_postfix(self, name: str) -> OpEntry | None: ...
    def is_operator(self, name: str) -> bool: ...
    def user_defined(self) -> list[OpEntry]: ...   # entries not in default set

    @classmethod
    def iso_default(cls) -> "OperatorTable": ...
    @classmethod
    def swi_default(cls) -> "OperatorTable": ...
    @classmethod
    def scryer_default(cls) -> "OperatorTable": ...
```

### ISO standard operators (Table 7, ISO 13211-1)

Precedence | Specifier | Operators
---|---|---
1200 | xfx | `:-`, `-->`
1200 | fx | `:-`, `?-`
1100 | xfy | `;`
1050 | xfy | `->`
1000 | xfy | `,`
900 | fy | `\+`
700 | xfx | `=`, `\=`, `==`, `\==`, `is`, `=:=`, `=\=`, `<`, `>`, `>=`, `=<`, `=..`
600 | xfy | `:`
500 | yfx | `+`, `-`, `/\`, `\/`
400 | yfx | `*`, `/`, `//`, `rem`, `mod`, `<<`, `>>`
200 | xfx | `**`
200 | fy | `-`, `\`

### SWI additions (non-ISO defaults)

- `200 fy` : `+` (prefix plus)
- `700 xfx` : `>:<`, `:<` (dict operators)
- `500 yfx` : `xor`
- `400 yfx` : `rdiv`
- `100 yfx` : `.` (dict access, only in certain contexts)
- Various module-system operators

### Scryer additions

- CLP(Z) operators via `library(clpz)`: `#=`, `#\=`, `#<`, `#>`, `#=<`, `#>=` (all `700 xfx`)
- `library(reif)`: `if_/3` (not an operator, but relevant for translation)

---

## Dialect Configuration

`clausal/tools/prolog_dialect.py`

```python
class Dialect:
    """Dialect-specific configuration for Prolog emission/parsing."""
    name: str                              # "iso", "swi", "scryer"
    operator_table: OperatorTable
    library_map: dict[str, str]            # clausal module → Prolog library path
    clpfd_module: str                      # "clpfd" (SWI) or "clpz" (Scryer)
    tabling_directive: str                 # ":- table" (SWI) or ":- use_module(library(tabling))"
    string_type: str                       # "string" (SWI) or "chars" (Scryer)
    has_dicts: bool                        # True for SWI
    module_system: str                     # "swi" or "iso"  (affects use_module syntax)
```

### Library mapping (clausal module → Prolog)

Clausal module | SWI-Prolog | Scryer Prolog
---|---|---
`clausal.logic.clpfd` | `:- use_module(library(clpfd)).` | `:- use_module(library(clpz)).`
`clausal.logic.clpb` | `:- use_module(library(clpb)).` | `:- use_module(library(clpb)).`
`clausal.logic.tabling` | `:- use_module(library(tabling)).` | `:- use_module(library(tabling)).`
`clausal.modules.regex` | **untranslatable** (Python-only) | **untranslatable**
`clausal.modules.py.*` | **untranslatable** (SciPy etc.) | **untranslatable**

---

## Phase 1: Clausal → ISO Prolog Emitter

**Files:**
- `clausal/tools/prolog_ast.py` — Prolog AST nodes (above)
- `clausal/tools/prolog_operators.py` — OperatorTable
- `clausal/tools/prolog_dialect.py` — Dialect configs
- `clausal/tools/clausal_to_prolog.py` — AST translator + emitter
- `tests/test_prolog_emit.py` — unit + roundtrip tests

### Step 1.1: Prolog AST + Operator Table

Implement `prolog_ast.py` and `prolog_operators.py` as described above. These are shared infrastructure for all phases.

Tests: operator table construction, lookup, ISO/SWI/Scryer defaults.

### Step 1.2: Clausal pythonic_ast → Prolog AST translator

`clausal/tools/clausal_to_prolog.py`

A visitor over pythonic_ast nodes that produces PItem nodes. The core mapping:

```python
class ClausalToProlog(ast.NodeVisitor):
    """Translates clausal pythonic_ast → Prolog AST."""

    def __init__(self, dialect: Dialect): ...

    # ── Clause-level ──────────────────────────────────────────────
    # Expr(Compare(left, [Is], [right]))      →  PClause (fact if no body)
    # Expr(Compare(head, [LtE], [body]))      →  PClause(head, body)  (<= is <-)
    # Expr(Compare(head, [RShift], [body]))    →  PDCGRule(head, body)
    # Expr(UnaryOp(USub, Call(name, args)))    →  PDirective(...)

    # ── Term-level ────────────────────────────────────────────────
    # Call(Name('Foo'), args)                  →  PCompound('foo', args)
    # Name('X_') in var context               →  PVar('X')
    # Name('X') if ALLCAPS                    →  PVar('X')
    # Name('foo') lowercase                   →  PAtom('foo')
    # Constant(42)                            →  PNumber(42)
    # List([a, b, Starred(t)])                →  PList([a, b], tail=t)
    # List([a, b, c])                         →  PList([a, b, c])

    # ── Operators ─────────────────────────────────────────────────
    # Compare(X, [Is], [Y])                   →  PCompound('=', (X, Y))
    # Compare(X, [IsNot], [Y])               →  PCompound('dif', (X, Y))  [or \=]
    # BinOp(X, MatMult, Y)  (:=)             →  PCompound('is', (X, Y))
    # BoolOp(And, [a, b])                     →  PCompound(',', (a, b))
    # BoolOp(Or, [a, b])                      →  PCompound(';', (a, b))
    # UnaryOp(Not, x)                         →  PCompound('\\+', (x,))
    # BinOp(X, Mod, Y)  (%)                  →  PCompound('mod', (X, Y))
    # BinOp(X, Pow, Y)  (**)                  →  PCompound('**', (X, Y))  [or ^]

    # ── Directives ────────────────────────────────────────────────
    # -module(name, exports)                  →  PDirective(:- module(name, exports))
    # -import_from(mod, preds)                →  PDirective(:- use_module(mod, preds))
    # -dynamic(pred/arity)                    →  PDirective(:- dynamic pred/arity)
    # -table(pred/arity)                      →  PDirective(:- table pred/arity)
    # -discontiguous(pred/arity)              →  PDirective(:- discontiguous pred/arity)

    # ── Untranslatable ────────────────────────────────────────────
    # ++expr                                  →  emit warning comment
    # f"..."                                  →  emit warning comment (or format/2 for SWI)
    # DictTerm                                →  SWI dict syntax or warning
    # SetTerm                                 →  warning
    # Lambda (X <- Body)                      →  warning
```

### Step 1.3: Prolog AST → source emitter (pretty-printer)

```python
def emit_term(term: PTerm, op_table: OperatorTable, max_prec: int = 1200) -> str:
    """Emit a Prolog term as a string, respecting operator precedence for minimal parenthesization."""
```

Key rules:
- **Operator precedence parenthesization:** Only parenthesize when a sub-term's operator has higher precedence (lower binding) than the context. Use specifier (xfx vs yfx vs xfy) to determine left/right associativity tie-breaking.
- **Atom quoting:** Quote atoms that start with uppercase, contain spaces/special chars, or clash with operators. Use `'...'` with `\` escaping inside.
- **Variable naming:** Strip trailing `_`, preserve `_` anonymous.
- **List sugar:** Emit `[a, b, c]` for proper lists, `[a, b | T]` for partial.
- **Clause termination:** Every clause/directive ends with `.` followed by newline.
- **Comments:** `#` → `%`.
- **Indentation:** Body goals indented 4 spaces after `:-`.

### Step 1.4: Naming conventions

Clausal predicates use PascalCase; Prolog uses snake_case. The translator needs a reversible name mapping.

```python
def pascal_to_snake(name: str) -> str:
    """FooBar → foo_bar, CLP → clp, AllDifferent → all_different"""

def snake_to_pascal(name: str) -> str:
    """foo_bar → FooBar, all_different → AllDifferent"""
```

Maintain a **known-names table** for builtins where the standard Prolog name differs from the mechanical conversion:

Clausal | Prolog | Notes
---|---|---
`AssertZ` | `assertz` | direct
`FindAll` | `findall` | direct
`AllDifferent` | `all_different` / `all_distinct` | SWI vs Scryer
`InDomain` | `ins` (SWI) / `in` (Scryer) | CLP(FD) domain
`Label` | `label` / `labeling` | dialect
`MapList` | `maplist` | direct
`Writeln` | `writeln` | direct
`CopyTerm` | `copy_term` | direct

Variable naming:

Clausal | Prolog
---|---
`X_` | `X`
`HEAD_` | `Head`
`RESULT` | `Result` (ALLCAPS → Titlecase)
`_` | `_`
`_ignored_` | `_Ignored`

### Step 1.5: CLI + integration

```bash
# Basic usage
python -m clausal.tools.clausal_to_prolog input.clausal -o output.pl

# Dialect selection
python -m clausal.tools.clausal_to_prolog input.clausal --dialect swi -o output.pl
python -m clausal.tools.clausal_to_prolog input.clausal --dialect scryer -o output.pl

# Pipe mode
cat input.clausal | python -m clausal.tools.clausal_to_prolog --dialect swi
```

### Step 1.6: Validation

- Translate every file in `tests/conformity/` → `.pl` and verify manually in SWI/Scryer
- Translate `tests/fixtures/*.clausal` → `.pl` and check for syntactic validity
- Unit tests for each operator/construct mapping
- Snapshot tests: golden `.pl` files checked into `tests/fixtures/prolog_golden/`

---

## Phase 2: Dialect Layer (Scryer vs SWI)

**Files:**
- Extend `clausal/tools/prolog_dialect.py`
- `clausal/tools/clausal_to_prolog.py` — dialect-specific hooks

### Step 2.1: SWI-Prolog dialect

- `use_module(library(...))` instead of bare module names
- Dict syntax: `DictTerm({"x": 1})` → `_{x: 1}` (SWI dicts)
- String handling: double-quoted strings are `string` type, not char lists
- `format/2` approximation for f-strings: `f"Hello {NAME}"` → `format("Hello ~w", [Name])`
- CLP(FD): `library(clpfd)`, operators `#=`, `#\=`, `#<`, `#>`, `in`, `ins`
- Tabling: `:- table pred/arity.`

### Step 2.2: Scryer Prolog dialect

- Stricter ISO compliance — no dicts, no `format/2` without `library(format)`
- CLP(Z): `library(clpz)` — same operators as CLP(FD) but name differs
- Tabling: `library(tabling)`
- Strings are char lists by default
- `dif/2` requires `library(dif)`

### Step 2.3: Untranslatable construct handling

Strategy per construct:

Construct | SWI fallback | Scryer fallback
---|---|---
`++expr` (Python interop) | Comment + error term | Comment + error term
`f"string"` | `format/2` | Comment + `atom_concat` chain
`DictTerm` | SWI dict syntax | Assoc list (via `library(assoc)`)
`SetTerm` | `library(ordsets)` | `library(ordsets)`
Lambda `(X <- Body)` | `\X^Body` (SWI lambda) | Meta-call structure
`-import_from(py_mod)` | Warning comment | Warning comment

When a construct is untranslatable, emit:

```prolog
/* WARNING: untranslatable clausal construct: ++len(List)
   Original: R_ := ++len(List_)
   Replace with Prolog equivalent manually. */
```

---

## Phase 3: Prolog → Clausal (Pratt Parser)

**Files:**
- `clausal/tools/prolog_tokenizer.py` — lexer
- `clausal/tools/prolog_parser.py` — Pratt parser → Prolog AST
- `clausal/tools/prolog_to_clausal.py` — Prolog AST → clausal source
- `tests/test_prolog_parse.py`
- `tests/test_prolog_to_clausal.py`

### Step 3.1: Tokenizer

Prolog tokenization is fussy. The tokenizer must handle:

```python
class TokenType(Enum):
    ATOM        = "atom"          # foo, 'hello world', +, =..
    VAR         = "var"           # X, _Y, _
    INTEGER     = "integer"       # 42, 0x1F, 0b1010, 0o77, 0'a
    FLOAT       = "float"        # 3.14, 1.0e-5
    STRING      = "string"       # "hello" (double-quoted)
    LPAREN      = "("
    RPAREN      = ")"
    LBRACKET    = "["
    RBRACKET    = "]"
    LCURLY      = "{"
    RCURLY      = "}"
    BAR         = "|"            # list tail separator
    COMMA       = ","
    DOT         = "."            # clause terminator (when followed by whitespace/EOF)
    END         = "end"          # end of input

@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    value: str | int | float
    line: int
    col: int
```

Tricky cases:
- **`.` (dot):** Clause terminator only when followed by whitespace or EOF. Inside `3.14` it's a decimal point. Inside `foo.bar` (SWI module qualification) it's an operator.
- **`-` (minus):** Could be prefix operator, infix operator, or start of negative number.
- **Quoted atoms:** `'hello''s world'` — doubled single quotes for escaping.
- **Character codes:** `0'a` → integer 97.
- **`/* */` comments:** Nestable in some dialects (SWI: yes, ISO: no).
- **`%` comments:** To end of line.
- **Graphic tokens:** Sequences of `# $ & * + - . / : < = > ? @ \ ^ ~` form a single atom token (e.g., `=..`, `\+`, `=:=`).

### Step 3.2: Pratt parser

The core of Phase 3. A Pratt parser (top-down operator-precedence) is the standard way to parse Prolog terms because:

1. Operator precedence is dynamic (`op/3` changes it mid-file)
2. Precedence ranges 1–1200 with fine-grained distinctions
3. Associativity specifiers (xfx, xfy, yfx, fx, fy, xf, yf) map directly to Pratt binding powers

```python
class PrologParser:
    """Pratt parser for Prolog terms."""

    def __init__(self, tokens: list[Token], op_table: OperatorTable):
        self._tokens = tokens
        self._pos = 0
        self._ops = op_table

    def parse_program(self) -> PModule:
        """Parse a sequence of clauses/directives terminated by '.'"""
        items = []
        while not self._at_end():
            items.append(self._parse_item())
        return PModule(tuple(items))

    def _parse_item(self) -> PItem:
        """Parse one clause, directive, or query, consuming the trailing '.'"""
        term = self._parse_term(1200)
        self._expect(TokenType.DOT)
        return self._classify_item(term)

    def _parse_term(self, max_prec: int) -> PTerm:
        """Parse a term with operators up to max_prec."""
        left = self._parse_primary()
        while True:
            op = self._peek_infix_or_postfix()
            if op is None:
                break
            entry = self._ops.lookup_infix(op.value) or self._ops.lookup_postfix(op.value)
            if entry is None or entry.precedence > max_prec:
                break
            # Pratt binding power from specifier
            if entry.specifier in ('xfx', 'xfy', 'yfx'):
                self._advance()
                r_prec = self._right_prec(entry)
                right = self._parse_term(r_prec)
                left = PCompound(entry.name, (left, right))
            elif entry.specifier in ('xf', 'yf'):
                self._advance()
                left = PCompound(entry.name, (left,))
            else:
                break
        return left

    def _parse_primary(self) -> PTerm:
        """Parse a primary (non-operator) term."""
        tok = self._peek()
        match tok.type:
            case TokenType.INTEGER | TokenType.FLOAT:
                return self._parse_number()
            case TokenType.STRING:
                return self._parse_string()
            case TokenType.VAR:
                return self._parse_variable()
            case TokenType.ATOM:
                return self._parse_atom_or_compound()
            case TokenType.LPAREN:
                return self._parse_parenthesized()
            case TokenType.LBRACKET:
                return self._parse_list()
            case TokenType.LCURLY:
                return self._parse_curly()
            case _:
                # Check for prefix operator
                entry = self._ops.lookup_prefix(tok.value)
                if entry:
                    return self._parse_prefix(entry)
                raise ParseError(f"Unexpected token {tok}", tok.line, tok.col)

    def _right_prec(self, entry: OpEntry) -> int:
        """Right-side precedence from specifier.
        xfx: right must be strictly less  → prec - 1
        xfy: right may be equal           → prec
        yfx: right must be strictly less  → prec - 1
        """
        match entry.specifier:
            case 'xfx' | 'yfx': return entry.precedence - 1
            case 'xfy':          return entry.precedence
            case _:              return entry.precedence - 1
```

Key points:
- **`op/3` directive handling:** When `_classify_item` detects `:- op(Prec, Spec, Name).`, it calls `self._ops.define(Prec, Spec, Name)` *immediately*, affecting all subsequent parsing.
- **Comma as operator:** `,` is `1000 xfy` — it's just another operator in the Pratt parser.
- **Specifier semantics:** `x` means "strictly lower precedence than this operator"; `y` means "lower or equal". This maps to Pratt binding powers: `x` side uses `prec - 1`, `y` side uses `prec`.

### Step 3.3: Prolog AST → clausal source emitter

```python
class PrologToClausal:
    """Translates Prolog AST → clausal source text."""

    def __init__(self, dialect: Dialect): ...

    def emit_module(self, module: PModule) -> str: ...
    def emit_item(self, item: PItem) -> str: ...
    def emit_term(self, term: PTerm) -> str: ...
```

Mappings (reverse of Phase 1):

Prolog | Clausal
---|---
`head :- body.` | `Head(Args) <- (body)`
`head.` (fact) | `Head(Args),`
`head --> body.` | `Head >> (body)`
`:- module(...)` | `-module(...)`
`:- use_module(library(L), [...])` | `-import_from(L, [...])`
`:- dynamic pred/N` | `-dynamic(pred/N)`
`:- op(P, T, N)` | `# operator: op(P, T, N)` (comment, can't represent)
`X = Y` | `X is Y`
`X \= Y` | `X is not Y`
`X is Expr` | `X := Expr`
`\+ Goal` | `not Goal`
`(A ; B)` | `(A or B)`
`(A , B)` | `(A, B)`
`[H|T]` | `[H, *T]`
`% comment` | `# comment`
`foo_bar(...)` | `FooBar(...)`
`X` (variable) | `X` (keep) or `X_` if lowercase needed

### Step 3.4: User-defined operator mapping file

For projects with custom operators, users can provide a mapping file:

```json
{
  "operator_mappings": {
    "<>":    {"clausal": "NotEqual",  "arity": 2},
    "==>":   {"clausal": "Implies",   "arity": 2},
    "@":     {"clausal": "At",        "arity": 1}
  }
}
```

This tells the Prolog→Clausal translator how to render user-defined operators that have no Python operator equivalent.

---

## Phase 4: Roundtrip Validation & CLI

### Step 4.1: Unified CLI

```bash
# Clausal → Prolog
clausal translate input.clausal --to swi -o output.pl
clausal translate input.clausal --to scryer -o output.pl

# Prolog → Clausal
clausal translate input.pl --to clausal -o output.clausal

# Auto-detect direction from file extension
clausal translate input.clausal    # → stdout as ISO Prolog
clausal translate input.pl         # → stdout as clausal

# Roundtrip check
clausal translate --roundtrip input.clausal --dialect swi
```

### Step 4.2: Roundtrip properties

Property | Test
---|---
Clausal → Prolog → Clausal preserves semantics | Translate conformity suite both ways, run clausal tests on result
Prolog → Clausal → Prolog preserves semantics | Use SWI/Scryer test suites, translate to clausal and back, diff
Operator precedence preserved | `a + b * c` stays `a + b * c`, not `(a + b) * c`
Variable identity preserved | Variables that unify in source still unify in translation
Comment preservation | Comments appear in output (possibly reformatted)
Clause order preserved | Predicate clause order is semantic in Prolog

### Step 4.3: Golden file tests

For each `.clausal` fixture:
1. Translate to `.pl` (SWI and Scryer variants)
2. Check in as `tests/fixtures/prolog_golden/<name>.swi.pl` and `<name>.scryer.pl`
3. CI compares output against golden files

For Prolog→Clausal: collect representative `.pl` files from SWI/Scryer examples, translate, check in golden `.clausal` files.

---

## Phase 5 (stretch): Self-Hosted DCG Translator

Rewrite the Prolog parser as a clausal DCG operating on a token stream. The tokenizer remains Python (character-level DCGs are too slow for real use).

```
# Prolog term grammar in clausal DCG syntax
# State carries the operator table for dynamic op/3 handling

term(T, MaxPrec) >> (primary(Left), rest_ops(Left, T, MaxPrec))

rest_ops(Left, Result, MaxPrec) >> (
    infix_op(Op, Prec, Assoc),
    {Prec =< MaxPrec},
    {right_prec(Assoc, Prec, RPrec)},
    term(Right, RPrec),
    rest_ops(compound(Op, [Left, Right]), Result, MaxPrec)
)
rest_ops(T, T, _) >> ([])

primary(T) >> ([atom(A)], args_or_atom(A, T))
primary(var(V)) >> ([var(V)])
primary(number(N)) >> ([number(N)])
primary(T) >> (["("], term(T, 1200), [")"])
primary(list(T)) >> (["["], list_body(T), ["]"])

# ... etc.
```

This would use the state-threading DCG pattern from `dcg_state.clausal` to carry and update the operator table.

---

## Phase 6 (stretch): Additional Dialects

- **GNU Prolog:** No modules, different constraint library names, `fd_*` predicates
- **ECLiPSe:** Different module system, `lib(ic)` for constraints, `do/2` loops
- **XSB Prolog:** HiLog, tabling differences
- **Tau Prolog:** JavaScript-hosted, limited builtins

Each dialect is a `Dialect` subclass with its own operator table and library mapping.

---

## File Layout Summary

```
clausal/tools/
    prolog_ast.py              # Phase 1.1: Prolog AST nodes, visitor, transformer, builders
    prolog_operators.py        # Phase 1.1: OperatorTable + ISO/SWI/Scryer defaults
    prolog_dialect.py          # Phase 1.1: Dialect configurations
    clausal_to_prolog.py       # Phase 1.2–1.5: clausal pythonic_ast → Prolog AST → text
    prolog_bridge.py           # Phase 1b: Tier 2 — AST ↔ clausal runtime conversions
    prolog_tokenizer.py        # Phase 3.1: Prolog lexer
    prolog_parser.py           # Phase 3.2: Pratt parser → Prolog AST
    prolog_to_clausal.py       # Phase 3.3: Prolog AST → clausal source text
    prolog_runtime.py          # Phase 3b: Tier 3 — PrologBridge ABC + SWI/Scryer impls

tests/
    test_prolog_ast.py         # Phase 1.1: AST nodes, visitor, transformer, builders
    test_prolog_operators.py   # Phase 1.1: operator table tests
    test_prolog_emit.py        # Phase 1.2–1.4: clausal → Prolog text tests
    test_prolog_bridge.py      # Phase 1b: Tier 2 round-trip: runtime → AST → runtime
    test_prolog_tokenizer.py   # Phase 3.1: tokenizer tests
    test_prolog_parser.py      # Phase 3.2: Pratt parser tests
    test_prolog_to_clausal.py  # Phase 3.3: Prolog AST → clausal text tests
    test_prolog_runtime.py     # Phase 3b: live bridge tests (requires SWI/Scryer install)
    test_prolog_roundtrip.py   # Phase 4: full roundtrip property tests
    fixtures/prolog_golden/    # Phase 4.3: golden .pl files
    fixtures/prolog_input/     # Phase 3: sample .pl files for parser tests
```

---

## Revised Phase Map

Phase | Tier | New files | Key deliverable
---|---|---|---
**1.1** Prolog AST + operators | — | 3 | Shared infrastructure: nodes, visitor, transformer, builders, OperatorTable
**1.2** clausal → Prolog text | 1 | 2 | pythonic_ast → Prolog AST → `.pl` source; naming; CLI
**1b** AST ↔ runtime bridge | 2 | 1 | `clausal_term_to_pterm`, `pterm_to_clausal_term`, `db_to_prolog_ast`, `prolog_ast_to_db`
**2** Dialect layer | 1,2 | 1 (extend) | SWI/Scryer-specific emission, library maps, untranslatable handling
**3.1** Prolog tokenizer | 1 | 1 | Lexer for Prolog source
**3.2** Pratt parser | 1 | 1 | Prolog source → Prolog AST with dynamic `op/3`
**3.3** Prolog → clausal text | 1 | 1 | Prolog AST → `.clausal` source
**3b** Runtime bridge | 3 | 1 | `PrologBridge` ABC, `SWIPrologBridge`, `ScryerPrologBridge`
**4** Roundtrip validation | 1,2 | 2 | Golden files, property tests, unified CLI
**5** (stretch) Self-hosted DCG | — | 1–2 .clausal | Pratt parser as clausal DCG grammar
**6** (stretch) More dialects | 1,2,3 | 1 per dialect | GNU Prolog, ECLiPSe, XSB, Tau Prolog

**Phase 1b can be done in parallel with Phase 1.2** — they share the Prolog AST nodes
from 1.1 but are otherwise independent. The bridge is especially valuable early because
it enables testing the AST layer against real clausal programs without needing the
text emitter to be complete.

**Phase 3b depends on 3.1 + 3.2** (the parser) for parsing Prolog engine responses,
but the abstract `PrologBridge` interface and term conversion functions can be
designed alongside Phase 1b.

---
---

# APPENDIX A: Concrete Implementation Guide

This appendix provides the exact codebase pointers, AST node mappings, worked
examples, and starter test cases needed to implement each phase.

---

## A.1: Codebase Pointers — Key Files and Functions

### Where clausal source becomes AST

1. **Python parses `.clausal` source** → standard `ast.Module`
2. **`EmbedTransformer`** (`clausal/templating/term_rewriting.py`, line ~1996) walks
   the module-level statements and rewrites them into `pythonic_ast` nodes:
   - `head,` (trailing comma fact) → `Predicate(head=..., body=true)`
   - `head <- body` → `Predicate(head=..., body=...)`
   - `head >> body` → DCG rule (rewritten to `Predicate` with hidden state args)
   - `-directive(...)` → `Directive`, `ModuleDeclaration`, `ImportFromDirective`, etc.
   - `# comment` → preserved in Python AST as-is (not in pythonic_ast)
3. **`TermTransformer`** (`clausal/templating/term_rewriting.py`, line ~409) transforms
   individual expressions within heads/bodies to `pythonic_ast` operator nodes.

The import hook entry point is `PredicateLoader.source_to_code()` in
`clausal/import_hook.py` (line ~196).

### How `<-` is detected

Python parses `Head(X) <- (Body)` as:

```python
ast.Expr(value=ast.Compare(
    left=ast.Call(func=ast.Name('Head'), args=[ast.Name('X')]),
    ops=[ast.Lt()],
    comparators=[ast.UnaryOp(op=ast.USub(), operand=...body...)]
))
```

The function `_detect_arrow(left, operators, comparators)` at line ~197 of
`term_rewriting.py` checks for `Lt` followed by `USub` on the leftmost spine
of the body. The `USub` is consumed (it's the `-` in `<-`).

### How trailing-comma facts work

Python parses `Edge(1, 2),` as `ast.Expr(value=ast.Tuple(elts=[ast.Call(...)]))`.
`EmbedTransformer` detects the single-element tuple wrapping a Call and emits
`Predicate(head=..., body=None)` (or `body=true` atom).

### How directives work

Python parses `-module(name, [...])` as `ast.Expr(value=ast.UnaryOp(op=ast.USub(),
operand=ast.Call(func=ast.Name('module'), ...)))`. `EmbedTransformer` detects the
top-level `USub(Call(...))` pattern and dispatches on the function name to produce
`ModuleDeclaration`, `Directive`, `ImportFromDirective`, etc.

### Logic variable detection

`_is_logic_var_name(identifier)` at line ~288 of `term_rewriting.py`:
- Trailing underscore: `X_`, `foo_`, `HEAD_` (single `_`, not dunder, not bare `_`)
- ALL-CAPS: `X`, `FOO`, `RESULT` (every cased char is uppercase, at least one cased char)

### pythonic_ast node classes

All defined in `clausal/pythonic_ast/nodes.py`. Key ones for translation:

**Clause-level:**
- `Predicate(head: Node, body: Node)` — line 968
- `Directive(name: str, specs: list)` — line 977
- `ModuleDeclaration(module_name: str, exports: list)` — line 994
- `ImportFromDirective(module: str, names: list)` — line 983
- `ImportModuleDirective(module: str)` — line 989
- `PrivateDeclaration(items: list)` — line 1000

**Operators (all have `left: Node, right: Node` or `operand: Node`):**
- `Unify` — `X is Y` (line 619)
- `DoesNotUnify` — `X is not Y` (line 624)
- `Evaluate` — `R := Expr` (line 629)
- `And` — `A and B` or `A, B` in body (line 559)
- `Or` — `A or B` (line 563)
- `Not(operand)` — `not G` (line 580)
- `StructuralEq` — `X == Y` (line 593)
- `StructuralNeq` — `X != Y` (line 598)
- `Lt`, `LtE`, `Gt`, `GtE` — comparisons (lines 603-616)
- `Add`, `Sub`, `Mult`, `Div`, `FloorDiv`, `Mod`, `Pow` — arithmetic (lines 502-527)
- `RShift` — `>>` used for DCG at clause level (line 539)

**Terms:**
- `Call(func: Node, args: list[Node], kwargs: list[Keyword])` — predicate/functor call
- `LoadName(name: str)` — bare name (variable or atom depending on convention)
- `StarUnpack(value: Node)` — `*T` in `[H, *T]`
- `ListLiteral(elements: list[Node])` — `[1, 2, 3]` or `[H, *T]`
- `IntLiteral(value: int)`, `FloatLiteral(value: float)`, `StringLiteral(value: str)`

### Runtime term types

- **`Var`**: `clausal/logic/variables/__init__.py` — C extension, has `._name` attr
- **`Compound(functor, args)`**: `clausal/terms.py` — generic compound term
- **`DictTerm(data: dict)`**: `clausal/terms.py`
- **`SetTerm(elements)`**: `clausal/terms.py`
- **`KWTerm(functor, **kwargs)`**: `clausal/terms.py`
- **`PredicateMeta` instances**: `clausal/logic/predicate.py` — known-functor terms with named fields via `._fields`

### Database clause storage

- `Clause(head, body)`: `clausal/logic/database.py`, line ~22
- `Database._clauses: dict[tuple[str, int], list[Clause]]` — keyed by `(functor, arity)`
- `Database.clauses_for(functor, arity) -> list[Clause]`
- `PredicateMeta._clauses: list[Clause]` — per-class clause list

### Existing pattern to follow: `visualize.py`

`clausal/tools/visualize.py` already does AST → source:
```python
def predicate_to_source(functor, arity, clauses, db, *, trampoline=False) -> str:
    func_def = predicate_ast(functor, arity, clauses, db, trampoline=trampoline)
    raw = ast.unparse(func_def)
    # ... format with black
```

The Prolog emitter follows the same pattern but produces Prolog text instead of
Python text, and works from Prolog AST nodes instead of Python `ast` nodes.

---

## A.2: Worked Examples — Clausal Source → Expected Prolog Output

### Example 1: Simple facts and rules

**Input** (`edge_graph.clausal`):
```
# Edge facts
Edge(1, 2),
Edge(2, 3),
Edge(1, 3),

# Reachability
Reach(X, Y) <- Edge(X, Y)
Reach(X, Y) <- (
    Edge(X, Z),
    Reach(Z, Y)
)
```

**Expected Prolog output** (ISO):
```prolog
% Edge facts
edge(1, 2).
edge(2, 3).
edge(1, 3).

% Reachability
reach(X, Y) :-
    edge(X, Y).
reach(X, Y) :-
    edge(X, Z),
    reach(Z, Y).
```

**Prolog AST for this example:**
```python
PModule(items=(
    PClause(head=PCompound('edge', (PNumber(1), PNumber(2)))),
    PClause(head=PCompound('edge', (PNumber(2), PNumber(3)))),
    PClause(head=PCompound('edge', (PNumber(1), PNumber(3)))),
    PClause(
        head=PCompound('reach', (PVar('X'), PVar('Y'))),
        body=PCompound('edge', (PVar('X'), PVar('Y')))
    ),
    PClause(
        head=PCompound('reach', (PVar('X'), PVar('Y'))),
        body=PCompound(',', (
            PCompound('edge', (PVar('X'), PVar('Z'))),
            PCompound('reach', (PVar('Z'), PVar('Y')))
        ))
    ),
))
```

### Example 2: Operators and arithmetic

**Input** (`iso_control.clausal` excerpt):
```
Test("conjunction binds two vars") <- (
    X_ is 1,
    Y_ is 2,
    X_ == 1,
    Y_ == 2
)
SafeMax(X, Y, X) <- (X >= Y)
SafeMax(X, Y, Y) <- (Y > X)
```

**Expected Prolog output:**
```prolog
test("conjunction binds two vars") :-
    X = 1,
    Y = 2,
    X =:= 1,
    Y =:= 2.
safe_max(X, Y, X) :-
    X >= Y.
safe_max(X, Y, Y) :-
    Y > X.
```

**Key mappings demonstrated:**
- `X_ is 1` → `X = 1` (Unify → `=`)
- `X_ == 1` → `X =:= 1` (StructuralEq → `=:=` for arithmetic context)
  - **Note:** `==` in clausal is structural equality. In Prolog, `==` is also
    structural equality, but `=:=` is arithmetic equality. The translator must
    determine from context which to use. Default: `==` → `==` (structural),
    but when both sides are ground arithmetic, consider `=:=`. This is a
    known ambiguity — document it and default to `==`.
- `X >= Y` → `X >= Y` (same)
- `SafeMax` → `safe_max` (PascalCase → snake_case)
- `X_` → `X` (strip trailing underscore)

### Example 3: Lists with spread syntax

**Input:**
```
Append([], L, L),
Append([H, *T], L, [H, *R]) <- Append(T, L, R)
```

**Expected Prolog output:**
```prolog
append([], L, L).
append([H|T], L, [H|R]) :-
    append(T, L, R).
```

**Key:** `[H, *T]` (Python star-unpack) → `[H|T]` (Prolog bar notation).
In the pythonic_ast, this is `ListLiteral([LoadName('H'), StarUnpack(LoadName('T'))])`.

### Example 4: Arithmetic evaluation

**Input:**
```
Double(X, Y) <- (Y := X * 2)
TriangleNumber(N, T) <- (T := N * (N + 1) // 2)
```

**Expected Prolog output:**
```prolog
double(X, Y) :-
    Y is X * 2.
triangle_number(N, T) :-
    T is N * (N + 1) // 2.
```

**Key:** `Y := X * 2` (Evaluate node) → `Y is X * 2`.

### Example 5: Negation, disjunction, unification operators

**Input:**
```
Test("negation") <- (not (a is b))
Test("disjunction") <- (X_ is 1 or X_ is 2)
Test("dif") <- (X_ is not Y_)
```

**Expected Prolog output:**
```prolog
test("negation") :-
    \+ a = b.
test("disjunction") :-
    (X = 1 ; X = 2).
test("dif") :-
    dif(X, Y).
```

**Key:** `not` → `\+`, `or` → `;`, `is not` → `dif` (or `\=` depending on dialect).

### Example 6: Module directive and imports

**Input:**
```
-module(iso_control, [Test(DESC)])
-import_from(tests.fixtures.importable_utils, [Helper, Double])
-private([Choose(X, Y, R), SafeMax(X, Y, M)])
```

**Expected Prolog output (SWI):**
```prolog
:- module(iso_control, [test/1]).
:- use_module('tests/fixtures/importable_utils', [helper/2, double/2]).
```

**Key:**
- `-module(...)` → `:- module(...)` with exports as `functor/arity`
- `-import_from(...)` → `:- use_module(...)` with dotted path → file path
- `-private(...)` → omitted (Prolog modules export by default; private is implicit)
- Export `Test(DESC)` → `test/1` (PascalCase→snake_case, count fields for arity)

### Example 7: DCG rules

**Input** (`dcg_grammar.clausal`):
```
greeting >> (["hello", "world"])
sentence >> (noun_phrase, verb_phrase, noun_phrase)
digit(D_) >> ([D_], {D_ >= 0}, {D_ <= 9})
```

**Expected Prolog output:**
```prolog
greeting --> [hello, world].
sentence --> noun_phrase, verb_phrase, noun_phrase.
digit(D) --> [D], {D >= 0}, {D =< 9}.
```

**Key:**
- `>>` → `-->` (DCG arrow)
- `["hello", "world"]` → `[hello, world]` (string terminals → atoms)
- `{D_ >= 0}` → `{D >= 0}` (inline goals in curly braces)
- `>=` stays `>=` but `<=` in clausal would become `=<` in Prolog (ISO: `=<` not `<=`)

### Example 8: CLP(FD) constraints

**Input** (`clpfd_queens.clausal`):
```
SafeQueens(N_, Qs_) <- (
    InDomain(Qs_, 1, N_)
    and AllDifferent(Qs_)
    and Label(Qs_)
    and CheckDiagonals(Qs_)
)
```

**Expected Prolog output (SWI):**
```prolog
:- use_module(library(clpfd)).

safe_queens(N, Qs) :-
    Qs ins 1..N,
    all_different(Qs),
    label(Qs),
    check_diagonals(Qs).
```

**Expected Prolog output (Scryer):**
```prolog
:- use_module(library(clpz)).

safe_queens(N, Qs) :-
    Qs ins 1..N,
    all_distinct(Qs),
    label(Qs),
    check_diagonals(Qs).
```

**Key:**
- `InDomain(Qs_, 1, N_)` → `Qs ins 1..N` (builtin-specific translation)
- `AllDifferent` → `all_different` (SWI) / `all_distinct` (Scryer)
- `and` → `,`

---

## A.3: Naming Convention Details

### PascalCase → snake_case algorithm

```python
import re

def pascal_to_snake(name: str) -> str:
    """Convert PascalCase predicate names to Prolog snake_case.

    FooBar      → foo_bar
    AllDifferent → all_different
    CLP         → clp
    CopyTerm    → copy_term
    DCGRule     → dcg_rule
    FStringThunk → f_string_thunk
    IOStream    → io_stream
    """
    # Insert underscore before uppercase runs:
    # "CopyTerm" → "Copy_Term" → "copy_term"
    # "DCGRule"  → "DCG_Rule"  → "dcg_rule"
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)
    return s.lower()

def snake_to_pascal(name: str) -> str:
    """Convert Prolog snake_case to clausal PascalCase.

    foo_bar        → FooBar
    all_different  → AllDifferent
    copy_term      → CopyTerm
    """
    return ''.join(word.capitalize() for word in name.split('_'))
```

### Variable name mapping

```python
def clausal_var_to_prolog(name: str) -> str:
    """Convert clausal variable names to Prolog convention.

    X_       → X          (strip trailing underscore, already uppercase)
    foo_     → Foo        (strip underscore, capitalize)
    HEAD_    → Head       (strip underscore, titlecase)
    RESULT   → Result     (ALLCAPS → titlecase)
    X        → X          (single uppercase letter stays)
    _        → _          (anonymous stays)
    """
    if name == '_':
        return '_'
    if name.endswith('_') and not name.endswith('__'):
        name = name[:-1]
    # Titlecase: first letter upper, rest lower
    if name.isupper() and len(name) > 1:
        return name[0] + name[1:].lower()
    if name[0].islower():
        return name[0].upper() + name[1:]
    return name

def prolog_var_to_clausal(name: str) -> str:
    """Convert Prolog variable names to clausal convention.

    X        → X          (single uppercase stays — it's ALLCAPS)
    Foo      → FOO or foo_ (depending on convention preference)
    Head     → HEAD_      (prefer trailing underscore for multi-char)
    _Ignored → _ignored_  (leading underscore → trailing, lowercase)
    _        → _          (anonymous stays)
    """
    if name == '_':
        return '_'
    if name.startswith('_'):
        # _Foo → foo_ (Prolog "don't care but named")
        return name[1:].lower() + '_'
    if len(name) == 1 and name.isupper():
        return name  # Single letter: X stays X
    # Multi-char: titlecase → trailing underscore lowercase
    return name.lower() + '_'
```

### Known-names override table

For builtins where mechanical conversion doesn't produce the standard Prolog name:

```python
BUILTIN_NAME_MAP = {
    # clausal name → (ISO Prolog, SWI-specific, Scryer-specific)
    'AssertZ':       ('assertz',        None, None),
    'AssertA':       ('asserta',        None, None),
    'Retract':       ('retract',        None, None),
    'FindAll':       ('findall',        None, None),
    'BagOf':         ('bagof',          None, None),
    'SetOf':         ('setof',          None, None),
    'ForAll':        ('forall',         None, None),
    'CopyTerm':      ('copy_term',      None, None),
    'TermVariables': ('term_variables', None, None),
    'NumberVars':    ('numbervars',     None, None),
    'AllDifferent':  (None,             'all_different', 'all_distinct'),
    'InDomain':      (None,             'ins',           'ins'),  # special: ternary → binary infix
    'Label':         ('label',          'label',         'label'),
    'Labeling':      ('labeling',       'labeling',      'labeling'),
    'MapList':       ('maplist',        None, None),
    'Writeln':       ('writeln',        None, None),
    'Write':         ('write',          None, None),
    'Nl':            ('nl',             None, None),
    'Tab':           ('tab',            None, None),
    'Call':          ('call',           None, None),
    'Atom':          ('atom',           None, None),
    'Number':        ('number',         None, None),
    'Integer':       ('integer',        None, None),
    'Float':         ('float',          None, None),
    'Var':           ('var',            None, None),  # type check, not logic Var
    'NonVar':        ('nonvar',         None, None),
    'Compound':      ('compound',       None, None),  # type check
    'Functor':       ('functor',        None, None),
    'Arg':           ('arg',            None, None),
    'Length':        ('length',         None, None),
    'Member':        ('member',         None, None),
    'Append':        ('append',         None, None),
    'Reverse':       ('reverse',        None, None),
    'Last':          ('last',           None, None),
    'Permutation':   ('permutation',    None, None),
    'Between':       ('between',        None, None),
    'Succ':          ('succ',           None, None),
    'Plus':          ('plus',           None, None),
    'Phrase':        ('phrase',         None, None),
    'TimeGoal':      (None,             'time', 'time'),  # different name entirely
}
```

---

## A.4: Starter Test Cases

### test_prolog_ast.py

```python
"""Tests for Prolog AST nodes, visitor, transformer, and builders."""
import pytest
from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PModule,
    PrologVisitor, PrologTransformer,
    atom, var, anon, compound, op, prefix, plist, cons,
    fact, rule, dcg_rule, directive, module,
    variables, functors, is_ground, term_size, subterms,
)


class TestNodeConstruction:
    def test_atom(self):
        a = PAtom("foo")
        assert a.name == "foo"
        assert a.quoted is False

    def test_atom_quoted(self):
        a = PAtom("Hello World", quoted=True)
        assert a.quoted is True

    def test_var(self):
        v = PVar("X")
        assert v.name == "X"

    def test_number_int(self):
        n = PNumber(42)
        assert n.value == 42

    def test_number_float(self):
        n = PNumber(3.14)
        assert n.value == 3.14

    def test_compound(self):
        c = PCompound("foo", (PAtom("a"), PVar("X")))
        assert c.functor == "foo"
        assert len(c.args) == 2

    def test_list_proper(self):
        l = PList((PNumber(1), PNumber(2), PNumber(3)))
        assert l.tail is None

    def test_list_partial(self):
        l = PList((PVar("H"),), tail=PVar("T"))
        assert l.tail == PVar("T")

    def test_clause_fact(self):
        c = PClause(head=PCompound("edge", (PNumber(1), PNumber(2))))
        assert c.body is None

    def test_clause_rule(self):
        c = PClause(
            head=PCompound("reach", (PVar("X"), PVar("Y"))),
            body=PCompound("edge", (PVar("X"), PVar("Y")))
        )
        assert c.body is not None

    def test_frozen(self):
        a = PAtom("foo")
        with pytest.raises(AttributeError):
            a.name = "bar"  # type: ignore


class TestBuilders:
    def test_atom_builder(self):
        assert atom("foo") == PAtom("foo")

    def test_var_builder(self):
        assert var("X") == PVar("X")

    def test_anon_builder(self):
        assert anon() == PVar("_")

    def test_compound_builder(self):
        c = compound("foo", atom("a"), var("X"))
        assert c == PCompound("foo", (PAtom("a"), PVar("X")))

    def test_op_builder(self):
        o = op(",", atom("a"), atom("b"))
        assert o == PCompound(",", (PAtom("a"), PAtom("b")))

    def test_cons_builder(self):
        c = cons(var("H"), var("T"))
        assert c == PList((PVar("H"),), tail=PVar("T"))

    def test_fact_builder(self):
        f = fact(compound("edge", PNumber(1), PNumber(2)))
        assert isinstance(f, PClause)
        assert f.body is None

    def test_rule_builder(self):
        r = rule(compound("reach", var("X"), var("Y")),
                 compound("edge", var("X"), var("Y")))
        assert isinstance(r, PClause)
        assert r.body is not None


class TestIntrospection:
    def test_variables_simple(self):
        t = PCompound("foo", (PVar("X"), PAtom("a"), PVar("Y")))
        assert variables(t) == {"X", "Y"}

    def test_variables_excludes_anon(self):
        t = PCompound("foo", (PVar("_"), PVar("X")))
        assert variables(t) == {"X"}

    def test_functors(self):
        t = PCompound(",", (
            PCompound("edge", (PVar("X"), PVar("Z"))),
            PCompound("reach", (PVar("Z"), PVar("Y")))
        ))
        assert ("edge", 2) in functors(t)
        assert ("reach", 2) in functors(t)
        assert (",", 2) in functors(t)

    def test_is_ground_true(self):
        assert is_ground(PCompound("foo", (PNumber(1), PAtom("a"))))

    def test_is_ground_false(self):
        assert not is_ground(PCompound("foo", (PVar("X"),)))

    def test_term_size(self):
        t = PCompound("f", (PAtom("a"), PCompound("g", (PNumber(1),))))
        assert term_size(t) == 4  # f, a, g, 1


class TestVisitor:
    def test_collects_atoms(self):
        class AtomCollector(PrologVisitor):
            def __init__(self):
                self.atoms = []
            def visit_PAtom(self, node):
                self.atoms.append(node.name)

        t = PCompound("foo", (PAtom("a"), PAtom("b")))
        v = AtomCollector()
        v.visit(t)
        assert v.atoms == ["a", "b"]


class TestTransformer:
    def test_rename_vars(self):
        class VarRenamer(PrologTransformer):
            def visit_PVar(self, node):
                return PVar(node.name + "_renamed")

        t = PCompound("foo", (PVar("X"), PAtom("a")))
        result = VarRenamer().visit(t)
        assert result == PCompound("foo", (PVar("X_renamed"), PAtom("a")))
```

### test_prolog_operators.py

```python
"""Tests for the Prolog operator table."""
import pytest
from clausal.tools.prolog_operators import OperatorTable, OpEntry


class TestOperatorTable:
    def test_iso_default_has_comma(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(",")
        assert e is not None
        assert e.precedence == 1000
        assert e.specifier == "xfy"

    def test_iso_default_has_plus(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("+")
        assert e is not None
        assert e.precedence == 500
        assert e.specifier == "yfx"

    def test_iso_default_has_negation(self):
        t = OperatorTable.iso_default()
        e = t.lookup_prefix("\\+")
        assert e is not None
        assert e.precedence == 900
        assert e.specifier == "fy"

    def test_iso_default_has_unify(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("=")
        assert e is not None
        assert e.precedence == 700
        assert e.specifier == "xfx"

    def test_iso_default_has_is(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("is")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_clause_arrow(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(":-")
        assert e is not None
        assert e.precedence == 1200
        assert e.specifier == "xfx"

    def test_iso_default_has_dcg_arrow(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("-->")
        assert e is not None
        assert e.precedence == 1200

    def test_define_user_op(self):
        t = OperatorTable.iso_default()
        t.define(700, "xfx", "<>")
        e = t.lookup_infix("<>")
        assert e is not None
        assert e.precedence == 700

    def test_user_defined_list(self):
        t = OperatorTable.iso_default()
        assert t.user_defined() == []
        t.define(700, "xfx", "<>")
        ud = t.user_defined()
        assert len(ud) == 1
        assert ud[0].name == "<>"

    def test_swi_default_has_xor(self):
        t = OperatorTable.swi_default()
        e = t.lookup_infix("xor")
        assert e is not None

    def test_scryer_default_is_iso_base(self):
        t = OperatorTable.scryer_default()
        # Scryer starts with ISO defaults
        e = t.lookup_infix("=")
        assert e is not None

    def test_prefix_minus(self):
        t = OperatorTable.iso_default()
        e = t.lookup_prefix("-")
        assert e is not None
        assert e.precedence == 200
        assert e.specifier == "fy"

    def test_same_name_prefix_and_infix(self):
        """'-' is both prefix (fy 200) and infix (yfx 500)."""
        t = OperatorTable.iso_default()
        pre = t.lookup_prefix("-")
        inf = t.lookup_infix("-")
        assert pre is not None
        assert inf is not None
        assert pre.specifier == "fy"
        assert inf.specifier == "yfx"
```

### test_prolog_emit.py (Phase 1.2)

```python
"""Tests for clausal → Prolog source emission."""
import pytest
from clausal.tools.prolog_ast import *
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.clausal_to_prolog import (
    emit_term, emit_item, emit_module,
    clausal_source_to_prolog, clausal_source_to_prolog_ast,
    pascal_to_snake, snake_to_pascal,
    clausal_var_to_prolog, prolog_var_to_clausal,
)


class TestNaming:
    def test_pascal_to_snake_simple(self):
        assert pascal_to_snake("FooBar") == "foo_bar"

    def test_pascal_to_snake_allcaps(self):
        assert pascal_to_snake("CLP") == "clp"

    def test_pascal_to_snake_mixed(self):
        assert pascal_to_snake("AllDifferent") == "all_different"

    def test_pascal_to_snake_dcg(self):
        assert pascal_to_snake("DCGRule") == "dcg_rule"

    def test_snake_to_pascal_simple(self):
        assert snake_to_pascal("foo_bar") == "FooBar"

    def test_snake_to_pascal_copy_term(self):
        assert snake_to_pascal("copy_term") == "CopyTerm"

    def test_var_trailing_underscore(self):
        assert clausal_var_to_prolog("X_") == "X"

    def test_var_allcaps(self):
        assert clausal_var_to_prolog("RESULT") == "Result"

    def test_var_single_letter(self):
        assert clausal_var_to_prolog("X") == "X"

    def test_var_anon(self):
        assert clausal_var_to_prolog("_") == "_"

    def test_var_lowercase_trailing(self):
        assert clausal_var_to_prolog("head_") == "Head"


class TestEmitTerm:
    def test_atom(self):
        assert emit_term(PAtom("foo"), OperatorTable.iso_default()) == "foo"

    def test_atom_needs_quoting(self):
        result = emit_term(PAtom("Hello World", quoted=True), OperatorTable.iso_default())
        assert result == "'Hello World'"

    def test_var(self):
        assert emit_term(PVar("X"), OperatorTable.iso_default()) == "X"

    def test_anon_var(self):
        assert emit_term(PVar("_"), OperatorTable.iso_default()) == "_"

    def test_integer(self):
        assert emit_term(PNumber(42), OperatorTable.iso_default()) == "42"

    def test_float(self):
        assert emit_term(PNumber(3.14), OperatorTable.iso_default()) == "3.14"

    def test_string(self):
        assert emit_term(PString("hello"), OperatorTable.iso_default()) == '"hello"'

    def test_compound_simple(self):
        t = PCompound("foo", (PAtom("a"), PVar("X")))
        assert emit_term(t, OperatorTable.iso_default()) == "foo(a, X)"

    def test_compound_binary_op(self):
        t = PCompound("+", (PNumber(1), PNumber(2)))
        assert emit_term(t, OperatorTable.iso_default()) == "1 + 2"

    def test_compound_op_precedence(self):
        # 1 + 2 * 3 should not parenthesize (+ is 500, * is 400 — lower binds tighter)
        t = PCompound("+", (PNumber(1), PCompound("*", (PNumber(2), PNumber(3)))))
        assert emit_term(t, OperatorTable.iso_default()) == "1 + 2 * 3"

    def test_compound_op_needs_parens(self):
        # (1 + 2) * 3 needs parens
        t = PCompound("*", (PCompound("+", (PNumber(1), PNumber(2))), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "(1 + 2) * 3"

    def test_conjunction(self):
        t = PCompound(",", (PCompound("a", ()), PCompound("b", ())))
        result = emit_term(t, OperatorTable.iso_default())
        assert result == "a, b"

    def test_disjunction(self):
        t = PCompound(";", (PCompound("a", ()), PCompound("b", ())))
        result = emit_term(t, OperatorTable.iso_default())
        assert result == "(a ; b)"  # disjunction usually parenthesized in body

    def test_negation(self):
        t = PCompound("\\+", (PCompound("a", ()),))
        result = emit_term(t, OperatorTable.iso_default())
        assert result == "\\+ a"

    def test_list_proper(self):
        t = PList((PNumber(1), PNumber(2), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "[1, 2, 3]"

    def test_list_partial(self):
        t = PList((PVar("H"),), tail=PVar("T"))
        assert emit_term(t, OperatorTable.iso_default()) == "[H|T]"

    def test_list_empty(self):
        t = PList(())
        assert emit_term(t, OperatorTable.iso_default()) == "[]"

    def test_curly(self):
        t = PCurly(PCompound(">", (PVar("X"), PNumber(0))))
        assert emit_term(t, OperatorTable.iso_default()) == "{X > 0}"

    def test_unify(self):
        t = PCompound("=", (PVar("X"), PNumber(1)))
        assert emit_term(t, OperatorTable.iso_default()) == "X = 1"

    def test_is_eval(self):
        t = PCompound("is", (PVar("Y"), PCompound("*", (PVar("X"), PNumber(2)))))
        assert emit_term(t, OperatorTable.iso_default()) == "Y is X * 2"


class TestEmitItem:
    def test_fact(self):
        c = PClause(head=PCompound("edge", (PNumber(1), PNumber(2))))
        assert emit_item(c, OperatorTable.iso_default()) == "edge(1, 2).\n"

    def test_rule(self):
        c = PClause(
            head=PCompound("reach", (PVar("X"), PVar("Y"))),
            body=PCompound("edge", (PVar("X"), PVar("Y")))
        )
        result = emit_item(c, OperatorTable.iso_default())
        assert "reach(X, Y) :-" in result
        assert "edge(X, Y)" in result
        assert result.endswith(".\n")

    def test_dcg_rule(self):
        r = PDCGRule(
            head=PAtom("greeting"),
            body=PList((PAtom("hello"), PAtom("world")))
        )
        result = emit_item(r, OperatorTable.iso_default())
        assert "greeting -->" in result
        assert "[hello, world]" in result

    def test_directive(self):
        d = PDirective(PCompound("dynamic", (
            PCompound("/", (PAtom("color"), PNumber(2))),
        )))
        result = emit_item(d, OperatorTable.iso_default())
        assert result.startswith(":- ")
        assert "dynamic" in result


class TestFullTranslation:
    """End-to-end: clausal source text → Prolog source text."""

    def test_edge_graph(self):
        source = '''
Edge(1, 2),
Edge(2, 3),
Reach(X, Y) <- Edge(X, Y)
Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
'''
        result = clausal_source_to_prolog(source)
        assert "edge(1, 2)." in result
        assert "edge(2, 3)." in result
        assert "reach(X, Y) :-" in result
        assert "edge(X, Y)" in result
        assert "edge(X, Z)" in result
        assert "reach(Z, Y)" in result

    def test_arithmetic(self):
        source = 'Double(X, Y) <- (Y := X * 2)'
        result = clausal_source_to_prolog(source)
        assert "double(X, Y) :-" in result
        assert "Y is X * 2" in result

    def test_negation(self):
        source = 'Safe(X) <- (not Danger(X))'
        result = clausal_source_to_prolog(source)
        assert "\\+ danger(X)" in result

    def test_list_spread(self):
        source = 'Append([H, *T], L, [H, *R]) <- Append(T, L, R)'
        result = clausal_source_to_prolog(source)
        assert "[H|T]" in result
        assert "[H|R]" in result

    def test_module_directive(self):
        source = '-module(my_mod, [Foo(X)])'
        result = clausal_source_to_prolog(source)
        assert ":- module(my_mod, [foo/1])." in result

    def test_unification(self):
        source = 'Id(X, Y) <- (X is Y)'
        result = clausal_source_to_prolog(source)
        assert "X = Y" in result

    def test_disequality(self):
        source = 'Different(X, Y) <- (X is not Y)'
        result = clausal_source_to_prolog(source)
        assert "dif(X, Y)" in result or "X \\= Y" in result
```

---

## A.5: Phase 1.1 Implementation Checklist

These are the exact steps for implementing Phase 1.1. Each step should be a
testable increment.

### Step 1: Create `clausal/tools/prolog_ast.py`

1. Define all `PTerm` node dataclasses: `PAtom`, `PVar`, `PNumber`, `PString`,
   `PCompound`, `PList`, `PCurly`
2. Define all `PItem` node dataclasses: `PClause`, `PDCGRule`, `PDirective`, `PQuery`
3. Define `PModule`
4. Define `PTerm` and `PItem` type aliases
5. Implement `_children(node)` helper that yields child nodes for any node type
6. Implement `PrologVisitor` with `visit()`, `generic_visit()`
7. Implement `PrologTransformer` with `visit()`, `generic_visit()` that rebuilds
   nodes using `dataclasses.replace()`
8. Implement builder functions: `atom()`, `var()`, `anon()`, `compound()`, `op()`,
   `prefix()`, `plist()`, `cons()`, `fact()`, `rule()`, `dcg_rule()`, `directive()`,
   `module()`
9. Implement introspection: `variables()`, `functors()`, `is_ground()`, `term_size()`,
   `subterms()`
10. Run `test_prolog_ast.py` — all tests should pass

### Step 2: Create `clausal/tools/prolog_operators.py`

1. Define `OpEntry(precedence, specifier, name)` dataclass
2. Implement `OperatorTable` class with `define()`, `lookup_infix()`,
   `lookup_prefix()`, `lookup_postfix()`, `is_operator()`, `user_defined()`
3. Implement `OperatorTable.iso_default()` — all ISO 13211-1 Table 7 operators
4. Implement `OperatorTable.swi_default()` — ISO + SWI additions
5. Implement `OperatorTable.scryer_default()` — ISO + Scryer additions
6. Run `test_prolog_operators.py` — all tests should pass

### Step 3: Create `clausal/tools/prolog_dialect.py`

1. Define `Dialect` dataclass with fields: `name`, `operator_table`, `library_map`,
   `clpfd_module`, `tabling_directive`, `string_type`, `has_dicts`, `module_system`
2. Implement `Dialect.iso()`, `Dialect.swi()`, `Dialect.scryer()` factory methods
3. Define `BUILTIN_NAME_MAP` dict
4. Implement `resolve_name(clausal_name, dialect)` that checks the map first,
   then falls back to `pascal_to_snake()`
