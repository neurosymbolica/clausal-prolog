"""Prolog → Clausal translation (Phase 3.3).

Pipeline: .pl source → tokens → Prolog AST → .clausal source text

Public API:
    prolog_to_clausal(source, *, dialect=None) -> str
    prolog_ast_to_clausal(pmodule, *, dialect=None) -> str
    emit_clausal_term(term, dialect) -> str
    emit_clausal_item(item, dialect) -> str
"""

from __future__ import annotations

import json
import keyword
from pathlib import Path


def _is_plain_atom_name(name: str) -> bool:
    """True if *name* can be emitted as a bare lowercase Clausal atom name."""
    return (
        bool(name)
        and name[0].islower()
        and name.isidentifier()
        and not keyword.iskeyword(name)
    )

from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PQuery, PComment, PModule,
    PTerm, PItem,
)
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_dialect import (
    Dialect,
    snake_to_pascal, prolog_var_to_clausal,
    BUILTIN_NAME_MAP,
)
from clausal.tools.prolog_parser import parse


__all__ = [
    "prolog_to_clausal", "prolog_ast_to_clausal",
    "emit_clausal_term", "emit_clausal_item",
    "PrologTranslationError",
]


class PrologTranslationError(Exception):
    """Raised when Prolog source contains constructs that cannot be translated.

    Cut (``!/0``) and if-then-else (``(C -> T ; E)``) are intentionally
    unsupported.  Programs using them must be rewritten to use pure
    alternatives (``dif/2``, reified conditionals, ``once/1``, indexing).
    """


# ── reverse builtin name map ────────────────────────────────────────
# prolog_name -> clausal_name, built from BUILTIN_NAME_MAP

# Prolog builtins whose Clausal predicate name cannot be derived from
# BUILTIN_NAME_MAP alone.  Bare `member/2` in goal position is rendered as
# infix `X in L`, so BUILTIN_NAME_MAP has no clausal-side name for it; but
# wherever a predicate *name* is required (qualified goals like
# `lists:member(X, L)`, metacall arguments like `findall(X, member(X, L), Xs)`)
# the underlying Clausal builtin is `in_/2` — `member` does not exist on the
# Clausal side (F033).
_REVERSE_OVERRIDES: dict[str, str] = {
    "member": "in_",
}


def _build_reverse_builtin_map() -> dict[str, str]:
    """Build a mapping from Prolog builtin names to clausal names."""
    rev: dict[str, str] = {}
    for clausal_name, dialect_map in BUILTIN_NAME_MAP.items():
        for prolog_name in dialect_map.values():
            if prolog_name not in rev:
                rev[prolog_name] = clausal_name
        # Also map the clausal name itself (snake_case names may appear
        # directly in Prolog sources and should not be pascal-cased).
        if clausal_name not in rev:
            rev[clausal_name] = clausal_name
    rev.update(_REVERSE_OVERRIDES)
    return rev


_REVERSE_BUILTIN_MAP = _build_reverse_builtin_map()


# ── Operator mapping: Prolog operators → clausal syntax ──────────────

# Prolog infix → clausal equivalent
_INFIX_MAP = {
    ":-":   "<-",       # clause arrow (body context)
# (Prolog ``is``/2 is handled as a special case → ``eval_(E, R)``, not infix.)
    "=":    "is",       # unification
    "\\=":  "is not",   # dis-unification
    "\\+":  "not",      # negation-as-failure (prefix, but listed here)
    ";":    "or",       # disjunction
    "==":   "==",       # structural equality (same)
    "\\==": "!=",       # structural inequality
    "=<":   "<=",       # arithmetic less-or-equal (Prolog =< → Python <=)
    ">=":   ">=",
    "<":    "<",
    ">":    ">",
    "=:=":  "==",       # arithmetic equality → == (context-dependent)
    "=\\=": "!=",       # arithmetic inequality
    "+":    "+",
    "-":    "-",
    "*":    "*",
    "/":    "/",
    "**":   "**",
    "^":    "**",       # ISO exponentiation (arithmetic context only, F026)
    ",":    ",",        # conjunction stays
    "div":  "//",       # SWI floored division → clausal // (also floored)
    "=..":  "=..",      # univ — no direct clausal equivalent, keep as comment
    "/\\":  "&",        # bitwise AND
    "\\/":  "|",        # bitwise OR
    "xor":  "^",        # bitwise XOR
    "<<":   "<<",
    ">>":   ">>",       # NOTE: >> is DCG in clausal, so only in arithmetic context
}

# Prolog operators whose ISO semantics differ from Python's.
# These are emitted as qualified calls: prolog.TruncDiv(X, Y)
# The ``prolog`` module (clausal.modules.prolog) provides ISO-compatible
# implementations (truncation toward zero, not floor).
_PROLOG_QUALIFIED_OPS = {
    "//":  "TruncDiv",   # ISO truncate-div (toward zero) vs Python // (floor)
    "mod": "TruncMod",   # ISO mod (sign follows divisor) — floored, like Python %
    "rem": "Rem",        # ISO remainder (sign follows dividend)
}

