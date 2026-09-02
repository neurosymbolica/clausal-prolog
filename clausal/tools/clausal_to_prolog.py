"""Clausal → Prolog translation (Phase 1.2).

Pipeline: .clausal source → Python AST → Prolog AST → .pl text

Public API:
    emit_term(pterm, op_table)          — Prolog AST term → text
    emit_item(pitem, op_table)          — Prolog AST clause/directive → text
    emit_module(pmodule, op_table)      — full PModule → text
    clausal_source_to_prolog_ast(src)   — .clausal source → PModule
    clausal_source_to_prolog(src, ...)  — .clausal source → .pl text
"""

from __future__ import annotations

import ast as python_ast
import re

from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PComment, PModule,
    PTerm, PItem,
)
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_dialect import (
    Dialect,
    pascal_to_snake, snake_to_pascal,
    clausal_var_to_prolog, prolog_var_to_clausal,
    resolve_name,
)

# Re-export naming helpers so tests can import from this module.
__all__ = [
    "emit_term", "emit_item", "emit_module",
    "clausal_source_to_prolog", "clausal_source_to_prolog_ast",
    "module_export_signature",
    "pascal_to_snake", "snake_to_pascal",
    "clausal_var_to_prolog", "prolog_var_to_clausal",
    "UntranslatableConstructError",
]


class UntranslatableConstructError(NotImplementedError):
    """Raised in strict mode when source contains constructs with no ISO Prolog equivalent."""

    def __init__(self, constructs: list[str]):
        self.constructs = constructs
        listing = "\n  ".join(constructs)
        super().__init__(
            f"{len(constructs)} untranslatable construct(s):\n  {listing}"
        )


# ── Prolog text emission ─────────────────────────────────────────────

# Operators that are typically displayed with spaces around them
_INFIX_NO_SPACE = frozenset()  # all infix operators get spaces


def _needs_quoting(name: str) -> bool:
    """True if an atom name needs single-quoting in Prolog."""
    if not name:
        return True
    # Alphanumeric atoms starting with lowercase don't need quoting
    if name[0].islower() and name.replace("_", "a").isalnum():
        return False
    # Pure operator-char atoms don't need quoting
    _OP_CHARS = set("+-*/\\^<>=~:.?@#&")
    if all(c in _OP_CHARS for c in name):
        return False
    # Special atoms
    if name in ("[]", "{}", "!", ",", ";"):
        return False
    return True


# ISO 6.4.2 control escape sequences (emitter leg of F034 — the tokenizer
# already reads all of these). NUL uses the octal form `\0\` (the closing
# backslash keeps a following digit from being absorbed into the escape).
_ATOM_ESCAPES = {
    "\\": "\\\\",
    "'":  "\\'",
    "\n": "\\n",
    "\t": "\\t",
    "\r": "\\r",
    "\b": "\\b",
    "\f": "\\f",
    "\v": "\\v",
    "\a": "\\a",
    "\0": "\\0\\",
}


def _quote_atom(name: str) -> str:
    """Single-quote an atom, escaping quotes and control characters.

    Control characters without a named ISO escape are emitted with the
    ISO hex form ``\\xHH\\`` — raw control chars inside a quoted atom are
    not valid ISO Prolog text (F034).
    """
    out: list[str] = []
    for ch in name:
        esc = _ATOM_ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):x}\\")
        else:
            out.append(ch)
    return "'" + "".join(out) + "'"


def emit_term(term: PTerm, op_table: OperatorTable, *,
              context_prec: int = 1201, context_assoc: str = "") -> str:
    """Render a Prolog AST term as text.

    *context_prec* and *context_assoc* control parenthesization based
    on the enclosing operator's precedence and associativity.
    """
    if isinstance(term, PAtom):
        if term.quoted or _needs_quoting(term.name):
            return _quote_atom(term.name)
        return term.name
    if isinstance(term, PVar):
        return term.name
    if isinstance(term, PNumber):
        if isinstance(term.value, float):
            return repr(term.value)
        return str(term.value)
    if isinstance(term, PString):
        return '"' + term.value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(term, PList):
        return _emit_list(term, op_table)
    if isinstance(term, PCurly):
        inner = emit_term(term.body, op_table)
        return "{" + inner + "}"
    if isinstance(term, PCompound):
        return _emit_compound(term, op_table, context_prec, context_assoc)
    return str(term)


def _emit_list(lst: PList, op_table: OperatorTable) -> str:
    """Render a PList as [a, b, c] or [H|T]."""
    if not lst.elements and lst.tail is None:
        return "[]"
    parts = [emit_term(e, op_table, context_prec=999) for e in lst.elements]
    if lst.tail is not None:
        tail_str = emit_term(lst.tail, op_table, context_prec=999)
        return "[" + ", ".join(parts) + "|" + tail_str + "]"
    return "[" + ", ".join(parts) + "]"


def _emit_compound(term: PCompound, op_table: OperatorTable,
                   context_prec: int, context_assoc: str) -> str:
    """Render a PCompound — either as f(a,b) or as infix/prefix operator."""
    functor = term.functor
    arity = len(term.args)

    # Zero-arity compound
    if arity == 0:
        if _needs_quoting(functor):
            return _quote_atom(functor)
        return functor

    # Try infix operator (arity 2)
    if arity == 2:
        entry = op_table.lookup_infix(functor)
        if entry is not None:
            return _emit_infix(term, entry, op_table, context_prec, context_assoc)

    # Try prefix operator (arity 1)
    if arity == 1:
        entry = op_table.lookup_prefix(functor)
        if entry is not None:
            return _emit_prefix(term, entry, op_table, context_prec, context_assoc)

    # Try postfix operator (arity 1)
    if arity == 1:
        entry = op_table.lookup_postfix(functor)
        if entry is not None:
            return _emit_postfix(term, entry, op_table, context_prec, context_assoc)

    # Standard compound: f(a, b, c)
    # Arguments separated by ',' (prec 1000) sit at context_prec 999, so
    # any contained operator with prec >= 1000 (', ;, :- etc.) gets parens.
    args_str = ", ".join(emit_term(a, op_table, context_prec=999) for a in term.args)
    if _needs_quoting(functor):
        return _quote_atom(functor) + "(" + args_str + ")"
    return functor + "(" + args_str + ")"


