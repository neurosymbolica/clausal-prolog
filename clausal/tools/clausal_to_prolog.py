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
import posixpath
import re
from typing import Iterator

from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PComment, PModule,
    PTerm, PItem, PrologVisitor, PrologTransformer, subterms,
)
from clausal.tools.prolog_operators import OperatorTable
# The engine's canonical `<-` detection primitives. The lambda arrow `<-` and
# the arithmetic comparison `< -` parse to an IDENTICAL AST
# (Compare(Lt, UnaryOp(USub, ...))); only the SOURCE SPACING separates them.
# We import the engine's own predicates rather than re-implementing them so
# the translator's term-position rule cannot drift from the clause-level rule
# the engine enforces (see _refuse_arrow_lambda_in_term_position).
from clausal.templating.term_rewriting import (
    _is_arrow_adjacent as _engine_is_arrow_adjacent,
    _leftmost_usub as _engine_leftmost_usub,
)
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


# Dotted clausal module → the file name it is exported under at the root of
# the export tree. These libraries are flattened out of their source package
# so every exported module can reach them by climbing to the root.
_LIBRARY_REMAP = {
    "clausal.stdlib.kleene": "clausal_kleene",
    "formalize_lib": "formalize_lib",
}


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
        if item.text.startswith("%"):
            # Already written as Prolog line comment(s) — emit verbatim so a
            # one-line note does not become a block comment.
            return item.text.rstrip("\n") + "\n"
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

    def __init__(self, dialect: Dialect, strict: bool = False, *,
                 module_path: str | None = None,
                 module_signatures: dict[str, set[tuple[str, int]]] | None = None,
                 meta_modes: MetaModeMap | None = None,
                 source_lines: list[str] | None = None):
        self.dialect = dialect
        self.strict = strict
        # Original source, split into lines. Required to tell the lambda arrow
        # `<-` from the comparison `< -`, which are indistinguishable in the
        # AST and differ only in source spacing. None when the caller built the
        # AST programmatically; the arrow-lambda refusal then cannot fire (the
        # engine's own fallback heuristic is used, matching clause-level).
        self._source_lines = source_lines
        # Dotted path of the module being translated. When set, use_module
        # file paths are emitted relative to this module's package directory
        # (Scryer resolves a consulted path against the consulting file).
        self.module_path = module_path
        # Dotted target path → that target's FILTERED export set, as returned
        # by module_export_signature. When set, import lists are narrowed to
        # names the target really exports.
        self.module_signatures = module_signatures
        # module_path -> {(name, arity): per-argument modes}. Supplies the meta
        # positions that this module's own text cannot show -- a THREADING host,
        # whose argument is only ever called further down the chain, often in
        # another module (the `find_mus/4` / `failing_ids/4` shape). Computed by
        # the exporter's cross-module fixpoint and keyed by exactly the
        # `module_path` string the exporter hands this translation.
        self.meta_modes = meta_modes
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
        # Top-level statement currently being converted. The provably-list
        # analysis behind the negated-membership refusal is CLAUSE-LOCAL: it
        # reads only this statement's own AST, never other clauses.
        self._current_stmt: python_ast.stmt | None = None
        self._provable_lists: set[str] | None = None

    def _meta_predicate_directives(self, seen_order: list[tuple[str, int]],
                                   defined: set[tuple[str, int]]) -> list[PDirective]:
        """Build the `:- meta_predicate` directives for this module.

        Per-argument union of two sources, under ONE contract shared with
        :func:`collect_local_meta_modes` and the exporter's fixpoint: a position with
        ANY goal evidence is annotated -- with its call arity when that is
        single-valued, else with :data:`MODE_MODULE_SENSITIVE` -- and a position with
        NO goal evidence is emitted as `?`, never guessed. Two sources that disagree
        make the position module-sensitive rather than letting either win, which is
        what makes the shipped behaviour equal the documented one: an earlier draft
        used `setdefault` here, and body-local evidence quietly reinstated a position
        the fixpoint had deliberately left alone.

        `?` is the LOUD outcome: a bare reference consumed at an unannotated position
        raises existence_error at the call site. A guessed mode is the quiet one, and
        would module-qualify a term that may not be a goal at all.

        Emitted in first-appearance order, like the discontiguous pass, so the output
        is byte-stable across runs.
        """
        local = collect_local_meta_modes(PModule(tuple(self._items)))
        supplied = (self.meta_modes or {}).get(self.module_path or "", {})

        merged: dict[tuple[str, int], dict[int, int | str]] = {
            key: dict(positions) for key, positions in local.items()
        }
        for key, modes in supplied.items():
            slot = merged.setdefault(key, {})
            for index, mode in enumerate(modes):
                if mode is None:
                    continue
                previous = slot.get(index, mode)
                slot[index] = mode if previous == mode else MODE_MODULE_SENSITIVE

        already = set()
        for item in self._items:
            already |= _existing_meta_predicate_indicators(item)

        directives: list[PDirective] = []
        for name, arity in seen_order:
            key = (name, arity)
            positions = merged.get(key)
            if not positions or arity == 0 or key in already or key not in defined:
                continue
            args = tuple(
                _mode_term(positions[index]) if index in positions else PAtom("?")
                for index in range(arity)
            )
            directives.append(
                PDirective(PCompound("meta_predicate", (PCompound(name, args),))))
        return directives

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
            self._current_stmt = stmt
            self._provable_lists = None
            item = self._convert_stmt(stmt)
            # Emit any warnings accumulated during conversion
            for w in self._warnings:
                self._items.append(PComment(
                    f"WARNING: untranslatable clausal construct: {w}\n"
                    f"   Replace with Prolog equivalent manually."
                ))
            if item is not None:
                if isinstance(item, list):
                    self._items.extend(_prefix_singletons(i) for i in item)
                else:
                    self._items.append(_prefix_singletons(item))

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

        # (3) emit :- meta_predicate(Name(Mode, ...)) for every locally-defined
        # predicate with a known meta position. Scryer resolves a meta-call in the
        # CALLEE's module, so a bare predicate reference handed to a higher-order
        # predicate raises existence_error without this -- even same-module (the
        # design note's §3.2/§3.3, both measured in Scryer). Two sources, unioned
        # per argument: body-local evidence read off the clauses being emitted, and
        # the caller-supplied map for positions no single module can see.
        meta_directives = self._meta_predicate_directives(seen_order, defined)

        rewritten: list[PItem] = []
        module_seen = False
        for item in self._items:
            if _is_module_directive(item):
                rewritten.append(_filter_module_exports(item, defined))
                rewritten.extend(meta_directives)
                rewritten.extend(discontiguous_directives)
                module_seen = True
            else:
                rewritten.append(item)
        if not module_seen:
            rewritten = meta_directives + discontiguous_directives + rewritten
        self._items = rewritten

        if self.strict and self._all_warnings:
            raise UntranslatableConstructError(list(self._all_warnings))
        return PModule(tuple(self._items))

    def _convert_stmt(self, stmt) -> PItem | list[PItem] | None:
        """Convert a top-level statement to PItem(s).

        FAIL-CLOSED NET: every exit path below either returns a PItem(s) it
        produced, or calls ``_add_warning`` before returning None. There is
        no bare ``return None`` left in this method — an unrecognized
        top-level shape must never vanish silently (strict mode is the only
        thing standing between a translation bug and a corpus that looks
        clean while dropping clauses; see the 2026-09 rule-drop incident).
        """
        if not isinstance(stmt, python_ast.Expr):
            self._add_warning(
                "unsupported top-level statement (not an expression): "
                f"{type(stmt).__name__}"
            )
            return None

        value = stmt.value

        # -directive(...): unary minus on a call. Directives are a fully
        # recognized construct that can legitimately emit nothing (a
        # dialect-gated skip, e.g. GNU Prolog has no module system; or
        # -private(...), which has no Prolog emission at all) — so they
        # are dispatched here, before the fail-closed net below, and are
        # exempt from its warning.
        if isinstance(value, python_ast.UnaryOp) and isinstance(value.op, python_ast.USub):
            operand = value.operand
            if isinstance(operand, python_ast.Call) and isinstance(operand.func, python_ast.Name):
                return self._convert_directive(operand)
            # -strict_atoms / -implicit_atoms: a parenless, argument-less
            # directive (UnaryOp(USub(Name)), not Call) — engine-only atom-
            # resolution bookkeeping with no Prolog equivalent, same
            # legitimately-silent category as -private(...) above. 523
            # corpus sites (2026-09 rule-drop census) would otherwise all
            # start refusing under strict once the fail-closed net below
            # stopped exempting unrecognized UnaryOp shapes.
            if isinstance(operand, python_ast.Name):
                return self._convert_bare_directive(operand.id)

        # Trailing-comma statement(s): Foo(1, 2), or a comma-joined run of
        # facts/rules sharing one Python statement: Foo(1, 2), Bar(x) <- (...),
        # A 1-tuple is the common case (one fact, or — the bug this comment
        # marks the fix for — one `<-` RULE, both followed by the ordinary
        # fact-separator comma); a multi-element tuple is the same AST shape
        # for several comma-joined statements on one line. Every element is
        # dispatched through _convert_clause_value so a rule in ANY tuple
        # position translates identically to an unwrapped rule.
        if isinstance(value, python_ast.Tuple):
            items: list[PItem] = []
            for elt in value.elts:
                item = self._convert_clause_value(elt)
                if item is None:
                    self._add_warning(
                        "unsupported statement in comma group: "
                        f"{python_ast.unparse(elt)}"
                    )
                    continue
                if isinstance(item, list):
                    items.extend(item)
                else:
                    items.append(item)
            return items or None

        item = self._convert_clause_value(value)
        if item is not None:
            return item

        self._add_warning(
            f"unsupported top-level statement: {python_ast.unparse(value)}"
        )
        return None

    def _convert_clause_value(self, value) -> PItem | list[PItem] | None:
        """Convert one fact/rule/DCG-rule expression.

        Used both for a bare top-level statement and for each element of a
        comma-joined statement tuple (see _convert_stmt) — the same
        dispatch either way, so a rule's position relative to a trailing
        comma or sibling statements never changes how it translates.

        Returns None when *value* matches none of the recognized clause
        shapes; the caller is responsible for warning in that case (this
        method never emits nothing without a caller-visible signal).
        """
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
                body = self._convert_expr(body_ast, goal_position=True)
                return PClause(head, body)
            return None

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

    def _convert_bare_directive(self, name: str) -> PItem | list[PItem] | None:
        """Convert a parenless, argument-less directive: ``-strict_atoms``.

        These are clausal-engine-only bookkeeping (atom-resolution mode)
        with no Prolog equivalent — always a legitimate no-op, not an
        unrecognized shape, so this does NOT fall through to the
        fail-closed net's warning. An actually-unknown bare directive
        still warns below: only the names the engine itself recognizes
        (clausal/reflection.py's StrictAtomsDeclaration / the mutually-
        exclusive -implicit_atoms) are exempted.
        """
        if name in ("strict_atoms", "implicit_atoms"):
            return None
        self._add_warning(f"-{name}")
        return None

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

    def _module_reference(self, mod_path: str) -> PTerm | None:
        """The term naming *mod_path* in a use_module directive.

        Dialect libraries keep their ``library(name)`` form. Everything else
        is a file path with dots turned into slashes. Without ``module_path``
        that path is the dotted path verbatim. With it — the export-tree case
        — the libraries in :data:`_LIBRARY_REMAP` are first relocated to the
        root of the tree they are exported into, then the whole path is made
        relative to the consuming module's own package, because Scryer
        resolves a consulted path against the consulting file.

        Returns None when the relative path does not name a file: a consumer
        whose own package IS the target (``formalize_lib.helper`` importing
        ``formalize_lib``) relativizes to ``'.'``, and one nested inside it
        to ``'..'``. Both are directory references that Scryer cannot consult,
        so the import is recorded as an untranslatable construct instead —
        raising under strict, a warning comment otherwise — rather than
        emitting a path that only fails at load time.
        """
        library_name = self.dialect.library_map.get(mod_path)
        if library_name is not None:
            # Known library: parse "library(clpfd)" → library(clpfd).
            lib_inner = library_name[len("library("):-1]  # "clpfd"
            return PCompound("library", (PAtom(lib_inner),))

        if self.module_path is None:
            # Single-file use: absolute dotted path, unchanged.
            return PAtom(mod_path.replace(".", "/"), quoted=True)

        target = _LIBRARY_REMAP.get(mod_path, mod_path)
        consumer_pkg = "/".join(self.module_path.split(".")[:-1])
        prolog_path = posixpath.relpath(target.replace(".", "/"), consumer_pkg or ".")
        if posixpath.basename(prolog_path) in ("", ".", ".."):
            self._add_warning(
                f"unresolvable use_module path: consumer package "
                f"'{consumer_pkg}' shadows root target '{target}'"
            )
            return None
        return PAtom(prolog_path, quoted=True)

    def _import_list(self, mod_path: str, elts: list) -> list[PTerm] | None:
        """The import-list elements for -import_from(*mod_path*, [*elts*]).

        With no ``module_signatures`` the requested names are emitted as they
        always were (bare atoms, or Name/Arity when written with arguments).
        With signatures, each requested name is resolved the same way a
        predicate name is (PascalCase → snake_case, builtin remaps) and then
        looked up in the target's export set; names the target does not export
        — atoms, term constructors, signature-only predicates — are dropped,
        because Scryer raises at load time on an import it cannot satisfy.
        """
        requested: list[tuple[str, int | None]] = []
        for elt in elts:
            if isinstance(elt, python_ast.Call) and isinstance(elt.func, python_ast.Name):
                requested.append((resolve_name(elt.func.id, self.dialect), len(elt.args)))
            elif isinstance(elt, python_ast.Name):
                requested.append((resolve_name(elt.id, self.dialect), None))

        if self.module_signatures is None:
            if self.module_path is not None:
                # Relative-path mode without signatures: no way to tell which
                # requested names the target really exports, so import its
                # whole export set instead of naming any of them.
                return None
            return [
                PCompound("/", (PAtom(name), PNumber(arity)))
                if arity is not None else PAtom(name)
                for name, arity in requested
            ]

        exported = self.module_signatures.get(mod_path)
        if exported is None:
            # Target outside the export set being built: nothing to filter
            # against, so import everything it exports (a listless use_module
            # can never claim an export the target does not have).
            return None

        imports: list[PTerm] = []
        seen: set[tuple[str, int]] = set()
        for name, arity in requested:
            arities = ([arity] if arity is not None
                       else sorted(a for n, a in exported if n == name))
            for a in arities:
                if (name, a) in exported and (name, a) not in seen:
                    seen.add((name, a))
                    imports.append(PCompound("/", (PAtom(name), PNumber(a))))
        return imports

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

        prolog_mod = self._module_reference(mod_path)
        if prolog_mod is None:
            # No path names this target from here — _module_reference has
            # already recorded the warning.
            return PComment(
                f"WARNING: unresolvable use_module path: "
                f"-import_from({mod_path}, ...)\n"
                f"   No relative path from this module names that file."
            )

        elts = (call.args[1].elts
                if len(call.args) > 1 and isinstance(call.args[1], python_ast.List)
                else [])
        imports = self._import_list(mod_path, elts)

        if imports is None:
            # Unknown or unfiltered target: import its whole export set.
            return PDirective(PCompound("use_module", (prolog_mod,)))
        if not imports and self.module_signatures is not None:
            # Nothing the target exports was asked for — a use_module naming
            # predicates it does not export would abort the consult.
            #
            # The wording is about the INTERSECTION, not the target: this
            # branch is reached whenever the filtered list comes back empty,
            # which is usually a target that exports plenty, just none of the
            # names this import asked for. Saying "exports nothing" there is
            # simply false, and sends a reader looking for a bug in the target
            # module instead of at the import list in front of them.
            return PComment(
                f"% skipped: {mod_path} exports none of the requested names")

        return PDirective(PCompound("use_module", (prolog_mod, PList(tuple(imports)))))

    def _convert_import_module(self, call: python_ast.Call) -> PDirective | PComment:
        """Convert -import_module(module)."""
        mod_path = self._get_string_or_name(call.args[0])

        if mod_path.startswith("py.") or mod_path.startswith("clausal.modules.py."):
            self._add_warning(f"-import_module({mod_path})")
            return PComment(
                f"WARNING: Python-only module import: -import_module({mod_path})\n"
                f"   No Prolog equivalent available."
            )

        prolog_mod = self._module_reference(mod_path)
        if prolog_mod is None:
            return PComment(
                f"WARNING: unresolvable use_module path: "
                f"-import_module({mod_path})\n"
                f"   No relative path from this module names that file."
            )
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

    def _convert_expr(self, node, goal_position: bool = False) -> PTerm:
        """Convert a Python AST expression node to a Prolog AST term.

        *goal_position* is True exactly when *node* is being converted as a
        goal — the whole clause body, or a body conjunct — rather than as
        data nested inside an argument/value position (a Call argument, a
        list element, a dict value, ...). It defaults to False and is only
        propagated True through the constructs that combine sub-goals
        (a parenthesized comma-body Tuple, ``and``/``or`` BoolOp) from a
        caller that itself received True. It gates constructs whose Prolog
        lowering is only valid as an executed goal (e.g. the `is`-RHS
        dict-splat → ``attrs_put/3`` rewrite) — see `_convert_compare`.
        """
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
                return self._convert_expr(node.elts[0], goal_position=goal_position)
            # Multi-element tuple → Prolog comma-separated (conjunction-like)
            if len(node.elts) >= 2:
                result = self._convert_expr(node.elts[-1], goal_position=goal_position)
                for elt in reversed(node.elts[:-1]):
                    result = PCompound(",", (
                        self._convert_expr(elt, goal_position=goal_position),
                        result,
                    ))
                return result
            return PAtom("true")

        if isinstance(node, python_ast.BoolOp):
            return self._convert_boolop(node, goal_position=goal_position)

        if isinstance(node, python_ast.UnaryOp):
            return self._convert_unaryop(node)

        if isinstance(node, python_ast.BinOp):
            return self._convert_binop(node)

        if isinstance(node, python_ast.Compare):
            return self._convert_compare(node, goal_position=goal_position)

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

    def _convert_boolop(self, node: python_ast.BoolOp, goal_position: bool = False) -> PTerm:
        """Convert 'and'/'or' to ','/';'.

        Each operand is itself a body conjunct/disjunct, so *goal_position*
        (whatever this BoolOp itself was converted under) propagates
        unchanged to every operand.
        """
        if isinstance(node.op, python_ast.And):
            op = ","
        else:
            op = ";"

        result = self._convert_expr(node.values[-1], goal_position=goal_position)
        for val in reversed(node.values[:-1]):
            result = PCompound(op, (
                self._convert_expr(val, goal_position=goal_position),
                result,
            ))
        return result

    def _convert_unaryop(self, node: python_ast.UnaryOp) -> PTerm:
        """Convert unary operators."""
        if isinstance(node.op, python_ast.Not):
            # `not (X in XS)` is the OTHER spelling of negated membership: it
            # reaches _convert_compare as a POSITIVE `In` under this `\+`, so
            # the refusal has to be applied here, where the negation is
            # visible (2026-09-03). `X not in XS` is caught in _convert_compare.
            operand = node.operand
            if isinstance(operand, python_ast.Compare):
                refused = False
                for op, comp in zip(operand.ops, operand.comparators):
                    if isinstance(op, python_ast.In):
                        refused |= self._check_negated_membership(comp)
                if refused:
                    return PAtom("???")
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

    # ── Interim refusals (operator decision, 2026-09-03) ──────────────
    #
    # See docs/iso-export-pilot-2026-09.md, "Operator decision — 2026-09-03
    # (dict-membership fail-open, class P census)" in the clausify-executor-
    # train repo. Two shapes that used to translate SILENTLY WRONG now refuse.

    # Goals whose output argument is guaranteed to be a proper list, keyed by
    # (name, arity) → index of that output argument. Deliberately tiny: each
    # entry is checkable from the clause's own AST with no cross-clause
    # inference and no doubt about the callee's contract.
    _LIST_PRODUCING_GOALS = {
        ("findall", 3): 2,
        ("bagof", 3): 2,
        ("setof", 3): 2,
        ("msort", 2): 1,
        ("sort", 2): 1,
        ("sort", 4): 3,
    }

    def _clause_binding_sites(self):
        """Every binding occurrence in the CURRENT clause, as name → [RHS].

        A "binding" is any place the clause can give a name its value:

        * ``V is X`` — Clausal's ``is`` is UNIFICATION, and unification is
          symmetric, so this binds ``V`` to ``X`` and, when ``X`` is itself a
          name, ``X`` to ``V``. Both directions are recorded.
        * a call to a goal in :attr:`_LIST_PRODUCING_GOALS` whose output
          argument is a name — recorded as ``None``, meaning "bound to a
          proper list by construction".

        Clause-local by construction: the walk never leaves
        ``self._current_stmt``.
        """
        bindings: dict[str, list] = {}
        stmt = self._current_stmt
        if stmt is None:
            return bindings
        for sub in python_ast.walk(stmt):
            if (isinstance(sub, python_ast.Compare)
                    and len(sub.ops) == 1
                    and isinstance(sub.ops[0], python_ast.Is)):
                left, right = sub.left, sub.comparators[0]
                if isinstance(left, python_ast.Name):
                    bindings.setdefault(left.id, []).append(right)
                if isinstance(right, python_ast.Name):
                    bindings.setdefault(right.id, []).append(left)
            if (isinstance(sub, python_ast.Call)
                    and isinstance(sub.func, python_ast.Name)
                    and not sub.keywords):
                idx = self._LIST_PRODUCING_GOALS.get(
                    (sub.func.id, len(sub.args)))
                if idx is not None:
                    out = sub.args[idx]
                    if isinstance(out, python_ast.Name):
                        bindings.setdefault(out.id, []).append(None)
        return bindings

    def _clause_local_list_vars(self) -> set[str]:
        """Names this clause proves to be a proper list on EVERY binding.

        A name qualifies only when it has at least one binding in the clause
        and **all** of its bindings are list-producing — a list display, a
        list-producing goal's output, or another qualifying name. A single
        binding that is not provably a list DISQUALIFIES the name outright.

        That "all bindings" rule is the whole point, and it is what makes the
        analysis control-flow-safe without tracking control flow. The walk
        cannot tell a disjunct from a conjunct, so an earlier version that
        qualified a name on ANY list binding was unsound via aliasing::

            p(K, D) <- ((V is D) or (V is [a, b]), K not in V)

        There ``V`` may be the dict ``D`` at the membership site, and
        ``\\+ member(K, V)`` is silently always true — precisely the hazard
        this refusal exists to close. Requiring every binding to be
        list-producing rejects that clause, because ``V is D`` is not.

        The result is therefore a CONSERVATIVE approximation of control flow:
        merging all branches and demanding they all produce a list can only
        *narrow* what is accepted relative to any single real execution path,
        so an imprecision here costs an extra refusal, never a missed one.

        Resolution is a LEAST fixpoint, starting from nothing and adding only
        names whose bindings are already known provable. Cyclic bindings
        (``V is [a, *V]``) therefore never qualify — fail-closed.
        """
        if self._provable_lists is not None:
            return self._provable_lists
        bindings = self._clause_binding_sites()
        qualified: set[str] = set()
        while True:
            added = False
            for name, rhss in bindings.items():
                if name in qualified:
                    continue
                if rhss and all(
                        self._binding_is_list(r, qualified) for r in rhss):
                    qualified.add(name)
                    added = True
            if not added:
                break
        self._provable_lists = qualified
        return qualified

    def _binding_is_list(self, node, qualified: set[str]) -> bool:
        """True when a single binding RHS provably yields a proper list.

        *qualified* is the set of names already proven, threaded through so
        the fixpoint in :meth:`_clause_local_list_vars` stays monotone (this
        must NOT call back into ``_clause_local_list_vars``, which would
        recurse).
        """
        if node is None:
            return True                      # list-producing goal output
        if isinstance(node, python_ast.List):
            return all(
                self._binding_is_list(e.value, qualified)
                for e in node.elts
                if isinstance(e, python_ast.Starred)
            )
        if isinstance(node, python_ast.Name):
            return node.id in qualified
        return False

    def _is_provably_list(self, node: python_ast.expr) -> bool:
        r"""True when *node* is PROVABLY a proper list at this site.

        The rule is deliberately minimal and syntactic — there is no type
        inference here, and anything not matched below refuses:

        (a) a list display ``[a, b, c]``. A display with a splat tail
            (``[H, *T]``, Clausal's ``[H|T]``) qualifies only when the tail is
            itself provably a list, because ``[H|T]`` with an unbound ``T`` is
            a PARTIAL list and ``\+ member/2`` over one is exactly as unsound
            as over a dict.
        (b) a variable ALL of whose clause-local bindings produce a list —
            see :meth:`_clause_local_list_vars`.

        Everything else — a bare parameter, a call result, an attribute, a
        dict — is NOT provably a list. Exported dicts (attribute-lists) land
        here, which is the point: ``\+ member(K, Dict)`` is silently
        always-true, and that is the emission this refusal removes.
        """
        if isinstance(node, python_ast.List):
            return all(
                self._is_provably_list(e.value)
                for e in node.elts
                if isinstance(e, python_ast.Starred)
            )
        if isinstance(node, python_ast.Name):
            return node.id in self._clause_local_list_vars()
        return False

    def _check_negated_membership(self, right: python_ast.expr) -> bool:
        """Refuse a NEGATED membership whose RHS is not provably a list.

        Returns True when the site was refused. Positive membership is NOT
        checked here: the operator explicitly deferred that polarity, because
        positive ``member/2`` over a dict fails loudly (absent derivation)
        rather than succeeding silently.
        """
        if self._is_provably_list(right):
            return False
        self._add_warning(
            "negated membership over a value not provably a list: "
            + python_ast.unparse(right)
            + " — if the RHS is a dict/profile, respell via the accessor "
            "(not profile_has(P, K)); see the 2026-09-03 decision"
        )
        return True

    def _refuse_arrow_lambda_in_term_position(
            self, node: python_ast.Compare) -> bool:
        """Refuse a ``<-`` lambda that reached TERM position.

        A ``<-`` lambda is only meaningful as a CLAUSE arrow. Reaching a term
        position — ``include((D <- Goal), Xs, Ys)`` — it was previously
        emitted as inert operator soup (``include(D < -(...), ...)``): data,
        not a closure. It never runs, and nothing downstream says so.

        The lambda arrow ``<-`` and the comparison ``< -`` parse to the SAME
        AST; only source spacing separates them. This mirrors the engine's
        clause-level rule by calling the engine's own predicates
        (:func:`_is_arrow_adjacent`), so `a < -b` — a genuine comparison
        against a negated term — keeps its current behavior untouched.

        Returns True when the site was refused.
        """
        if not node.ops or not isinstance(node.ops[0], python_ast.Lt):
            return False
        usub_node, _depth = _engine_leftmost_usub(node.comparators[0])
        if usub_node is None:
            return False
        try:
            adjacent = _engine_is_arrow_adjacent(
                node.left, usub_node, self._source_lines)
        except ValueError:
            # Missing source positions (programmatically built AST): we
            # cannot tell `<-` from `< -`, so do not guess — leave the
            # pre-existing comparison behavior in place.
            return False
        if not adjacent:
            return False
        self._add_warning(
            "`<-` lambda in term position: "
            + python_ast.unparse(node)
            + " — a `<-` lambda is a clause arrow, not a closure; in term "
            "position it emits inert operator soup that never runs. Define a "
            "named auxiliary predicate and pass its name instead (class-M "
            "design note; see the 2026-09-03 decision)"
        )
        return True

    def _convert_compare(self, node: python_ast.Compare, goal_position: bool = False) -> PTerm:
        """Convert comparison operators.

        Handles special clausal patterns:
        - X is Y → X = Y (Unify)
        - X is not Y → dif(X, Y) (DoesNotUnify)
        - X == Y → X == Y (structural) / X =:= Y+1 (arithmetic operand)
        - X != Y → X \\== Y (structural) / X =\\= Y+1 (arithmetic operand)

        *goal_position* gates the `is`-RHS dict-splat → `attrs_put/3` lowering
        (see `_convert_is_rhs_splat`): that rewrite produces a goal, which is
        only valid Prolog when the `is` comparison is itself executed as a
        goal (the whole clause body, or a body conjunct). Reached in a
        nested/argument position (e.g. `q(X is {**D, k: v})`, an argument to
        `q`), `attrs_put(...)` would sit there as an inert, never-called data
        term — silently wrong output. So when *goal_position* is False, the
        splat still falls through to the generic dict-splat warning path.

        `attrs_put/3` is an ISO-export staging predicate — it does not exist
        under SWI dict semantics, so the lowering also requires
        `not self.dialect.has_dicts`. Under a `has_dicts` dialect the splat
        instead falls through to the plain `X = Dict` unify, where
        `_convert_dict`'s SWI branch renders the splat's `**D` entry as a
        `_=D` pair inside `dict_create/3` (pre-existing behavior, unchanged
        by this gate).
        """
        # A `<-` lambda reaching term position is untranslatable (2026-09-03).
        # Checked before any Lt lowering, and on the chained path too.
        if self._refuse_arrow_lambda_in_term_position(node):
            return PAtom("???")

        # Handle single comparison
        if len(node.ops) == 1:
            op = node.ops[0]

            # Membership. Negated membership over a value not provably a list
            # is untranslatable (2026-09-03); positive membership is
            # unchanged — the operator deferred that polarity.
            if isinstance(op, python_ast.In):
                return PCompound("member", (
                    self._convert_expr(node.left),
                    self._convert_expr(node.comparators[0]),
                ))
            if isinstance(op, python_ast.NotIn):
                if self._check_negated_membership(node.comparators[0]):
                    return PAtom("???")
                return PCompound("\\+", (
                    PCompound("member", (
                        self._convert_expr(node.left),
                        self._convert_expr(node.comparators[0]),
                    )),
                ))

            if (goal_position and not self.dialect.has_dicts
                    and isinstance(op, python_ast.Is)
                    and isinstance(node.comparators[0], python_ast.Dict)):
                splat_goal = self._convert_is_rhs_splat(
                    node.left, node.comparators[0])
                if splat_goal is not None:
                    return splat_goal

            left = self._convert_expr(node.left)
            right = self._convert_expr(node.comparators[0])

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
                if self._check_negated_membership(comp):
                    parts.append(PAtom("???"))
                else:
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

    def _dict_attr_list(self, keys, values) -> tuple[PTerm, ...]:
        """Build a key-sorted ``attribute(K, V)`` list from parallel
        key/value node sequences.

        Callers must ensure *keys* contains no splat (``**``, i.e. ``None``)
        entries — this only builds the plain-pair list shared by
        :meth:`_convert_dict` (ISO branch) and :meth:`_convert_is_rhs_splat`.
        """
        pairs = [(self._convert_expr(k), self._convert_expr(v))
                 for k, v in zip(keys, values)]
        pairs.sort(key=lambda kv: emit_term(kv[0], self.dialect.operator_table))
        return tuple(PCompound("attribute", (k, v)) for k, v in pairs)

    def _convert_is_rhs_splat(self, left_node, dict_node: python_ast.Dict):
        """Lower ``X is {**D, k1: v1, ...}`` to
        ``attrs_put(D, [attribute(k1, v1), ...], X)``.

        Only the single-splat-FIRST shape (the kit's ``override_key``
        idiom) is translatable this way. Returns ``None`` for any other
        shape — no splat, splat not first, or more than one splat — so the
        caller falls through to the generic ``is``/dict handling, which
        keeps the existing warning/strict-raise path for those cases.
        """
        keys, values = dict_node.keys, dict_node.values
        if not keys or keys[0] is not None:
            return None  # no splat, or the splat isn't the first entry
        if any(k is None for k in keys[1:]):
            return None  # multi-splat — stays untranslatable

        left = self._convert_expr(left_node)
        splat_target = self._convert_expr(values[0])
        attr_list = self._dict_attr_list(keys[1:], values[1:])
        return PCompound("attrs_put", (splat_target, PList(attr_list), left))

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
        if any(k is None for k in node.keys):  # {**expr} splat — no static key set
            self._add_warning("dict splat " + python_ast.unparse(node))
            return PAtom("???")
        return PList(self._dict_attr_list(node.keys, node.values))


