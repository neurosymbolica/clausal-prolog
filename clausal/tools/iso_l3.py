"""L3: lower ISO ReaderItems to the SAME transformed Python AST the seam produces.

Plan: `implementation_plans/clausal-iso-to-transformed-ast-2026-09-14.md` (rev 4).
**P1 scope: FACTS ONLY** — facts, atoms, integers, lists. Rules, directives and
arithmetic are P2/P3 and are REFUSED here rather than half-handled, so a gap is a
loud error and not a silently-skipped clause.

WHY THE TRANSFORMED AST IS THE JOIN (plan §1): `compile_module`'s `module_dict` is
the name-resolution environment for the whole compile, touched ~102 times in
compiler_v2. Lowering "direct to the compiler" would mean a second implementation of
name resolution; routing through seam source text goes via the reverse translator,
which is measured NOT an inverse. Producing the same AST inherits module semantics by
construction.

TWO REPRESENTATIONS, and conflating them is the easy mistake:

    reader output   ('fact_a', 1, ('foo_atom',))     functor-first TUPLES; atoms are 1-tuples
    runtime term    fact_a(arg_0=1, arg_1=...)       a PredicateMeta class INSTANCE

L3 is exactly the bridge between them.

`_fields` SPELLING (plan §6 decision 1, taken 2026-09-14): L3 emits positional
`arg_0..arg_{n-1}`. The seam derives field names from the ARGUMENT EXPRESSION -- a
variable `A` becomes field `a`, a non-variable becomes `arg_N` -- which has no stable
ISO analogue, since ISO variable names differ per clause. Measured: `positional(A, B)`
gives `('a','b')` while `mylen([], 0)` gives `('arg_0','arg_1')`. A mismatch between
the two front ends is unreachable within a module (one file, one suffix, one front
end); across modules the class object travels via import, so field names never meet.
Pinned by test.
"""
from __future__ import annotations

import ast
import bisect
from typing import Any

# `$`-prefixed names are not parseable Python, so templates use a DOLLAR_ prefix
# and are renamed after parsing. dump_transformed.py does the same trick in reverse
# to run black over transformed output.
_DOLLAR = "DOLLAR_"


class LoweringRefused(Exception):
    """A construct outside P1 scope. Raised, never skipped -- a silently dropped
    clause is the failure mode the plan's §8.4 ('print the denominator') exists for.
    *span* is the refused item's ``(start, end)`` offset in the ``.pl`` text."""

    def __init__(self, message: str, span=None):
        super().__init__(message)
        self.span = span