def _emit_infix(term: PCompound, entry, op_table: OperatorTable,
                context_prec: int, context_assoc: str) -> str:
    """Render infix operator: left op right."""
    prec = entry.precedence
    spec = entry.specifier  # xfx, xfy, yfx

    # Determine child context for left and right operands
    left_prec = prec if spec.startswith("y") else prec - 1
    right_prec = prec if spec.endswith("y") else prec - 1
    left_assoc = spec if spec.startswith("y") else ""
    right_assoc = spec if spec.endswith("y") else ""

    left_str = emit_term(term.args[0], op_table,
                         context_prec=left_prec, context_assoc=left_assoc)
    right_str = emit_term(term.args[1], op_table,
                          context_prec=right_prec, context_assoc=right_assoc)

    # Comma is special: "a, b" not "a , b"
    # Slash in predicate indicators: "f/2" not "f / 2"
    if term.functor == ",":
        result = left_str + ", " + right_str
    elif term.functor == "/":
        result = left_str + "/" + right_str
    else:
        result = left_str + " " + term.functor + " " + right_str

    # Parenthesize if this operator binds looser than the context, or has equal
    # precedence in a non-associative (xfx) parent position. The caller already
    # encodes whether an equal-precedence child is allowed by passing the
    # parent's specifier as context_assoc only on the y-side (see left_assoc /
    # right_assoc above), so an x-side child arrives with context_assoc "xfx".
    if prec > context_prec:
        return "(" + result + ")"
    if prec == context_prec and context_assoc == "xfx":
        return "(" + result + ")"
    return result


def _emit_prefix(term: PCompound, entry, op_table: OperatorTable,
                 context_prec: int, context_assoc: str) -> str:
    """Render prefix operator: op arg."""
    prec = entry.precedence
    spec = entry.specifier  # fx or fy

    arg_prec = prec if spec == "fy" else prec - 1
    arg_str = emit_term(term.args[0], op_table, context_prec=arg_prec)

    result = term.functor + " " + arg_str

    if prec > context_prec:
        return "(" + result + ")"
    return result


def _emit_postfix(term: PCompound, entry, op_table: OperatorTable,
                  context_prec: int, context_assoc: str) -> str:
    """Render postfix operator: arg op."""
    prec = entry.precedence
    spec = entry.specifier  # xf or yf

    arg_prec = prec if spec == "yf" else prec - 1
    arg_str = emit_term(term.args[0], op_table, context_prec=arg_prec)

    result = arg_str + " " + term.functor

    if prec > context_prec:
        return "(" + result + ")"
    return result


# ── Item emission ────────────────────────────────────────────────────

def emit_item(item: PItem, op_table: OperatorTable) -> str:
    """Render a single PItem (clause, DCG rule, directive) as Prolog text."""
    if isinstance(item, PClause):
        head_str = emit_term(item.head, op_table)
        if item.body is None:
            return head_str + ".\n"
        body_str = _emit_body(item.body, op_table)
        return head_str + " :-\n    " + body_str + ".\n"
    if isinstance(item, PDCGRule):
        head_str = emit_term(item.head, op_table)
        body_str = _emit_dcg_body(item.body, op_table)
        return head_str + " -->\n    " + body_str + ".\n"
    if isinstance(item, PDirective):
        body_str = emit_term(item.body, op_table)
        return ":- " + body_str + ".\n"
    if isinstance(item, PComment):
        return "/* " + item.text + " */\n"
    # PQuery
    body_str = emit_term(item.body, op_table)
    return "?- " + body_str + ".\n"


def _emit_body(body: PTerm, op_table: OperatorTable) -> str:
    """Render a clause body, handling conjunction layout."""
    # Flatten top-level conjunctions for indented layout
    goals = _flatten_conjunction(body)
    if len(goals) == 1:
        return emit_term(goals[0], op_table)
    parts = [emit_term(g, op_table, context_prec=999) for g in goals]
    return (",\n    ").join(parts)


def _emit_dcg_body(body: PTerm, op_table: OperatorTable) -> str:
    """Render a DCG rule body."""
    # DCG bodies use comma-separated items
    goals = _flatten_conjunction(body)
    if len(goals) == 1:
        return emit_term(goals[0], op_table)
    parts = [emit_term(g, op_table, context_prec=999) for g in goals]
    return ", ".join(parts)


def _flatten_conjunction(term: PTerm) -> list[PTerm]:
    """flatten nested ','(A, B) into a flat list of goals."""
    if isinstance(term, PCompound) and term.functor == "," and len(term.args) == 2:
        return _flatten_conjunction(term.args[0]) + _flatten_conjunction(term.args[1])
    return [term]


# ── Module emission ──────────────────────────────────────────────────

def emit_module(pmodule: PModule, op_table: OperatorTable) -> str:
    """Render a full PModule as Prolog source text."""
    parts = []
    for item in pmodule.items:
        parts.append(emit_item(item, op_table))
    return "\n".join(parts)


# ── Clausal source → Prolog AST conversion ───────────────────────────

def _is_constant_name(identifier: str) -> bool:
    """True for the module-constant lexical class (``_PI_``, ``_円周率_``).

    Mirrors ``term_rewriting._is_constant_name``; kept local so this module
    stays free of an engine import.
    """
    return (
        len(identifier) >= 3
        and identifier[0] == "_" and identifier[-1] == "_"
        and identifier[1] != "_" and identifier[-2] != "_"
        and not identifier[1].isdigit()
    )


def _is_logic_var_name(identifier: str) -> bool:
    """Return True if identifier should be treated as a logic variable.

    Bare ``_`` stays a variable here (translation context) — pinned by
    test_var_classifier_conformance, which also pins the constant-shape
    exclusion below.
    """
    if identifier == "_":
        return True
    if identifier.startswith("__"):
        return False
    if _is_constant_name(identifier):
        return False
    if identifier.startswith("_"):
        return True
    return identifier.isupper()


def _leftmost_usub(node):
    """Find the leftmost USub in a Python AST expression (for <- detection).

    Returns (usub_node, depth) or (None, 0).
    """
    if isinstance(node, python_ast.UnaryOp) and isinstance(node.op, python_ast.USub):
        return node, 0
    if isinstance(node, python_ast.BinOp):
        result, depth = _leftmost_usub(node.left)
        if result is not None:
            return result, depth + 1
    if isinstance(node, python_ast.Compare):
        result, depth = _leftmost_usub(node.left)
        if result is not None:
            return result, depth + 1
    return None, 0