# ── Singleton variable post-pass ────────────────────────────────────────

def _prefix_singletons(item: PItem) -> PItem:
    """Rename every singleton (exactly-one-occurrence) variable in *item*
    to a ``_``-prefixed name.

    ISO engines (Scryer) warn on a singleton variable — a name occurring
    only once anywhere it appears. The corpus deliberately writes some
    variables exactly once (a fact-head "any value" position, e.g.
    ``schedule_by_criteria(high, no_accepted_medical_use, DEPENDENCE,
    schedule_i)``), relying on Prolog's convention that a leading ``_``
    silences the warning. clausal_var_to_prolog renames ``DEPENDENCE`` to
    ``Dependence``, which un-silences it purely as an artifact of
    translation — this pass restores the silence at emission time without
    touching source semantics (a rename only; unification is unaffected).

    Counted over *item* alone (clause head+body together, a fact's args,
    or a DCG rule's head+body): the same per-item scope convert_module
    already resets its variable-rename table on (F022), since a variable
    name has no meaning across top-level items in the first place.
    The anonymous variable (``_``) is exempt — every occurrence is already
    independent, so it is never "a singleton" in the sense that matters
    here. A name already spelled with a leading underscore (a Clausal
    ``_x``-style singleton, which clausal_var_to_prolog may leave
    underscore-led in edge cases) is left as-is rather than double-prefixed.

    A plain AST rewrite, applied per item by construction: walking every
    PVar in the item's subterms means DCG hidden args, nested compounds,
    and list elements are all covered without enumerating term shapes by
    hand.
    """
    counts: dict[str, int] = {}

    class _Counter(PrologVisitor):
        def visit_PVar(self, node):
            if node.name != "_":
                counts[node.name] = counts.get(node.name, 0) + 1

    _Counter().visit(item)

    singletons = {name for name, n in counts.items() if n == 1}
    if not singletons:
        return item

    class _Renamer(PrologTransformer):
        def visit_PVar(self, node):
            if node.name in singletons and not node.name.startswith("_"):
                return PVar("_" + node.name)
            return node

    return _Renamer().visit(item)


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


