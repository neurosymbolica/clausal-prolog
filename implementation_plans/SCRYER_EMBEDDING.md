# Scryer Prolog Embedding via PyO3/Maturin

## Background and Motivation

Clausal is a Prolog-style logic programming DSL embedded in Python. It has its own
solver, compiler, Trail/Var-based unification, and a rich term system. `.clausal`
files are imported as Python modules via `import_hook.py`, compiled to bytecode, and
executed by Clausal's own trampoline-based engine.

Clausal already has a **bidirectional translation pipeline** between `.clausal` syntax
and ISO Prolog (see `PROLOG_TRANSLATION.md`):

- `clausal_source_to_prolog(src, dialect=Dialect.scryer())` — `.clausal` text to `.pl` text
- `clausal_source_to_prolog_ast(src)` — `.clausal` text to `PModule` AST
- Prolog AST types: `PAtom`, `PVar`, `PNumber`, `PString`, `PCompound`, `PList`, etc.
- Dialect-aware: `Dialect.scryer()` handles `=<` for `<=`, `clpz` for `clpfd`, etc.

The existing `test_scryer_backend.py` uses Scryer as an **external subprocess**: it
writes translated Prolog to a temp file, appends `:- initialization(...)` directives,
and invokes `scryer-prolog` on PATH. This works but is slow (process startup per query)
and cannot maintain stateful sessions.

The goal of this plan is **Tier 3** of the bridge architecture: a live, in-process
Scryer Prolog engine accessible from Python, via a Rust extension built with PyO3 and
maturin.

### How Scryer's Library API Works

The Scryer Prolog Rust crate (`scryer-prolog = "0.10.0"`) exposes a clean embedding API
in `src/machine/lib_machine/`:

```rust
// Build a machine (bootstraps standard library, ~200ms)
let machine = MachineBuilder::default().build();

// Load Prolog source (simple file_load, no module system)
machine.load_module_string("facts", "parent(tom, bob).");

// Load with full module system (consult_stream)
machine.consult_module_string("user", source);

// Query — returns a lazy iterator over solutions
let query_state: QueryState<'_> = machine.run_query("parent(X, Y).");
for result in query_state {
    match result {
        Ok(LeafAnswer::True) => ...,
        Ok(LeafAnswer::False) => ...,     // no more solutions
        Ok(LeafAnswer::LeafAnswer { bindings }) => {
            // bindings: BTreeMap<String, Term>
            // e.g. {"X": Term::Atom("tom"), "Y": Term::Atom("bob")}
        },
        Ok(LeafAnswer::Exception(term)) => ...,
        Err(error_term) => ...,
    }
}
```

The `Term` enum:
```rust
pub enum Term {
    Integer(dashu::Integer),   // arbitrary precision
    Rational(dashu::Rational), // arbitrary precision
    Float(f64),
    Atom(String),              // Prolog atom
    String(String),            // char-list (double_quotes=chars)
    List(Vec<Term>),
    Compound(String, Vec<Term>),
    Var(String),               // unbound or aliased variable
}
```

**Key constraint**: `QueryState<'a>` borrows `&'a mut Machine`. You cannot store both
the machine and query state in one struct. The Rust borrow checker enforces this. All
solutions must be collected before the machine is usable again.

**Thread safety**: `Machine` uses `Rc<>` internally and is `!Send`. It must stay on one
thread for its entire lifetime.

**Tokio**: `dispatch_loop()` is synchronous when `http` feature is disabled. We must
compile scryer-prolog with `default-features = false` to avoid a
`tokio::Handle::current()` panic.

---

## Design Decisions

### How is Scryer "invoked"?

Clausal's existing pattern for engine interaction is the `Module` object. You create a
`Module`, define predicates in it, and query it via `solve(goal, module)`. The REPL
wraps this in `Solutions(query(goal, vars, module))`.

For the Scryer embedding, the pattern should be analogous but distinct: the user creates
a `Scryer` session object, loads programs into it (as `.clausal` source, `.pl` source,
or files), and queries it. The session is a Python context manager for clean resource
management:

```python
from clausal.scryer import Scryer

with Scryer() as s:
    s.consult_string("parent(tom, bob). parent(bob, ann).")
    for sol in s.query("parent(tom, X)."):
        print(sol["X"])  # "bob"
```

Or without a context manager (machine is garbage-collected):

```python
s = Scryer()
s.consult_string("parent(tom, bob).")
```

The context manager form is idiomatic Python, not `setup_call_cleanup/3` — we let
Python's `__enter__`/`__exit__` handle lifecycle. The Scryer machine is heavyweight
(~200ms to bootstrap, ~100MB memory for the standard library), so it should be
long-lived and reused across queries. The context manager makes the expected lifetime
explicit.

### Is Scryer passed around?

Yes, as a plain Python object. It is **not** a Clausal `Module` — it is a separate
engine. You interact with it directly:

```python
s = Scryer()
s.consult_file("my_program.clausal")   # translates to Prolog, loads
s.consult_file("library.pl")           # loads raw Prolog
results = s.query_all("ancestor(tom, X).")
```

This mirrors how you'd use an embedded database connection: create it, interact with it,
close it. It is not passed into `solve()` or `call()` — those are Clausal's own engine.
Scryer is a different solver.

### Term bridge

Solutions from Scryer queries are returned as plain Python dicts mapping variable name
strings to Python values. The Rust layer converts Scryer `Term` variants to Python
objects:

| Scryer `Term`         | Python type          |
|-----------------------|----------------------|
| `Integer(n)`          | `int`                |
| `Rational(r)`         | `fractions.Fraction` |
| `Float(f)`            | `float`              |
| `Atom(s)`             | `str`                |
| `String(s)`           | `str`                |
| `List(elems)`         | `list`               |
| `Compound(f, args)`   | `Compound(f, tuple(args))` |
| `Var(name)`           | `str` (the variable name as-is) |

Compound terms are converted to `clausal.terms.Compound` so they interoperate with
Clausal's term system. `Compound.args` is always a `tuple` in clausal, so the Rust
layer must convert the `Vec<Term>` to a Python tuple, not a list.

For **input**, we serialize Python values to Prolog text for use in query strings via
`clausal.scryer.to_prolog()`:

```python
from clausal.scryer import to_prolog
s.query(f"parent({to_prolog('tom')}, X).")
```

Or more commonly, queries are just string literals with Prolog syntax since we are
talking to a Prolog engine directly.

### Loading programs: `consult` vs `load` semantics

Scryer has two loading modes:
- `consult_module_string("user", src)` — full `consult_stream` processing. This
  **replaces** earlier clauses for the same predicate (standard Prolog `consult`
  semantics). Has full module system support.
- `load_module_string("facts", src)` — simpler `file_load`. Asserts clauses
  without wiping earlier definitions.

For the embedding, `load_string` (which uses `load_module_string`) is the right
default for incremental use — you can load facts in one call and rules in another
without the second call erasing the first. `consult_string` (which uses
`consult_module_string`) is for loading complete modules that should replace earlier
definitions.

The Python API exposes both so the user can choose.

### Loading .clausal files

The key integration point: `Scryer.consult_file()` detects `.clausal` files and
automatically translates them via the existing `clausal_source_to_prolog()` pipeline
before loading the Prolog text into the machine. This means any `.clausal` program can
be loaded into Scryer with no user intervention:

```python
s = Scryer()
s.consult_file("clausal/examples/graph.clausal")
results = s.query_all("reachable(1, X).")
```

