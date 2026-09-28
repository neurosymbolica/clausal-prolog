# Clausal — Project Goals

## Mission

Clausal aims to provide logic programming in Python as tightly integrated as possible — not as a front-end to an external Prolog, but as a genuine part of the Python runtime. Python code and logic code call into each other freely, share the same objects, and run on the same VM. Existing Prolog programs can be [imported directly](importing_prolog.md) — translated, compiled, and cached on the fly.

The inspiration is heavily drawn from existing Prologs, particularly the insights of Markus Triska (The Power of Prolog), Richard O'Keefe, and Ulrich Neumerkel. Clausal's surface syntax is Python's, not ISO Prolog's; its *semantics* follow ISO Prolog (ISO 13211-1) first, and Scryer Prolog where ISO is silent. In today's syntax a **bare** operator keeps its Python meaning (`-7 // 2` is -4) while the **quoted** ISO spelling follows Scryer (`'//'(-7, 2)` is -3) — see [Operators](operators.md). Clausal is cut-free by design: `once/1`, `if_/3` and negation cover committed choice.

## Why logic programming + Python?

Neural networks and machine learning offer extraordinary power for dealing with noisy real-world data. But they also:

- demand significant compute resources, tending to centralise them
- often have significant output latency
- use much more energy than traditional computation
- are very difficult to analyse — processing is cryptic, behaviour hard to guarantee
- cannot be used for many critical applications without external verification

Logic programming, by contrast, struggles with noisy data but offers powerful, transparent reasoning when the rules are well-understood:

- built-in search over combinatorial spaces
- efficient expression of [constraint satisfaction](constraints.md) and optimisation problems
- exceptional power to reason about and analyse programs
- naturally expressible [meta-interpreters](metainterpreters.md)

These two kinds of AI have complementary strengths. A self-driving car, for example, might use neural networks to interpret sensor data (video, radar, voice) and a logic system to reason about traffic laws, collision avoidance, and route planning — domains where rules are precise, latency must be low, and behaviour may need to be formally verified.

Marrying these in Python — the lingua franca of machine learning — is the goal.

??? abstract "Design principles"

    **Genuine integration, not interop.** The logic system runs on the Python VM. Logic predicates and Python functions call into each other with no subprocess overhead, no re-entrancy issues, no marshalling across a process boundary.

    **Python syntax throughout.** All syntax is valid Python syntax, acceptable to the Python parser. No new parser is required. This means logic code can be syntax-highlighted, linted, and processed by standard Python tooling.

    **Pythonic, not puristic.** Python culture allows breaking rules. Calling Python from within logic code is supported without apology. Side effects, I/O, and mutable state can coexist with backtracking — the programmer understands what they are doing.

    **Homoiconicity.** Python code can be extracted as AST nodes and manipulated by the logic system or by Python code. This unlocks powerful compile-time transformations and meta-programming that are essentially impossible in standard Python.

    **Compile once.** The AST transformation overhead is paid once, at import time. Transformed bytecode is cached by Python's standard import machinery.

## What clausal provides

- **`clausal.logic.variables`** — C extension for logic variables and trail-based backtracking. Foundation for all unification.
- **Terms are plain Python values** — an atom is a `str`, a compound is a cell tuple `('f', 1, 2)`, a list is a Python list, a string is the `('$chars', s)` carrier. `clausal.cell_functor`, `cell_args` and `make_cell` read and build cells.
- **`clausal.import_hook`** — transparent [import](import.md) of `.clausal`/`.seam` modules; [IPython](ipython.md) integration.
- **`clausal.logic.compiler`** — compiles clauses to Python generators run on a stack-safe trampoline (`clausal.logic.trampoline`).
- **The goal-position seam** — in a `.seam` file, Python calls logic with `for X in --pred(X):` / `if --pred(a):`, and logic calls Python with `++expr` (see [Python integration](python_integration.md)).

What 1.0 covers is listed in [Public API](public-api.md).

Planned additions are described in the [Architecture](architecture.md) document.
