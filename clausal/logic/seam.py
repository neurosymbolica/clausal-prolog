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
from clausal.logic.cells import QUALIFIED_GOAL_FUNCTOR


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
            from clausal.logic.compiler.terms_to_ast import (
                ARITH_RUNTIME_NAMES, arith_to_ast_expr)
            from clausal.logic.exceptions import LogicException  # noqa: PLC0415
            for name in _load_names(term):
                lookup(name)        # the seam's own NameError for an unbound atom
            if _contains_var(term):
                raise SyntaxError(
                    f"--: arithmetic over an unbound variable has no value; "
                    f"bind it first or pass the term through ++(...)")
            expr = _ast.Call(func=_ast.Name(id="$present", ctx=_ast.Load()),
                             args=[arith_to_ast_expr(term, {})], keywords=[])
            code = compile(_ast.fix_missing_locations(_ast.Expression(body=expr)),
                           "<seam>", "eval")
            # The two ``$``-runtime names the value emitter can produce for
            # GROUND arithmetic are not in a module's globals (a literal
            # ``4 / 2`` here raised NameError on ``$Fraction``); they are
            # supplied as eval locals (ARITH_RUNTIME_NAMES, owned by the
            # emitter), without copying the module. Only those: a non-scalar
            # operand can still make the term emitter reach for other
            # ``$``-names, which stay unresolved.
            try:
                result = eval(code, module_globals, ARITH_RUNTIME_NAMES)  # noqa: S307 — the module's own arithmetic
            except LogicException as exc:
                # The exact helpers ($add & co.) refuse a non-number operand
                # LOUDLY in-engine (a catchable type_error(evaluable, ...));
                # this is the PYTHON-facing surface, so the same refusal
                # arrives as the TypeError it always was here.
                raise TypeError(
                    f"--: arithmetic over non-numbers; an atom is not "
                    f"evaluable (type_error(evaluable, ...)): {exc}") from None
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
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_atom(value):
        return spelling(value)
    if is_chars(value):
        return chars_text(value)       # stage 1: a chars string IS its text here
    return str(value)


def text_value(value: Any) -> Any:
    """The value an f-string's bare ``{x}`` hands to ``format()``.

    An ATOM crosses as its spelling; anything else crosses UNCHANGED, so a
    format spec still meets the original value -- ``f"{n:02d}"`` on an int
    is ``"06"`` in a hosted file exactly as in a plain one.  (Spelling
    first and formatting the string, as this crossing once did, raised
    ``Unknown format code 'd' for object of type 'str'`` for every spec that
    is not valid for ``str``.)  ``{x!s}`` keeps Python's meaning -- ``str``
    first, then the spec -- through :func:`text_of` instead.
    """
    from clausal.logic.atoms import is_atom, spelling
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_atom(value):
        return spelling(value)
    if is_chars(value):
        return chars_text(value)       # stage 1
    return value


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


def _has_var_thunk(term: Any) -> bool:
    """True if *term* holds a ``++`` thunk that reads a logic variable."""
    import dataclasses
    from clausal.terms import Compound
    if isinstance(term, PyThunk):
        return bool(term.var_objects)
    if isinstance(term, Node) and dataclasses.is_dataclass(term):
        return any(_has_var_thunk(getattr(term, f.name))
                   for f in dataclasses.fields(term))
    if isinstance(term, Compound):
        return any(_has_var_thunk(a) for a in term.args)
    if isinstance(term, (list, tuple)):
        return any(_has_var_thunk(e) for e in term)
    if isinstance(term, dict):
        return any(_has_var_thunk(k) or _has_var_thunk(v)
                   for k, v in term.items())
    return False


def _goal_vars(goal: Any) -> list:
    """Every Var object reachable in *goal*, first occurrence first, each
    once.  These are the variables an answer binds and a deferred answer
    must be frozen by and re-bound from."""
    import dataclasses
    from clausal.terms import Compound
    seen: set = set()
    out: list = []
    def walk(t):
        if isinstance(t, Var):
            if id(t) not in seen:
                seen.add(id(t))
                out.append(t)
        elif isinstance(t, PyThunk):
            for v in t.var_objects:
                walk(v)
        elif isinstance(t, Node) and dataclasses.is_dataclass(t):
            for f in dataclasses.fields(t):
                walk(getattr(t, f.name))
        elif isinstance(t, Compound):
            for a in t.args:
                walk(a)
        elif isinstance(t, (list, tuple)):
            for e in t:
                walk(e)
        elif isinstance(t, dict):
            for k, v in t.items():
                walk(k)
                walk(v)
    walk(goal)
    return out