def _undollar(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.startswith(_DOLLAR):
            node.id = "$" + node.id[len(_DOLLAR):]
    return tree


def _pos_tuple(span) -> ast.expr:
    if not span:
        return ast.Constant(value=None)
    return ast.Tuple(elts=[ast.Constant(value=int(x)) for x in span], ctx=ast.Load())


def lower_arg(t: Any, span=None) -> ast.expr:
    """One ISO argument term -> the seam's AST for it. P1 subset."""
    if isinstance(t, bool):
        raise LoweringRefused(f"P1: unexpected bool {t!r}")
    if isinstance(t, int):
        return ast.Constant(value=t)
    if isinstance(t, str):
        # STAGE 2: an atom IS its str; a string is the ('$chars', s) TUPLE
        # carrier, which P1 does not lower (refused below).
        return ast.Constant(value=t)
    if isinstance(t, list):
        return ast.List(elts=[lower_arg(x) for x in t], ctx=ast.Load())
    raise LoweringRefused(
        f"P1 handles atoms, integers and proper lists of them (not strings, "
        f"floats, variables or compounds); got {t!r}")


def lower_fact(term: tuple, span=None) -> list[ast.stmt]:
    """A fact term ('name', arg...) -> [declaration, $define_predicate(...)].

    The declaration is the ``$declare_head`` statement the seam rewriter
    emits for a predicate name (``term_rewriting._make_predicate_decl_ast``,
    W4b-3 slice 5; it was a guarded ``PredicateMeta`` class block), and the
    head is built through ``$head`` exactly as the rewriter builds it."""
    if type(term) is not tuple or not term or type(term[0]) is not str:
        raise LoweringRefused(f"not a callable term: {term!r}")
    name, args = term[0], list(term[1:])
    if name == ":-":
        raise LoweringRefused("P1 is facts only; rules are P2")
    fields = tuple(f"arg_{i}" for i in range(len(args)))
    fields_src = "(" + "".join(f"{f!r}, " for f in fields) + ")"

    guard = ast.parse(
        f"{_DOLLAR}declare_head({name!r}, {fields_src})").body

    head = ast.Call(
        func=ast.Name(id=f"{_DOLLAR}head", ctx=ast.Load()),
        args=[ast.Name(id=name, ctx=ast.Load())],
        keywords=[ast.keyword(arg=f, value=lower_arg(a))
                  for f, a in zip(fields, args)],
    )
    define = ast.parse(
        f"{_DOLLAR}define_predicate({_DOLLAR}Predicate(head=None, body=True, "
        f"position=None), {_DOLLAR}module)").body[0]
    pred_call = define.value.args[0]
    pred_call.keywords[0].value = head
    pred_call.keywords[2].value = _pos_tuple(span)
    return guard + [define]


def _line_starts(source: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _item_span(it):
    """(start, end) character offsets of a ReaderItem: a SyntaxIssue carries
    ``span``; a Clause/Directive's span tree leads with it (``spans``)."""
    span = getattr(it, "span", None)
    if span is None:
        span = getattr(it, "spans", None)
        while type(span) is tuple and span and type(span[0]) is tuple:
            span = span[0]
    if (type(span) is tuple and len(span) == 2
            and all(type(x) is int for x in span) and span[0] >= 0):
        return span
    return None


def lower_items(items, *, strict: bool = True, source: "str | None" = None,
                filename: "str | None" = None) -> tuple[ast.Module, dict]:
    """ReaderItems -> (ast.Module, stats). Stats carry the DENOMINATOR (plan §8.4):
    a shrinking population must be visible, not silent.

    *strict* (the default) raises :class:`LoweringRefused` on the first item
    it cannot lower -- a clause, a directive, or a reader ``SyntaxIssue`` --
    so a module never imports with a clause missing (2026-09-29: the item
    was counted and the module loaded without it).  ``strict=False`` is the
    explicit counting mode for tooling that surveys a corpus: it skips and
    counts every refusal in ``stats``.

    *source* (the ``.pl`` text the items were read from) makes every refusal
    name its ``file:line``; *filename* is the file named."""
    body: list[ast.stmt] = []
    stats = {"read": 0, "lowered": 0, "refused": 0, "refusals": []}
    starts = _line_starts(source) if source is not None else None

    def where(span) -> str:
        if span is None:
            return ""
        if starts is None:
            return f"at {span}: "
        line = bisect.bisect_right(starts, span[0])
        return f"{filename or '<.pl>'}:{line}: "

    def refuse(msg: str, span) -> None:
        msg = where(span) + msg
        if strict:
            raise LoweringRefused(msg, span)
        stats["refused"] += 1
        stats["refusals"].append(msg)

    for it in items:
        stats["read"] += 1
        span = _item_span(it)
        kind = type(it).__name__
        if kind == "SyntaxIssue":
            refuse(f"syntax error (SyntaxIssue): {it.message}", span)
            continue
        if kind != "Clause":
            refuse(f"{kind} (P3): {it.term!r}", span)
            continue
        try:
            lowered = lower_fact(it.term)   # positions arrive with slice 1
        except LoweringRefused as e:
            refuse(str(e), span)
            continue
        body.extend(lowered)
        stats["lowered"] += 1
    mod = ast.Module(body=body, type_ignores=[])
    _undollar(mod)
    ast.fix_missing_locations(mod)
    return mod, stats


def read_iso(source: str, op_table=None) -> list:
    """ISO source text -> ReaderItems (L0+L1+L2, unchanged -- plan §2).

    The reader is CLOSED after the source is fed, as ``read_module`` does:
    an end ``.`` is one only when layout or EOF follows it, so without the
    close a last clause with no trailing newline stayed pending and was lost
    (2026-09-29).  ``SyntaxIssue`` items are returned like any other.

    The operator table is Scryer's with no library loaded (D2(b), ISO first
    then Scryer): ``Dialect.scryer_reader()``'s, the table the ``.pl``
    translator reads with -- a FRESH one per call, since ``op/3`` directives
    mutate the reader's table.  So ``:- dynamic d/1.`` is a syntax error, as
    in Scryer, and ``:- dynamic(d/1).`` is the spelling."""
    from clausal.tools.prolog_dialect import Dialect
    from clausal.tools.prolog_reader import read_module
    return read_module(source, op_table=(
        op_table or Dialect.scryer_reader().operator_table))


def lower_module(source: str, filename: "str | None" = None, *,
                 op_table=None) -> tuple[ast.Module, dict, list]:
    """``.pl`` text -> (ast.Module, stats, singletons), strict: the native
    loader's one call.  Raises :class:`LoweringRefused` with a ``file:line``
    message (and the item's span) on the first item it cannot lower.
    *singletons* lists ``(variable name, span)`` for the singleton lint."""
    mod, stats = lower_items(read_iso(source, op_table), source=source,
                             filename=filename)
    return mod, stats, []


def line_of(source: str, span) -> "int | None":
    """The 1-based ``.pl`` line of *span*'s start, or None."""
    if span is None:
        return None
    return bisect.bisect_right(_line_starts(source), span[0])


def warn_singletons(singletons, source: str, filename: str) -> None:
    """The ``.pl`` singleton lint: one ``ClausalSingletonWarning`` per named
    variable occurring once in its clause (a ``_``-prefixed name is exempt,
    the Prolog convention -- D19)."""
    if not singletons:
        return
    import warnings  # noqa: PLC0415
    from clausal.lint_warnings import ClausalSingletonWarning  # noqa: PLC0415
    for name, span in singletons:
        warnings.warn(
            f"{filename}:{line_of(source, span)}: singleton variable `{name}` "
            f"-- a variable occurring once binds nothing. Misspelling? Rename "
            f"to `_{name}` (or `_`) if deliberate",
            ClausalSingletonWarning, stacklevel=3)