# ISO evaluable constants (functors of arity 0 in arithmetic context).
# Emitted as math.* attribute references — emit_module adds the matching
# -import_module(math) preamble. epsilon has no math.* name, so it is
# emitted as the numeric literal (sys.float_info.epsilon) instead (F025).
_EVALUABLE_CONSTANTS = {
    "pi":      "math.pi",
    "e":       "math.e",
    "inf":     "math.inf",
    "nan":     "math.nan",
    "epsilon": "2.220446049250313e-16",  # sys.float_info.epsilon
}

# Prolog prefix → clausal equivalent
_PREFIX_MAP = {
    "\\+": "not",
    "-":   "-",
    "\\":  "~",         # bitwise complement
    "+":   "+",
}

# Prolog library paths → clausal module names
_LIBRARY_TO_MODULE: dict[str, str] = {
    "clpfd": "clausal.logic.clpfd",
    "clpz": "clausal.logic.clpfd",
    "clpb": "clausal.logic.clpb",
    "tabling": "clausal.logic.tabling",
    "lists": None,       # built-in, no import needed
    "apply": None,       # built-in
}


# ── Public API ───────────────────────────────────────────────────────


def prolog_to_clausal(source: str, *, dialect: Dialect | None = None) -> str:
    """Translate Prolog source text to clausal source text.

    Parameters
    ----------
    source : str
        Complete Prolog (.pl) source text.
    dialect : Dialect, optional
        Dialect for operator table and name resolution.
        Defaults to SWI-Prolog.
    """
    if dialect is None:
        dialect = Dialect.swi()
    pmodule = parse(source, dialect=dialect)
    return prolog_ast_to_clausal(pmodule, dialect=dialect)


def prolog_ast_to_clausal(pmodule: PModule, *,
                          dialect: Dialect | None = None) -> str:
    """Translate a Prolog AST module to clausal source text."""
    if dialect is None:
        dialect = Dialect.swi()
    emitter = _PrologToClausal(dialect)
    return emitter.emit_module(pmodule)


def emit_clausal_term(term: PTerm, dialect: Dialect | None = None) -> str:
    """Render a single Prolog AST term as clausal syntax."""
    if dialect is None:
        dialect = Dialect.swi()
    emitter = _PrologToClausal(dialect)
    return emitter._emit_term(term)


def emit_clausal_item(item: PItem, dialect: Dialect | None = None) -> str:
    """Render a single Prolog AST item as clausal syntax."""
    if dialect is None:
        dialect = Dialect.swi()
    emitter = _PrologToClausal(dialect)
    return emitter._emit_item(item)


# ── User-defined operator mapping (Step 3.4) ────────────────────────


def load_operator_mapping(path: str | Path) -> dict[str, dict]:
    """Load a user-defined operator mapping file.

    The file is JSON with the structure::

        {
          "operator_mappings": {
            "<>": {"clausal": "NotEqual", "arity": 2},
            ...
          }
        }

    Returns the ``operator_mappings`` dict.
    """
    with open(path) as f:
        data = json.load(f)
    return data.get("operator_mappings", {})


# ── Emitter ──────────────────────────────────────────────────────────


