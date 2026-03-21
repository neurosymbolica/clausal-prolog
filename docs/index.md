# Clausal

**Logic programming embedded in Python.**

Clausal brings Prolog-style logic programming to Python — not as a front-end to an external engine, but as a genuine part of the Python runtime. Python code and logic code call into each other freely, share the same objects, and run on the same VM.

```python
import clausal
from fibonacci import fib

for solution in clausal.query(fib(10, N)):
    print(solution[N])  # 55
```

---

## Why Clausal?

- **Pure Python syntax** — all clausal code is valid Python. No separate parser, no foreign syntax to learn.
- **Deep integration** — predicates are Python classes, logic variables are Python objects, backtracking uses Python generators.
- **Full-featured** — tabling, CLP(FD), DCGs, EDCGs, modules, term expansion, goal expansion, reified if-then-else.
- **Fast** — C extension for unification/trails, first-argument indexing, groundness-keyed dispatch, bytecode caching.

---

## Quick taste

A `.clausal` file defines predicates using Python syntax with a trailing comma:

```python
# fibonacci.clausal

-table(fib/2),

fib(0, 0),
fib(1, 1),
fib(N, F) <- (
    N > 1
    and N1 is N - 1
    and N2 is N - 2
    and fib(N1, F1)
    and fib(N2, F2)
    and F is F1 + F2
),
```

Call it from Python:

```python
import clausal
from fibonacci import fib

results = list(clausal.solve(fib(10, F)))
# F binds to 55
```

---

## What's inside

| Section | What you'll find |
|---|---|
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
| **Standard Library Modules** | |
| [Physical Units](units.md) | `n(Unit)` sugar, dimensional arithmetic, AttVar constraints |
| [Regex](regex.md) | Pattern matching, group extraction, auto-binding |
| [Symbolic Math](sympy.md) | SymPy integration — calculus, algebra, number theory |
| [YAML](yaml.md) | YAML parsing and generation |
| [Date/Time](date_time.md) | Date, time, and datetime predicates |
| [Logging](logging.md) | Structured logging predicates |
| [UUID](uuid.md) | UUID generation and inspection |
| [Graphs](graphs.md) | Graph traversal, pathfinding, connectivity, MST |
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
| [Testing](testing.md) | Writing test predicates, running the test suite |
| [DCGs](dcg.md) | Definite Clause Grammars for parsing |
| [Exceptions](exceptions.md) | throw/catch, structured error terms |
| [CLP(B)](clpb.md) | Boolean constraint programming |