#: Meta-callers the body-local detector recognises, as
#: ``(functor, arity) -> (index of the goal argument, arguments appended to it)``.
#: The appended count IS the mode Scryer wants: ``call_goal(G, A, B, C)`` applies G
#: to three arguments, so G's position is mode ``3`` (§3.3, measured).
#:
#: `call_goal/N` is the kit's whole higher-order protocol and, measured over the kit,
#: the only meta-caller a real host reaches. `call/N` is registered in the engine as
#: an alias of the same trampolines
#: (``clausal/logic/builtins/higher_order.py:46-50``) and is here for that reason.
#:
#: NOTHING SPECULATIVE BELONGS IN THIS TABLE. An earlier draft carried `include/3`,
#: `exclude/3`, `max_by/3` and `min_by/3` on the reasoning that a host reaching one
#: *would* be a meta host. They were removed: no kit host reaches any of them, and
#: they are exactly the shapes a legal corpus is most likely to use as ordinary data
#: constructors, so carrying them bought nothing and risked annotating a data
#: position. Step B re-adds `include/3` when the `clausal_hof` companion exists and
#: something actually consumes it.
META_CALLER_SIGNATURES: dict[tuple[str, int], tuple[int, int]] = {
    **{("call_goal", n): (0, n - 1) for n in range(1, 9)},
    **{("call", n): (0, n - 1) for n in range(1, 9)},
}