class _PrologToClausal:
    """Translates Prolog AST → clausal source text."""

    def __init__(self, dialect: Dialect,
                 operator_mappings: dict[str, dict] | None = None):
        self._dialect = dialect
        self._user_ops = operator_mappings or {}
        self._data_atoms: set[str] = set()  # atoms used as data values
        # Per-clause variable rename table (reset in _emit_item). Prolog var
        # names are scoped per clause; prolog_var_to_clausal is non-injective
        # (Foo and FOO both → _foo), so without disambiguation a satisfiable
        # clause could silently merge two variables into one (F022).
        self._var_map: dict[str, str] = {}
        self._var_used: set[str] = set()

    def _var_name(self, name: str) -> str:
        """Map a Prolog variable to a unique clausal name within the clause."""
        if name == "_":
            return "_"  # anonymous: every occurrence is independent
        existing = self._var_map.get(name)
        if existing is not None:
            return existing
        base = prolog_var_to_clausal(name)
        candidate = base
        n = 2
        while candidate in self._var_used:
            candidate = f"{base}_{n}"
            n += 1
        self._var_map[name] = candidate
        self._var_used.add(candidate)
        return candidate

    def emit_module(self, pmodule: PModule) -> str:
        """Emit a complete module as clausal source text."""
        lines: list[str] = []
        for item in pmodule.items:
            text = self._emit_item(item)
            if text is not None:
                lines.append(text)
        body = "\n\n".join(lines) + "\n"
        # Prepend auto-generated directives.
        preamble_parts: list[str] = []
        if "prolog." in body:
            preamble_parts.append("-import_module(prolog)")
        if "math." in body:
            preamble_parts.append("-import_module(math)")
        if self._data_atoms:
            atom_list = ", ".join(sorted(self._data_atoms))
            preamble_parts.append(f"-private([{atom_list}])")
        if preamble_parts:
            body = "\n".join(preamble_parts) + "\n\n" + body
        return body

    def _emit_item(self, item: PItem) -> str | None:
        # Variable names are scoped per top-level item (clause/rule/directive).
        self._var_map = {}
        self._var_used = set()
        if isinstance(item, PClause):
            return self._emit_clause(item)
        if isinstance(item, PDCGRule):
            return self._emit_dcg_rule(item)
        if isinstance(item, PDirective):
            return self._emit_directive(item)
        if isinstance(item, PQuery):
            return f"# ?- {self._emit_term(item.body)}"
        if isinstance(item, PComment):
            return f"# {item.text}"
        return None

    # ── Clauses ──────────────────────────────────────────────────────

    def _emit_clause(self, clause: PClause) -> str:
        head = self._emit_head(clause.head)
        if clause.body is None:
            # Fact: trailing comma
            return f"{head},"
        # Rule: head <- (body)
        body = self._emit_body(clause.body)
        return f"{head} <- ({body})"

    def _emit_head(self, term: PTerm) -> str:
        """Emit a clause head as a clausal predicate call."""
        # A ','/2 head is a DCG pushback (`Head, [Tokens] --> Body`), not a
        # callable predicate — emitting it bare produced invalid Python
        # silently (F039). Reject with a clear message.
        if isinstance(term, PCompound) and term.functor == ",":
            raise PrologTranslationError(
                "DCG pushback heads ('Head, [Tokens] --> Body') are not "
                "supported by the translator.\n"
                "Rewrite the grammar rule without a pushback list."
            )
        if isinstance(term, PCompound):
            name = self._predicate_name(term.functor)
            if not term.args:
                return f"{name}()"
            args = ", ".join(self._emit_term(a) for a in term.args)
            return f"{name}({args})"
        if isinstance(term, PAtom):
            name = self._predicate_name(term.name)
            return f"{name}()"
        return self._emit_term(term)

    def _emit_body(self, body: PTerm) -> str:
        """Emit a clause body as comma-separated goals."""
        goals = self._flatten_conjunction(body)
        parts = [self._emit_goal(g) for g in goals]
        return ", ".join(parts)

    def _emit_goal(self, goal: PTerm) -> str:
        """Emit a single goal in body context."""
        # A10-F001: a body-position cut must be REJECTED, not emitted as a
        # dead ``Cut()`` goal (no Cut predicate exists — the query later died
        # with KeyError). Delegate to _emit_atom, which raises the documented
        # PrologTranslationError (the cut-free contract, docs/import.md).
        if isinstance(goal, PAtom) and goal.name == "!":
            return self._emit_atom(goal)
        # Disjunction: (A ; B) → (A or B)
        if isinstance(goal, PCompound) and goal.functor == ";":
            return self._emit_disjunction(goal)
        # If-then: (Cond -> Then) — REJECTED
        if isinstance(goal, PCompound) and goal.functor == "->":
            return self._emit_if_then(goal)
        # Negation: \+(Goal) → not Goal
        if isinstance(goal, PCompound) and goal.functor == "\\+" and len(goal.args) == 1:
            inner = self._emit_goal(goal.args[0])
            return f"not {inner}"
        # Unification: X = Y → X is Y
        if isinstance(goal, PCompound) and goal.functor == "=" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_term(goal.args[1])
            return f"{left} is {right}"
        # Dis-unification: X \= Y → X is not Y
        if isinstance(goal, PCompound) and goal.functor == "\\=" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_term(goal.args[1])
            return f"{left} is not {right}"
        # Arithmetic is: R is Expr → eval_(Expr, R) — the eager arithmetic
        # builtin (the former ':=' operator, now deprecated).
        if isinstance(goal, PCompound) and goal.functor == "is" and len(goal.args) == 2:
            result = self._emit_term(goal.args[0])
            expr = self._emit_expr(goal.args[1])
            return f"eval_({expr}, {result})"
        # Structural equality: X == Y → X == Y
        if isinstance(goal, PCompound) and goal.functor == "==" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_term(goal.args[1])
            return f"{left} == {right}"
        # Structural inequality: X \== Y → X != Y
        if isinstance(goal, PCompound) and goal.functor == "\\==" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_term(goal.args[1])
            return f"{left} != {right}"
        # Comparison operators
        if isinstance(goal, PCompound) and goal.functor in ("<", ">", ">=", "=<") and len(goal.args) == 2:
            left = self._emit_expr(goal.args[0])
            right = self._emit_expr(goal.args[1])
            op = "<=" if goal.functor == "=<" else goal.functor
            return f"{left} {op} {right}"
        # Arithmetic comparison: =:=, =\=
        if isinstance(goal, PCompound) and goal.functor == "=:=" and len(goal.args) == 2:
            left = self._emit_expr(goal.args[0])
            right = self._emit_expr(goal.args[1])
            return f"{left} == {right}"
        if isinstance(goal, PCompound) and goal.functor == "=\\=" and len(goal.args) == 2:
            left = self._emit_expr(goal.args[0])
            right = self._emit_expr(goal.args[1])
            return f"{left} != {right}"
        # member/2 → X in List
        if isinstance(goal, PCompound) and goal.functor == "member" and len(goal.args) == 2:
            elem = self._emit_term(goal.args[0])
            lst = self._emit_term(goal.args[1])
            return f"{elem} in {lst}"
        # Regular compound goal → PascalCase call
        return self._emit_term(goal)

    def _emit_disjunction(self, term: PTerm) -> str:
        """Emit (A ; B) as (A or B). Reject if-then-else."""
        if not isinstance(term, PCompound) or term.functor != ";" or len(term.args) != 2:
            return self._emit_goal(term)

        left, right = term.args
        # If-then-else: (Cond -> Then ; Else) — REJECTED
        if isinstance(left, PCompound) and left.functor == "->" and len(left.args) == 2:
            raise PrologTranslationError(
                "If-then-else (( -> ; )) cannot be translated to Clausal.\n"
                "ISO defines (C -> T ; E) in terms of cut, so it inherits "
                "cut's problems — non-monotonicity, broken completeness, and "
                "unsound interaction with constraints.\n"
                "Rewrite using pure alternatives:\n"
                "  - Reified if-then-else: (THEN if COND else ELSE)\n"
                "  - Separate clauses with dif/2 guards\n"
                "  - CLP(FD) / CLP(B) constraints\n"
                "See: docs/reified_ite.md, docs/for_prolog_programmers.md"
            )

        left_s = self._emit_goal(left)
        right_s = self._emit_goal(right)
        return f"({left_s} or {right_s})"

    def _emit_if_then(self, term: PCompound) -> str:
        """Bare (Cond -> Then) without else — REJECTED."""
        raise PrologTranslationError(
            "If-then (( -> )) cannot be translated to Clausal.\n"
            "The -> operator is defined in terms of cut and inherits "
            "cut's problems.\n"
            "Rewrite using pure alternatives:\n"
            "  - Reified if-then-else: (THEN if COND else ELSE)\n"
            "  - Separate clauses with dif/2 guards\n"
            "See: docs/reified_ite.md, docs/for_prolog_programmers.md"
        )

    # ── DCG rules ────────────────────────────────────────────────────

    def _emit_dcg_rule(self, rule: PDCGRule) -> str:
        # A ','/2 DCG head is a pushback (`Head, [Tokens] --> Body`), which
        # Clausal expresses as `(Head, [Tokens]) >> (Body)`; translate it
        # faithfully rather than mangling it into invalid Python (F039).
        if isinstance(rule.head, PCompound) and rule.head.functor == ",":
            parts = ", ".join(
                self._emit_term(p) for p in self._flatten_conjunction(rule.head)
            )
            head = f"({parts})"
        else:
            head = self._emit_head(rule.head)
        body = self._emit_dcg_body(rule.body)
        return f"{head} >> ({body})"

    def _emit_dcg_body(self, body: PTerm) -> str:
        """Emit DCG rule body."""
        # Conjunction in DCG
        goals = self._flatten_conjunction(body)
        parts = [self._emit_dcg_goal(g) for g in goals]
        return ", ".join(parts)

    def _emit_dcg_goal(self, goal: PTerm) -> str:
        """Emit a single DCG body goal."""
        # Terminal list: [a, b, c]
        if isinstance(goal, PList):
            return self._emit_term(goal)
        # Inline goal: {Goal}
        if isinstance(goal, PCurly):
            return self._emit_goal(goal.body)
        # Pushback: comma([T], ...) — handled as regular term
        # Negation in DCG
        if isinstance(goal, PCompound) and goal.functor == "\\+" and len(goal.args) == 1:
            inner = self._emit_dcg_goal(goal.args[0])
            return f"not {inner}"
        # Disjunction in DCG
        if isinstance(goal, PCompound) and goal.functor == ";":
            return self._emit_disjunction(goal)
        # Regular non-terminal
        return self._emit_term(goal)

    # ── Directives ───────────────────────────────────────────────────

    def _emit_directive(self, directive: PDirective) -> str:
        body = directive.body
        # :- module(Name, Exports)
        if isinstance(body, PCompound) and body.functor == "module" and len(body.args) == 2:
            return self._emit_module_directive(body)
        # :- use_module(library(Lib), Imports) or :- use_module(library(Lib))
        if isinstance(body, PCompound) and body.functor == "use_module":
            return self._emit_use_module(body)
        # :- dynamic pred/N
        if isinstance(body, PCompound) and body.functor == "dynamic":
            return self._emit_meta_directive("dynamic", body)
        # :- discontiguous pred/N
        if isinstance(body, PCompound) and body.functor == "discontiguous":
            return self._emit_meta_directive("discontiguous", body)
        # :- table pred/N
        if isinstance(body, PCompound) and body.functor == "table":
            return self._emit_meta_directive("table", body)
        # :- op(P, T, N) → comment
        if isinstance(body, PCompound) and body.functor == "op" and len(body.args) == 3:
            return f"# operator: op({self._emit_term(body.args[0])}, {self._emit_term(body.args[1])}, {self._emit_term(body.args[2])})"
        # Generic directive
        return f"-{self._emit_term(body)}"

    def _emit_module_directive(self, body: PCompound) -> str:
        name = self._emit_atom_name(body.args[0])
        exports = self._emit_export_list(body.args[1])
        return f"-module({name}, {exports})"

    def _emit_use_module(self, body: PCompound) -> str:
        """Emit :- use_module(...) as -import_from(...) or -import_module(...)."""
        if len(body.args) == 0:
            return f"# use_module({self._emit_term(body)})"

        lib_term = body.args[0]
        lib_name = self._extract_library_name(lib_term)

        if lib_name is not None:
            # library(X) form — check known mapping.
            # A None value means "built-in, no import needed".
            if lib_name in _LIBRARY_TO_MODULE:
                clausal_mod = _LIBRARY_TO_MODULE[lib_name]
                if clausal_mod is None:
                    return f"# library({lib_name}) is built-in — no import needed"
            else:
                # Unknown library — use the name directly as module path.
                clausal_mod = lib_name
        elif isinstance(lib_term, PAtom):
            # Bare atom: use_module(bar) or use_module('./bar')
            # Strip leading ./ from relative paths
            name = lib_term.name
            if name.startswith('./') or name.startswith('.\\'):
                name = name[2:]
            clausal_mod = name
        else:
            return f"# use_module: {self._emit_term(body)}"

        if len(body.args) >= 2:
            # With import list
            imports = self._emit_import_list(body.args[1])
            return f"-import_from({clausal_mod}, {imports})"
        else:
            return f"-import_module({clausal_mod})"

    def _emit_meta_directive(self, kind: str, body: PCompound) -> str:
        """Emit -dynamic(pred/N), -discontiguous(pred/N), -table(pred/N)."""
        if len(body.args) == 1:
            indicator = self._emit_pred_indicator(body.args[0])
            return f"-{kind}({indicator})"
        # Multiple: :- dynamic(a/1, b/2)
        indicators = ", ".join(self._emit_pred_indicator(a) for a in body.args)
        return f"-{kind}({indicators})"

    def _emit_pred_indicator(self, term: PTerm) -> str:
        """Emit pred/N as a predicate indicator."""
        if isinstance(term, PCompound) and term.functor == "/" and len(term.args) == 2:
            name = self._emit_atom_name(term.args[0])
            pascal = self._predicate_name(name)
            arity = self._emit_term(term.args[1])
            return f"{pascal}/{arity}"
        # Comma-separated list: (a/1, b/2)
        if isinstance(term, PCompound) and term.functor == ",":
            parts = self._flatten_conjunction(term)
            return ", ".join(self._emit_pred_indicator(p) for p in parts)
        return self._emit_term(term)

    # ── Terms ────────────────────────────────────────────────────────

    def _emit_term(self, term: PTerm) -> str:
        """Emit a Prolog AST term as clausal syntax."""
        if isinstance(term, PAtom):
            return self._emit_atom(term)
        if isinstance(term, PVar):
            return self._var_name(term.name)
        if isinstance(term, PNumber):
            if isinstance(term.value, float):
                return repr(term.value)
            return str(term.value)
        if isinstance(term, PString):
            return repr(term.value)
        if isinstance(term, PList):
            return self._emit_list(term)
        if isinstance(term, PCurly):
            return "{" + self._emit_term(term.body) + "}"
        if isinstance(term, PCompound):
            return self._emit_compound(term)
        return str(term)

    # Atoms that map to Python builtins and should not be collected as data atoms.
    _BUILTIN_ATOMS = frozenset({"true", "false", "fail", "True", "False", "None"})

    # Prolog spelling -> Clausal spelling for builtin truth atoms. Prolog uses
    # lowercase 'true'/'false'/'fail'; Clausal uses Python 'True'/'False'.
    _BUILTIN_ATOM_REWRITES = {
        "true": "True",
        "false": "False",
        "fail": "False",
    }

    def _emit_atom(self, atom: PAtom) -> str:
        """Emit an atom as a bare name, registering it for ``-private`` declaration.

        Prolog atoms like ``red``, ``foo_bar`` are symbolic constants.  in_
        Clausal they become module-level string variables declared via
        ``-private([red, foo_bar, ...])``, which the EmbedTransformer
        compiles to ``red = "red"`` etc.
        """
        name = atom.name
        # Special atoms that map to Python builtins
        if name in self._BUILTIN_ATOMS:
            return self._BUILTIN_ATOM_REWRITES.get(name, name)
        if name == "!":
            raise PrologTranslationError(
                "Cut (!/0) cannot be translated to Clausal.\n"
                "Clausal intentionally omits cut — it breaks declarative "
                "semantics and monotonicity.\n"
                "Rewrite using pure alternatives:\n"
                "  - dif/2 and constraints for mutual exclusion between clauses\n"
                "  - once(Goal) for first-solution commitment\n"
                "  - First-argument indexing (automatic) for determinism\n"
                "  - Reified if-then-else for conditional branching\n"
                "See: docs/for_prolog_programmers.md"
            )
        if name == "[]":
            return "[]"
        if name == "{}":
            return "{}"
        # A quoted atom, or one whose spelling is not a plain lowercase
        # identifier (space, punctuation, uppercase) or collides with a Python
        # keyword, cannot be emitted as a bare Clausal name — `p('hello world')`
        # / `p(class)` would be a SyntaxError and `p('Foo')` would silently
        # become a variable/predicate reference. Emit a Python string literal
        # instead (F025).
        if getattr(atom, "quoted", False) or not _is_plain_atom_name(name):
            return repr(name)
        # Register as a data atom (will be declared via -private).
        self._data_atoms.add(name)
        return name

    def _emit_compound(self, term: PCompound) -> str:
        """Emit a compound term."""
        functor = term.functor
        args = term.args

        # Control constructs in term/metacall position (e.g. inside findall's
        # goal argument) are rejected the same way as in goal position — the
        # bare fall-through would otherwise emit invalid `->(...)` / `*->(...)`
        # (F024, sibling of A10-F001).
        if functor in ("->", "*->") and len(args) == 2:
            raise PrologTranslationError(
                f"If-then(-else) / soft-cut ('{functor}') cannot be translated "
                "to Clausal, even in a metacall argument.\n"
                "Rewrite using reified conditionals or dif/2 guards.\n"
                "See: docs/reified_ite.md, docs/for_prolog_programmers.md"
            )

        # Standard-order comparison has no Clausal equivalent — the language
        # exposes no standard term order (setof's internal sort is not a
        # user-facing builtin). Reject rather than emit `@<(X, Y)` (F026).
        if functor in ("@<", "@>", "@=<", "@>=") and len(args) == 2:
            raise PrologTranslationError(
                f"Standard-order comparison ('{functor}') cannot be "
                "translated: Clausal has no standard-order term comparison "
                "builtins.\n"
                "Use arithmetic comparison (<, =<, ...) for numbers, or "
                "structural ==/\\== for term identity."
            )

        # Variant equality has no Clausal equivalent (F041 — the designed
        # rejection promised when =@=/\=@= were added to the parser tables).
        if functor in ("=@=", "\\=@=") and len(args) == 2:
            raise PrologTranslationError(
                f"Variant equality ('{functor}') cannot be translated: "
                "Clausal has no term-variance builtin.\n"
                "Rewrite using structural ==/\\== (for identical terms) or "
                "an explicit double copy_term/subsumes check."
            )

        # bagof/setof: strip ISO existential quantifiers (V^Goal) from the
        # goal argument. Clausal's bagof/setof never group by free variables
        # (they collect over all solutions, failing when empty), which is
        # exactly ISO's behaviour when the free variables are ^-quantified —
        # dropping the quantifier is faithful (F026).
        if functor in ("bagof", "setof") and len(args) == 3:
            inner = args[1]
            while (isinstance(inner, PCompound) and inner.functor == "^"
                    and len(inner.args) == 2):
                inner = inner.args[1]
            if inner is not args[1]:
                args = (args[0], inner, args[2])
                term = PCompound(functor, args)

        # (^)/2 anywhere else in goal/term position: in arithmetic context it
        # is exponentiation (handled in _emit_expr → Python **); as a plain
        # goal or data term Clausal has no equivalent — reject rather than
        # emit `^(Y, Goal)` (F026).
        if functor == "^" and len(args) == 2:
            raise PrologTranslationError(
                "The existential quantifier ((^)/2) is only supported inside "
                "the goal argument of bagof/3 or setof/3, where it is "
                "stripped (Clausal's bagof/setof never group by free "
                "variables).\n"
                "In arithmetic context, (^)/2 translates to Python's ** "
                "operator."
            )

        # ','/2 in term position is a tuple, NOT a flattened argument list:
        # emitting it bare turned foo(a, (b, c)) into a foo/3 call (F023).
        if functor == "," and len(args) == 2:
            parts = ", ".join(
                self._emit_term(p) for p in self._flatten_conjunction(term)
            )
            return f"({parts})"

        # Univ: T =.. L → unpack(T, L) (=.. is not valid Clausal syntax) — F033.
        if functor == "=.." and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"unpack({left}, {right})"

        # Module-qualified goal: Module:Goal → Module.Goal(...) (F033).
        if functor == ":" and len(args) == 2 and isinstance(args[0], PAtom):
            module = args[0].name
            goal = args[1]
            if isinstance(goal, PCompound):
                goal_name = _REVERSE_BUILTIN_MAP.get(goal.functor, goal.functor)
                inner = ", ".join(self._emit_term(a) for a in goal.args)
                return f"{module}.{goal_name}({inner})"
            if isinstance(goal, PAtom):
                return f"{module}.{goal.name}()"

        # Check user-defined operator mappings
        if functor in self._user_ops:
            mapping = self._user_ops[functor]
            clausal_name = mapping.get("clausal", functor)
            if len(args) == 2:
                left = self._emit_term(args[0])
                right = self._emit_term(args[1])
                return f"{clausal_name}({left}, {right})"
            elif len(args) == 1:
                operand = self._emit_term(args[0])
                return f"{clausal_name}({operand})"

        # Negation prefix: \+(X) → not X
        if functor == "\\+" and len(args) == 1:
            inner = self._emit_term(args[0])
            return f"not {inner}"

        # Unification: X = Y → X is Y
        if functor == "=" and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{left} is {right}"

        # Dis-unification: X \= Y → X is not Y
        if functor == "\\=" and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{left} is not {right}"

        # Arithmetic is: R is Expr → eval_(Expr, R)
        if functor == "is" and len(args) == 2:
            # R is E → eval_(E, R): the eager arithmetic builtin (the former
            # ':=' operator, now deprecated).
            result = self._emit_term(args[0])
            expr = self._emit_expr(args[1])
            return f"eval_({expr}, {result})"

        # Arithmetic operators (precedence-aware)
        if functor in self._EXPR_PREC and len(args) == 2:
            return self._emit_expr(term)

        # Comparison operators
        if functor in _INFIX_MAP and len(args) == 2:
            clausal_op = _INFIX_MAP[functor]
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{left} {clausal_op} {right}"

        # ISO operators with different semantics → prolog.'//'(X, Y)
        if functor in _PROLOG_QUALIFIED_OPS and len(args) == 2:
            op_name = _PROLOG_QUALIFIED_OPS[functor]
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"prolog.{op_name}({left}, {right})"

        # Prefix operators
        if functor in _PREFIX_MAP and len(args) == 1:
            clausal_op = _PREFIX_MAP[functor]
            operand = self._emit_term(args[0])
            if clausal_op == "not":
                return f"not {operand}"
            return f"{clausal_op}{operand}"

        # Regular compound: functor(args) → PascalCase(args)
        name = self._predicate_name(functor)
        if not args:
            return f"{name}()"
        arg_strs = ", ".join(self._emit_term(a) for a in args)
        return f"{name}({arg_strs})"

    # Python operator precedence (higher number = tighter binding).
    _EXPR_PREC: dict[str, int] = {
        "xor": 1, "\\/": 2, "/\\": 3,
        "<<": 4, ">>": 4,
        "+": 5, "-": 5,
        "*": 6, "/": 6, "div": 6,
        "**": 8, "^": 8,
    }

    def _emit_expr(self, term: PTerm, parent_prec: int = 0) -> str:
        """Emit an arithmetic expression with precedence-aware parenthesization."""
        if isinstance(term, PNumber):
            return str(term.value) if isinstance(term.value, int) else repr(term.value)
        if isinstance(term, PVar):
            return self._var_name(term.name)
        if isinstance(term, PAtom):
            # ISO evaluable constants: X is pi must not emit a bare `pi`
            # name (NameError at runtime) — map to math.* / a literal (F025).
            mapped = _EVALUABLE_CONSTANTS.get(term.name)
            if mapped is not None:
                return mapped
            # Any other atom goes through the normal atom path so it is
            # quoted/registered like an arg-position atom.
            return self._emit_atom(term)
        if isinstance(term, PCompound):
            # ISO operators with different semantics → prolog.Op(X, Y)
            if len(term.args) == 2 and term.functor in _PROLOG_QUALIFIED_OPS:
                left = self._emit_expr(term.args[0])
                right = self._emit_expr(term.args[1])
                op_name = _PROLOG_QUALIFIED_OPS[term.functor]
                return f"prolog.{op_name}({left}, {right})"
            # Arithmetic binary operators
            if len(term.args) == 2 and term.functor in self._EXPR_PREC:
                my_prec = self._EXPR_PREC[term.functor]
                if term.functor in ("**", "^"):
                    # ** is right-associative in Python: the LEFT child needs
                    # parens at equal precedence so (2**3)**2 doesn't collapse
                    # to 2**3**2 == 2**(3**2) (F030). ISO ^ is xfy (also
                    # right-associative), so the same rule applies (F026).
                    left = self._emit_expr(term.args[0], my_prec + 1)
                    right = self._emit_expr(term.args[1], my_prec)
                else:
                    left = self._emit_expr(term.args[0], my_prec)
                    right = self._emit_expr(term.args[1], my_prec + 1)
                op = _INFIX_MAP.get(term.functor, term.functor)
                result = f"{left} {op} {right}"
                if my_prec < parent_prec:
                    result = f"({result})"
                return result
            # Arithmetic unary operators
            if len(term.args) == 1 and term.functor in ("-", "+", "\\"):
                operand = self._emit_expr(term.args[0], 9)
                op = _PREFIX_MAP.get(term.functor, term.functor)
                return f"{op}{operand}"
            # Arithmetic functions
            name = self._predicate_name(term.functor)
            args = ", ".join(self._emit_expr(a) for a in term.args)
            return f"{name}({args})"
        return self._emit_term(term)

    def _emit_list(self, lst: PList) -> str:
        """Emit a list, converting [H|T] to [H, *T]."""
        if not lst.elements and lst.tail is None:
            return "[]"
        parts = [self._emit_term(e) for e in lst.elements]
        if lst.tail is not None:
            tail_s = self._emit_term(lst.tail)
            parts.append(f"*{tail_s}")
        return "[" + ", ".join(parts) + "]"

    # ── Name conversion helpers ──────────────────────────────────────

    def _predicate_name(self, prolog_name: str) -> str:
        """Convert a Prolog predicate/functor name to clausal PascalCase."""
        # Check reverse builtin map first
        clausal_name = _REVERSE_BUILTIN_MAP.get(prolog_name)
        if clausal_name is not None:
            return clausal_name
        # Fall back to snake_to_pascal
        name = snake_to_pascal(prolog_name)
        # A functor whose converted name is not a plain Python identifier
        # (quoted atoms like 'hello world', operator soup from unmapped
        # user ops, keyword collisions like `none` → None) cannot become a
        # Clausal predicate — emitting it bare would be a SyntaxError or a
        # silent rebinding downstream (F035, sibling of the F025 arg-position
        # check in _emit_atom). Reject loudly instead.
        if not name.isidentifier() or keyword.iskeyword(name):
            raise PrologTranslationError(
                f"Prolog functor {prolog_name!r} cannot be translated to a "
                f"Clausal predicate name ({name!r} is not a valid Python "
                "identifier).\n"
                "Only plain (unquoted-style) functor names can name Clausal "
                "predicates. Rename the predicate, or provide a user "
                "operator mapping for operator functors."
            )
        return name

    def _emit_atom_name(self, term: PTerm) -> str:
        """Extract an atom name from a term."""
        if isinstance(term, PAtom):
            return term.name
        return self._emit_term(term)

    def _emit_export_list(self, term: PTerm) -> str:
        """Emit an export list [pred/N, ...]."""
        if isinstance(term, PList):
            items = [self._emit_pred_indicator(e) for e in term.elements]
            return "[" + ", ".join(items) + "]"
        return self._emit_term(term)

    def _emit_import_list(self, term: PTerm) -> str:
        """Emit an import list [pred1, pred2, ...]."""
        if isinstance(term, PList):
            items = []
            for e in term.elements:
                if isinstance(e, PCompound) and e.functor == "/" and len(e.args) == 2:
                    name = self._emit_atom_name(e.args[0])
                    items.append(self._predicate_name(name))
                elif isinstance(e, PAtom):
                    items.append(self._predicate_name(e.name))
                else:
                    items.append(self._emit_term(e))
            return "[" + ", ".join(items) + "]"
        return self._emit_term(term)

    def _extract_library_name(self, term: PTerm) -> str | None:
        """Extract library name from library(Name) term."""
        if isinstance(term, PCompound) and term.functor == "library" and len(term.args) == 1:
            if isinstance(term.args[0], PAtom):
                return term.args[0].name
        if isinstance(term, PAtom):
            return term.name
        return None

    # ── Conjunction/disjunction flattening ────────────────────────────

    def _flatten_conjunction(self, term: PTerm) -> list[PTerm]:
        """flatten nested ',' into a flat list of goals."""
        if isinstance(term, PCompound) and term.functor == "," and len(term.args) == 2:
            left = self._flatten_conjunction(term.args[0])
            right = self._flatten_conjunction(term.args[1])
            return left + right
        return [term]


# ── CLI ──────────────────────────────────────────────────────────────

def _main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="prolog_to_clausal",
        description="Translate Prolog (.pl) source to clausal (.clausal) source.",
    )
    parser.add_argument("input", nargs="?", help="Input .pl file (stdin if omitted)")
    parser.add_argument("-o", "--output", help="Output .clausal file (stdout if omitted)")
    parser.add_argument("--dialect", choices=["swi", "scryer", "iso"], default="swi",
                        help="Prolog dialect (default: swi)")
    parser.add_argument("--operator-map", help="JSON file with user-defined operator mappings")

    args = parser.parse_args()

    # Read input
    if args.input:
        source = Path(args.input).read_text()
    else:
        source = sys.stdin.read()

    # Dialect
    dialect_factories = {"swi": Dialect.swi, "scryer": Dialect.scryer, "iso": Dialect.iso}
    dialect = dialect_factories[args.dialect]()

    # Translate
    result = prolog_to_clausal(source, dialect=dialect)

    # Write output
    if args.output:
        Path(args.output).write_text(result)
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    _main()
