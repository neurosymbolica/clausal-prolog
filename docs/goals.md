# Clausal — Project Goals

## Mission

Clausal aims to provide logic programming in Python as tightly integrated as possible — not as a front-end to an external Prolog, but as a genuine part of the Python runtime. Python code and logic code call into each other freely, share the same objects, and run on the same VM. Existing Prolog programs can be [imported directly](importing_prolog.md) — translated, compiled, and cached on the fly.

The inspiration is heavily drawn from existing Prologs, particularly the insights of Marcus Triska (Power of Prolog), Richard O'Keefe, and Ulrich Neumerkel. Clausal does not claim to be a Prolog and does not follow ISO Prolog syntax, because those conventions are sufficiently alien to Python programmers that they would add unnecessary obstacles. Instead, clausal brings the spirit of Prolog to Python — using Python semantics for operators and keywords, retaining familiar Python concepts, and leveraging Python's runtime as much as possible.

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
- **`clausal.simple_ast`** and **`clausal.conversion`** — simplified Python AST, used as the term representation for homoiconic code.
- **`clausal.term_rewriting`** — transforms DSL [syntax](syntax.md) (`--expr`, `head<-body`, trailing-comma facts) to AST-building Python.
- **`clausal.trampoline`** — stack-safe CPS execution via generator-based trampoline.
- **`clausal.continuation_search`** — greenlet-based search iterator.
- **`clausal.import_hook`** — transparent [import](import.md) of logic modules; [IPython](ipython.md) integration.

Planned additions are described in the [Architecture](architecture.md) document.
