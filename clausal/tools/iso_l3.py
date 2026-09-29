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
from typing import Any

# `$`-prefixed names are not parseable Python, so templates use a DOLLAR_ prefix
# and are renamed after parsing. dump_transformed.py does the same trick in reverse
# to run black over transformed output.
_DOLLAR = "DOLLAR_"


class LoweringRefused(Exception):
    """A construct outside P1 scope. Raised, never skipped -- a silently dropped
    clause is the failure mode the plan's §8.4 ('print the denominator') exists for."""


def _undollar(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.startswith(_DOLLAR):
            node.id = "$" + node.id[len(_DOLLAR):]
    return tree


def _pos_tuple(span) -> ast.expr:
    if not span:
        return ast.Constant(value=None)
    return ast.Tuple(elts=[ast.Constant(value=int(x)) for x in span], ctx=ast.Load())


def _is_atom(t: Any) -> bool:
    return type(t) is str              # STAGE 2: an atom is a str


def lower_arg(t: Any, span=None) -> ast.expr:
    """One ISO argument term -> the seam's AST for it. P1 subset."""
    if isinstance(t, bool):
        raise LoweringRefused(f"P1: unexpected bool {t!r}")
    if isinstance(t, int):
        return ast.Constant(value=t)
    if isinstance(t, str):
        return ast.Constant(value=t)
    if _is_atom(t):
        # An atom reference resolves by NAME at load time (strict atoms), exactly
        # as the seam's $LoadName does.
        call = ast.parse(f"{_DOLLAR}LoadName(name={t[0]!r}, position=None)",
                         mode="eval").body
        call.keywords[1].value = _pos_tuple(span)
        return call
    if isinstance(t, list):
        return ast.List(elts=[lower_arg(x) for x in t], ctx=ast.Load())
    raise LoweringRefused(f"P1 handles atoms, integers, strings and lists; got {t!r}")


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


def lower_items(items, *, strict: bool = True) -> tuple[ast.Module, dict]:
    """ReaderItems -> (ast.Module, stats). Stats carry the DENOMINATOR (plan §8.4):
    a shrinking population must be visible, not silent.

    *strict* (the default) raises :class:`LoweringRefused` on the first item
    it cannot lower -- a clause, a directive, or a reader ``SyntaxIssue`` --
    so a module never imports with a clause missing (2026-09-29: the item
    was counted and the module loaded without it).  ``strict=False`` is the
    explicit counting mode for tooling that surveys a corpus: it skips and
    counts every refusal in ``stats``."""
    body: list[ast.stmt] = []
    stats = {"read": 0, "lowered": 0, "refused": 0, "refusals": []}

    def refuse(msg: str) -> None:
        if strict:
            raise LoweringRefused(msg)
        stats["refused"] += 1
        stats["refusals"].append(msg)

    for it in items:
        stats["read"] += 1
        span = getattr(it, "span", None)
        where = f" at {span}" if span else ""
        if type(it).__name__ != "Clause":
            detail = getattr(it, "message", None) or getattr(it, "term", None)
            refuse(f"{type(it).__name__} (P3){where}"
                   + (f": {detail!r}" if detail is not None else ""))
            continue
        try:
            lowered = lower_fact(it.term, span)
        except LoweringRefused as e:
            refuse(f"{e}{where}")
            continue
        body.extend(lowered)
        stats["lowered"] += 1
    mod = ast.Module(body=body, type_ignores=[])
    _undollar(mod)
    ast.fix_missing_locations(mod)
    return mod, stats


def read_iso(source: str) -> list:
    """ISO source text -> ReaderItems (L0+L1+L2, unchanged -- plan §2).

    The reader is CLOSED after the source is fed, as ``read_module`` does:
    an end ``.`` is one only when layout or EOF follows it, so without the
    close a last clause with no trailing newline stayed pending and was lost
    (2026-09-29).  ``SyntaxIssue`` items are returned like any other."""
    from clausal.tools.prolog_reader import read_module
    return read_module(source)
