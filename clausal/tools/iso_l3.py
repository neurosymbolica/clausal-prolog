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
    return type(t) is tuple and len(t) == 1 and type(t[0]) is str


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
    """A fact term ('name', arg...) -> [class guard, $define_predicate(...)]."""
    if type(term) is not tuple or not term or type(term[0]) is not str:
        raise LoweringRefused(f"not a callable term: {term!r}")
    name, args = term[0], list(term[1:])
    if name == ":-":
        raise LoweringRefused("P1 is facts only; rules are P2")
    fields = tuple(f"arg_{i}" for i in range(len(args)))
    fields_src = "(" + "".join(f"{f!r}, " for f in fields) + ")"

    guard_src = f'''
try:
    if "{name}" not in globals():
        raise NameError
    if isinstance({name}, {_DOLLAR}PredicateMeta) and getattr({name}, "_fields", None) != {fields_src}:
        raise NameError
    if type({name}) is tuple and {name} == ({name!r},):
        raise NameError
except NameError:
    class {name}(metaclass={_DOLLAR}PredicateMeta):
        _fields = {fields_src}
'''
    guard = ast.parse(guard_src).body

    head = ast.Call(
        func=ast.Name(id=name, ctx=ast.Load()),
        args=[],
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


def lower_items(items) -> tuple[ast.Module, dict]:
    """ReaderItems -> (ast.Module, stats). Stats carry the DENOMINATOR (plan §8.4):
    a shrinking population must be visible, not silent."""
    body: list[ast.stmt] = []
    stats = {"read": 0, "lowered": 0, "refused": 0, "refusals": []}
    for it in items:
        stats["read"] += 1
        if type(it).__name__ != "Clause":
            stats["refused"] += 1
            stats["refusals"].append(f"{type(it).__name__} (P3)")
            continue
        try:
            body.extend(lower_fact(it.term, getattr(it, "span", None)))
            stats["lowered"] += 1
        except LoweringRefused as e:
            stats["refused"] += 1
            stats["refusals"].append(str(e))
    mod = ast.Module(body=body, type_ignores=[])
    _undollar(mod)
    ast.fix_missing_locations(mod)
    return mod, stats


def read_iso(source: str) -> list:
    """ISO source text -> ReaderItems (L0+L1+L2, unchanged -- plan §2)."""
    from clausal.tools.prolog_reader import PrologReader
    from clausal.tools.toklex import EOF, NEED_MORE
    r = PrologReader()
    r.feed(source)
    r.feed("")
    out = []
    while True:
        it = r.read_term()
        if it is EOF or it is NEED_MORE:
            return out
        out.append(it)
