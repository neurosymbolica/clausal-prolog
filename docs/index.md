# Clausal

!!! warning "Beta"
    Clausal is in early **beta**. The API, syntax, and module interfaces are all subject to change. The developer experience has not been widely tested beyond the author's own use. Expect rough edges — bug reports and feedback are very welcome.

**Logic programming embedded in Python.**

Clausal brings Prolog-style logic programming to Python — not as a front-end to an external engine, but as a genuine part of the Python runtime. Python code and logic code call into each other freely, share the same objects, and run on the same VM.

```python
import clausal
from fibonacci import Fib

for solution in clausal.query(Fib(10, N)):
    print(solution[N])  # 55
```

---

## Why Clausal?

- **Pure Python syntax** — all clausal code is valid Python. No separate parser, no foreign syntax to learn.
- **Deep integration** — predicates are Python classes, logic variables are Python objects, backtracking uses Python generators.
- **Full-featured** — tabling, CLP(FD), DCGs, EDCGs, modules, term expansion, goal expansion, reified if-then-else.
- **Fast** — C extension for unification/trails, first-argument indexing, groundness-keyed dispatch, tail recursion optimization, bytecode caching.

---

## Quick taste

A `.clausal` file defines predicates using Python syntax with a trailing comma:

```clausal
# skip
# fibonacci.clausal

-table(Fib/2),

Fib(0, 0),
Fib(1, 1),
Fib(N, F) <- (
    N > 1,
    N1 := N - 1,
    N2 := N - 2,
    Fib(N1, F1),
    Fib(N2, F2),
    F := F1 + F2
)
```

Call it from Python:

```python
import clausal
from fibonacci import Fib

results = list(clausal.query(Fib(10, F)))
# F binds to 55
```

---

## Interactive example — Sudoku in IPython

Start IPython with the integration enabled:

```bash
CLAUSAL_IPYTHON=True ipython
```

Then solve a Sudoku puzzle interactively:

```python
In [1]: from clausal.examples.sudoku import *

In [2]: *(ROWS is [
   ...:   [1, _, _, 8, _, 4, _, _, _],
   ...:   [_, 2, _, _, _, _, 4, 5, 6],
   ...:   [_, _, 3, 2, _, 5, _, _, _],
   ...:   [_, _, _, 4, _, _, 8, _, 5],
   ...:   [7, 8, 9, _, 5, _, _, _, _],
   ...:   [_, _, _, _, _, 6, 2, _, 3],
   ...:   [8, _, 1, _, _, _, 7, _, _],
   ...:   [_, _, _, 1, 2, 3, _, 8, _],
   ...:   [2, _, 5, _, _, _, _, _, 9],
   ...: ], Solve(ROWS))
Out[2]: ROWS is [
  [1, 5, 6, 8, 9, 4, 3, 2, 7],
  [9, 2, 8, 7, 3, 1, 4, 5, 6],
  [4, 7, 3, 2, 6, 5, 9, 1, 8],
  [3, 6, 2, 4, 1, 7, 8, 9, 5],
  [7, 8, 9, 3, 5, 2, 6, 4, 1],
  [5, 1, 4, 9, 8, 6, 2, 7, 3],
  [8, 3, 1, 5, 4, 9, 7, 6, 2],
  [6, 9, 7, 1, 2, 3, 5, 8, 4],
  [2, 4, 5, 6, 7, 8, 1, 3, 9]
]
No more solutions.
```

Uppercase names (`ROWS`) are automatically allocated as logic variables.  The
`*(...)` form is the IPython query syntax — see [IPython / Jupyter REPL](ipython.md)
for the full feature set.

---

## What's inside

