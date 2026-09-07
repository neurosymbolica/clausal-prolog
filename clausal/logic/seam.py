"""The ``--`` seam: build a runtime TERM from Python-hosted code.

``++expr`` escapes from Clausal to Python; ``--term`` escapes from Python
back to Clausal.  The rewriter turns ``--verdict(good, "baz")`` into
``$seam(<node>, globals())`` where ``<node>`` is the same intermediate
term node a clause body produces for the same source, and this module
turns that node into the term the engine itself would build:

* a data functor becomes the cell ``("verdict", ...)`` — placed against
  the functor's declared signature exactly as ``term_to_ast_expr`` places
  it (positional args fill leading slots, keywords their named slots,
  omitted slots backfill with a fresh ``Var``), under the host module's
  own functor rules (declared, imported, or ``-implicit_functors``);
* a bare name is the ATOM the host module binds it to — ``("good",)`` —
  under the host module's own atom rules (strict atoms, declarations,
  imports, ``-implicit_atoms``);
* an ALL-CAPS / leading-underscore name is a fresh logic variable, shared
  within the one ``--`` expression;
* ``++expr`` is evaluated EAGERLY: a Python caller is building a value
  now, not a clause to be solved later, so the thunk the rewriter emitted
  is called at once with the expression's own variables;
* quoted literals already arrived decided by the rewriter — ``'...'`` an
  atom in every mode, ``"..."`` per the module's ``-double_quotes`` —
  and pass through unchanged, as do numbers, lists and dicts.

Anything else the term grammar allows in a clause but a Python value
cannot mean (arithmetic nodes, slices, comprehensions) raises a
``SyntaxError`` naming the construct rather than guessing.
"""
from __future__ import annotations

import sys
from typing import Any

from clausal.pythonic_ast.nodes import Call, LoadAttr, LoadName, Node
from clausal.terms import PyThunk, Var