def judged_answers(goal: Any, module, exported_vars, trail) -> "Iterator[tuple]":
    """Solve *goal* and yield ``(truth, delays)`` per WFS-surviving answer,
    with the answer's bindings live on *trail* at the yield.  ``truth`` is
    ``True`` or ``Undefined``; an answer that resolution makes WFS-false is
    never yielded.

    HOW: a fresh, never-stored ``TableEntry`` is pushed as the tabling
    LEADER for the whole solve.  Every condition the derivation incurs -- a
    ``not tabled(...)`` that had to be delayed, from any clause body, tabled
    or not; a conditional answer consumed from a complete table; a streaming
    conditional answer from a tabled call that is no longer the root because
    we are beneath it -- lands on that entry through the bookkeeping tabling
    already does for real leaders.  So a conjunction, an untabled wrapper, a
    ``++``-fed call, a nested predicate chain are all judged by exactly the
    conditions THEIR derivation carried, and nothing is reconstructed from a
    table key.

    Three things make the judgement per-ANSWER rather than per-solve:

    * the conditions are TRAILED (``tabling._charge_delays``), so a branch
      that delayed and then FAILED does not leave its delays behind for the
      next answer to inherit -- and a delay incurred before a choice point
      still covers every answer beyond it;
    * a condition consumed from a table is recorded as the ROW it came from
      (``_sources``), not as the delay set that row held at that moment: a
      later delay-free re-derivation makes the row unconditional and nothing
      re-streams it, so only the row itself knows how the table settled.
      The rows are read back HERE, after resolution;
    * DEFINITE answers go into the same entry as everything else, so a
      definite derivation of bindings already deferred as conditional
      collapses them to unconditional (WFS truth is a disjunction OVER
      derivations).  They still stream the moment they are found; the
      collapsed row is skipped at delivery rather than delivered twice.

    Conditional answers are delivered LAST: after the solve is exhausted --
    and only if a real table was driven -- global resolution runs over every
    store the derivation touched, the entry's own rows are resolved against
    them, and the survivors are re-bound from their frozen rows: True ones
    as answers, Undefined ones with their delays, WFS-false ones not at all.
    This is the order a tabled root already delivers in.

    While this generator is SUSPENDED at a yield it holds no place on the
    leader stack: its own leader (and any tabled frame parked above it) is
    detached at the yield and restored on resume.  Two judged goals alive at
    once -- a caller interleaving two ``--`` loops -- would otherwise charge
    the one that resumed to the leader of the one that pushed last.

    A caller that stops early (``once``/``break``) simply abandons the
    generator: ``finally`` pops the leader by identity; the store's own
    drive-episode repair never sees an entry it did not create.
    """
    from clausal.logic.solve import solve
    from clausal.logic.tabling import (
        _FAILED, TableEntry, _leader_ctx, _resolve_all_conditions,
        _resolve_conditions, _unify_answer, current_leader, freeze_args,
        make_subgoal_key, pop_leader, push_leader,
    )
    from clausal.terms import Undefined
    # Judge, freeze and re-bind over the goal's OWN variables -- deduplicating
    # deferred answers over what the caller asked to EXPORT would merge two
    # answers into one row when it asked for nothing.  The caller's variables
    # are added for the goal shapes ``_goal_vars`` cannot walk (a
    # ``ModulePredicate`` call object holds its arguments privately), where
    # they are all there is to go on.
    judge_vars = _goal_vars(goal)
    seen = {id(v) for v in judge_vars}
    for v in exported_vars or ():
        if isinstance(v, Var) and id(v) not in seen:
            seen.add(id(v))
            judge_vars.append(v)
    leader = TableEntry()
    leader._sources = {}          # opt in to late-bound positive conditions
    stack = _leader_ctx.stack

    def detach():
        """Lift our leader -- and any tabled frame parked above it, which is
        ours too -- off the stack for the duration of a yield, and stop
        collecting driven stores while we are not running.  Both are the same
        mistake otherwise: a table another judged goal drives while we are
        suspended is not ours, and resolving its store at our exit would run
        the global fixpoint over a store we never touched."""
        registry = _leader_ctx.driven_stores
        for i in range(len(registry) - 1, -1, -1):
            if registry[i] is driven:
                del registry[i]
                break
        for i in range(len(stack) - 1, -1, -1):
            if stack[i] is leader:
                seg = stack[i:]
                del stack[i:]
                # Still LEADING, just not running: a nested call on a table we
                # are parked inside must consume it, not re-lead it.
                _leader_ctx.detached.append(seg)
                return seg
        return []

    def reattach(seg):
        for i in range(len(_leader_ctx.detached) - 1, -1, -1):
            if _leader_ctx.detached[i] is seg:
                del _leader_ctx.detached[i]
                break
        stack.extend(seg)
        _leader_ctx.driven_stores.append(driven)

    # One entry per CONDITIONAL derivation, in derivation order: (frozen
    # answer, the delays it incurred directly, the table rows it consumed).
    # The rows are only read at the end, so the entry is built after the
    # solve.  A definite derivation needs nothing kept: it streams at once,
    # and its key in ``streamed`` is enough to skip whatever row the
    # conditional derivations of the same bindings later build (a delay-free
    # derivation makes the answer WFS-true whatever else it has).
    derivations: list = []
    streamed: set = set()         # canonical keys already delivered as definite
    driven: list = []             # every table store driven beneath us
    _leader_ctx.driven_stores.append(driven)
    push_leader(leader)
    try:
        for _ in solve(goal, module, trail):
            # Both channels are usually empty (an unconditional derivation),
            # and the emptiness test is what keeps this off the hot path:
            # copying the accumulated source map per answer would be
            # quadratic in a long conjunction.
            conditional = bool(leader._current_delays) or bool(leader._sources)
            answer = freeze_args(judge_vars, trail)
            if not conditional:
                streamed.add(make_subgoal_key(answer, None))
                seg = detach()
                try:
                    yield True, frozenset()
                finally:
                    reattach(seg)
                continue
            derivations.append((answer,
                                frozenset(leader._current_delays),
                                tuple(leader._sources.items())))

        store = module.db.table_store
        stores = [store]
        for st in driven:
            if all(st is not known for known in stores):
                stores.append(st)
        for _answer, direct, sources in derivations:
            # A condition can name a store we never drove: a table another
            # query completed, consumed here off the COMPLETE path.
            for dn in direct:
                if dn.store is not None and all(
                        dn.store is not st for st in stores):
                    stores.append(dn.store)
            for _row, src_store in sources:
                if src_store is not None and all(
                        src_store is not st for st in stores):
                    stores.append(src_store)
        # Resolve only if there is something to resolve.  (The leader
        # context's push COUNTER cannot answer that: it is thread-global, so
        # a table another judged goal drove while we were suspended would
        # make us run the global fixpoint over stores we never touched.)
        if driven or derivations:
            for st in stores:
                _resolve_all_conditions(st)

        # Now every table the derivation touched has settled: read the rows
        # back and give the entry each derivation's FINAL condition.
        for answer, direct, sources in derivations:
            delays = set(direct)
            dead = False
            for (src_entry, i), _src_store in sources:
                if src_entry.conditions[i] is _FAILED:
                    dead = True   # the premise turned out WFS-false
                    break
                delays |= src_entry.delays_for(i)
            if not dead:
                leader.add_answer(answer, frozenset(delays))
        if leader.answers:
            _resolve_conditions(leader, store)

        for i in range(len(leader.answers)):
            truth = leader.truth_value(i)
            if truth is False:
                continue
            if make_subgoal_key(leader.answers[i], None) in streamed:
                continue          # a definite derivation already delivered it
            mark = trail.mark()
            if _unify_answer(judge_vars, leader.answers[i], trail):
                seg = detach()
                try:
                    if truth is Undefined:
                        yield Undefined, leader.delays_for(i)
                    else:
                        yield True, frozenset()
                finally:
                    reattach(seg)
            trail.undo(mark)
    finally:
        pop_leader(leader)
        for i in range(len(_leader_ctx.driven_stores) - 1, -1, -1):
            if _leader_ctx.driven_stores[i] is driven:
                del _leader_ctx.driven_stores[i]
                break
        # A04-F001: an SCC edge recorded against US belongs to the derivation
        # that CALLED us -- a judged goal reached from inside a tabled clause
        # body consumed an evaluating ancestor on ITS behalf.  Dropping the
        # edge with the throwaway would let that leader complete mid-fixpoint.
        if leader.scc_deps:
            below = current_leader()
            if below is not None:
                below.scc_deps |= {d for d in leader.scc_deps if d is not below}