| Section | What you'll find |
|---|---|
| **Foundations** | |
| [Thinking Relationally](thinking_relationally.md) | The most important idea: predicates as relations, not functions |
| [Purity and Monotonicity](purity.md) | Why pure code has better properties and how to write it |
| **Getting Started** | |
| [Syntax](syntax.md) | The trailing-comma convention, escape operators, logic variables, clause syntax |
| [Predicates](predicates.md) | How to define predicates in .clausal files |
| [Builtins](builtins.md) | Complete index of built-in predicates |
| [Dicts & Sets](dicts_sets.md) | DictTerm, SetTerm, `__unify__` protocol |
| [Constraints](constraints.md) | Dif/2, CLP(FD) finite-domain constraints, and CLP(R) real-domain constraints |
| [CLP(R)](clpr.md) | Interval arithmetic, non-linear propagation, and bisection labeling over the reals |
| [Tabling](tabling.md) | SLG resolution and well-founded semantics |
| [Lambdas](lambdas.md) | Goal closures for higher-order logic programming |
| [If-Then-Else](reified_ite.md) | Reified branching (no cut, no committed choice) |
| [Import System](import.md) | `.clausal` file loading, module directives, qualified calls |
| [Architecture](architecture.md) | Layer stack, execution model, why not a WAM |
| [Python Integration](python_integration.md) | Query API, `++()` escape, Python interop |
| [IPython / Jupyter REPL](ipython.md) | Interactive queries, `*(goals)` syntax, solution browsing |
| **Standard Library Modules** | |
| [Physical Units](units.md) | `n(Unit)` sugar, dimensional arithmetic, AttVar constraints |
| [Regex](regex.md) | Pattern matching, group extraction, auto-binding |
| [Symbolic Math](sympy.md) | SymPy integration — calculus, algebra, number theory |
| [YAML](yaml.md) | YAML parsing and generation |
| [Date/Time](date_time.md) | Date, time, and datetime predicates |
| [Logging](logging.md) | Structured logging predicates |
| [UUID](uuid.md) | UUID generation and inspection |
| [Graphs](graphs.md) | Graph traversal, pathfinding, connectivity, MST |
| [Random](random.md) | Random number generation, selection, seeding |
| [JSON](json.md) | JSON parsing, generation, DictTerm integration |
| [CSV](csv.md) | CSV parsing, generation, DictTerm records |
| [OS](os.md) | Environment variables, working directory, process info, platform |
| [Files](files.md) | File/directory existence, listing, metadata, CRUD, path manipulation |
| [Process](process.md) | Shell commands, subprocess execution, sleep |
| [SQLite](sqlite.md) | SQLite database predicates |
| [spaCy NLP](spacy.md) | NLP pipeline — tokenisation, NER, POS, similarity |
| [scipy.special](scipy_special.md) | Special mathematical functions — gamma, Bessel, elliptic, hypergeometric, orthogonal polynomials |
| [scipy.linalg](scipy_linalg.md) | Linear algebra — solvers, decompositions, matrix functions, factorisations |
| [scipy.optimize](scipy_optimize.md) | Optimisation — minimisation, root finding, curve fitting, linear programming |
| [scipy.integrate](scipy_integrate.md) | Numerical integration — quadrature, ODE solvers, sampled-data methods |
| [scipy.interpolate](scipy_interpolate.md) | Interpolation — splines, PCHIP, Akima, regular grids, radial basis functions |
| [scipy.stats](scipy_stats.md) | Statistics — descriptive stats, hypothesis tests, distributions |
| [scipy.fft](scipy_fft.md) | Discrete Fourier transforms — FFT, inverse FFT, helper functions |
| [scipy.ndimage](scipy_ndimage.md) | N-dimensional image processing — filters, morphology, transforms, measurements |
| [scipy.spatial](scipy_spatial.md) | Spatial algorithms — distance functions, KD-tree, ConvexHull, Delaunay, Rotation |
| [Crypto](crypto.md) | Cryptographic hashing, HMAC signing, PBKDF2 key derivation |
| [HTTP & URL](http.md) | HTTP requests (GET, POST, JSON), URL encoding and parsing |
| [TCP](tcp.md) | TCP client/server sockets — connect, listen, send, receive |
| [Testing](testing.md) | Writing test predicates, running the test suite |
| [DCGs](dcg.md) | Definite Clause Grammars for parsing |
| [Exceptions](exceptions.md) | throw/catch, structured error terms |
| [Coroutining](coroutining.md) | Freeze/2, When/2, SetupCallCleanup/3, CallNth/2, CountAll/2 |
| [CLP(B)](clpb.md) | Boolean constraint programming |
| [Meta-Interpreter Specialization](specialization.md) | Partial deduction — specialize MIs to remove interpretation overhead |
| [Prolog Translation](prolog_translation.md) | Bidirectional clausal ↔ Prolog translation |
