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
from pathlib import Path

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
]


# ── Reverse builtin name map ────────────────────────────────────────
# prolog_name -> clausal_name, built from BUILTIN_NAME_MAP

def _build_reverse_builtin_map() -> dict[str, str]:
    """Build a mapping from Prolog builtin names to clausal names."""
    rev: dict[str, str] = {}
    for clausal_name, (iso, swi, scryer) in BUILTIN_NAME_MAP.items():
        for prolog_name in (iso, swi, scryer):
            if prolog_name is not None and prolog_name not in rev:
                rev[prolog_name] = clausal_name
    return rev


_REVERSE_BUILTIN_MAP = _build_reverse_builtin_map()


# ── Operator mapping: Prolog operators → clausal syntax ──────────────

# Prolog infix → clausal equivalent
_INFIX_MAP = {
    ":-":   "<-",       # clause arrow (body context)
    "is":   ":=",       # arithmetic evaluation
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
    "//":   "//",
    "**":   "**",
    "mod":  "%",
    "rem":  "%",
    ",":    ",",        # conjunction stays
    "=..":  "=..",      # univ — no direct clausal equivalent, keep as comment
    "/\\":  "&",        # bitwise AND
    "\\/":  "|",        # bitwise OR
    "xor":  "^",        # bitwise XOR
    "<<":   "<<",
    ">>":   ">>",       # NOTE: >> is DCG in clausal, so only in arithmetic context
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

    def emit_module(self, pmodule: PModule) -> str:
        """Emit a complete module as clausal source text."""
        lines: list[str] = []
        for item in pmodule.items:
            text = self._emit_item(item)
            if text is not None:
                lines.append(text)
        return "\n\n".join(lines) + "\n"

    def _emit_item(self, item: PItem) -> str | None:
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
        # Disjunction: (A ; B) → (A or B)
        if isinstance(goal, PCompound) and goal.functor == ";":
            return self._emit_disjunction(goal)
        # If-then: (Cond -> Then) → (Cond -> Then)
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
        # Arithmetic is: X is Expr → X := Expr
        if isinstance(goal, PCompound) and goal.functor == "is" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_expr(goal.args[1])
            return f"{left} := {right}"
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
        """Emit (A ; B) as (A or B), handling if-then-else."""
        if not isinstance(term, PCompound) or term.functor != ";" or len(term.args) != 2:
            return self._emit_goal(term)

        left, right = term.args
        # If-then-else: (Cond -> Then ; Else)
        if isinstance(left, PCompound) and left.functor == "->" and len(left.args) == 2:
            cond = self._emit_goal(left.args[0])
            then = self._emit_goal(left.args[1])
            els = self._emit_goal(right)
            return f"({cond} -> {then} or {els})"

        left_s = self._emit_goal(left)
        right_s = self._emit_goal(right)
        return f"({left_s} or {right_s})"

    def _emit_if_then(self, term: PCompound) -> str:
        """Emit (Cond -> Then) without else."""
        cond = self._emit_goal(term.args[0])
        then = self._emit_goal(term.args[1])
        return f"({cond} -> {then})"

    # ── DCG rules ────────────────────────────────────────────────────

    def _emit_dcg_rule(self, rule: PDCGRule) -> str:
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
        return f"-{self._emit_term(body)},"

    def _emit_module_directive(self, body: PCompound) -> str:
        name = self._emit_atom_name(body.args[0])
        exports = self._emit_export_list(body.args[1])
        return f"-module({name}, {exports}),"

    def _emit_use_module(self, body: PCompound) -> str:
        """Emit :- use_module(library(Lib), [...]) as -import_from(...)."""
        if len(body.args) == 0:
            return f"# use_module({self._emit_term(body)})"

        lib_term = body.args[0]
        lib_name = self._extract_library_name(lib_term)
        if lib_name is None:
            return f"# use_module: {self._emit_term(body)}"

        # Check if this is a known library that maps to a clausal module
        clausal_mod = _LIBRARY_TO_MODULE.get(lib_name)
        if clausal_mod is None:
            # Unknown library — use the name directly
            clausal_mod = lib_name

        if len(body.args) >= 2:
            # With import list
            imports = self._emit_import_list(body.args[1])
            return f"-import_from({clausal_mod}, {imports}),"
        else:
            return f"-import_module({clausal_mod}),"

    def _emit_meta_directive(self, kind: str, body: PCompound) -> str:
        """Emit -dynamic(pred/N), -discontiguous(pred/N), -table(pred/N)."""
        if len(body.args) == 1:
            indicator = self._emit_pred_indicator(body.args[0])
            return f"-{kind}({indicator}),"
        # Multiple: :- dynamic(a/1, b/2)
        indicators = ", ".join(self._emit_pred_indicator(a) for a in body.args)
        return f"-{kind}({indicators}),"

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
            return prolog_var_to_clausal(term.name)
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

    def _emit_atom(self, atom: PAtom) -> str:
        """Emit an atom — lowercase atoms stay as atoms in clausal."""
        name = atom.name
        # Special atoms
        if name in ("true", "false", "fail"):
            return name
        if name == "!":
            return "cut"
        if name == "[]":
            return "[]"
        if name == "{}":
            return "{}"
        return name

    def _emit_compound(self, term: PCompound) -> str:
        """Emit a compound term."""
        functor = term.functor
        args = term.args

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

        # Arithmetic is: X is Expr → X := Expr
        if functor == "is" and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_expr(args[1])
            return f"{left} := {right}"

        # Arithmetic/comparison operators
        if functor in _INFIX_MAP and len(args) == 2:
            clausal_op = _INFIX_MAP[functor]
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{left} {clausal_op} {right}"

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

    def _emit_expr(self, term: PTerm) -> str:
        """Emit an arithmetic expression."""
        if isinstance(term, PNumber):
            return str(term.value) if isinstance(term.value, int) else repr(term.value)
        if isinstance(term, PVar):
            return prolog_var_to_clausal(term.name)
        if isinstance(term, PAtom):
            return term.name
        if isinstance(term, PCompound):
            # Arithmetic binary operators
            if len(term.args) == 2 and term.functor in ("+", "-", "*", "/", "//", "**", "mod", "rem", "/\\", "\\/", "xor", "<<", ">>"):
                left = self._emit_expr(term.args[0])
                right = self._emit_expr(term.args[1])
                op = _INFIX_MAP.get(term.functor, term.functor)
                return f"{left} {op} {right}"
            # Arithmetic unary operators
            if len(term.args) == 1 and term.functor in ("-", "+", "\\"):
                operand = self._emit_expr(term.args[0])
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
        return snake_to_pascal(prolog_name)

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
        """Flatten nested ',' into a flat list of goals."""
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