#: The mode for a position that IS a goal but whose call arity is not single-valued.
#: ISO's "module-sensitive term": Scryer qualifies the argument at the call site
#: WITHOUT binding it to a name/arity. See :func:`collect_local_meta_modes` for why an
#: integer cannot be used there, and why ``0`` is not a safe stand-in either.
MODE_MODULE_SENSITIVE = ":"

#: What a caller may hand the translator as *meta_modes*: a module path, then each of
#: that module's predicates, then one mode per argument -- an ``int`` for a goal called
#: at that fixed arity, :data:`MODE_MODULE_SENSITIVE` for a goal whose call arity
#: varies, ``None`` for a position that is not a meta position at all. Mirrors
#: *module_signatures*' shape and is keyed the same way.
MetaModeMap = dict[str, dict[tuple[str, int], tuple[int | str | None, ...]]]

#: Goal combinators, as ``(functor, arity) -> indexes of the arguments that are GOALS``.
#: Used to walk a clause body through goal positions only. Everything absent from this
#: table is a leaf as far as the walk is concerned: it is itself a goal, but its
#: arguments are DATA and are never descended into.
GOAL_TRANSPARENT: dict[tuple[str, int], tuple[int, ...]] = {
    (",", 2): (0, 1),
    (";", 2): (0, 1),
    ("->", 2): (0, 1),
    ("*->", 2): (0, 1),
    ("\\+", 1): (0,),
    ("not", 1): (0,),
    ("once", 1): (0,),
    ("ignore", 1): (0,),
    ("call", 1): (0,),
    ("forall", 2): (0, 1),
    ("catch", 3): (0, 2),
    ("findall", 3): (1,),
    ("findall", 4): (1,),
    ("bagof", 3): (1,),
    ("setof", 3): (1,),
    ("aggregate_all", 3): (1,),
    ("^", 2): (1,),
}