def seam_term(node: Any, module_globals: dict, loose: bool = False) -> Any:
    """Return the runtime term *node* denotes in the module *module_globals*.

    *loose* is the interactive (REPL / IPython) relaxation the rewriter
    requests for a cell: no compiler pass runs there to auto-mint bare
    atoms or declare functors, so an unbound bare name mints its atom and
    an undeclared functor builds a cell at the written arity — the same
    open world ``-implicit_atoms`` + ``-implicit_functors`` give a file.
    A file never asks for it: its own directives decide.
    """
    import ast as _ast
    from clausal.logic.compiler.terms_to_ast import (
        _implicit_functors_active,
        _place_signature_slots,
        _resolve_functor_binding,
        cell_signature_for_name,
        lowering_scope,
    )
    from clausal.logic.predicate import PredicateMeta

    def dotted(attr: LoadAttr) -> str:
        parts = []
        cur: Any = attr
        while isinstance(cur, LoadAttr):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, LoadName):
            raise SyntaxError(
                f"--: unsupported qualified reference {attr!r} in a term")
        parts.append(cur.name)
        return ".".join(reversed(parts))

    def lookup(name: str) -> Any:
        # An imported name is remapped by the rewriter to its module-qualified
        # spelling (``probe.lib.ok``), and ``-import_from`` binds exactly that
        # dotted string as a KEY of the host module's namespace -- the same
        # lookup the compiler's ``LOAD_GLOBAL`` performs for a clause.  Ask
        # for the whole spelling first; only then walk it as attribute access
        # (``-import_module``'d module objects).
        if name in module_globals:
            return module_globals[name]
        cur: Any = module_globals
        for part in name.split("."):
            if isinstance(cur, dict):
                if part not in cur:
                    if loose and "." not in name:
                        from clausal.logic.atoms import mint
                        return mint(name)
                    raise NameError(
                        f"--: {name!r} is not bound in this module — declare "
                        f"or import the atom, or add -implicit_atoms")
                cur = cur[part]
            else:
                cur = getattr(cur, part)
        return cur

    def build(term: Any) -> Any:
        if isinstance(term, Var):
            return term
        if isinstance(term, PyThunk):
            return term.fn(*term.var_objects)
        if isinstance(term, Call) and isinstance(term.func, (LoadName, LoadAttr)):
            fname = (term.func.name if isinstance(term.func, LoadName)
                     else dotted(term.func))
            if not term.args and not term.kwargs:
                # Ruled 2026-09-06: ``foo()`` is not a term form.  The atom
                # is the bare name; a compound has at least one argument.
                raise SyntaxError(
                    f"--: {fname}() is not a term; write the atom {fname}")
            args = [build(a) for a in term.args]
            kwargs = [(kw.name, build(kw.value)) for kw in (term.kwargs or [])]
            with lowering_scope(module_globals):
                sig = cell_signature_for_name(fname)
                owa = loose or _implicit_functors_active(module_globals)
                if sig is not None:
                    functor, fields = sig
                    if owa and not kwargs:
                        return (functor, *args)
                    placed = _place_signature_slots(
                        fields, args, kwargs, functor=functor, missing=Var)
                    return (functor, *placed)
                # The module's own registry lists every functor it declares,
                # data and predicate alike, and it is bound before the module
                # body runs -- so a seam evaluated at module level (a gold
                # table, say) still builds the cell while ``fname`` is
                # transiently bound to a class.  A PREDICATE functor builds
                # the same cell: post-P3-3 a cell is a goal (``call/N``), and
                # no class instance is ever minted from a seam.
                registry = module_globals.get("__clausal_functor_signatures__") or {}
                fields = registry.get(fname)
                if fields is not None:
                    placed = _place_signature_slots(
                        fields, args, kwargs, functor=fname, missing=Var)
                    return (fname, *placed)
                binding = None
                resolved = _resolve_functor_binding(fname, module_globals)
                if resolved is not None:
                    binding = resolved[0]
                if isinstance(binding, PredicateMeta):
                    if kwargs:
                        raise SyntaxError(
                            f"--: {fname!r} is a predicate; a goal cell takes "
                            f"positional arguments only")
                    return (sys.intern(fname), *args)
                if owa and "." not in fname:
                    if kwargs:
                        raise SyntaxError(
                            f"--: functor {fname!r} has no declared signature; "
                            f"keyword placement needs one even under "
                            f"-implicit_functors")
                    return (sys.intern(fname), *args)
            raise NameError(
                f"--: {fname!r} is not a declared or imported functor of this "
                f"module (add it to -module/-private, -import_from it, or "
                f"declare -implicit_functors)")
        if isinstance(term, LoadName):
            return lookup(term.name)
        if isinstance(term, LoadAttr):
            return lookup(dotted(term))
        if isinstance(term, list):
            return [build(e) for e in term]
        if isinstance(term, tuple):
            return tuple(build(e) for e in term)
        if isinstance(term, dict):
            return {k: build(v) for k, v in term.items()}
        if isinstance(term, Node) and _is_arith(term):
            # Arithmetic is a VALUE in this surface (``1 + 2`` in a clause
            # body is 3), so it is evaluated here exactly as the compiler
            # would emit it — provided it is ground; a variable inside
            # arithmetic has no value to give.
            from clausal.logic.compiler.terms_to_ast import arith_to_ast_expr
            for name in _load_names(term):
                lookup(name)        # the seam's own NameError for an unbound atom
            if _contains_var(term):
                raise SyntaxError(
                    f"--: arithmetic over an unbound variable has no value; "
                    f"bind it first or pass the term through ++(...)")
            expr = arith_to_ast_expr(term, {})
            code = compile(_ast.fix_missing_locations(_ast.Expression(body=expr)),
                           "<seam>", "eval")
            result = eval(code, module_globals)  # noqa: S307 — the module's own arithmetic
            import numbers
            if not (isinstance(result, numbers.Number)
                    or type(result).__name__ in ("Decimal", "Quantity")):
                raise TypeError(
                    f"--: arithmetic over non-numbers evaluated to "
                    f"{type(result).__name__}; an atom is not evaluable "
                    f"(type_error(evaluable, ...))")
            return result
        if isinstance(term, Node):
            raise SyntaxError(
                f"--: {type(term).__name__} is not a term a Python caller can "
                f"build; compute it in Python and pass it through ++(...)")
        return term

    return build(node)


def text_of(value: Any) -> str:
    """The text Python-hosted code means by ``str(value)`` / ``f"{value}"``.

    An ATOM gives its spelling -- the one case where Python's own ``str``
    answers with a tuple repr (``"('ok',)"``) that a comparison against text
    then silently mis-scores.  Everything else is plain ``str``: a compound
    still prints as its cell, a Python list of strings the Python way.  The
    rewriter routes only the EXPLICIT text crossings here (``str(x)``, an
    f-string's ``{x}``); ``%s``, ``.format``, ``print`` and container reprs
    are untouched and still show the cell.
    """
    from clausal.logic.atoms import is_atom, spelling
    if is_atom(value):
        return spelling(value)
    return str(value)


def _contains_var(term: Any) -> bool:
    from clausal.logic.variables import is_var
    if is_var(term):
        return True
    if isinstance(term, Node):
        import dataclasses
        if dataclasses.is_dataclass(term):
            return any(_contains_var(getattr(term, f.name))
                       for f in dataclasses.fields(term))
        return any(_contains_var(v) for v in vars(term).values())
    if isinstance(term, (list, tuple)):
        return any(_contains_var(e) for e in term)
    return False


def _load_names(term: Any) -> list:
    """Every bare name inside an arithmetic node, in source order."""
    import dataclasses
    out: list = []
    def walk(t):
        if isinstance(t, LoadName):
            out.append(t.name)
        elif isinstance(t, Node) and dataclasses.is_dataclass(t):
            for f in dataclasses.fields(t):
                walk(getattr(t, f.name))
        elif isinstance(t, (list, tuple)):
            for e in t:
                walk(e)
    walk(term)
    return out


def _is_arith(term: Any) -> bool:
    from clausal.pythonic_ast.nodes import BinOp, UnaryOp
    return isinstance(term, (BinOp, UnaryOp))
