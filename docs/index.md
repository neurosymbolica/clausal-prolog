<p align="center"><img src="assets/logo/clausal-banner.png" alt="Clausal Prolog" width="460"></p>

# Prolog in Python for Neurosymbolic AI

[GitHub](https://github.com/neurosymbolica/clausal-prolog) ·
[GitLab](https://gitlab.com/MikeAmy/clausal) ·
[PyPI](https://pypi.org/project/clausal/)

Neural networks are good at perception, language and pattern-matching, but are
slow, resource-hungry, unreliable and need to be constrained. Symbolic AI is
good at rules, reasoning and guarantees but can't deal with the real world.
Neurosymbolic AI combines the two, giving you the best of both worlds:

- **Capable**: neural networks do what hand-written rules can't. They read
  images, understand and generate language, and learn patterns from data.
- **Explainable**: conclusions come from rules you can read and a derivation
  you can trace, not only from weights.
- **Reliable**: hard constraints such as regulations, safety rules and
  business policy hold exactly, every time, rather than approximately.
- **Data-efficient**: knowledge you can state as a rule doesn't have to be
  learned from examples.
- **Correctable**: change a rule and the behaviour changes, with no
  retraining.

Each side already has a leading platform. Python is the de facto home of
neural networks: PyTorch, JAX and the rest of the deep-learning ecosystem are
built for it. Prolog is the leading language of symbolic AI. It has more than
50 years of maturity behind it, and it is still chosen for demanding systems,
IBM Watson's question analysis among them, for its robustness and expressive
power. Neurosymbolic AI needs the two working together.

Clausal Prolog is a Prolog implemented in Python that aims for ISO Prolog
conformity. It is not a wrapper around an external engine: it runs in the
Python process, on the same objects and the same garbage collector, so Prolog
and Python call each other freely. A neural model can call a logic program,
and that logic can call back into the model, with no serialisation in between.

## Start here

<div class="grid cards" markdown>

-   :material-school:{ .lg .middle } **[Tutorial](tutorial.md)**

    ---

    Relations, queries and unification, from first principles. No Prolog
    experience needed.

-   :material-head-lightbulb:{ .lg .middle } **[Thinking Relationally](thinking_relationally.md)**

    ---

    The one idea to absorb first: predicates are relations, not functions.

-   :material-language-python:{ .lg .middle } **[For Python Programmers](for_python_programmers.md)**

    ---

    From functions and loops to relations and search.

-   :clausal-neck:{ .lg .middle } **[For Prolog Programmers](for_prolog_programmers.md)**

    ---

    What's the same as ISO Prolog, what's different, and where Python comes in.

-   :material-robot:{ .lg .middle } **[For AI Agents](for_ai_agents.md)**

    ---

    Why LLMs should generate logic programs, and how to do it well.

-   :material-briefcase:{ .lg .middle } **[For Decision Makers](for_decision_makers.md)**

    ---

    The business case: explainability, reliability, rules as code.

</div>

The rest of this page is a quick tour. [Command line](cli.md) and
[Examples](examples.md) are good next stops after the tutorial.

## Running Prolog

Install the package from PyPI. It also installs the `clausal` command:

```bash
pip install clausal
```

Write ordinary Prolog in a `.clausal` file. Tests live next to the code:

```prolog
% fibonacci.clausal
:- module(fibonacci, [fib/2]).
:- use_module(library(clpz)).

:- table(fib/2).
fib(0, 0).
fib(1, 1).
fib(N, F) :-
    N #> 1,
    N1 #= N - 1, N2 #= N - 2,
    fib(N1, F1), fib(N2, F2),
    F #= F1 + F2.

test(fib_10_55) :- fib(10, 55).

:- end_module(fibonacci).
```

Run it with the `clausal` command. `-g` runs a goal and prints its answers,
the way a Prolog toplevel does; `--test` runs the module's tests:

```bash
$ clausal fibonacci.clausal -g "fib(10, F)"
F = 55.
$ clausal --test fibonacci.clausal
1 tests: 1 passed, 0 failed [PASSED]
```

A program that defines `main/0` runs it when given just the file:
`clausal program.clausal`. See [Command line](cli.md).

Existing ISO Prolog lives in `.pl` files; see [Importing Prolog](importing_prolog.md).

## Running from Python

Import the module like any Python module and ask it questions. In a `.seam`
file, a goal after `--` is a query, and its variables become Python
variables:

```python
# report.seam
-import_from(fibonacci, [fib])

for F in --fib(10, F):
    print(F)  # 55
```

```bash
python -c "import clausal, report"
```

Answers are plain Python values: an atom is a `str`, a compound term is a
tuple such as `('point', 1, 2)`. See [Python Integration](python_integration.md).

## Three source surfaces

| Extension | Surface | Use it for |
|---|---|---|
| `.clausal` | [Clausal Prolog](clausal_prolog.md): ISO syntax, cut-free | Your logic programs |
| `.pl` | [ISO Prolog](importing_prolog.md) (experimental) | Existing Prolog code |
| `.seam` | The seam: Python syntax | The boundary with Python: `++expr`, hosted Python, adapters |

Many language pages in these docs still show their examples in seam syntax.
Each one says so, and the semantics carry over to Clausal Prolog.
[Clausal Prolog](clausal_prolog.md) gives the spelling differences and the
rules the surface enforces.

---

## Why Clausal Prolog?

- **Heading for ISO Prolog** — ISO syntax, ISO builtin names and ISO error terms; where ISO is silent, Clausal Prolog follows [Scryer Prolog](https://www.scryer.pl/). See [Operators](operators.md) and [Public API](public-api.md).
- **Pure by design** — no cut and no committed choice: [`dif/2`](constraints.md), [reified if-then-else](reified_ite.md), constraints and [tabling](tabling.md) keep programs monotonic. See [Purity](purity.md).
- **Deep integration** — terms are Python tuples and atoms are Python strings, backtracking uses Python generators, and Python libraries are reached through `library(...)` facades and `.seam` modules.
- **Asyncio, not a home-grown scheduler** — queries run on Python's own mature [`asyncio`](asyncio.md) event loop rather than a scheduler of our own. A proof can wait on a model, a database, a person or an event stream while other queries run, and timeouts, cancellation and racing come straight from `asyncio`. Backtracking still works across waits (experimental).
- **Full-featured** — [tabling](tabling.md), [CLP(ℤ)](constraints.md), [DCGs](dcg.md), EDCGs, [modules](import.md), [term expansion](term_expansion.md), goal expansion, [reified if-then-else](reified_ite.md).
- **Fast** — C extension for unification/trails, [first-argument indexing](indexing.md), groundness-keyed dispatch, [tail recursion optimization](compiler.md#tail-recursion-optimization-tro), [bytecode caching](caching.md).

---

## Interactive example — Sudoku in IPython

The IPython integration uses seam syntax, since it runs inside Python.

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
   ...: ], solve(ROWS))
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
# No more solutions.
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
| **Start Here** | |
| [For Python Programmers](for_python_programmers.md) | Bridge from functions and loops to relations and search |
| [For Prolog Programmers](for_prolog_programmers.md) | Syntax mapping, what's the same, what's different |
| [For AI Agents](for_ai_agents.md) | Why LLMs should generate logic programs |
| [For Decision Makers](for_decision_makers.md) | The business case: explainability, reliability, rules-as-code |
| **Getting Started** | |
| [Syntax](syntax.md) | The trailing-comma convention, escape operators, logic variables, clause syntax |
| [Style & Formatting](style.md) | One goal per line, clause separation, `clausal-fmt` |
| [Clausal Prolog](clausal_prolog.md) | The `.clausal` surface: ISO syntax, cut-free, its rules and how it differs from the seam |
| [Predicates](predicates.md) | How to define predicates |
| [Builtins](builtins.md) | Complete index of built-in predicates |
| [Dicts & Sets](dicts_sets.md) | DictTerm, SetTerm, `__unify__` protocol |
| [Constraints](constraints.md) | dif/2, CLP(ℤ) integer constraints, and CLP(ℝ) real-domain constraints |
| [CLP(ℝ)](clpr.md) | Interval arithmetic, non-linear propagation, and bisection labeling over the reals |
| [CLP(Q)](clpq.md) | Exact rational constraints via Gaussian elimination and the revised simplex method |
| [Tabling](tabling.md) | SLG resolution and well-founded semantics |
| [Lambdas](lambdas.md) | Goal closures for higher-order logic programming |
| [If-Then-Else](reified_ite.md) | Reified branching (no cut, no committed choice) |
| [Import System](import.md) | Module loading, module directives, qualified calls |
| [Importing Prolog](importing_prolog.md) | Import `.pl` files directly — on-the-fly translation and caching (experimental in 1.0) |
| [Architecture](architecture.md) | Layer stack, execution model, why not a WAM |
| [Python Integration](python_integration.md) | Querying with `--goal`, the `++()` escape, `solve()`, converters |
| [Asyncio](asyncio.md) | Queries on Python's `asyncio` loop: waiting on models, data, people and streams mid-search |
| [Operators](operators.md) | What each operator means bare (Python) and quoted (Scryer/ISO) |
| [Arithmetic](arithmetic.md) | Evaluation, exact rationals, the evaluable functors |
| [Public API](public-api.md) | What the 1.0 semantic-versioning promise covers |
| [Reflection](reflection.md) | Reify `.seam` source as matchable terms — linters and matchers written as logic programs |
| [IPython / Jupyter REPL](ipython.md) | Interactive queries, `*(goals)` syntax, solution browsing |
| **Standard Library Modules** | |
| [Physical Units](units.md) | `n(Unit)` sugar, dimensional arithmetic, AttVar constraints |
| [Currency](currency.md) | Exact-decimal money as units base dimensions; rounding/display; precision checks |
| [Regex](regex.md) | Pattern matching, group extraction, auto-binding |
| [Symbolic Math](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sympy/docs/sympy.md) | SymPy integration — calculus, algebra, number theory |
| [YAML](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-yaml/docs/yaml.md) | YAML parsing and generation |
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
| [spaCy NLP](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-spacy/docs/spacy.md) | NLP pipeline — tokenisation, NER, POS, similarity |
| [scipy.special](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_special.md) | Special mathematical functions — gamma, Bessel, elliptic, hypergeometric, orthogonal polynomials |
| [scipy.linalg](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_linalg.md) | Linear algebra — solvers, decompositions, matrix functions, factorisations |
| [scipy.optimize](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_optimize.md) | Optimisation — minimisation, root finding, curve fitting, linear programming |
| [scipy.integrate](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_integrate.md) | Numerical integration — quadrature, ODE solvers, sampled-data methods |
| [scipy.interpolate](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_interpolate.md) | Interpolation — splines, PCHIP, Akima, regular grids, radial basis functions |
| [scipy.stats](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_stats.md) | statistics — descriptive stats, hypothesis tests, distributions |
| [scipy.fft](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_fft.md) | Discrete Fourier transforms — FFT, inverse FFT, helper functions |
| [scipy.ndimage](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_ndimage.md) | N-dimensional image processing — filters, morphology, transforms, measurements |
| [scipy.spatial](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_spatial.md) | Spatial algorithms — distance functions, KD-tree, ConvexHull, Delaunay, Rotation |
| [Crypto](crypto.md) | Cryptographic hashing, HMAC signing, PBKDF2 key derivation |
| [HTTP & URL](http.md) | HTTP requests (GET, POST, JSON), URL encoding and parsing |
| [TCP](tcp.md) | TCP client/server sockets — connect, listen, send, receive |
| [Testing](testing.md) | Writing test predicates, running the test suite |
| [DCGs](dcg.md) | Definite Clause Grammars for parsing |
| [Exceptions](exceptions.md) | throw/catch, structured error terms |
| [Coroutining](coroutining.md) | freeze/2, when/2, setup_call_cleanup/3, call_nth/2, count_all/2 |
| [CLP(B)](clpb.md) | Boolean constraint programming |
| [Z3 SMT Solver](z3.md) | Multi-theory constraints via Z3 — integers, reals, booleans, bitvectors, arrays, strings, optimization, unsat cores |
| [Meta-Interpreter Specialization](specialization.md) | Partial deduction — specialize MIs to remove interpretation overhead |
| [Prolog Translation](prolog_translation.md) | Bidirectional seam ↔ Prolog translation |
| [Trealla Prolog Embedding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-trealla/docs/trealla.md) | In-process Trealla Prolog engine via ctypes — fast, lightweight, instant startup |
| [Scryer Prolog Embedding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) | In-process Scryer Prolog engine via PyO3 — lazy queries, tabling support |
| [Examples](examples.md) | Example programs: Fibonacci, N-Queens, Sudoku, meta-interpreters |
| **Scientific Computing** | |
| [scikit-learn](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sklearn/docs/sklearn.md) | Machine learning: estimators, pipelines, cross-validation |
| [scipy.cluster](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_cluster.md) | Hierarchical clustering, k-means, vector quantisation |
| [scipy.constants](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_constants.md) | CODATA physical constants, SI prefixes |
| [scipy.differentiate](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_differentiate.md) | Numerical differentiation: Derivative, Jacobian, Hessian |
| [scipy.signal](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_signal.md) | Signal processing: filter design, filtering, spectral analysis |
| [scipy.sparse](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_sparse.md) | Sparse matrices and sparse linear algebra |
| **Infrastructure** | |
| [Compiler](compiler.md) | Compilation pipeline: head patterns, body goals, trampoline, TRO |
| [Jupyter Notebooks](jupyter.md) | Notebook integration with HTML rendering |
| [Free Threading](free_threading.md) | Free-threaded Python (PEP 703) support, C extension safety |
| [Parallel Predicates](tutorial_parallel_clausal.md) | Writing thread-safe predicates |
| [Parallel Queries](tutorial_parallel_python.md) | Running parallel queries from Python |