def goal_subterms(body: PTerm) -> Iterator[PTerm]:
    """Yield the goals of a clause *body*, and ONLY the goals.

    Descends through the goal combinators of :data:`GOAL_TRANSPARENT` -- so a goal
    under ``once/1``, in a ``findall/3`` goal argument, or in either branch of a
    ``;/2`` is reached -- and stops at everything else: a plain compound is yielded
    as a goal, but its arguments are DATA and are not walked.

    THIS IS A CORRECTNESS FENCE, NOT AN OPTIMISATION. A blanket ``subterms`` walk
    cannot tell a meta-call from a term that merely LOOKS like one, so a clause that
    only BUILDS such a term --

        mk(D, X, Y, T) <- unify(T, include(D, X, Y))

    -- would have ``D`` read as a meta position, and the emitted directive would make
    Scryer module-qualify an ordinary data argument at every call site. Measured
    consequence: the caller gets back ``user_m:foo`` where it passed ``foo``, so a
    later ``X == foo`` FAILS, silently and with no error anywhere. That is precisely
    the class of silent wrongness this ladder exists to remove, so the walk is
    fenced at the source rather than filtered afterwards.
    """
    stack = [body]
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, PCompound):
            continue
        for index in GOAL_TRANSPARENT.get((node.functor, len(node.args)), ()):
            if index < len(node.args):
                stack.append(node.args[index])