### What the API is NOT

- It is not a replacement for Clausal's own solver. Clausal's engine is tightly
  integrated with Python (Var objects, Trail, PredicateMeta dispatch, Python-native
  unification). Scryer is a separate ISO Prolog engine for cases where you want ISO
  conformance, constraint solving (CLP(Z), CLP(B)), or access to Scryer's library
  ecosystem.

- It does not bridge live state between the two engines. You cannot unify a Clausal
  `Var` with a Scryer variable. They are separate worlds connected by text translation.

### Clausal-syntax Integration

The Python API (`Scryer` class, query strings) is the low-level interface.  On top
of that, we want clausal-native syntax for working with Scryer — so you don't have
to drop into Prolog strings to use the embedded engine.

There are three levels:

#### Level 1: Whole-module Scryer execution

A `.clausal` file declares that its entire contents should be loaded into Scryer
and queried there, not compiled by Clausal's native engine.  This is the primary
use case for programs that need features Scryer provides (CLP(Z), tabling, ISO
conformance).

```
-backend(scryer)
-module(queens, [Queens(N, QS)])

-import_from(clausal.logic.clpfd, [in_domain, all_different, Labeling])

Queens(N, QS) <- (
    length(QS, N),
    in_domain(QS, 1, N),
    SafeQueens(QS),
    Labeling([], QS)
)

SafeQueens([]),
SafeQueens([Q, *QS]) <- (NoAttack(Q, QS, 1), SafeQueens(QS))
NoAttack(_, [], _),
NoAttack(Q, [Q1, *QS], D) <- (
    Q != Q1 + D,
    Q != Q1 - D,
    D1 := D + 1,
    NoAttack(Q, QS, D1)
)
```

when the import hook sees `-backend(scryer)`, it changes strategy entirely:
instead of compiling to Python bytecode, it:

1. Translates the `.clausal` source to Prolog via `clausal_source_to_prolog`
   with `Dialect.scryer()`
2. Creates a `Scryer` session and loads the translated Prolog
3. For each exported predicate in `-module(name, [exports])`, generates a
   Python `PredicateMeta` class whose dispatch function converts its arguments
   to a Prolog query string, runs it through the Scryer session, and yields
   the results back as Clausal terms

This means a Scryer-backed module looks exactly like a native module to callers:

```python
from queens import Queens
from clausal import Var, Solutions

N, QS = Var(), Var()
*Queens(4, QS)   # drives Scryer under the hood, displays via Solutions
```

The exported predicates become proper PredicateMeta classes, so they work with
`call()`, `solve()`, `query()`, `Solutions`, and the `*(goal)` REPL syntax.
The Scryer session is module-scoped — one machine per imported module, created
on first import and reused.

**Implementation sketch** for the import hook:

```python
# in_ import_hook.py or a new clausal/scryer/_loader.py

def _exec_scryer_module(module, source, module_items, module_dict):
    """Load a -backend(scryer) module."""
    from clausal.scryer import Scryer
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    from clausal.tools.prolog_dialect import Dialect

    prolog = clausal_source_to_prolog(source, dialect=Dialect.scryer())

    session = Scryer()
    session.consult_string(prolog)
    module_dict["$scryer_session"] = session

    # For each exported predicate, generate a bridge class
    for export in exports:
        functor, arity, field_names = export
        _make_scryer_predicate(functor, arity, field_names, session, module_dict)
```

The bridge predicate's dispatch function:

```python
def _scryer_dispatch(session, prolog_functor, field_names, *args, trail):
    """Dispatch function for a Scryer-backed predicate."""
    from clausal.scryer import to_prolog
    from clausal.logic.variables import Var, deref, unify

    # Separate ground args from Var args
    query_args = []
    var_positions = {}
    for i, (name, arg) in enumerate(zip(field_names, args)):
        arg = deref(arg)
        if isinstance(arg, Var):
            # Use a Prolog variable name
            pvar = name.upper() if name[0].islower() else name
            query_args.append(pvar)
            var_positions[pvar] = (i, arg)
        else:
            query_args.append(to_prolog(arg))

    query_str = f"{prolog_functor}({', '.join(query_args)})."

    for sol in session.query(query_str):
        # Unify each Prolog result back into the Clausal Var
        mark = trail.mark()
        ok = True
        for pvar, (pos, clausal_var) in var_positions.items():
            if pvar in sol:
                if not unify(clausal_var, sol[pvar], trail):
                    ok = False
                    break
        if ok:
            yield trail  # solution found
        trail.undo(mark)
```

This bridges the two worlds: Clausal's Trail/Var unification on the Python side,
Scryer's backtracking on the Rust side.  Ground arguments are serialized into the
query; variable arguments become Prolog variables and are unified with the results.

#### Level 2: Per-predicate delegation

A file using the native Clausal engine can delegate specific predicates to Scryer:

```
-import_from(clausal.logic.clpfd, [in_domain, all_different, Labeling])

# These run on Clausal's native engine
Edge(1, 2), Edge(2, 3), Edge(3, 4),

# This predicate should run on Scryer (e.g. for CLP(Z))
-scryer(ConstrainedPath/3)
ConstrainedPath(X, Y, COST) <- (
    in_domain(COST, 0, 100),
    Path(X, Y, ROUTE),
    length(ROUTE, COST)
)
```

This is more complex and can be deferred to a later phase.  The `-backend(scryer)`
whole-module approach covers the primary use case.

#### Level 3: REPL/IPython Scryer queries

The `*(goal)` syntax in IPython currently drives the native engine.  We could add
a Scryer-aware variant, perhaps:

```python
# in_ IPython with clausal loaded:
s = Scryer()
s.load_string("parent(tom, bob). parent(bob, ann).")

# Query using clausal syntax (would need a helper or special form)
*s.Queens(4, QS)     # hypothetical — bridge predicate
```

This falls out naturally from Level 1: once a Scryer-backed module is imported,
its predicates work with `*(goal)` exactly like native predicates.

#### Phase 5 scope

Level 1 (`-backend(scryer)`) is the planned integration.  Levels 2 and 3 are
natural extensions that fall out from it, but are not in scope for the initial
implementation.  The priority order is:

1. Phase 1–4: Raw embedding + Python API + tests (the existing plan)
2. Phase 5: `-backend(scryer)` directive in the import hook
3. Future: per-predicate delegation, REPL integration

---

## Phased Implementation Plan

### Phase 1: Rust Extension Crate

**Goal**: Build a minimal PyO3 extension that creates a Scryer machine and runs queries.

#### 1.1 Create the crate skeleton

Create `clausal-scryer/` inside the project root:

```
clausal-scryerembedding/
    clausal-scryer/
        Cargo.toml
        src/
            lib.rs
```

**IMPORTANT — first thing to verify**: The Cargo.toml uses a path dependency to
scryer-prolog. The path `../../scryer-prolog` resolves relative to the Cargo.toml file,
i.e. from `clausal-scryerembedding/clausal-scryer/` up two levels to `/workspace/`.
Verify this exists before writing any Rust code.

`Cargo.toml`:
```toml
[package]
name = "clausal-scryer"
version = "0.1.0"
edition = "2021"

[lib]
name = "_scryer_ext"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
scryer-prolog = { path = "../../scryer-prolog", default-features = false }
```

Key: `default-features = false` disables `ffi`, `repl`, `hostname`, `tls`, `http`,
`crypto-full`. This avoids the tokio Handle panic and reduces binary size and compile
time significantly.