def _definite_answers(goal: Any, module,
                      module_globals: "dict | None" = None) -> "Iterator[None]":
    """Yield once per UNCONDITIONAL answer of *goal*; raise UndefinedAnswer
    on a conditional one.  All the judgement is :func:`judged_answers`;
    this adds the goal-position contract on top (raise, never export, a
    conditional answer) and one refusal that predates it: a ``++`` that
    reads a variable of the same goal in a single tabled call has no value
    before the search, and the compiled query would hand the lambda an
    unbound Var -- refuse loudly rather than run garbage."""
    from clausal.logic.solve import _tabled_call_site
    from clausal.logic.variables import Trail
    from clausal.terms import Undefined
    trail = Trail()
    site = _tabled_call_site(goal, module, trail)
    if site is not None and any(_has_var_thunk(a) for a in site[3]):
        raise SyntaxError(
            f"--: {goal!r}: a ++ over a goal variable in a tabled call has no "
            f"value to judge the call by; bind it in Python first or write "
            f"the term in the goal")
    for truth, _delays in judged_answers(goal, module, (), trail):
        if truth is Undefined:
            raise UndefinedAnswer(
                f"--: {goal!r} has a conditional (undefined) answer; use "
                f"clausal.query_wfs for truth values and delays")
        yield


def each_fresh(make, module_globals: dict):
    """``each``, but the goal's logic variables are MINTED PER EVALUATION.

    THE RE-ENTRANT FORM (roborev job 79, finding 1 -- CONFIRMED by probe, and
    the first three probes of it passed by COINCIDENCE).  A comprehension has
    nowhere to put a statement, so the first version of this hoisted
    ``$v_S = $Var()`` above the enclosing statement.  That is correct only
    where the statement is re-executed per evaluation.  It is not, for a
    comprehension in a lambda body, a ``while`` test, or a nested
    comprehension -- and there one ``Var`` is shared across every evaluation.

    Measured, with the discriminating probe (``sp/1`` has three clauses):

        f = lambda: (S for S in --sp(S))
        g1 = f(); first = next(g1)      # g1 LEFT LIVE, $v_S still bound to 1
        g2 = f(); list(g2)              # saw [1]   -- should be [1, 2, 3]

    Counting ``g2``'s answers is what exposes it: asking only for its FIRST
    answer returns 1 either way, which is why ``(1, 1, 2)`` from the obvious
    probe looked like a pass.

    *make* takes one fresh ``Var`` per goal variable, in the order the
    rewriter emitted its parameters, and returns ``(goal, exported_vars)``.
    Calling it here -- once per evaluation of the iterable -- is what makes
    the binding per-evaluation without any statement to hoist to, and a
    plain CALL is legal in a comprehension iterable where an assignment
    expression is not (the restriction reaches into a lambda body too, so
    the walrus ``while`` uses cannot simply be moved inside one).
    """
    # ``__code__.co_argcount``, NOT ``inspect.signature``: the rewriter names
    # these parameters ``$v_S``, which is a legal name in a compiled AST and
    # not a legal Python IDENTIFIER, and ``inspect`` validates identifiers.
    arity = make.__code__.co_argcount
    goal, variables = make(*(Var() for _ in range(arity)))
    yield from each(goal, variables, module_globals)


