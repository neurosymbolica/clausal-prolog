"""clausal.pythonic_terms — Python-as-data statement and control-flow nodes.

These classes represent Python statements and control flow as homoiconic data.
They keep the Node base class and its visit_children / transform_children
infrastructure since tree traversal is genuinely useful for statement-level
rewriting.

Expression-level functor/operator classes live in clausal.terms instead.
"""

from .pythonic_ast.nodes import (
    # Base
    Node,
    REMOVED,
    locate,
    dump,
    simplify,
    # Modules / top-level
    Module,
    Interactive,
    Expression,
    # Statements
    Assign,
    AnnAssign,
    Return,
    Pass,
    Break,
    Continue,
    Raise,
    assertz,
    Global,
    Nonlocal,
    # Imports
    Import,
    ImportFrom,
    # Compound statements
    If,
    While,
    For,
    With,
    Try,
    ExceptHandler,
    # Definitions
    FunctionDef,
    ClassDef,
    TypeAlias,
    # Type parameters
    TypeVar,
    ParamSpec,
    TypeVarTuple,
    # Pattern matching
    Match,
    MatchCase,
    MatchLiteral,
    MatchSequence,
    MatchMapping,
    MatchClass,
    MatchStar,
    MatchAs,
    MatchOr,
)

__all__ = [
    # Base
    "Node",
    "REMOVED",
    "locate",
    "dump",
    "simplify",
    # Modules
    "Module",
    "Interactive",
    "Expression",
    # Statements
    "Assign",
    "AnnAssign",
    "Return",
    "Pass",
    "Break",
    "Continue",
    "Raise",
    "assertz",
    "Global",
    "Nonlocal",
    # Imports
    "Import",
    "ImportFrom",
    # Compound statements
    "If",
    "While",
    "For",
    "With",
    "Try",
    "ExceptHandler",
    # Definitions
    "FunctionDef",
    "ClassDef",
    "TypeAlias",
    # Type parameters
    "TypeVar",
    "ParamSpec",
    "TypeVarTuple",
    # Pattern matching
    "Match",
    "MatchCase",
    "MatchLiteral",
    "MatchSequence",
    "MatchMapping",
    "MatchClass",
    "MatchStar",
    "MatchAs",
    "MatchOr",
]
