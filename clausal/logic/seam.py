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


class UndefinedAnswer(Exception):
    """A goal in goal position produced a WFS-conditional (undefined) answer.

    The sugar is strict: it neither skips the answer nor takes it as true.
    Truth-aware code uses ``clausal.query_wfs``.
    """


class ResidualConstraints(Exception):
    """An exported variable is still unbound and carries constraint attributes.

    Exports are answers; a constraint store crossing a seam is the lower
    level (``solve`` with an explicit ``Trail``) or, once it exists,
    ``copy_term/3`` inside the goal.
    """


def export(var: Any) -> Any:
    """The fully dereferenced copy of *var*'s value for Python to keep."""
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import deref, is_var
    d = deref(var)
    if is_var(d) and getattr(d, "attrs", None):
        raise ResidualConstraints(
            f"--: exported variable is unbound and constrained "
            f"({sorted(d.attrs)}); exports are answers. Keep the store alive "
            f"with an explicit Trail, or ask for the residue inside the goal")
    return _deref_walk(var)


def _module_of(module_globals: dict):
    try:
        return module_globals["$module"]
    except KeyError:
        raise NameError(
            "--: goal position needs the host module's `$module`; a plain "
            ".py file never reaches the rewriter — host this code in a "
            ".clausal file") from None


def _definite_answers(goal: Any, module) -> "Iterator[None]":
    """Yield once per UNCONDITIONAL answer of *goal*; raise UndefinedAnswer
    on a conditional one.

    Two moments, and they are deliberately different ones:

    * The CALL SITE — which predicate, in which module, with which argument
      objects, and therefore which subgoal key — is taken BEFORE ``solve()``
      starts. That key names the call AS WRITTEN, unbound variables and all,
      which is the key its table entry is stored under. Taking it later
      instead would read the arguments as the answer in hand has just bound
      them, so an OPEN call (``wins(X)``) would go looking for ``wins(d)``'s
      entry and miss — every answer, conditional ones included, then streamed
      out unjudged. Nothing in the site walk depends on the bindings, so
      taking it early costs only the walk.
    * The table ENTRY is still looked up at the FIRST ANSWER. A tabled goal
      can only be judged once SLG has completed for it, and that completion
      happens INSIDE ``solve()``, before its first answer streams out — the
      entry does not exist yet on a goal's first-ever call, so a lookup before
      the loop starts would misread a genuinely tabled goal as untabled. Once
      found the entry is stable for the rest of this call, and a goal with no
      tabled site does no lookup at all.

    Each ANSWER is then judged on its own: the per-answer key of the
    now-bound arguments picks that answer's row out of the entry's index, so
    a table holding one definite and one conditional answer exports the first
    and refuses the second.
    """
    from clausal.logic.solve import solve, _tabled_call_site
    from clausal.logic.tabling import make_subgoal_key
    from clausal.logic.variables import Trail, deref
    from clausal.terms import Undefined
    trail = Trail()
    site = _tabled_call_site(goal, module, trail)
    call_key = None
    goal_args = None
    if site is not None:
        _mod, _functor, _arity, goal_args = site
        call_key = make_subgoal_key(goal_args, trail)
    entry = None
    checked = False
    for _ in solve(goal, module, trail):
        if not checked:
            checked = True
            if site is not None:
                tmod, functor, arity, _ = site
                entry = tmod.db.table_store.get((functor, arity, call_key))
        if entry is not None:
            cand = [deref(a) for a in goal_args]
            idx = entry._answer_index.get(make_subgoal_key(cand, None))
            if idx is not None and entry.truth_value(idx) is Undefined:
                raise UndefinedAnswer(
                    f"--: {goal!r} has a conditional (undefined) answer; use "
                    f"clausal.query_wfs for truth values and delays")
        yield


def once_bind(goal: Any, module_globals: dict) -> bool:
    """True on the first unconditional answer, leaving the goal's variables
    bound for the caller's ``$export`` lines; False if the goal fails."""
    gen = _definite_answers(goal, _module_of(module_globals))
    try:
        next(gen)
    except StopIteration:
        return False
    finally:
        # Close the abandoned search explicitly rather than leaving it to the
        # frame's refcount: on a success we walk away from a generator that
        # still holds a suspended ``solve()``, and CPython's prompt
        # finalization is an implementation detail, not a promise.
        #
        # Closing does NOT undo the trail — ``_definite_answers`` owns a
        # private ``Trail`` and nothing in the close path rewinds it — which
        # is exactly what the two ``$export`` lines the rewriter emits right
        # after this call depend on: the goal's variables are still bound when
        # they run.  (Spec §4: the seam's own variables are discarded WITH
        # their bindings; nothing undoes a trail on the caller's behalf.)
        gen.close()
    return True


def each(goal: Any, variables: tuple, module_globals: dict):
    """Yield the exported values of *variables* once per unconditional answer:
    the bare value for one variable, else a tuple in *variables* order."""
    single = len(variables) == 1
    for _ in _definite_answers(goal, _module_of(module_globals)):
        if single:
            yield export(variables[0])
        else:
            yield tuple(export(v) for v in variables)