def with_bases(goal: Any, bases: dict) -> Any:
    """Resolve a goal written ``--m.pred(A, B)`` against the RUNTIME value of
    *m*, returning the module-qualified goal ``(":", m, pred(A, B))``.

    THE DOTTED RUNTIME MODULE FORM (2026-09-21).  The seam resolves a goal's
    NAME at compile time against the host file's own rules, so ``m.pred``
    reached ``solve`` as the dotted FUNCTOR ``"m.pred"`` and failed with
    ``name 'm.pred' is not defined``.  That shut out the shape every sealed
    scorer is built on -- load the rulebase under test at runtime
    (``module = _RULE.get()``), then call into it -- which had been reaching
    the engine through ``solve(module.pred(X))`` until a term stopped being a
    self-describing goal.

    *bases* maps each dotted base NAME in the goal to a zero-argument thunk
    that reads it where it was written, so a base that is a LOCAL resolves.
    The rewriter emits the thunks; a module-level ``globals()`` read would
    miss every real caller, since the harness binds its module inside a
    function.

    CONSERVATIVE BY CONSTRUCTION.  A base is rewritten ONLY when its thunk
    both evaluates and yields something ``resolve_module`` accepts.  An
    unbound name, a non-module value, or a base this function was handed no
    thunk for leaves the node EXACTLY as it was, so every spelling that
    resolved statically before still does and no new diagnostic can fire on
    working code.

    TOP-LEVEL GOAL ONLY.  A conjunction seam (``--(m.p(X), m.q(Y))``) is left
    alone: the qualified cell is a goal form, and nesting one inside a
    conjunction node is a lowering this has not been measured against.  Each
    ``if``/``for``/``while``/statement seam is one goal, which is the shape
    the harnesses use.
    """
    from clausal.pythonic_ast.nodes import Call, LoadAttr, LoadName

    if not isinstance(goal, Call) or not isinstance(goal.func, LoadAttr):
        return goal
    attr = goal.func
    if not isinstance(attr.object, LoadName):
        return goal                      # a chain deeper than one dot
    base_name = attr.object.name
    thunk = (bases or {}).get(base_name)
    if thunk is None:
        return goal
    try:
        value = thunk()
    except NameError:
        return goal
    module = _module_designator(value)
    if module is None:
        return goal
    inner = Call(func=LoadName(name=attr.attr), args=goal.args,
                 kwargs=goal.kwargs)
    return (QUALIFIED_GOAL_FUNCTOR, module, inner)