class _ClausalToProlog:
    """Convert Python AST (from .clausal source) to Prolog AST.

    Recognizes clausal DSL patterns: trailing-comma facts, <- rules,
    >> DCG rules, -directives.
    """

    def __init__(self, dialect: Dialect, strict: bool = False):
        self.dialect = dialect
        self.strict = strict
        self._items: list[PItem] = []
        self._warnings: list[str] = []
        self._all_warnings: list[str] = []
        # Per-clause variable rename table (reset per top-level item).
        # clausal_var_to_prolog is non-injective (_result and RESULT both →
        # Result), so without disambiguation two distinct clausal variables
        # silently merge into one Prolog variable (F022). Mirrors
        # _PrologToClausal._var_name.
        self._var_map: dict[str, str] = {}
        self._var_used: set[str] = set()

    def _prolog_var_name(self, name: str) -> str:
        """Map a clausal variable to a unique Prolog name within the clause."""
        if name == "_":
            return "_"  # anonymous: every occurrence is independent
        existing = self._var_map.get(name)
        if existing is not None:
            return existing
        base = clausal_var_to_prolog(name)
        candidate = base
        n = 2
        while candidate in self._var_used:
            candidate = f"{base}{n}"
            n += 1
        self._var_map[name] = candidate
        self._var_used.add(candidate)
        return candidate

    def _add_warning(self, construct: str) -> None:
        """Record an untranslatable construct warning."""
        self._warnings.append(construct)
        self._all_warnings.append(construct)

    def convert_module(self, tree: python_ast.Module) -> PModule:
        """Convert a full Python AST Module to a PModule."""
        for stmt in tree.body:
            self._warnings.clear()
            # Variable names are scoped per top-level item (F022).
            self._var_map = {}
            self._var_used = set()
            item = self._convert_stmt(stmt)
            # Emit any warnings accumulated during conversion
            for w in self._warnings:
                self._items.append(PComment(
                    f"WARNING: untranslatable clausal construct: {w}\n"
                    f"   Replace with Prolog equivalent manually."
                ))
            if item is not None:
                if isinstance(item, list):
                    self._items.extend(item)
                else:
                    self._items.append(item)

        # Post-pass: (1) keep only locally-defined predicates in :- module
        # exports. Scryer raises permission_error(...
        # module_does_not_contain_claimed_export...) on an export with no
        # backing clause (signature-only kernels, term constructors like
        # cite/1, 0-arity atoms), so a name only ever *declared* in the
        # export list must not survive into the emitted directive.
        # (2) emit :- discontiguous(Name/Arity) for every predicate whose
        # clause run is interrupted by another item — Scryer treats an
        # interrupted run as a silent redefinition, so leaving it unmarked
        # is a correctness hazard, not a style nicety.
        defined: set[tuple[str, int]] = set()
        existing_discontiguous: set[tuple[str, int]] = set()
        seen_order: list[tuple[str, int]] = []   # first-appearance order
        seen_set: set[tuple[str, int]] = set()
        interrupted: set[tuple[str, int]] = set()
        last_key: tuple[str, int] | None = None
        for item in self._items:
            dcg_key = _dcg_head_key(item)
            if dcg_key is not None:
                defined.add(dcg_key)

            existing_discontiguous |= _existing_discontiguous_indicators(item)

            # Run-tracking covers both PClause and PDCGRule (+2 arity) —
            # an interrupted DCG rule run is the same Scryer silent-
            # redefinition hazard as an interrupted plain clause run.
            key = _run_key(item)
            if key is None:
                continue
            defined.add(key)  # no-op when this is the dcg_key already added above
            if key != last_key and key in seen_set:
                interrupted.add(key)
            if key not in seen_set:
                seen_order.append(key)
                seen_set.add(key)
            last_key = key

        discontiguous_directives = [
            PDirective(PCompound("discontiguous", (
                PCompound("/", (PAtom(name), PNumber(arity))),
            )))
            for name, arity in seen_order
            if (name, arity) in interrupted and (name, arity) not in existing_discontiguous
        ]

        rewritten: list[PItem] = []
        module_seen = False
        for item in self._items:
            if _is_module_directive(item):
                rewritten.append(_filter_module_exports(item, defined))
                rewritten.extend(discontiguous_directives)
                module_seen = True
            else:
                rewritten.append(item)
        if not module_seen:
            rewritten = discontiguous_directives + rewritten
        self._items = rewritten

        if self.strict and self._all_warnings:
            raise UntranslatableConstructError(list(self._all_warnings))
        return PModule(tuple(self._items))

    def _convert_stmt(self, stmt) -> PItem | list[PItem] | None:
        """Convert a top-level statement to PItem(s)."""
        if not isinstance(stmt, python_ast.Expr):
            return None

        value = stmt.value

        # -directive(...): unary minus on a call
        if (isinstance(value, python_ast.UnaryOp)
                and isinstance(value.op, python_ast.USub)
                and isinstance(value.operand, python_ast.Call)
                and isinstance(value.operand.func, python_ast.Name)):
            return self._convert_directive(value.operand)

        # Trailing-comma fact: Foo(1, 2),
        if (isinstance(value, python_ast.Tuple)
                and len(value.elts) == 1
                and isinstance(value.elts[0], python_ast.Call)):
            head = self._convert_head(value.elts[0])
            return PClause(head)

        # Bare fact (no trailing comma): Foo(1, 2)
        if isinstance(value, python_ast.Call):
            head = self._convert_head(value)
            return PClause(head)

        # head <- body (Compare with Lt followed by USub)
        if isinstance(value, python_ast.Compare):
            arrow = self._detect_arrow(value)
            if arrow is not None:
                head_ast, body_ast = arrow
                head = self._convert_head(head_ast)
                body = self._convert_expr(body_ast)
                return PClause(head, body)

        # head >> body (DCG rule — RShift)
        if (isinstance(value, python_ast.BinOp)
                and isinstance(value.op, python_ast.RShift)):
            head = self._convert_expr(value.left)
            body = self._convert_dcg_body(value.right)
            return PDCGRule(head, body)

        return None

    def _detect_arrow(self, compare: python_ast.Compare):
        """Detect <- pattern in a Compare node."""
        if not compare.ops or not isinstance(compare.ops[0], python_ast.Lt):
            return None
        first_comp = compare.comparators[0]
        usub_node, depth = _leftmost_usub(first_comp)
        if usub_node is None:
            return None
        if depth > 0 or len(compare.ops) > 1:
            return None
        return compare.left, usub_node.operand

    def _convert_directive(self, call: python_ast.Call) -> PItem | list[PItem] | None:
        """Convert a -directive(...) call."""
        name = call.func.id

        if name == "module":
            if self.dialect.module_system == "none":
                # GNU Prolog has no module system — skip module declarations
                return None
            return self._convert_module_directive(call)
        if name == "import_from":
            if self.dialect.module_system == "none":
                # GNU Prolog: library predicates are built-in, no import needed
                return None
            return self._convert_import_from(call)
        if name == "import_module":
            if self.dialect.module_system == "none":
                return None
            return self._convert_import_module(call)
        if name == "private":
            # Private is not emitted in Prolog (module exports handle visibility)
            return None
        if name == "constants":
            raise NotImplementedError(
                "clausal_to_prolog: -constants files are not translatable "
                "yet — Prolog has no constants; inlining is tracked in "
                "implementation_plans/module-level-constants.md")
        if name in ("dynamic", "discontiguous", "table"):
            return self._convert_meta_directive(name, call)
        # Generic directive
        args = tuple(self._convert_expr(a) for a in call.args)
        return PDirective(PCompound(name, args))

    def _convert_module_directive(self, call: python_ast.Call) -> PDirective:
        """Convert -module(name, [exports])."""
        mod_name = self._get_string_or_name(call.args[0])
        exports = []
        if len(call.args) > 1 and isinstance(call.args[1], python_ast.List):
            for elt in call.args[1].elts:
                if isinstance(elt, python_ast.Call) and isinstance(elt.func, python_ast.Name):
                    functor = resolve_name(elt.func.id, self.dialect)
                    arity = len(elt.args)
                    exports.append(PCompound("/", (PAtom(functor), PNumber(arity))))
                elif isinstance(elt, python_ast.Name):
                    functor = resolve_name(elt.id, self.dialect)
                    exports.append(PCompound("/", (PAtom(functor), PNumber(0))))
        export_list = PList(tuple(exports))
        return PDirective(PCompound("module", (PAtom(mod_name), export_list)))

    def _convert_import_from(self, call: python_ast.Call) -> PDirective | PComment:
        """Convert -import_from(module, [names]).

        Uses the dialect's library_map to resolve known clausal modules to
        Prolog library(...) form. Python-only modules emit a warning.
        """
        mod_path = self._get_string_or_name(call.args[0])

        # Check if this is a Python-only module (no Prolog equivalent)
        if mod_path.startswith("py.") or mod_path.startswith("clausal.modules.py."):
            self._add_warning(f"-import_from({mod_path}, ...)")
            return PComment(
                f"WARNING: Python-only module import: -import_from({mod_path}, ...)\n"
                f"   No Prolog equivalent available."
            )

        # Resolve via dialect library_map, or fallback to path
        library_name = self.dialect.library_map.get(mod_path)
        if library_name is not None:
            # Known library: parse "library(clpfd)" → library(clpfd).
            lib_inner = library_name[len("library("):-1]  # "clpfd"
            prolog_mod = PCompound("library", (PAtom(lib_inner),))
        else:
            # Unknown: use plain path
            prolog_path = mod_path.replace(".", "/")
            prolog_mod = PAtom(prolog_path, quoted=True)

        imports = []
        if len(call.args) > 1 and isinstance(call.args[1], python_ast.List):
            for elt in call.args[1].elts:
                if isinstance(elt, python_ast.Call) and isinstance(elt.func, python_ast.Name):
                    functor = resolve_name(elt.func.id, self.dialect)
                    arity = len(elt.args)
                    imports.append(PCompound("/", (PAtom(functor), PNumber(arity))))
                elif isinstance(elt, python_ast.Name):
                    functor = resolve_name(elt.id, self.dialect)
                    imports.append(PAtom(functor))

        import_list = PList(tuple(imports))
        return PDirective(PCompound("use_module", (prolog_mod, import_list)))

    def _convert_import_module(self, call: python_ast.Call) -> PDirective | PComment:
        """Convert -import_module(module)."""
        mod_path = self._get_string_or_name(call.args[0])

        if mod_path.startswith("py.") or mod_path.startswith("clausal.modules.py."):
            self._add_warning(f"-import_module({mod_path})")
            return PComment(
                f"WARNING: Python-only module import: -import_module({mod_path})\n"
                f"   No Prolog equivalent available."
            )

        library_name = self.dialect.library_map.get(mod_path)
        if library_name is not None:
            lib_inner = library_name[len("library("):-1]
            prolog_mod = PCompound("library", (PAtom(lib_inner),))
        else:
            prolog_path = mod_path.replace(".", "/")
            prolog_mod = PAtom(prolog_path, quoted=True)
        return PDirective(PCompound("use_module", (prolog_mod,)))

    def _convert_meta_directive(self, name: str, call: python_ast.Call) -> PDirective | list:
        """Convert -dynamic(pred/arity), -table(...), -discontiguous(...)."""
        specs = []
        for arg in call.args:
            spec = self._convert_pred_spec(arg)
            if spec is not None:
                specs.append(spec)

        if len(specs) == 1:
            directive = PDirective(PCompound(name, (specs[0],)))
        else:
            directive = PDirective(PCompound(name, (PList(tuple(specs)),)))

        # GNU Prolog has no tabling support — emit warning comment
        if name == "table" and not self.dialect.tabling_directive:
            return PComment(
                "WARNING: GNU Prolog does not support tabling.\n"
                "   :- table directive skipped."
            )

        # Scryer needs :- use_module(library(tabling)) before :- table
        if name == "table" and self.dialect.name == "scryer":
            use_tabling = PDirective(PCompound("use_module", (
                PCompound("library", (PAtom("tabling"),)),
            )))
            return [use_tabling, directive]
        return directive

    def _convert_pred_spec(self, node) -> PTerm | None:
        """Convert a predicate specification like Foo(X, Y) to foo/2."""
        if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Name):
            functor = resolve_name(node.func.id, self.dialect)
            arity = len(node.args)
            return PCompound("/", (PAtom(functor), PNumber(arity)))
        if isinstance(node, python_ast.Name):
            functor = resolve_name(node.id, self.dialect)
            return PAtom(functor)
        return None

    def _convert_head(self, call) -> PTerm:
        """Convert a clause head (a Call node) to a PCompound."""
        if isinstance(call, python_ast.Call) and isinstance(call.func, python_ast.Name):
            functor = resolve_name(call.func.id, self.dialect)
            args = [self._convert_expr(a) for a in call.args]
            for kw in call.keywords:
                args.append(self._convert_expr(kw.value))
            args = tuple(args)
            if not args:
                return PAtom(functor)
            return PCompound(functor, args)
        return self._convert_expr(call)

    def _convert_expr(self, node) -> PTerm:
        """Convert a Python AST expression node to a Prolog AST term."""
        if isinstance(node, python_ast.Constant):
            return self._convert_constant(node.value)

        if isinstance(node, python_ast.Name):
            return self._convert_name(node.id)

        if isinstance(node, python_ast.Call):
            return self._convert_call(node)

        if isinstance(node, python_ast.List):
            return self._convert_list(node)

        if isinstance(node, python_ast.Tuple):
            # Single-element tuple used for trailing-comma facts in nested context
            if len(node.elts) == 1:
                return self._convert_expr(node.elts[0])
            # Multi-element tuple → Prolog comma-separated (conjunction-like)
            if len(node.elts) >= 2:
                result = self._convert_expr(node.elts[-1])
                for elt in reversed(node.elts[:-1]):
                    result = PCompound(",", (self._convert_expr(elt), result))
                return result
            return PAtom("true")

        if isinstance(node, python_ast.BoolOp):
            return self._convert_boolop(node)

        if isinstance(node, python_ast.UnaryOp):
            return self._convert_unaryop(node)

        if isinstance(node, python_ast.BinOp):
            return self._convert_binop(node)

        if isinstance(node, python_ast.Compare):
            return self._convert_compare(node)

        if isinstance(node, python_ast.IfExp):
            return self._convert_ifexp(node)

        # python_ast.NamedExpr (':=') no longer reaches here: the Clausal
        # transformer rejects it with a SyntaxError (use eval_/2, ==, or is).

        if isinstance(node, python_ast.Starred):
            # *X in list context — handled by _convert_list
            return self._convert_expr(node.value)

        # Attribute access: mod.pred
        if isinstance(node, python_ast.Attribute):
            base = self._convert_expr(node.value)
            if isinstance(base, PAtom):
                return PAtom(base.name + ":" + node.attr)
            return PCompound(":", (base, PAtom(node.attr)))

        # f-string: f"Hello {Name}" → format/2 (SWI) or warning
        if isinstance(node, python_ast.JoinedStr):
            return self._convert_fstring(node)

        # Dict literal → SWI dict or warning
        if isinstance(node, python_ast.Dict):
            return self._convert_dict(node)

        # Set literal: single-element sets are DCG inline goals {Goal}
        if isinstance(node, python_ast.Set):
            if len(node.elts) == 1:
                # {Goal} — DCG inline goal
                return PCurly(self._convert_expr(node.elts[0]))
            self._add_warning("set literal {" + ", ".join(
                python_ast.unparse(e) for e in node.elts
            ) + "}")
            return PAtom("???")

        # Fallback: no conversion rule for this Python AST node type
        self._add_warning(f"unsupported expression: {python_ast.unparse(node)}")
        return PAtom("???")

    def _convert_constant(self, value) -> PTerm:
        """Convert a Python constant to a Prolog term."""
        if isinstance(value, bool):
            return PAtom("true" if value else "false")
        if isinstance(value, int):
            return PNumber(value)
        if isinstance(value, float):
            return PNumber(value)
        if isinstance(value, str):
            return PString(value)
        if value is None:
            return PAtom("none")
        return PAtom(str(value))

    def _convert_name(self, name: str) -> PTerm:
        """Convert a Python name to PVar or PAtom."""
        if name == "_":
            return PVar("_")
        # ``Undefined`` — the Kleene (K3) third truth value builtin — maps OUTBOUND
        # to the plain Prolog atom ``undefined``, the spelling XSB and SWI use for
        # the well-founded third value (originally ``unknown``, decision 4 of
        # todo/kleene-unknown-builtin-and-stdlib.md; renamed with the builtin).
        # This mapping is DELIBERATELY asymmetric: ``prolog_to_clausal`` is left
        # unchanged, so an inbound atom ``undefined`` stays a plain atom rather
        # than being rewritten to the builtin — auto-rewriting would silently
        # change the identity semantics of existing Prolog imports.
        # (``pascal_to_snake`` would also yield ``undefined`` here, but this
        # explicit case documents the intent and pins it against future
        # name-resolution changes.)
        if name == "Undefined":
            return PAtom("undefined")
        if _is_logic_var_name(name):
            return PVar(self._prolog_var_name(name))
        # Atoms: lowercase or PascalCase predicate name
        return PAtom(resolve_name(name, self.dialect))

    # Reverse mapping from clausal qualified names (e.g. prolog.TruncDiv)
    # back to Prolog infix operators.  These are the operators that
    # prolog_to_clausal emits as ``prolog.<Name>(X, Y)`` because their
    # ISO semantics differ from Python's.
    _QUALIFIED_OP_REVERSE: dict[tuple[str, str], str] = {
        ("prolog", "TruncDiv"): "//",
        ("prolog", "TruncMod"): "mod",
        ("prolog", "Rem"):      "rem",
    }

    def _convert_call(self, node: python_ast.Call) -> PTerm:
        """Convert a function call to a PCompound."""
        if isinstance(node.func, python_ast.Name):
            # Clausal has no cut: a Cut() goal in source is a call to an
            # undefined predicate, and exporting it (as `cut` or as `!`)
            # would launder cut through cut-free Clausal (F036). Reject.
            if node.func.id == "Cut":
                from clausal.tools.prolog_to_clausal import PrologTranslationError
                raise PrologTranslationError(
                    "Cut() cannot be translated to Prolog.\n"
                    "Clausal has no Cut predicate — cut is intentionally "
                    "omitted (it breaks declarative semantics and "
                    "monotonicity), so a Cut() goal in Clausal source is "
                    "already an error and must not be exported as Prolog "
                    "!/0 or as an undefined `cut` predicate.\n"
                    "Rewrite using once/1, dif/2 guards, or reified "
                    "conditionals. See: docs/for_prolog_programmers.md"
                )
            if node.func.id == "eval_" and len(node.args) == 2 \
                    and not node.keywords:
                # eval_(EXPR, RESULT) — eager arithmetic evaluate-and-bind —
                # is Prolog's is/2: RESULT is EXPR.
                expr = self._convert_expr(node.args[0])
                result = self._convert_expr(node.args[1])
                return PCompound("is", (result, expr))
            functor = resolve_name(node.func.id, self.dialect)
        elif isinstance(node.func, python_ast.Attribute):
            # Check for qualified operator calls (e.g. prolog.TruncDiv)
            # that should be emitted as infix operators.
            op = self._try_qualified_op(node.func, node.args)
            if op is not None:
                return op
            # Qualified call: mod.pred(...)
            functor = self._qualified_name(node.func)
        else:
            self._add_warning(f"unsupported call target: {python_ast.unparse(node.func)}")
            functor = "???"

        args = [self._convert_expr(a) for a in node.args]
        # Keyword args become positional (kwarg names are field labels in clausal)
        for kw in node.keywords:
            args.append(self._convert_expr(kw.value))
        args = tuple(args)
        return PCompound(functor, args)

    def _try_qualified_op(
        self, attr: python_ast.Attribute, args: list,
    ) -> PTerm | None:
        """If *attr* is a qualified operator (e.g. ``prolog.TruncDiv``),
        return the corresponding Prolog infix ``PCompound``; else ``None``."""
        if not isinstance(attr.value, python_ast.Name) or len(args) != 2:
            return None
        key = (attr.value.id, attr.attr)
        op_str = self._QUALIFIED_OP_REVERSE.get(key)
        if op_str is None:
            return None
        left = self._convert_expr(args[0])
        right = self._convert_expr(args[1])
        return PCompound(op_str, (left, right))

    def _qualified_name(self, attr: python_ast.Attribute) -> str:
        """Get a qualified name from an Attribute node."""
        if isinstance(attr.value, python_ast.Name):
            base = resolve_name(attr.value.id, self.dialect)
            pred = resolve_name(attr.attr, self.dialect)
            return base + ":" + pred
        return resolve_name(attr.attr, self.dialect)

    def _convert_list(self, node: python_ast.List) -> PTerm:
        """Convert a Python list literal to a PList.

        Handles [H, *T] → [H|T] (star-unpack as list tail).
        """
        elements = []
        tail = None
        for i, elt in enumerate(node.elts):
            if isinstance(elt, python_ast.Starred):
                # *T is the tail — must be the last element
                tail = self._convert_expr(elt.value)
                # Elements before starred are the head elements
                break
            elements.append(self._convert_expr(elt))
        else:
            # No starred element — proper list
            return PList(tuple(elements))

        return PList(tuple(elements), tail=tail)

    def _convert_boolop(self, node: python_ast.BoolOp) -> PTerm:
        """Convert 'and'/'or' to ','/';'."""
        if isinstance(node.op, python_ast.And):
            op = ","
        else:
            op = ";"

        result = self._convert_expr(node.values[-1])
        for val in reversed(node.values[:-1]):
            result = PCompound(op, (self._convert_expr(val), result))
        return result

    def _convert_unaryop(self, node: python_ast.UnaryOp) -> PTerm:
        """Convert unary operators."""
        if isinstance(node.op, python_ast.Not):
            return PCompound("\\+", (self._convert_expr(node.operand),))
        if isinstance(node.op, python_ast.USub):
            inner = self._convert_expr(node.operand)
            if isinstance(inner, PNumber):
                return PNumber(-inner.value)
            return PCompound("-", (inner,))
        if isinstance(node.op, python_ast.UAdd):
            # ++expr is Python interop escape — untranslatable
            if (isinstance(node.operand, python_ast.UnaryOp)
                    and isinstance(node.operand.op, python_ast.UAdd)):
                self._add_warning("++(" + python_ast.unparse(node.operand.operand) + ")")
                return PAtom("???")
            return self._convert_expr(node.operand)
        if isinstance(node.op, python_ast.Invert):
            return PCompound("\\", (self._convert_expr(node.operand),))
        return self._convert_expr(node.operand)

    def _convert_binop(self, node: python_ast.BinOp) -> PTerm:
        """Convert binary operators to Prolog operators."""
        left = self._convert_expr(node.left)
        right = self._convert_expr(node.right)

        op_map = {
            python_ast.Add: "+",
            python_ast.Sub: "-",
            python_ast.Mult: "*",
            python_ast.Div: "/",
            # Clausal/Python // is floored; Prolog // truncates toward zero, so
            # emit SWI/Scryer `div` (floored) to preserve semantics (F031). The
            # forward direction routes Prolog // through prolog.TruncDiv for the
            # same reason. Python % and Prolog mod are both floored — mod is OK.
            python_ast.FloorDiv: "div",
            python_ast.Mod: "mod",
            python_ast.Pow: "**",
            python_ast.BitAnd: "/\\",
            python_ast.BitOr: "\\/",
            python_ast.BitXor: "xor",
            python_ast.LShift: "<<",
            python_ast.RShift: ">>",
        }
        op_str = op_map.get(type(node.op))
        if op_str is None:
            self._add_warning(f"unsupported operator: {type(node.op).__name__}")
            op_str = "???"
        return PCompound(op_str, (left, right))

    @staticmethod
    def _is_arith_operand(node: python_ast.expr) -> bool:
        """True if *node* is a compound arithmetic expression.

        Used to distinguish arithmetic `==`/`!=` (`X == Y + 1`, an evaluation)
        from structural `==`/`!=` (`X == foo`), so the former round-trips to
        Prolog `=:=`/`=\\=` rather than `==`/`\\==` (F032).
        """
        if isinstance(node, python_ast.BinOp):
            return True
        if isinstance(node, python_ast.UnaryOp) and isinstance(
            node.op, (python_ast.USub, python_ast.UAdd)
        ):
            return True
        return False

    def _convert_compare(self, node: python_ast.Compare) -> PTerm:
        """Convert comparison operators.

        Handles special clausal patterns:
        - X is Y → X = Y (Unify)
        - X is not Y → dif(X, Y) (DoesNotUnify)
        - X == Y → X == Y (structural) / X =:= Y+1 (arithmetic operand)
        - X != Y → X \\== Y (structural) / X =\\= Y+1 (arithmetic operand)
        """
        # First check for <- arrow (should already be handled at statement level)
        # Handle single comparison
        if len(node.ops) == 1:
            left = self._convert_expr(node.left)
            right = self._convert_expr(node.comparators[0])
            op = node.ops[0]

            if isinstance(op, python_ast.Is):
                # Check for "is not"
                if (isinstance(node.comparators[0], python_ast.Compare)
                        and len(node.comparators[0].ops) == 1
                        and isinstance(node.comparators[0].ops[0], python_ast.Not)):
                    # This shouldn't happen with standard Python parsing
                    pass
                return PCompound("=", (left, right))

            if isinstance(op, python_ast.IsNot):
                return PCompound("dif", (left, right))

            if isinstance(op, python_ast.Eq):
                arith = (self._is_arith_operand(node.left)
                         or self._is_arith_operand(node.comparators[0]))
                return PCompound("=:=" if arith else "==", (left, right))

            if isinstance(op, python_ast.NotEq):
                arith = (self._is_arith_operand(node.left)
                         or self._is_arith_operand(node.comparators[0]))
                return PCompound("=\\=" if arith else "\\==", (left, right))

            if isinstance(op, python_ast.Lt):
                # <- is Lt + USub (handled at statement level); pure Lt is <.
                return PCompound("<", (left, right))

            if isinstance(op, python_ast.LtE):
                return PCompound("=<", (left, right))

            if isinstance(op, python_ast.Gt):
                return PCompound(">", (left, right))

            if isinstance(op, python_ast.GtE):
                return PCompound(">=", (left, right))

        # Multi-comparison: chain into conjunction
        parts = []
        prev = self._convert_expr(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self._convert_expr(comp)
            if isinstance(op, python_ast.Is):
                parts.append(PCompound("=", (prev, right)))
            elif isinstance(op, python_ast.IsNot):
                parts.append(PCompound("dif", (prev, right)))
            elif isinstance(op, python_ast.Eq):
                parts.append(PCompound("==", (prev, right)))
            elif isinstance(op, python_ast.NotEq):
                parts.append(PCompound("\\==", (prev, right)))
            elif isinstance(op, python_ast.Lt):
                parts.append(PCompound("<", (prev, right)))
            elif isinstance(op, python_ast.LtE):
                parts.append(PCompound("=<", (prev, right)))
            elif isinstance(op, python_ast.Gt):
                parts.append(PCompound(">", (prev, right)))
            elif isinstance(op, python_ast.GtE):
                parts.append(PCompound(">=", (prev, right)))
            elif isinstance(op, python_ast.In):
                parts.append(PCompound("member", (prev, right)))
            elif isinstance(op, python_ast.NotIn):
                parts.append(PCompound("\\+", (
                    PCompound("member", (prev, right)),
                )))
            prev = right

        if len(parts) == 1:
            return parts[0]
        result = parts[-1]
        for p in reversed(parts[:-1]):
            result = PCompound(",", (p, result))
        return result

    def _convert_ifexp(self, node: python_ast.IfExp) -> PTerm:
        """Reject Clausal if-then-else → Prolog (C -> T ; E) translation.

        Clausal's reified if-then-else has monotonic, three-valued semantics
        that cannot be faithfully represented by Prolog's committed-choice
        (C -> T ; E), which is defined in terms of cut.
        """
        from clausal.tools.prolog_to_clausal import PrologTranslationError
        raise PrologTranslationError(
            "Clausal's if-then-else (THEN if COND else ELSE) cannot be "
            "translated to Prolog.\n"
            "Clausal's reified ITE has monotonic, three-valued semantics "
            "that differ from Prolog's committed-choice (C -> T ; E), "
            "which is defined in terms of cut.\n"
            "To translate this program, rewrite as separate clauses with "
            "dif/2 guards or constraint-based branching."
        )

    def _convert_dcg_body(self, node) -> PTerm:
        """Convert DCG rule body, wrapping inline goals in {curly}."""
        # For now, treat the same as regular body conversion
        return self._convert_expr(node)

    def _get_string_or_name(self, node) -> str:
        """Extract string from a Constant or Name node."""
        if isinstance(node, python_ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, python_ast.Name):
            return node.id
        # Attribute chain: foo.bar.baz
        if isinstance(node, python_ast.Attribute):
            parts = []
            current = node
            while isinstance(current, python_ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, python_ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return str(node)

    def _convert_fstring(self, node: python_ast.JoinedStr) -> PTerm:
        """Convert f-string to format/2 (SWI) or warning.

        f"Hello {Name}, you have {Count} items"
        → format("Hello ~w, you have ~w items", [Name, Count])  (SWI)
        → warning comment + ??? (ISO/Scryer)
        """
        fmt_parts = []
        args = []
        for value in node.values:
            if isinstance(value, python_ast.Constant) and isinstance(value.value, str):
                # Literal text — escape ~ for Prolog format
                fmt_parts.append(value.value.replace("~", "~~"))
            elif isinstance(value, python_ast.FormattedValue):
                fmt_parts.append("~w")
                args.append(self._convert_expr(value.value))
            else:
                fmt_parts.append("~w")
                args.append(self._convert_expr(value))
        fmt_string = "".join(fmt_parts)

        if self.dialect.name == "swi":
            return PCompound("format", (
                PString(fmt_string),
                PList(tuple(args)),
            ))
        # ISO / Scryer: untranslatable
        self._add_warning(f'f-string: f"{fmt_string}"')
        return PAtom("???")

    def _convert_dict(self, node: python_ast.Dict) -> PTerm:
        """Convert dict literal: SWI dict, or key-sorted attribute-list (ISO)."""
        if self.dialect.has_dicts:
            # SWI dict: tag{key: val, ...}
            # Emit as: dict_create(D, _, [key=val, ...]) or use Tag.put_dict
            # For now, emit as a compound with key=value pairs
            pairs = []
            for k, v in zip(node.keys, node.values):
                key = self._convert_expr(k) if k is not None else PAtom("_")
                val = self._convert_expr(v)
                pairs.append(PCompound("=", (key, val)))
            if not pairs:
                return PAtom("_{}")
            return PCompound("dict_create", (
                PVar("_"),
                PAtom("_"),
                PList(tuple(pairs)),
            ))
        # ISO / Scryer / Trealla: lower to a key-sorted attribute(K, V) list.
        pairs = []
        for k, v in zip(node.keys, node.values):
            if k is None:  # {**expr} splat — no static key set
                self._add_warning("dict splat " + python_ast.unparse(node))
                return PAtom("???")
            pairs.append((self._convert_expr(k), self._convert_expr(v)))
        pairs.sort(key=lambda kv: emit_term(kv[0], self.dialect.operator_table))
        return PList(tuple(
            PCompound("attribute", (k, v)) for k, v in pairs
        ))


# ── Module export / discontiguous post-pass ────────────────────────────
#
# Shared by convert_module's post-pass (Task 4: filter dead module
# exports; Task 5: emit :- discontiguous for interrupted clause runs).

def _clause_key(item: PItem) -> tuple[str, int] | None:
    """(functor, arity) for a PClause head; None for any other item kind.

    DCG rules deliberately return None here — a DCG predicate's real
    callable arity (written arity + 2 hidden state args) is computed
    separately by _dcg_head_key. Combined with it via _run_key for
    clause-run/interruption tracking, so both PClause and PDCGRule runs
    are covered.
    """
    if not isinstance(item, PClause):
        return None
    head = item.head
    if isinstance(head, PCompound):
        return (head.functor, len(head.args))
    if isinstance(head, PAtom):
        return (head.name, 0)
    return None


def _dcg_head_key(item: PItem) -> tuple[str, int] | None:
    """(functor, explicit_arity + 2) for a PDCGRule head; None otherwise.

    A ``-->`` clause is expanded (by the Prolog engine, not this
    translator) to take two extra difference-list state arguments, so a
    DCG predicate's real callable arity is the written arity plus 2. A
    pushback/semicontext head arrives as a comma pair
    ``(Call, PushbackList)`` — the callable predicate is the left side.
    """
    if not isinstance(item, PDCGRule):
        return None
    head = item.head
    if isinstance(head, PCompound) and head.functor == "," and len(head.args) == 2:
        head = head.args[0]
    if isinstance(head, PCompound):
        return (head.functor, len(head.args) + 2)
    if isinstance(head, PAtom):
        return (head.name, 2)
    return None


def _run_key(item: PItem) -> tuple[str, int] | None:
    """(name, arity) for clause-run/interruption tracking; None to be skipped.

    Unifies PClause (as written) and PDCGRule (+2 hidden state args, via
    _dcg_head_key — the same indicator Scryer calls the translated DCG
    predicate with, and the same one _filter_module_exports uses for
    module exports) into one run-tracking key. Anything else — module
    directives, discontiguous directives, comments — returns None and is
    skipped by the caller: it neither starts nor breaks a run.
    """
    key = _clause_key(item)
    if key is not None:
        return key
    return _dcg_head_key(item)


def _is_module_directive(item: PItem) -> bool:
    """True if *item* is a ``:- module(Name, Exports).`` directive."""
    return (
        isinstance(item, PDirective)
        and isinstance(item.body, PCompound)
        and item.body.functor == "module"
        and len(item.body.args) == 2
    )


def _export_pairs(directive: PDirective) -> set[tuple[str, int]]:
    """The (name, arity) pairs a ``:- module(...)`` directive's export list names."""
    exports = directive.body.args[1]
    pairs: set[tuple[str, int]] = set()
    if not isinstance(exports, PList):
        return pairs
    for elt in exports.elements:
        if (isinstance(elt, PCompound) and elt.functor == "/" and len(elt.args) == 2
                and isinstance(elt.args[0], PAtom) and isinstance(elt.args[1], PNumber)):
            pairs.add((elt.args[0].name, int(elt.args[1].value)))
    return pairs


def _filter_module_exports(directive: PDirective,
                            defined: set[tuple[str, int]]) -> PDirective:
    """Rebuild *directive*'s export list keeping only Name/Arity pairs in *defined*."""
    mod_name, exports = directive.body.args
    if not isinstance(exports, PList):
        return directive
    kept = tuple(
        elt for elt in exports.elements
        if isinstance(elt, PCompound) and elt.functor == "/" and len(elt.args) == 2
        and isinstance(elt.args[0], PAtom) and isinstance(elt.args[1], PNumber)
        and (elt.args[0].name, int(elt.args[1].value)) in defined
    )
    return PDirective(PCompound("module", (mod_name, PList(kept))))


def _existing_discontiguous_indicators(item: PItem) -> set[tuple[str, int]]:
    """(name, arity) pairs an already-present ``:- discontiguous(...)`` names.

    A hand-written ``-discontiguous(...)`` (via _convert_meta_directive)
    emits either a single spec or a PList of specs, each either
    ``Name/Arity`` (PCompound) or a bare 0-arity atom (PAtom). Used so the
    auto-inserted directive (below) never duplicates one the source
    already wrote out.
    """
    if not (isinstance(item, PDirective) and isinstance(item.body, PCompound)
            and item.body.functor == "discontiguous" and len(item.body.args) == 1):
        return set()
    spec = item.body.args[0]
    specs = spec.elements if isinstance(spec, PList) else (spec,)
    pairs: set[tuple[str, int]] = set()
    for s in specs:
        if (isinstance(s, PCompound) and s.functor == "/" and len(s.args) == 2
                and isinstance(s.args[0], PAtom) and isinstance(s.args[1], PNumber)):
            pairs.add((s.args[0].name, int(s.args[1].value)))
        elif isinstance(s, PAtom):
            pairs.add((s.name, 0))
    return pairs


def module_export_signature(pmodule: PModule) -> set[tuple[str, int]]:
    """The (name, arity) set the emitted :- module directive exports."""
    for item in pmodule.items:
        if _is_module_directive(item):
            return _export_pairs(item)
    return set()


# ── Public API ───────────────────────────────────────────────────────

def clausal_source_to_prolog_ast(source: str, *,
                                  dialect: Dialect | None = None,
                                  strict: bool = False) -> PModule:
    """Parse .clausal source text and return a Prolog AST (PModule).

    Uses Python's parser on the clausal source, then converts the
    Python AST patterns (trailing comma facts, <- rules, -directives)
    directly into Prolog AST nodes.

    When *strict* is True, any construct with no ISO Prolog equivalent
    raises :class:`UntranslatableConstructError` instead of emitting a
    ``???`` placeholder plus a warning comment.
    """
    if dialect is None:
        dialect = Dialect.iso()
    tree = python_ast.parse(source)
    converter = _ClausalToProlog(dialect, strict=strict)
    return converter.convert_module(tree)


def clausal_source_to_prolog(source: str, *,
                              dialect: Dialect | None = None,
                              strict: bool = False) -> str:
    """Translate .clausal source text to Prolog source text.

    Full pipeline: .clausal → Python AST → Prolog AST → .pl text.

    When *strict* is True, any construct with no ISO Prolog equivalent
    raises :class:`UntranslatableConstructError` instead of emitting a
    ``???`` placeholder plus a warning comment.
    """
    if dialect is None:
        dialect = Dialect.iso()
    pmodule = clausal_source_to_prolog_ast(source, dialect=dialect, strict=strict)
    return emit_module(pmodule, dialect.operator_table)


# ── CLI ──────────────────────────────────────────────────────────────

def _main() -> None:
    """Command-line interface for clausal → Prolog translation.

    Usage:
        python -m clausal.tools.clausal_to_prolog input.clausal [-o output.pl] [--dialect swi|scryer|gprolog|iso]
        cat input.clausal | python -m clausal.tools.clausal_to_prolog [--dialect swi]
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="clausal_to_prolog",
        description="Translate .clausal source files to Prolog (.pl).",
    )
    parser.add_argument(
        "input", nargs="?", default=None,
        help="Input .clausal file (reads stdin if omitted)",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output .pl file (writes stdout if omitted)",
    )
    parser.add_argument(
        "--dialect", choices=["iso", "swi", "scryer", "gprolog"], default="iso",
        help="Target Prolog dialect (default: iso)",
    )
    args = parser.parse_args()

    dialect_map = {"iso": Dialect.iso, "swi": Dialect.swi, "scryer": Dialect.scryer,
                   "gprolog": Dialect.gprolog}
    dialect = dialect_map[args.dialect]()

    if args.input is None:
        source = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as f:
            source = f.read()

    result = clausal_source_to_prolog(source, dialect=dialect)

    if args.output is None:
        sys.stdout.write(result)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)


if __name__ == "__main__":
    _main()