def collect_local_meta_modes(pmodule: PModule) -> dict[tuple[str, int], dict[int, int | str]]:
    """Meta positions provable from *pmodule*'s own clause bodies.

    A predicate has a meta position at argument *i* when one of its clauses applies a
    known meta-caller (:data:`META_CALLER_SIGNATURES`) to the variable sitting at head
    position *i*. The search runs over :func:`goal_subterms`, i.e. over GOAL POSITIONS
    ONLY -- a term that merely looks like a meta-call, sitting in an argument of some
    other goal, is data and is never read as evidence.

    Returns ``{(name, arity): {argument index: mode}}``. This is a LOWER BOUND, and
    deliberately so: a host that only threads its argument onward has no body-local
    evidence at all, and guessing one would be worse than the loud failure. Measured
    over the kit, the bound covers the hosts of 258 of the 390 lambda sites; the other
    116 sit at threading hosts and are the exporter fixpoint's job.

    THE AMBIGUOUS-POSITION CONTRACT (controller ruling of 2026-09-05, implemented with
    the mechanism the ruling's premise got wrong -- see below). When two clauses call
    the same argument with DIFFERENT arities the position is still, beyond doubt, a
    goal; only the integer is in question. It is annotated
    :data:`MODE_MODULE_SENSITIVE` (``:``), which qualifies the argument without binding
    an arity, so EVERY chain works. ``?`` stays reserved for positions with NO goal
    evidence at all.

    WHY NOT THE MAXIMUM, AND WHY NOT ``0``. The ruling assumed Scryer reads the integer
    as merely "meta"/"not meta" and ignores its value, which would have made any
    candidate safe. Measured, it does not: **mode ``N`` resolves the argument against
    ``name/N`` in the CALLER's module.** With a caller defining both ``p/2`` and
    ``p/3``, and a host calling its argument at both arities:

        mode 2 -> [short]        only the 2-appended clause resolves
        mode 3 -> [long]         only the 3-appended clause resolves
        mode 0 -> [short,long]   ... but only because no p/0 exists
        mode : -> [short,long]

    so the maximum candidate silently drops the other chain. ``0`` looks like a safe
    stand-in until the caller happens to define ``p/0``, at which point the argument
    binds to that and the caller gets back unbound variables -- no error, wrong
    answers. ``:`` is the only spelling right in all four rows.

    Where a position DOES have a single call arity the integer is emitted: it is the
    most precise annotation and is what §3.3's verified probe uses.
    """
    found: dict[tuple[str, int], dict[int, int | str]] = {}
    for item in pmodule.items:
        if not isinstance(item, PClause) or item.body is None:
            continue
        head = item.head
        if not isinstance(head, PCompound):
            continue
        key = (head.functor, len(head.args))
        position: dict[str, int] = {}
        for index, arg in enumerate(head.args):
            if isinstance(arg, PVar) and arg.name != "_":
                position.setdefault(arg.name, index)
        if not position:
            continue
        for node in goal_subterms(item.body):
            if not isinstance(node, PCompound):
                continue
            signature = META_CALLER_SIGNATURES.get((node.functor, len(node.args)))
            if signature is None:
                continue
            goal_index, appended = signature
            goal = node.args[goal_index]
            if not isinstance(goal, PVar):
                continue
            index = position.get(goal.name)
            if index is None:
                continue
            slot = found.setdefault(key, {})
            previous = slot.get(index, appended)
            slot[index] = appended if previous == appended else MODE_MODULE_SENSITIVE
    return found