#### 1.2 Implement `lib.rs`

**The ownership-transfer pattern for lazy iteration**

The central design problem: `QueryState<'a>` borrows `&'a mut Machine`. Python
iterators are objects with arbitrary lifetime. We cannot return a `QueryState` to
Python directly because Rust's borrow checker won't let us store both the Machine
and a reference into it in the same PyO3 object.

Scryer's own WASM binding (`src/wasm.rs`) solves this exact problem using
`ouroboros::self_referencing` to create a self-referential struct that *owns* the
Machine and borrows it for the QueryState. We use the same pattern:

1. `RawScryerMachine` stores `Option<Machine>` (not `Machine` directly)
2. when `query()` is called, the Machine is **taken** out of the Option
3. The Machine is moved into a `QueryIterator` which uses `ouroboros` to
   self-referentially borrow it for the `QueryState<'this>`
4. While a `QueryIterator` exists, the `RawScryerMachine` is "empty" — any
   attempt to use it (load, query) returns an error
5. when the `QueryIterator` is dropped (iterator exhausted, Python GC, or
   explicit `close()`), the Machine is **returned** to the `RawScryerMachine`

This gives genuine lazy iteration: each call to `__next__` on the Python side
calls `QueryState::next()` on the Rust side, which calls `dispatch_loop()` to
resume backtracking for one more solution. Dropping a partially-consumed iterator
is safe — `QueryState::drop` calls `trust_me()` to clean up Scryer's internal
state.

**Cargo.toml** needs the `ouroboros` dependency:

```toml
[package]
name = "clausal-scryer"
version = "0.1.0"
edition = "2021"

[lib]
name = "_scryer_ext"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
scryer-prolog = { path = "../../scryer-prolog", default-features = false }
ouroboros = "0.18"
```