def _module_designator(value: Any) -> Any:
    """*value* if it is a MODULE OBJECT, else None.

    NARROWER THAN ``resolve_module`` ON PURPOSE (roborev job 79, finding 3).
    That function is the designator chain, and a designator includes a ``str``
    or an ATOM looked up in ``sys.modules`` — so accepting everything it
    accepts would mean a base bound to a plain string, or to a declared atom
    whose spelling collides with any loaded module (``json``, ``time``,
    ``io``, ``code``), silently turned the goal into a qualified call into
    that Python module.  A base written ``m.pred`` is a module OBJECT or it is
    not this form, and "is this a module?" must not be answered by "would a
    designator resolve?".

    A ``Module`` itself, and an imported ``.clausal`` module (which carries
    its ``Module`` under ``$module`` / ``__clausal_module__``), both answer.
    Anything else — a str, an atom, an int, a class — answers None and leaves
    the goal exactly as it was.
    """
    from clausal.logic.database import Module
    if isinstance(value, Module):
        return value
    namespace = getattr(value, "__dict__", None)
    if isinstance(namespace, dict) and (
            "__clausal_module__" in namespace or "$module" in namespace):
        return value
    return None


def once_bind(goal: Any, module_globals: dict) -> bool:
    """True on the first unconditional answer, leaving the goal's variables
    bound for the caller's ``$export`` lines; False if the goal fails."""
    gen = _definite_answers(goal, _module_of(module_globals), module_globals)
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
    for _ in _definite_answers(goal, _module_of(module_globals), module_globals):
        if single:
            yield export(variables[0])
        else:
            yield tuple(export(v) for v in variables)