def _mode_term(mode: int | str) -> PTerm:
    """One argument of a meta_predicate spec: an integer arity, or ``:``."""
    return PNumber(mode) if isinstance(mode, int) else PAtom(mode)


def _existing_meta_predicate_indicators(item: PItem) -> set[tuple[str, int]]:
    """(name, arity) already declared by a hand-written :- meta_predicate directive.

    Both spellings count. ISO allows one directive to carry a COMMA-SEPARATED list of
    specs -- ``:- meta_predicate(foo(0, ?), bar(?, 2)).`` parses as a single ``,``/2
    argument -- and a hand-written directive in either spelling must suppress the
    generated one for every predicate it names, or the emitted file ends up carrying
    two directives for the same predicate.
    """
    if not isinstance(item, PDirective):
        return set()
    body = item.body
    if not (isinstance(body, PCompound) and body.functor == "meta_predicate"
            and len(body.args) == 1):
        return set()

    found: set[tuple[str, int]] = set()
    pending = [body.args[0]]
    while pending:
        spec = pending.pop()
        if not isinstance(spec, PCompound):
            continue
        if spec.functor == "," and len(spec.args) == 2:
            pending.extend(spec.args)
            continue
        found.add((spec.functor, len(spec.args)))
    return found


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
                                  strict: bool = False,
                                  module_path: str | None = None,
                                  module_signatures: dict[str, set[tuple[str, int]]] | None = None,
                                  meta_modes: MetaModeMap | None = None,
                                  ) -> PModule:
    """Parse .clausal source text and return a Prolog AST (PModule).

    Uses Python's parser on the clausal source, then converts the
    Python AST patterns (trailing comma facts, <- rules, -directives)
    directly into Prolog AST nodes.

    When *strict* is True, any construct with no ISO Prolog equivalent
    raises :class:`UntranslatableConstructError` instead of emitting a
    ``???`` placeholder plus a warning comment.

    *module_path* is the dotted path of the module being translated
    (``"eu.ai_act.prohibited_practices.prohibition"``). When given,
    ``use_module`` file paths are emitted relative to that module's package
    directory, which is what Scryer resolves a consulted path against.

    *module_signatures* maps a dotted target path to that target's filtered
    export set (:func:`module_export_signature`'s return value). When given,
    import lists are narrowed to ``Name/Arity`` pairs the target really
    exports; when omitted alongside *module_path*, the import list is dropped
    entirely (``:- use_module('path').``).

    *meta_modes* supplies ``:- meta_predicate`` argument modes this module's own
    text cannot show -- see :data:`MetaModeMap`. It is looked up under
    *module_path* exactly as passed, and unioned per argument with the body-local
    detection of :func:`collect_local_meta_modes`. Only predicates this module
    actually defines are declared.
    """
    if dialect is None:
        dialect = Dialect.iso()
    tree = python_ast.parse(source)
    converter = _ClausalToProlog(dialect, strict=strict,
                                 module_path=module_path,
                                 module_signatures=module_signatures,
                                 meta_modes=meta_modes,
                                 source_lines=source.splitlines())
    return converter.convert_module(tree)


def clausal_source_to_prolog(source: str, *,
                              dialect: Dialect | None = None,
                              strict: bool = False,
                              module_path: str | None = None,
                              module_signatures: dict[str, set[tuple[str, int]]] | None = None,
                              meta_modes: MetaModeMap | None = None,
                              ) -> str:
    """Translate .clausal source text to Prolog source text.

    Full pipeline: .clausal → Python AST → Prolog AST → .pl text.

    When *strict* is True, any construct with no ISO Prolog equivalent
    raises :class:`UntranslatableConstructError` instead of emitting a
    ``???`` placeholder plus a warning comment.

    *module_path* and *module_signatures* control ``use_module`` emission —
    see :func:`clausal_source_to_prolog_ast`.
    """
    if dialect is None:
        dialect = Dialect.iso()
    pmodule = clausal_source_to_prolog_ast(source, dialect=dialect, strict=strict,
                                           module_path=module_path,
                                           module_signatures=module_signatures,
                                           meta_modes=meta_modes)
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