(Note: scryer-prolog already uses ouroboros 0.18 for its WASM binding, so this
is a known-compatible version and doesn't add a new transitive dependency.)

**The Rust code**:

```rust
use std::cell::RefCell;
use std::rc::Rc;

use ouroboros::self_referencing;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use scryer_prolog::Machine;
use scryer_prolog::machine::config::MachineBuilder;
use scryer_prolog::machine::lib_machine::{LeafAnswer, QueryState, Term as ScryerTerm};

// Custom exception for Prolog errors/exceptions
pyo3::create_exception!(_scryer_ext, ScryerError, pyo3::exceptions::PyException);

// ── Machine storage ──────────────────────────────────────────────
//
// The Machine lives in an Rc<RefCell<Option<Machine>>>.  Both the
// RawScryerMachine and any active QueryIterator hold an Rc clone.
// when a query starts, the Machine is *taken* out of the Option.
// when the query ends, it is put back.

type MachineSlot = Rc<RefCell<Option<Machine>>>;

#[pyclass(unsendable)]
struct RawScryerMachine {
    slot: MachineSlot,
}

impl RawScryerMachine {
    /// Borrow the machine, returning a clear error if a query is active.
    fn with_machine<R>(&mut self, f: impl FnOnce(&mut Machine) -> R) -> PyResult<R> {
        let mut guard = self.slot.borrow_mut();
        match guard.as_mut() {
            Some(m) => Ok(f(m)),
            None => Err(PyErr::new::<ScryerError, _>(
                "Machine is busy — a query iterator is still active. \
                 Exhaust, drop, or close() the iterator first."
            )),
        }
    }
}

#[pymethods]
impl RawScryerMachine {
    #[new]
    fn new() -> PyResult<Self> {
        let mut machine = MachineBuilder::default().build();
        // Set double_quotes to atom so "hello" is an atom, not a char list.
        machine.consult_module_string(
            "user",
            ":- set_prolog_flag(double_quotes, atom)."
        );
        Ok(RawScryerMachine {
            slot: Rc::new(RefCell::new(Some(machine))),
        })
    }

    /// Load via consult_stream (full module system; replaces earlier clauses).
    fn consult_module_string(&mut self, module_name: &str, program: &str) -> PyResult<()> {
        self.with_machine(|m| m.consult_module_string(module_name, program))
    }

    /// Load via file_load (no module processing; accumulates clauses).
    fn load_module_string(&mut self, module_name: &str, program: &str) -> PyResult<()> {
        self.with_machine(|m| m.load_module_string(module_name, program))
    }

    /// Start a lazy query.  Returns a QueryIterator (Python iterator protocol).
    /// While the iterator is alive, the machine cannot be used for anything else.
    fn query(&mut self, query: String) -> PyResult<QueryIterator> {
        // take the machine out of the slot.
        let machine = {
            let mut guard = self.slot.borrow_mut();
            guard.take().ok_or_else(|| PyErr::new::<ScryerError, _>(
                "Machine is busy — a query iterator is still active."
            ))?
        };

        // Build the self-referencing struct: owns Machine, borrows it for QueryState.
        let inner = QueryIteratorInnerBuilder {
            machine,
            query_state_builder: |m: &mut Machine| m.run_query(query),
        }
        .build();

        Ok(QueryIterator {
            inner: Some(inner),
            slot: Rc::clone(&self.slot),
        })
    }
}

// ── Self-referencing query state ─────────────────────────────────

#[self_referencing]
struct QueryIteratorInner {
    machine: Machine,
    #[covariant]
    #[borrows(mut machine)]
    query_state: QueryState<'this>,
}

#[pyclass(unsendable)]
struct QueryIterator {
    inner: Option<QueryIteratorInner>,
    slot: MachineSlot,    // return Machine here when done
}

impl QueryIterator {
    /// Return the Machine to the RawScryerMachine.
    fn return_machine(&mut self) {
        if let Some(inner) = self.inner.take() {
            let machine = inner.into_heads().machine;
            *self.slot.borrow_mut() = Some(machine);
        }
    }
}

impl drop for QueryIterator {
    fn drop(&mut self) {
        self.return_machine();
    }
}

#[pymethods]
impl QueryIterator {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<PyObject>> {
        let inner = match &mut self.inner {
            Some(inner) => inner,
            None => return Ok(None),  // already exhausted/closed
        };

        let mut result: Option<PyResult<Option<PyObject>>> = None;

        inner.with_query_state_mut(|qs| {
            result = Some(match qs.next() {
                Some(Ok(LeafAnswer::True)) => {
                    Ok(Some(PyDict::new(py).into()))
                }
                Some(Ok(LeafAnswer::False)) => {
                    Ok(None)  // will trigger return_machine below
                }
                Some(Ok(LeafAnswer::LeafAnswer { bindings })) => {
                    let dict = PyDict::new(py);
                    for (name, term) in &bindings {
                        match scryer_term_to_py(py, term) {
                            Ok(val) => { let _ = dict.set_item(name, val); }
                            Err(e) => return result = Some(Err(e)),
                        }
                    }
                    Ok(Some(dict.into()))
                }
                Some(Ok(LeafAnswer::Exception(term))) => {
                    Err(ScryerError::new_err(format!("{:?}", term)))
                }
                Some(Err(term)) => {
                    Err(ScryerError::new_err(format!("{:?}", term)))
                }
                None => Ok(None),
            });
        });

        let result = result.unwrap();

        // If the query is done (None or error), return the machine.
        match &result {
            Ok(None) | Err(_) => self.return_machine(),
            _ => {}
        }

        result
    }

    /// Explicitly close the iterator and return the machine.
    fn close(&mut self) {
        self.return_machine();
    }

    /// Remaining solution count is unknown — not sized.
    fn __length_hint__(&self) -> usize { 0 }
}

// ── Term conversion ──────────────────────────────────────────────

fn scryer_term_to_py(py: Python<'_>, term: &ScryerTerm) -> PyResult<PyObject> {
    match term {
        ScryerTerm::Integer(i) => {
            // For values that fit in i64, convert directly.
            // For bigger values, go through string → Python int().
            match i64::try_from(i.clone()) {
                Ok(n) => Ok(n.into_pyobject(py)?.into()),
                Err(_) => {
                    let s = i.to_string();
                    let builtins = py.import("builtins")?;
                    Ok(builtins.call_method1("int", (s,))?.into())
                }
            }
        }
        ScryerTerm::Rational(r) => {
            let frac_cls = py.import("fractions")?.getattr("Fraction")?;
            Ok(frac_cls.call1((
                r.numerator().to_string(),
                r.denominator().to_string(),
            ))?.into())
        }
        ScryerTerm::Float(f) => Ok(f.into_pyobject(py)?.into()),
        ScryerTerm::Atom(s) => Ok(s.into_pyobject(py)?.into()),
        ScryerTerm::String(s) => Ok(s.into_pyobject(py)?.into()),
        ScryerTerm::List(elems) => {
            let items: Vec<PyObject> = elems.iter()
                .map(|t| scryer_term_to_py(py, t))
                .collect::<PyResult<_>>()?;
            Ok(PyList::new(py, &items)?.into())
        }
        ScryerTerm::Compound(functor, args) => {
            // Partial lists show up as Compound(".", [head, tail]).
            // Convert to clausal.terms.Compound in all cases.
            let compound_cls = py.import("clausal.terms")?.getattr("Compound")?;
            let py_args: Vec<PyObject> = args.iter()
                .map(|t| scryer_term_to_py(py, t))
                .collect::<PyResult<_>>()?;
            // Compound.__init__ takes (functor, args) where args is a tuple.
            let args_tuple = PyTuple::new(py, &py_args)?;
            Ok(compound_cls.call1((functor, args_tuple))?.into())
        }
        ScryerTerm::Var(name) => {
            // Unbound/aliased variable in result — return the name as a string.
            Ok(name.into_pyobject(py)?.into())
        }
    }
}

// ── Module definition ────────────────────────────────────────────

#[pymodule]
fn _scryer_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RawScryerMachine>()?;
    m.add_class::<QueryIterator>()?;
    m.add("ScryerError", m.py().get_type::<ScryerError>())?;
    Ok(())
}
```

#### 1.3 Build and verify

```bash
# Verify scryer-prolog is where we expect
ls /workspace/scryer-prolog/Cargo.toml

# Build
cd clausal-scryer
maturin develop --release
cd ..

# Smoke test
python -c "import _scryer_ext; m = _scryer_ext.RawScryerMachine(); print('ok')"
```

`--release` is important because scryer's debug build is extremely slow (~10x).

**Tests at this level** — `tests/test_scryer_raw.py`:

```python
import pytest
try:
    import _scryer_ext
    HAS_EXT = True
except ImportError:
    HAS_EXT = False

needs_ext = pytest.mark.skipif(not HAS_EXT, reason="scryer extension not built")

@needs_ext
def test_raw_machine_creates():
    m = _scryer_ext.RawScryerMachine()
    assert m is not None

@needs_ext
def test_raw_query_iteration():
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "parent(tom, bob).")
    results = list(m.query("parent(tom, X)."))
    assert len(results) == 1
    assert results[0]["X"] == "bob"

@needs_ext
def test_raw_arithmetic():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X is 2 + 3.")))
    assert sol["X"] == 5

@needs_ext
def test_raw_no_solutions():
    m = _scryer_ext.RawScryerMachine()
    results = list(m.query("fail."))
    assert results == []

@needs_ext
def test_raw_multiple_solutions():
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "color(red). color(green). color(blue).")
    results = list(m.query("color(X)."))
    assert [r["X"] for r in results] == ["red", "green", "blue"]

@needs_ext
def test_raw_lazy_iteration():
    """Iterator is truly lazy — can break after first result."""
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "n(1). n(2). n(3).")
    it = m.query("n(X).")
    first = next(it)
    assert first["X"] == 1
    # drop the iterator without consuming the rest
    del it
    # Machine should be available again
    second = list(m.query("n(X)."))
    assert len(second) == 3

@needs_ext
def test_raw_machine_busy_while_iterating():
    """Cannot start a second query while one is active."""
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "n(1). n(2).")
    it = m.query("n(X).")
    next(it)  # start iterating
    with pytest.raises(_scryer_ext.ScryerError, match="busy"):
        m.query("n(X).")
    # close the iterator, machine should be free
    it.close()
    results = list(m.query("n(X)."))
    assert len(results) == 2

@needs_ext
def test_raw_list():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X = [1, 2, 3].")))
    assert sol["X"] == [1, 2, 3]

@needs_ext
def test_raw_compound():
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "data(point(1, 2)).")
    sol = next(iter(m.query("data(X).")))
    from clausal.terms import Compound
    assert sol["X"] == Compound("point", (1, 2))

@needs_ext
def test_raw_large_integer():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X is 2 ^ 100.")))
    assert sol["X"] == 2**100

@needs_ext
def test_raw_exception():
    """Prolog errors become Python ScryerError exceptions."""
    m = _scryer_ext.RawScryerMachine()
    with pytest.raises(_scryer_ext.ScryerError):
        next(iter(m.query("X is foo.")))
```

---

### Phase 2: Python API Layer (`clausal/scryer/`)

**Goal**: A Pythonic wrapper around the raw extension that integrates with Clausal's
translation pipeline and provides idiomatic resource management.

#### 2.1 Package structure

```
clausal/scryer/
    __init__.py      # public API, availability check, re-exports
    _scryer.py       # Scryer class
    _bridge.py       # to_prolog() helper for embedding Python values in queries
```

#### 2.2 `clausal/scryer/__init__.py`

```python
"""clausal.scryer — embedded Scryer Prolog via PyO3.

Usage::

    from clausal.scryer import Scryer

    with Scryer() as s:
        s.consult_string("parent(tom, bob). parent(bob, ann).")
        for sol in s.query("parent(tom, X)."):
            print(sol["X"])  # "bob", "ann"

To build the Scryer embedding::

    cd clausal-scryer
    maturin develop --release

Requires: Rust toolchain, scryer-prolog source at ../../scryer-prolog
"""

try:
    import _scryer_ext
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


def _not_available(*args, **kwargs):
    raise ImportError(
        "clausal.scryer requires the _scryer_ext extension.\n"
        "Build it with: cd clausal-scryer && maturin develop --release"
    )


if AVAILABLE:
    from clausal.scryer._scryer import Scryer
    from clausal.scryer._bridge import to_prolog
else:
    Scryer = _not_available  # callable that raises ImportError with instructions
    to_prolog = _not_available

__all__ = ["Scryer", "AVAILABLE", "to_prolog"]
```

This way `from clausal.scryer import Scryer` always works — calling `Scryer()` when
the extension isn't built gives a clear `ImportError` with build instructions instead
of a confusing `cannot import name` traceback.

#### 2.3 `clausal/scryer/_scryer.py` — The `Scryer` class

```python
"""The Scryer session class."""
from __future__ import annotations

import _scryer_ext


class Scryer:
    """Embedded Scryer Prolog session.

    A heavyweight object (~200ms to create). Create once, reuse across
    many queries. Supports context manager protocol for explicit lifecycle.

    The primary query interface is iteration::

        with Scryer() as s:
            s.load_string("parent(tom, bob). parent(bob, ann).")
            for sol in s.query("parent(X, Y)."):
                print(sol["X"], "->", sol["Y"])

    While iterating, the machine is exclusively held by the query.
    You can break out of the loop early — the iterator cleans up on
    drop.  But you cannot start a second query or load more code
    until the current iterator is exhausted, dropped, or closed.

    Examples
    --------
    >>> with Scryer() as s:
    ...     s.load_string("parent(tom, bob).")
    ...     s.query_one("parent(tom, X).")
    {'X': 'bob'}

    >>> s = Scryer()
    >>> s.consult_file("clausal/examples/graph.clausal")
    >>> s.query_all("reachable(1, X).")
    [{'X': 2}, {'X': 3}, {'X': 4}, {'X': 5}, {'X': 6}]
    """

    def __init__(self):
        self._machine = _scryer_ext.RawScryerMachine()

    def _check_open(self):
        if self._machine is None:
            raise RuntimeError("This Scryer session has been closed")

    def close(self):
        """Release the Scryer machine. Idempotent."""
        self._machine = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        self.close()

    # ── Loading programs ──────────────────────────────────────────

    def consult_string(self, source: str, module: str = "user") -> None:
        """Load Prolog source via consult (full module system).

        Warning: consult *replaces* earlier clauses for the same predicate
        within the same module. If you want to accumulate facts across
        multiple calls, use load_string() instead.
        """
        self._check_open()
        self._machine.consult_module_string(module, source)

    def load_string(self, source: str, module: str = "user") -> None:
        """Load Prolog source via file_load (accumulates clauses).

        Unlike consult_string, this does not replace earlier definitions.
        Use this for incremental loading of facts and rules.
        """
        self._check_open()
        self._machine.load_module_string(module, source)

    def consult_file(self, path: str, module: str = "user") -> None:
        """Load a file into the machine.

        If the path ends with .clausal, the source is automatically
        translated to Prolog via clausal_source_to_prolog with Scryer
        dialect before loading.
        """
        self._check_open()
        from pathlib import Path
        p = Path(path)
        source = p.read_text(encoding="utf-8")
        if p.suffix == ".clausal":
            from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
            from clausal.tools.prolog_dialect import Dialect
            source = clausal_source_to_prolog(source, dialect=Dialect.scryer())
        self.consult_string(source, module)

    def consult_clausal(self, source: str, module: str = "user") -> None:
        """Translate .clausal source to Prolog and consult it."""
        self._check_open()
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        from clausal.tools.prolog_dialect import Dialect
        prolog = clausal_source_to_prolog(source, dialect=Dialect.scryer())
        self.consult_string(prolog, module)

    # ── Querying ──────────────────────────────────────────────────

    def query(self, goal: str):
        """Run a Prolog query. Returns an iterator over solution dicts.

        Each solution is a dict mapping variable names (str) to Python
        values (int, float, str, list, Compound).

        Iteration is lazy — each call to next() resumes Prolog
        backtracking for one more solution.  Breaking out of the loop
        early is fine; the iterator cleans up on drop.

        While the iterator is alive, the machine is locked — you cannot
        load code or start another query until this one finishes.

        Parameters
        ----------
        goal : str
            Prolog query text, including the trailing period.
            E.g. "parent(tom, X)."
        """
        self._check_open()
        return self._machine.query(goal)

    def query_all(self, goal: str) -> list[dict]:
        """Run a query and collect all solutions into a list of dicts."""
        return list(self.query(goal))

    def query_one(self, goal: str) -> dict | None:
        """Return the first solution, or None if the query fails.

        Only evaluates one solution — does not backtrack further.
        """
        self._check_open()
        it = self._machine.query(goal)
        try:
            return next(it)
        except StopIteration:
            return None
        # `it` is dropped here → machine returned immediately.

    def query_bool(self, goal: str) -> bool:
        """Return True if the query succeeds at least once.

        Only evaluates one solution — does not backtrack further.
        """
        return self.query_one(goal) is not None
```

The key design: **`query()` returns a lazy iterator** — a `QueryIterator` from the
Rust layer that implements Python's `__iter__`/`__next__` protocol. Each call to
`next()` calls `dispatch_loop()` on the Scryer side to produce one more solution.
`query_one` takes one result and drops the iterator immediately. `query_all`
collects via `list()`.

While a `QueryIterator` is alive, the Machine is "on loan" to it. Attempts to
load code or start another query will raise `ScryerError` with a clear message.
The iterator can be closed explicitly via its `.close()` method, or it returns
the machine automatically when exhausted or garbage-collected.

#### 2.4 `clausal/scryer/_bridge.py` — Python-to-Prolog text helpers

```python
"""Helpers for embedding Python values into Prolog query strings.

Usage::

    from clausal.scryer import Scryer, to_prolog
    with Scryer() as s:
        s.load_string("likes(alice, X) :- friend(alice, X).")
        s.query(f"likes({to_prolog('alice')}, X).")
"""

from clausal.terms import Compound


def to_prolog(value) -> str:
    """Convert a Python value to its Prolog text representation.

    Useful for building queries programmatically::

        s.query(f"foo({to_prolog(my_list)}, X).")
    """
    if value is None:
        return "[]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, list):
        return "[" + ", ".join(to_prolog(e) for e in value) + "]"
    if isinstance(value, Compound):
        args = ", ".join(to_prolog(a) for a in value.args)
        return f"{value.functor}({args})"
    raise TypeError(f"Cannot convert {type(value).__name__} to Prolog text")
```

---

### Phase 3: Integration Tests

**Goal**: Tests that exercise the full pipeline: `.clausal` source → translation → Scryer
machine → query → Python results.

File: `tests/test_scryer_embedding.py`

```python
"""Test the embedded Scryer Prolog engine.

These tests verify the full pipeline: .clausal source is translated to Prolog
by the existing clausal_to_prolog machinery, loaded into an in-process Scryer
machine, queried, and results converted back to Python values.

Requires the _scryer_ext extension to be built (maturin develop --release).
"""
import textwrap
from pathlib import Path
import pytest

from clausal.scryer import AVAILABLE

needs_scryer = pytest.mark.skipif(not AVAILABLE, reason=(
    "scryer extension not built; run: cd clausal-scryer && maturin develop --release"
))


@needs_scryer
class TestScryerBasics:
    """Core query functionality."""

    def test_true(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert s.query_bool("true.")

    def test_fail(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert not s.query_bool("fail.")
            assert s.query_one("fail.") is None

    def test_fact_and_query(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("parent(tom, bob).")
            assert s.query_one("parent(tom, X).") == {"X": "bob"}

    def test_multiple_solutions(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("color(red). color(green). color(blue).")
            results = s.query_all("color(X).")
            assert [r["X"] for r in results] == ["red", "green", "blue"]

    def test_arithmetic(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert s.query_one("X is 2 + 3.") == {"X": 5}
            assert s.query_one("X is 10 mod 3.") == {"X": 1}

    def test_list_unification(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X = [1, 2, 3].")
            assert sol["X"] == [1, 2, 3]

    def test_compound_term(self):
        from clausal.scryer import Scryer
        from clausal.terms import Compound
        with Scryer() as s:
            s.load_string("data(point(1, 2)).")
            sol = s.query_one("data(X).")
            assert sol["X"] == Compound("point", (1, 2))

    def test_no_bindings_goal(self):
        """A goal that succeeds with no variables returns empty dict."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert s.query_one("true.") == {}

    def test_iterator_protocol(self):
        """query() returns a lazy iterator, not a list."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("n(1). n(2). n(3).")
            it = s.query("n(X).")
            assert next(it)["X"] == 1
            assert next(it)["X"] == 2
            assert next(it)["X"] == 3
            with pytest.raises(StopIteration):
                next(it)

    def test_early_break(self):
        """Can break out of iteration early — machine is released."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("n(1). n(2). n(3). n(4). n(5).")
            for sol in s.query("n(X)."):
                if sol["X"] == 3:
                    break
            # Machine should be usable again after the for loop
            assert s.query_one("n(1).") == {}

    def test_machine_busy_during_iteration(self):
        """Cannot load or query while an iterator is active."""
        from clausal.scryer import Scryer
        import _scryer_ext
        with Scryer() as s:
            s.load_string("n(1). n(2).")
            it = s.query("n(X).")
            next(it)  # start iterating
            with pytest.raises(_scryer_ext.ScryerError, match="busy"):
                s.load_string("n(99).")
            with pytest.raises(_scryer_ext.ScryerError, match="busy"):
                s.query("true.")
            # Closing the iterator frees the machine
            it.close()
            assert s.query_bool("n(1).")


@needs_scryer
class TestClausalTranslation:
    """Loading .clausal source through the translation pipeline."""

    def test_consult_clausal_facts(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal("Foo(1, 2),\nFoo(3, 4),")
            results = s.query_all("foo(X, Y).")
            assert len(results) == 2

    def test_consult_clausal_rules(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal(textwrap.dedent("""\
                Edge(1, 2),
                Edge(2, 3),
                Edge(3, 4),
                Reach(X, Y) <- Edge(X, Y)
                Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
            """))
            assert s.query_bool("reach(1, 4).")
            results = s.query_all("reach(1, X).")
            xs = sorted(r["X"] for r in results)
            assert xs == [2, 3, 4]

    def test_consult_clausal_arithmetic(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal("Double(X, Y) <- (Y := X * 2)")
            assert s.query_one("double(5, Y).") == {"Y": 10}

    def test_consult_clausal_list_patterns(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal(textwrap.dedent("""\
                MyAppend([], L, L),
                MyAppend([H, *T], L, [H, *R]) <- MyAppend(T, L, R)
            """))
            sol = s.query_one("my_append([1,2], [3,4], R).")
            assert sol["R"] == [1, 2, 3, 4]

    def test_consult_file_clausal(self, tmp_path):
        """consult_file auto-detects .clausal extension."""
        f = tmp_path / "facts.clausal"
        f.write_text("Color(red),\nColor(blue),\n")
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_file(str(f))
            results = s.query_all("color(X).")
            assert len(results) == 2

    def test_consult_file_prolog(self, tmp_path):
        """consult_file loads .pl files as raw Prolog."""
        f = tmp_path / "facts.pl"
        f.write_text("animal(cat). animal(dog).\n")
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_file(str(f))
            results = s.query_all("animal(X).")
            assert len(results) == 2


@needs_scryer
class TestScryerExamples:
    """Load actual .clausal example files from the repo."""

    EXAMPLES = Path(__file__).parent.parent / "clausal" / "examples"

    def test_fibonacci(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_file(str(self.EXAMPLES / "fibonacci.clausal"))
            sol = s.query_one("fib(10, R).")
            assert sol is not None
            assert sol["R"] == 55

    def test_graph_reachable(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_file(str(self.EXAMPLES / "graph.clausal"))
            assert s.query_bool("reachable(1, 6).")
            assert not s.query_bool("reachable(5, 1).")


@needs_scryer
class TestScryerSession:
    """Verify session-like behavior: state persists across queries."""

    def test_incremental_load(self):
        """load_string accumulates clauses."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("likes(alice, bob).")
            assert s.query_bool("likes(alice, bob).")
            s.load_string("likes(bob, carol).")
            assert s.query_bool("likes(bob, carol).")
            # Earlier facts still present
            assert s.query_bool("likes(alice, bob).")

    def test_multiple_queries_same_session(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("num(1). num(2). num(3).")
            assert len(s.query_all("num(X).")) == 3
            assert s.query_one("num(2).") == {}  # no bindings (ground query)
            assert not s.query_bool("num(99).")

    def test_context_manager_cleanup(self):
        """After exiting context, machine is released."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("foo(1).")
            assert s.query_bool("foo(1).")
        assert s._machine is None

    def test_use_after_close_raises(self):
        """Using a closed session gives a clear error."""
        from clausal.scryer import Scryer
        s = Scryer()
        s.close()
        with pytest.raises(RuntimeError, match="closed"):
            s.query_one("true.")


@needs_scryer
class TestScryerEdgeCases:
    """Edge cases: empty results, exceptions, large integers."""

    def test_large_integer(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X is 2 ^ 100.")
            assert sol["X"] == 2**100

    def test_float_result(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X is 1.0 + 2.5.")
            assert abs(sol["X"] - 3.5) < 1e-10

    def test_nested_list(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X = [[1, 2], [3, 4]].")
            assert sol["X"] == [[1, 2], [3, 4]]

    def test_empty_list(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X = [].")
            assert sol["X"] == []

    def test_prolog_error_raises(self):
        """Prolog errors become Python ScryerError exceptions."""
        from clausal.scryer import Scryer
        import _scryer_ext
        with Scryer() as s:
            with pytest.raises(_scryer_ext.ScryerError):
                s.query("X is foo.")
```

---

### Phase 4: Build System Integration

**Goal**: Make the extension easy to build and optional — the rest of clausal works
without it.

#### 4.1 Maturin configuration

Add a `pyproject.toml` inside `clausal-scryer/` for maturin:

```toml
[build-system]
requires = ["maturin>=1.7,<2.0"]
build-backend = "maturin"

[project]
name = "clausal-scryer"
version = "0.1.0"
requires-python = ">=3.13"

[tool.maturin]
python-source = ".."
module-name = "clausal._scryer_ext"
```

Note `module-name = "clausal._scryer_ext"` — this tells maturin to place the `.so`
inside the existing `clausal/` package directory (as `clausal/_scryer_ext.so`), so
`import _scryer_ext` works when clausal is on the path. Alternatively, use just
`_scryer_ext` if maturin has trouble with dotted module names and the virtualenv
site-packages approach works.

The main `clausal-scryerembedding/pyproject.toml` is **not modified** for the build
system — the C extensions (`_variables.c`, `_trampoline.c`) continue to build via
setuptools. The scryer extension is a separate optional build.

#### 4.2 Optional dependency marker

Add to the main `pyproject.toml`:

```toml
[project.optional-dependencies]
scryer = []  # built separately via maturin; marker only
```

---

### Phase 5: `-backend(scryer)` Directive (Clausal-syntax Integration)

**Goal**: A `.clausal` file can declare `-backend(scryer)` to have its predicates
compiled and executed by the embedded Scryer engine, while looking exactly like a
native module to importers.

This phase depends on Phases 1–4 being complete and tested.

#### 5.1 New directive: `-backend(scryer)`

Add to `_handle_directive` in `clausal/templating/term_rewriting.py`:

```python
if name == "backend":
    if args and getattr(args[0], 'id', None) == "scryer":
        transformer._module_items.append(
            DirectiveItem(name="backend", specs=[("scryer",)])
        )
        return expr_stmt  # remove the directive from output; handled at load time
    raise SyntaxError(f"Unknown backend: {args}")
```

#### 5.2 Modify the import hook

in_ `import_hook.py`, `PredicateLoader._exec_module_v2` currently calls
`compile_module()` to compile predicates into Python bytecode.  when
`-backend(scryer)` is present in the `module_items`, it should branch:

```python
def _exec_module_v2(self, module, module_dict, filename):
    # ... existing code to parse module_items ...

    if _has_backend(module_items, "scryer"):
        self._exec_module_scryer(module, module_dict, filename, module_items)
        return

    # ... existing native compilation path ...
```

#### 5.3 `_exec_module_scryer` implementation

```python
def _exec_module_scryer(self, module, module_dict, filename, module_items):
    """Load a -backend(scryer) module.

    Instead of compiling predicates to Python bytecode, translates the
    entire .clausal source to Prolog, loads it into an embedded Scryer
    session, and generates bridge PredicateMeta classes for each export.
    """
    from clausal.scryer import Scryer, AVAILABLE
    if not AVAILABLE:
        raise ImportError(
            f"Module {module.__name__} requires -backend(scryer) but the "
            "scryer extension is not built. Run: cd clausal-scryer && maturin develop --release"
        )
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    from clausal.tools.prolog_dialect import Dialect

    # Read the original .clausal source and translate to Prolog
    source = self.get_data(self._path).decode("utf-8")
    prolog = clausal_source_to_prolog(source, dialect=Dialect.scryer())

    # Create and populate the Scryer session
    session = Scryer()
    session.consult_string(prolog)

    # Store session on the module for lifetime management
    module.__scryer_session__ = session

    # Extract exports from module_items
    exports = _extract_exports(module_items)

    # Generate bridge PredicateMeta classes
    logic_module = LogicModule(module.__name__, module_dict=module_dict)
    for functor, arity, field_names in exports:
        bridge_cls = _make_scryer_bridge_predicate(
            functor, arity, field_names, session, module_dict
        )
        module_dict[functor] = bridge_cls

    module_dict["$module"] = logic_module
    module.__clausal_module__ = logic_module
```

#### 5.4 Bridge predicate generation

The bridge predicate is a `PredicateMeta` class whose `_dispatch_fn` translates
arguments to a Prolog query, runs it on Scryer, and yields solutions by unifying
the results back into Clausal Vars:

```python
from clausal.tools.prolog_dialect import pascal_to_snake

def _make_scryer_bridge_predicate(functor, arity, field_names, session, module_dict):
    """Create a PredicateMeta class that delegates to Scryer."""
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.variables import Var, Trail, deref, unify
    from clausal.scryer._bridge import to_prolog

    prolog_functor = pascal_to_snake(functor)

    def dispatch(*args_and_trail):
        trail = args_and_trail[-1]
        args = args_and_trail[:-1]

        # Build the query string: ground args become Prolog values,
        # Var args become Prolog variables
        query_parts = []
        var_map = {}  # Prolog var name → (position, Clausal Var)
        for i, (name, arg) in enumerate(zip(field_names, args)):
            arg = deref(arg)
            if isinstance(arg, Var):
                pvar = name.upper()
                # Ensure uniqueness if field_names collide when uppercased
                while pvar in var_map:
                    pvar = pvar + "_"
                query_parts.append(pvar)
                var_map[pvar] = (i, arg)
            else:
                query_parts.append(to_prolog(arg))

        query = f"{prolog_functor}({', '.join(query_parts)})."

        for sol in session.query(query):
            mark = trail.mark()
            ok = True
            for pvar, (pos, clausal_var) in var_map.items():
                if pvar in sol:
                    if not unify(clausal_var, sol[pvar], trail):
                        ok = False
                        break
            if ok:
                yield None, None  # trampoline: (None, None) = "solution found"
                # On next iteration, trail is undone to try next Scryer solution
            trail.undo(mark)

    # Build the PredicateMeta class
    cls = PredicateMeta(functor, (), {
        '_fields': tuple(field_names),
        '_dispatch_fn': dispatch,
        '_clauses': [],
        '_signature': tuple(field_names),
    })
    return cls
```

Note: the `yield None, None` trampoline protocol needs to match how Clausal's
`_drive_trampoline` expects solutions.  The exact yield protocol depends on
whether the bridge predicate is compiled as trampoline-mode or shallow-mode.
The simplest approach is to make it a direct generator that `_drive_trampoline`
can drive, yielding `trail` per solution — study `_drive_trampoline` in
`clausal/logic/solve.py` to match the protocol exactly.

#### 5.5 Example `.clausal` file

```
-backend(scryer)
-module(clpz_queens, [Queens(N, QS)])

-import_from(clausal.logic.clpfd, [in_domain, all_different, Labeling])

Queens(N, QS) <- (
    length(QS, N),
    Maplist(in_domain(1, N), QS),
    SafeQueens(QS),
    Labeling([], QS)
)

SafeQueens([]),
SafeQueens([Q, *QS]) <- (NoAttack(Q, QS, 1), SafeQueens(QS))

NoAttack(_, [], _),
NoAttack(Q, [Q1, *QS], D) <- (
    Q != Q1 + D,
    Q != Q1 - D,
    D1 := D + 1,
    NoAttack(Q, QS, D1)
)
```

Used from Python or another `.clausal` module:

```python
from clpz_queens import Queens
from clausal import Var, Solutions

QS = Var()
*Queens(8, QS)    # drives Scryer under the hood, Solutions displays results
```

Or from Python:

```python
from clpz_queens import Queens
from clausal import Var, call

QS = Var()
for trail in call(Queens, 8, QS):
    print(deref(QS))
```

#### 5.6 Tests for Phase 5

```python
@needs_scryer
class TestScryerBackendDirective:
    """Test -backend(scryer) modules."""

    def test_import_scryer_module(self, tmp_path):
        """A -backend(scryer) module can be imported and queried."""
        f = tmp_path / "facts.clausal"
        f.write_text(textwrap.dedent("""\
            -backend(scryer)
            -module(facts, [Color(X)])
            Color(red),
            Color(green),
            Color(blue),
        """))
        sys.path.insert(0, str(tmp_path))
        try:
            import facts
            from clausal import Var, call
            X = Var()
            results = [deref(X) for _ in call(facts.Color, X)]
            assert sorted(results) == ["blue", "green", "red"]
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("facts", None)

    def test_scryer_module_with_rules(self, tmp_path):
        """Rules in a -backend(scryer) module execute correctly."""
        f = tmp_path / "reach.clausal"
        f.write_text(textwrap.dedent("""\
            -backend(scryer)
            -module(reach, [Reach(X, Y)])
            Edge(1, 2), Edge(2, 3), Edge(3, 4),
            Reach(X, Y) <- Edge(X, Y)
            Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
        """))
        sys.path.insert(0, str(tmp_path))
        try:
            import reach
            from clausal import Var, call, deref
            Y = Var()
            results = sorted(deref(Y) for _ in call(reach.Reach, 1, Y))
            assert results == [2, 3, 4]
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("reach", None)

    def test_scryer_module_solutions_display(self, tmp_path):
        """Scryer-backed predicates work with the Solutions display."""
        f = tmp_path / "nums.clausal"
        f.write_text(textwrap.dedent("""\
            -backend(scryer)
            -module(nums, [Num(X)])
            Num(1), Num(2), Num(3),
        """))
        sys.path.insert(0, str(tmp_path))
        try:
            import nums
            from clausal import Var, Solutions
            X = Var()
            sol = Solutions(nums.Num(X))
            # Solutions wraps the iterator — verify it works
            results = list(sol._iter)
            assert len(results) == 3
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("nums", None)
```

---

## Implementation Notes for the Implementer

### Things that will require careful attention

1. **Verify the scryer-prolog path first.** The Cargo.toml uses
   `path = "../../scryer-prolog"`. From `clausal-scryerembedding/clausal-scryer/`,
   this resolves to `/workspace/scryer-prolog`. Before writing any Rust, verify this
   directory exists and contains `Cargo.toml`.

2. **PyO3 version and Python 3.13 compatibility.** PyO3 0.22+ supports 3.13. Check
   the exact PyO3 version available when implementing. The API surface (especially
   `into_pyobject`) may differ between 0.22 and 0.23.

3. **`double_quotes` flag.** Scryer defaults to `double_quotes = chars`, meaning
   `"hello"` is a list of characters. The machine `__new__` on the **Rust side** must
   set `double_quotes = atom` immediately after building the machine, before returning
   to Python. This is done via `machine.consult_module_string("user",
   ":- set_prolog_flag(double_quotes, atom).")`.

4. **`consult` replaces; `load` accumulates.** in_ standard Prolog, consulting a file
   replaces all clauses for predicates defined in that file. Loading (via `file_load`
   / `load_module_string`) asserts without replacing. The Python API documents this
   distinction clearly. Tests for incremental loading should use `load_string`, not
   `consult_string`.

5. **Error handling.** Define `ScryerError` as a Python exception on the Rust side
   (via `pyo3::create_exception!`). Prolog `error(type_error(...), ...)` terms should
   be formatted readably in the exception message.

6. **Machine bootstrap time.** ~200ms per `MachineBuilder::default().build()`.
   Tests that create many machines will be slow. Consider a session-scoped pytest
   fixture for tests that only read (don't need a fresh database):
   ```python
   @pytest.fixture(scope="module")
   def scryer():
       from clausal.scryer import Scryer
       return Scryer()
   ```

7. **The `tokio` dependency.** Even with `default-features = false`, scryer-prolog
   unconditionally depends on tokio for non-wasm targets (see its `Cargo.toml` line
   102). The key is that `dispatch_loop()` doesn't *call* `Handle::current()` unless
   HTTP builtins are invoked. If the build or runtime fails with a tokio error, you
   may need to initialize a minimal tokio runtime in `RawScryerMachine::new()`.

8. **Integer conversion.** `dashu::Integer` → Python `int`: for values fitting in
   `i64`, convert directly. For big values, `i.to_string()` → `int(s)` in Python.
   This is the only safe path. Note that `i64::try_from(dashu::Integer)` may need
   `use dashu::base::ConvertPrimitive` or similar — check the dashu 0.4 API.

9. **Partial list handling.** Scryer's `Term::from_heapcell` produces
   `Term::Compound(".", [head, tail])` for partial lists (non-nil tail). The Rust
   conversion handles this uniformly as `Compound(".", (head, tail))` — it's a
   valid clausal Compound and the user can pattern-match on it.

10. **`Compound.__eq__` and tuple args.** Verify that `Compound("point", (1, 2))`
    compares equal to a Compound constructed on the Rust side. The Rust code must pass
    a Python *tuple* to `Compound.__init__`, not a list. Check that
    `Compound.__init__` accepts the result of `PyTuple::new(py, &py_args)`.

11. **Reuse across queries.** The `Scryer` class holds a single `Machine`. Each
    `load_string` call adds to the machine's database. There is no "reset" — if
    you want a clean machine, create a new `Scryer()`. This matches how Prolog
    top-levels work.

12. **maturin `module-name` with dotted paths.** Test whether
    `module-name = "clausal._scryer_ext"` works with your maturin version. If not,
    use `module-name = "_scryer_ext"` and it will land in site-packages as a
    top-level module (which is fine for `import _scryer_ext`). The underscore prefix
    signals it's private/internal.

13. **The `ouroboros` self-referencing pattern.** This is the same pattern used by
    Scryer's own WASM binding (`src/wasm.rs`). The `#[self_referencing]` macro from
    `ouroboros = "0.18"` generates a struct that owns the `Machine` and borrows it
    for `QueryState<'this>`. Study the `WasmQueryState` / `WasmQueryStateInner` code
    in `src/wasm.rs` as the reference implementation — our PyO3 version follows the
    same pattern but uses `Rc<RefCell<Option<Machine>>>` to return the machine
    instead of the WASM version's `mpsc::channel` (because Machine is `!Send` and
    we don't cross threads).

14. **`QueryIterator.close()` vs Python GC.** The `__del__` / `drop` impl on
    `QueryIterator` returns the machine to the slot automatically. But Python's GC
    is non-deterministic — if the user stores the iterator in a variable and forgets
    about it, the machine stays locked until GC runs. The `.close()` method and the
    "machine is busy" error message make this diagnosable. The test
    `test_machine_busy_during_iteration` verifies the error and the recovery path.

15. **`for` loops drop the iterator.** Python's `for` loop calls `__del__` on the
    iterator when the loop exits (including `break`). This means the machine is
    returned after the loop body finishes, even with early exit. The test
    `test_early_break` verifies this.

### Build and test sequence

```bash
# 1. Verify scryer-prolog is where we expect
ls /workspace/scryer-prolog/Cargo.toml

# 2. Build the Rust extension (first build is slow — scryer is a big crate)
cd clausal-scryer
maturin develop --release
cd ..

# 3. Smoke test
python -c "import _scryer_ext; m = _scryer_ext.RawScryerMachine(); print('ok')"

# 4. Run the raw extension tests
pytest tests/test_scryer_raw.py -v

# 5. Run the integration tests
pytest tests/test_scryer_embedding.py -v

# 6. Run the existing scryer backend tests (still subprocess-based, for comparison)
pytest tests/test_scryer_backend.py -v
```

### Files to create (in order)

**Phases 1–4 (raw embedding + Python API)**:
1. `clausal-scryer/Cargo.toml`
2. `clausal-scryer/src/lib.rs`
3. `clausal-scryer/pyproject.toml` (for maturin)
4. `clausal/scryer/__init__.py`
5. `clausal/scryer/_scryer.py`
6. `clausal/scryer/_bridge.py`
7. `tests/test_scryer_raw.py`
8. `tests/test_scryer_embedding.py`

**Phase 5 (`-backend(scryer)` directive)**:
9. `clausal/scryer/_loader.py` — `_exec_module_scryer`, `_make_scryer_bridge_predicate`
10. `tests/test_scryer_backend_directive.py`

### Files to modify

**Phases 1–4**:
1. `pyproject.toml` — add `scryer = []` to optional-dependencies (minor)

**Phase 5**:
2. `clausal/templating/term_rewriting.py` — add `backend` to `_handle_directive`
3. `clausal/import_hook.py` — branch in `_exec_module_v2` when `-backend(scryer)` is present

### Files NOT to modify

- `clausal/__init__.py` — Scryer is opt-in, not part of the default import
- `clausal/logic/solve.py` — Scryer is a separate engine, not integrated here
- `setup.py` — C extensions remain as-is
