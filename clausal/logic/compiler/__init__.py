"""clausal.logic.compiler — predicate compiler package.

Public API (see ``__all__`` below) — everything else is a package-
internal implementation detail.  External callers that reach into
private submodules (e.g. ``clausal.logic.compiler.arg_index``) do so at
their own risk and should expect the surface to change.

The module layout is documented in
``implementation_plans/COMPILER_MODULE_SPLIT.md``; key submodules:

- ``predicate``         — top-level ``compile_predicate_*`` entrypoints
- ``goal_shallow``      — ``compile_goal`` / ``compile_body`` (shallow)
- ``goal_trampoline``   — trampoline counterparts
- ``terms_to_ast``      — term → Python AST lowering (+ star parsing)
- ``head_match``        — head term → match-case patterns
- ``globals_env``       — compile-time globals-dict construction
- ``arg_index``         — first-arg + joint + secondary + groundness dispatch
- ``control_constructs``— once, catch, setup_call_cleanup, freeze, when, …
- ``tro``               — tail-recursion optimization analysis + rewrite
- ``strategy`` / ``compile_ctx`` — ``Strategy`` protocol + ``CompilationContext``

The ``_monolith`` re-export hub and ``__getattr__`` delegation that
previously fronted private names were retired in slice B6; the
remaining private re-exports were removed in slice H of the compiler
refactor (see ``implementation_plans/COMPILER_MIGRATION_PLAN.md``).
"""

from clausal.logic.trampoline import DONE

from .predicate import (
    compile_predicate,
    compile_predicate_ast,
    compile_predicate_shallow,
    compile_predicate_shallow_ast,
    compile_predicate_trampoline,
    compile_predicate_trampoline_ast,
)
from .strategy import ShallowStrategy, Strategy, TrampolineStrategy
from .compile_ctx import CompilationContext

__all__ = [
    "DONE",
    "compile_predicate",
    "compile_predicate_ast",
    "compile_predicate_shallow",
    "compile_predicate_shallow_ast",
    "compile_predicate_trampoline",
    "compile_predicate_trampoline_ast",
    "Strategy",
    "ShallowStrategy",
    "TrampolineStrategy",
    "CompilationContext",
]
