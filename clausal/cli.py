"""``clausal`` -- run a Prolog program from the command line.

    clausal [OPTIONS] [FILE [-- ARGS...]]

FILE is a Clausal Prolog (``.clausal``) or ISO Prolog (``.pl``) program.

* ``clausal FILE`` loads the program and runs ``main/0`` if it defines one:
  exit status 0 when ``main`` succeeds, 1 when it fails or raises.  With no
  ``main/0`` it only loads the file -- a load check -- and exits 0.
  (``initialization/1`` is refused in Clausal Prolog, so ``main/0`` is the
  entry point by name.)
* ``-g GOAL`` (repeatable) runs GOAL in the program's module instead of
  ``main/0`` and prints every answer the way a Prolog toplevel does
  (``F = 55.``, ``true.``, ``false.``).  ``--once`` / ``-1`` prints only the
  first answer.  A goal that fails or raises ends the run with status 1.
* ``--test`` runs the program's ``test/1`` and ``test/2`` clauses
  (the same runner as ``python -m clausal.testing FILE``).
* Arguments after ``--`` reach the program as
  ``current_prolog_flag(argv, Args)``, a list of atoms.

Without FILE, ``clausal`` opens the interactive ``?-`` top-level
(``clausal.toplevel``; ``--prolog`` lets queries use ``!`` and ``->``);
``clausal --python`` starts the Python/seam REPL.  Exit statuses: 0 success, 1 a goal failed or raised or the
program did not load, 2 a usage error.
"""
from __future__ import annotations

import argparse
import os
import sys

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

#: The program files the CLI runs: Clausal Prolog, then ISO Prolog.
PROGRAM_SUFFIXES: tuple[str, ...] = (*CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clausal",
        description="Run a Clausal Prolog (.clausal) or ISO Prolog (.pl) "
                    "program. Without FILE, start the interactive REPL.",
        epilog="Arguments after -- are the program's "
               "current_prolog_flag(argv, Args).")
    p.add_argument("file", nargs="?", metavar="FILE",
                   help="the program: " + ", ".join(PROGRAM_SUFFIXES))
    p.add_argument("-g", "--goal", action="append", default=[],
                   metavar="GOAL",
                   help="run GOAL instead of main/0 and print its answers "
                        "(repeatable)")
    p.add_argument("-1", "--once", action="store_true",
                   help="with -g, print only the first answer")
    p.add_argument("--test", action="store_true",
                   help="run the program's test/1 and test/2 clauses")
    p.add_argument("--prolog", action="store_true",
                   help="in the ?- top-level, accept full Prolog syntax in "
                        "queries (!, ->, *->); the default is the restricted "
                        "Clausal Prolog surface")
    p.add_argument("--quads", action="store_true",
                   help="run the quads of FILE (a ?- query and the answer "
                        "description after it) as tests")
    p.add_argument("--python", action="store_true",
                   help="without FILE, start the Python/seam REPL instead of "
                        "the ?- top-level")
    p.add_argument("--toplevel", action="store_true",
                   help="with FILE and no -g, load it and open ?- "
                        "(the default; --toplevel is accepted for symmetry)")
    return p


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """``[...options..., '--', *program_args]`` -> (options, program_args)."""
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1:]
    return argv, []


def _error(msg: str) -> None:
    print(f"clausal: {msg}", file=sys.stderr)


def _describe(exc: BaseException) -> str:
    """An exception as a reader sees it: a LogicException's ball as a term;
    a SyntaxError with a source line as the message, the line and a caret
    under the fault (as Python's own traceback renders one)."""
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    if isinstance(exc, LogicException):
        from clausal.terms import term_writeq  # noqa: PLC0415
        from clausal.logic.solve import _deref_walk  # noqa: PLC0415
        return term_writeq(_deref_walk(exc.term))
    if isinstance(exc, SyntaxError) and exc.text and exc.lineno:
        line = exc.text.rstrip("\n")
        caret = " " * max((exc.offset or 1) - 1, 0) + "^"
        return (f"{type(exc).__name__}: {exc}\n"
                f"    {line}\n    {caret}")
    if isinstance(exc, RecursionError):
        # The ISO term a program's catch/3 sees for it (``python_error_term``:
        # ``error(resource_error(stack), _)``), then the walker's message.
        from clausal.terms import term_writeq  # noqa: PLC0415
        from clausal.logic.exceptions import python_error_term  # noqa: PLC0415
        return f"{term_writeq(python_error_term(exc))}: {exc}"
    return f"{type(exc).__name__}: {exc}"


# ── reading a goal ────────────────────────────────────────────────────────


def _goal_reader_ops(source: str):
    """The operator table a ``-g`` goal is read with: Scryer's defaults,
    plus what the program itself makes an operator -- its ``op/3``
    directives and the operators of the libraries it imports (so a goal can
    use ``#=`` after ``use_module(library(clpz))``)."""
    from clausal.tools.prolog_reader import PrologReader  # noqa: PLC0415
    from clausal.tools.prolog_tokenizer import PL_SOURCE_NESTED_COMMENTS  # noqa: PLC0415
    from clausal.tools.iso_l3_directives import _LIBRARY_OPS  # noqa: PLC0415
    from clausal.tools.toklex import EOF  # noqa: PLC0415

    reader = PrologReader(nested_comments=PL_SOURCE_NESTED_COMMENTS)
    reader.feed(source)
    reader.close()
    table = reader.op_table
    libraries: set[str] = set()
    while True:
        item = reader.read_term()          # op/3 directives apply as read
        if item is EOF:
            break
        term = getattr(item, "term", None)
        if type(item).__name__ != "Directive" or type(term) is not tuple:
            continue
        if term[0] == "use_module" and len(term) >= 2:
            lib = term[1]
            if (type(lib) is tuple and len(lib) == 2 and lib[0] == "library"
                    and type(lib[1]) is str):
                libraries.add(lib[1])
        elif term[0] == "module" and len(term) == 3 and type(term[2]) is list:
            for entry in term[2]:
                if (type(entry) is tuple and len(entry) == 4
                        and entry[0] == "op"):
                    _, prec, spec, name = entry
                    for n in (name if type(name) is list else [name]):
                        table.define(prec, spec, n)
    for lib in libraries:
        for prec, spec, name in _LIBRARY_OPS.get(lib, ()):
            table.define(prec, spec, name)
    return table


def _lower_term(term):
    """A reader term -> ``(goal, {index: Var})``: ``VarRef`` s become fresh
    ``Var`` s and a list spelled with cons cells becomes a Python list
    (as the native front end lowers it).  Shared by ``-g`` and the top-level."""
    from clausal.pythonic_ast.nodes import StarUnpack  # noqa: PLC0415
    from clausal.logic.variables import Var  # noqa: PLC0415
    from clausal.tools.prolog_reader import VarRef  # noqa: PLC0415

    variables: dict[int, Var] = {}

    def build(t):
        if isinstance(t, VarRef):
            v = variables.get(t.i)
            if v is None:
                v = variables[t.i] = Var()
            return v
        if type(t) is tuple and len(t) == 3 and t[0] == ".":
            return build_cons(t)
        if type(t) is tuple:
            return tuple(build(x) for x in t)
        if type(t) is list:
            return [build(x) for x in t]
        return t

    def build_cons(t):
        # The reader spells ``[H|T]`` as the cons cells '.'(H, T), and a
        # proper or partial list never unifies with a cons cell.  So, as
        # the native front end lowers it (iso_l3 ``_cons``): a tail that
        # can be a list -- a variable, a list, ``[]``, a "..." -- splices
        # (a variable tail as the compiler's ``[H, *T]``, since the goal is
        # compiled as a query); any other tail keeps the cons cells of an
        # improper list (D50).  Heads are built before the tail: variables
        # are numbered in reading order.
        heads = []
        while type(t) is tuple and len(t) == 3 and t[0] == ".":
            heads.append(build(t[1]))
            t = t[2]
        if isinstance(t, VarRef):
            return heads + [StarUnpack(value=build(t))]
        if type(t) is list:
            return heads + [build(x) for x in t]
        if t == "[]":
            return heads
        if type(t) is tuple and len(t) == 2 and t[0] == "$chars" \
                and type(t[1]) is str:
            return heads + [sys.intern(c) for c in t[1]]
        out = build(t)
        for h in reversed(heads):
            out = (".", h, out)
        return out

    return build(term), variables


class _Shown(list):
    """The ``(name, Var)`` pairs a toplevel reports, plus ``hidden``: the
    ``_``-led ones it does not report but whose constraints it shows."""
    hidden: tuple = ()


def _read_goal(text: str, op_table):
    """``text`` -> ``(goal_cell, [(name, Var), ...])``: the named variables
    in first-occurrence order, ``_``-led names left out (a toplevel does not
    report them).  A syntax error raises ``SyntaxError``."""
    from clausal.tools.prolog_reader import PrologReader  # noqa: PLC0415
    from clausal.tools.prolog_tokenizer import PL_SOURCE_NESTED_COMMENTS  # noqa: PLC0415
    from clausal.tools.toklex import EOF  # noqa: PLC0415

    body = text.strip()
    if body.endswith("."):
        body = body[:-1]
    # Read as a .pl source file is: ISO block comments do not nest.
    reader = PrologReader(op_table=op_table,
                          nested_comments=PL_SOURCE_NESTED_COMMENTS)
    # The goal is read as a whole term, as a toplevel reads it (priority
    # 1201, ISO 6.2), not as the operand of ?- (at most 1199): a lone
    # operator atom such as \ is a goal (Ulrich #224). The reader sorts
    # the term into an item; a directive or query item gets back the
    # prefix operator it was read with.
    # The end token is set off by a space: glued to a goal that ends in a
    # graphic character (``X = $``) it would read as part of one atom.
    reader.feed(f"{body} .\n")
    reader.close()
    item = reader.read_term()
    kind = type(item).__name__
    if item is EOF or kind not in ("Clause", "DCGRule", "Directive", "Query"):
        from clausal.import_hook import PrologSyntaxError  # noqa: PLC0415
        if kind == "SyntaxIssue":
            # The term a program reading the same text would catch.
            raise PrologSyntaxError(item.message, term=item.error_term())
        raise SyntaxError(f"not a goal: {text}")
    if reader.read_term() is not EOF:
        raise SyntaxError(f"more than one goal in: {text}")
    term = item.term
    if kind == "Directive":
        term = (":-", term)
    elif kind == "Query":
        term = ("?-", term)
    names = dict(item.var_names) if hasattr(item, "var_names") else {}
    goal, variables = _lower_term(term)
    shown = _Shown((names.get(i, f"_G{i}"), v) for i, v in variables.items()
                   if not names.get(i, "_").startswith("_"))
    shown.hidden = tuple((names.get(i, f"_G{i}"), v)
                         for i, v in variables.items()
                         if names.get(i, "_").startswith("_"))
    return goal, shown


def _term_vars(t, out: dict) -> None:
    """The unbound variables of a walked answer, in first-occurrence order:
    ``term_variables/2``'s walk, which reads a partial list's elements
    (``E = [_7|_8]``: the tuple-and-list walk this was skipped them, and a
    constraint on ``_7`` went unprinted) and stops on a cycle."""
    from clausal.logic.builtins.inspection import _collect_vars_impl  # noqa: PLC0415
    found: list = []
    _collect_vars_impl(t, found)
    for x in found:
        out.setdefault(id(x), x)


def _attribute_closure(variables) -> list:
    """*variables*, and the variables their ``dif/2`` pairs and pending
    ``freeze/2``/``when/2`` goals reach, and so on: the variables whose
    constraints an answer shows, as Scryer's projection reaches them.
    ``dif(A, E), copy_term(E, F)`` leaves ``dif(_1, F)``, and ``_1`` may
    carry constraints of its own."""
    from clausal.logic.builtins.inspection import _collect_vars_impl  # noqa: PLC0415
    from clausal.logic.constraints import DIF_KEY  # noqa: PLC0415
    from clausal.logic.coroutining import pending_goals  # noqa: PLC0415
    from clausal.logic.variables import get_attr  # noqa: PLC0415
    out: list = []
    seen: set = set()
    queue = list(variables)
    i = 0
    while i < len(queue):
        v = queue[i]
        i += 1
        if id(v) in seen:
            continue
        seen.add(id(v))
        out.append(v)
        reached: list = []
        for pair in get_attr(v, DIF_KEY) or ():
            _collect_vars_impl(pair, reached)
        for goal in pending_goals([v]):
            _collect_vars_impl(goal, reached)
        queue.extend(x for x in reached if id(x) not in seen)
    return out


def _fd_domain_text(domain) -> str:
    """A CLP(FD) domain as ``1..3\\/5..7`` (``inf``/``sup`` for open ends)."""
    def end(x, low):
        if x in (float("-inf"), float("inf")):
            return "inf" if low else "sup"
        return str(x)
    parts = []
    for lo, hi in domain:
        parts.append(end(lo, True) if lo == hi
                     else f"{end(lo, True)}..{end(hi, False)}")
    return "\\/".join(parts)


_RELATIONS = {"EqConstraint": "#=", "NeConstraint": "#\\=",
              "LtConstraint": "#<", "LeConstraint": "#=<"}


def _fd_constraint_text(c, spell) -> str:
    """One pending CLP(FD) propagator as a goal, or ``pending(Kind, Vars)``
    for a kind not spelled yet (so an answer never claims more freedom than
    it has)."""
    kind = type(c).__name__
    if kind in _RELATIONS:
        return f"{spell(c.lhs)} {_RELATIONS[kind]} {spell(c.rhs)}"
    if kind == "AllDiffConstraint":
        return "all_different([" + ",".join(spell(v) for v in c.vars) + "])"
    if kind == "SumConstraint":
        return ("sum([" + ",".join(spell(v) for v in c.sum_vars)
                + f"],#=,{spell(c.total)})")
    if kind == "ScalarProductConstraint":
        return ("scalar_product([" + ",".join(spell(v) for v in c.coeffs)
                + "],[" + ",".join(spell(v) for v in c.sum_vars)
                + f"],#=,{spell(c.total)})")
    if kind in _NONLINEAR:
        op = _NONLINEAR[kind]
        a, b = spell(c.a), spell(c.b)
        rhs = f"{op}({a},{b})" if op in ("min", "max") else f"{a}{op}{b}"
        return f"{spell(c.z)} #= {rhs}"
    if kind == "LinearNeConstraint" and c.lhs is not None:
        return f"{spell(c.lhs)} #\\= {spell(c.rhs)}"
    if kind == "LinearNeConstraint":
        parts = []
        for k, v in zip(c.coeffs, c.lvars):
            term = spell(v) if abs(k) == 1 else f"{abs(k)}*{spell(v)}"
            parts.append(("-" if k < 0 else "+") + term)
        lhs = "".join(parts).lstrip("+")
        return f"{lhs} #\\= {spell(c.k)}"
    return (f"pending({kind.removesuffix('Constraint').lower()},["
            + ",".join(spell(v) for v in getattr(c, "vars", ())) + "])")


#: clpfd_nonlinear's propagators, as the operator each one is
_NONLINEAR = {"TimesConstraint": "*", "TruncDivConstraint": "//",
              "FloorDivConstraint": " div ", "ModConstraint": " mod ",
              "RemConstraint": " rem ", "PowConstraint": "^",
              "MinConstraint": "min", "MaxConstraint": "max"}


def _fd_dif_residuals(variables, spell) -> list[str]:
    """The ``dif/2`` and CLP(FD) goals on *variables*, in plain form
    (``dif(X,a)``, ``X in 4..5``, ``Y #< X``): what a toplevel prints for a
    constraint left on an answer (operator ruling 2026-10-24: not
    module-qualified).  A domain with no bound is not printed."""
    from clausal.logic.constraints import DIF_KEY, reify_eq  # noqa: PLC0415
    from clausal.logic.builtins.inspection import _copy_term_impl  # noqa: PLC0415
    from clausal.logic.variables import Trail, deref, get_attr, is_var  # noqa: PLC0415

    goals: list[str] = []
    seen: set[int] = set()
    for v in variables:
        for pair in get_attr(v, DIF_KEY) or ():
            if id(pair) in seen:
                continue
            seen.add(id(pair))
            # A pair a later binding made true for good stays in the
            # attribute of its other variables (the wake-up hook only
            # re-checks it): ``dif(C, [a|B]), C = 1`` leaves it on B.  It
            # constrains nothing, and Scryer does not show it.
            # (Tried on a copy with plain variables: on the pair itself the
            # trial binding would run its own dif hook.)
            var_map: dict = {}
            if reify_eq(_copy_term_impl(pair[0], var_map, []),
                        _copy_term_impl(pair[1], var_map, []),
                        Trail()) is False:
                continue
            # One term, so an argument is written as an argument
            # (``dif(A,=)``, as Scryer writes it), not as the right side of
            # ``=`` (``(=)``).
            goals.append(spell(("dif", pair[0], pair[1])))
    inf = float("inf")
    for v in variables:
        state = get_attr(v, "fd")
        if state is None or not state.domain:
            continue
        if state.domain != ((-inf, inf),):
            goals.append(f"{spell(v)} in {_fd_domain_text(state.domain)}")
    for v in variables:
        state = get_attr(v, "fd")
        for c in (state.constraints if state is not None else ()):
            if id(c) in seen:
                continue
            seen.add(id(c))
            # one with a single variable is what its domain already says
            open_vars = {id(deref(x)) for x in getattr(c, "vars", ())
                         if is_var(deref(x))}
            if len(open_vars) >= 2:
                goals.append(_fd_constraint_text(c, spell))
    return goals


def _fresh_names(taken):
    """``_A``, ``_B``, ... ``_Z``, ``_AA``, ... without the names in *taken*."""
    n = 0
    while True:
        i, name = n, ""
        while True:
            name = chr(ord("A") + i % 26) + name
            i = i // 26 - 1
            if i < 0:
                break
        n += 1
        if "_" + name not in taken:
            yield "_" + name


def _coroutine_residuals(variables, spell) -> list[str]:
    """The freeze/2 and when/2 goals pending on *variables*, as goals in
    plain form (``freeze(X,write(hi))``, ``when((nonvar(X);ground(Y)),g)``):
    what Scryer prints for them, without its module qualifiers (operator
    ruling 2026-10-26).  A goal whose variable is bound since is gone."""
    from clausal.logic.coroutining import pending_goals  # noqa: PLC0415
    return [spell(g) for g in pending_goals(variables)]


def _answer(shown, trail) -> str:
    """One answer as a toplevel prints it: ``Name = Value`` for each bound
    answer variable, an unbound one by its own name (``S = f(X)``), then
    the CLP(Q) constraints left on the answer's variables (``{X + Y = 3}``,
    ``{X >= 2}``); ``true`` when there is nothing to show."""
    from clausal.logic import clpq  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    from clausal.logic.variables import Var  # noqa: PLC0415
    from clausal.terms import term_writeq, writer_op_table  # noqa: PLC0415

    values = [(name, _deref_walk(v)) for name, v in shown]
    names: dict[int, str] = {}
    for name, w in values:
        if isinstance(w, Var):
            names.setdefault(id(w), name)
    free: dict = {}
    for _, w in values:
        _term_vars(w, free)
    for name, v in getattr(shown, "hidden", ()):
        w = _deref_walk(v)
        if isinstance(w, Var) and name != "_":     # `_` has no name to keep
            names.setdefault(id(w), name)
        _term_vars(w, free)
    # The variables the goal left constraints on that no answer variable
    # reaches (call_residue_vars/2): a constraint the incomplete solvers
    # (CLP(FD), dif/2, coroutines) cannot yet refute must still show, not
    # vanish into `true`.  (CLP(Q) is complete and projects onto the answer
    # variables, so these take no part in that.)
    from clausal.logic.variables import deref  # noqa: PLC0415
    hidden_residue: dict = {}
    for av in trail.attvars_since(0):
        d = deref(av)
        if isinstance(d, Var) and getattr(d, "attrs", None) \
                and id(d) not in free:
            hidden_residue[id(d)] = d
    # The remaining unbound variables get the names _A, _B, ... in order of
    # appearance (not the engine's _123), skipping any the query uses.
    taken = {n for n, _ in shown} | {n for n, _ in getattr(shown, "hidden", ())}
    fresh = _fresh_names(taken)
    for key in (*free, *hidden_residue):
        if key not in names:
            names[key] = next(fresh)
    # The operators in force now (op/3 run by the program or the goal), as
    # writeq/1 writes with them.
    ops = writer_op_table()
    parts = []
    for name, w in values:
        if isinstance(w, Var) and names[id(w)] == name:
            continue                    # X = X: nothing to say
        # The value is the right operand of = (xfx 700): written as
        # writeq writes an operand of priority 699, so (a,b) and a bare
        # operator atom such as (-) are bracketed, as Scryer prints them.
        parts.append(f"{name} = "
                     f"{term_writeq(w, var_names=names, priority=699, ops=ops)}")
    if free or hidden_residue:
        def spell(x):
            from clausal.logic.solve import _deref_walk as walk  # noqa: PLC0415
            return term_writeq(walk(x), var_names=names, priority=699, ops=ops)
        reached = _attribute_closure(
            list(free.values()) + list(hidden_residue.values()))
        parts += _fd_dif_residuals(reached, spell)
        parts += _coroutine_residuals(reached, spell)
        parts += clpq.residual_q(
            list(free.values()), trail,
            lambda v: names.get(id(v)) or term_writeq(v))
    return ", ".join(parts) if parts else "true"


def _end_answer(text: str) -> str:
    """*text* and its full stop, set off by a space when *text* ends in a
    graphic character (``X = $ .``): ``$.`` would read as one token."""
    from clausal.terms import _GRAPHIC_CHARS  # noqa: PLC0415
    return text + (" ." if text[-1:] in _GRAPHIC_CHARS else ".")


def _run_goal(module, text: str, op_table, once: bool) -> bool:
    """Run one ``-g`` goal, printing its answers.  True iff it had one."""
    from clausal import solve  # noqa: PLC0415

    goal, shown = _read_goal(text, op_table)
    found = False
    for trail in solve(("call", goal), module=module):
        found = True
        print(_end_answer(_answer(shown, trail)))
        sys.stdout.flush()
        if once:
            break
    if not found:
        print("false.")
    return found


# ── the command ───────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    options, program_args = _split_argv(
        list(sys.argv[1:] if argv is None else argv))
    parser = _parser()
    args = parser.parse_args(options)

    if args.toplevel and (args.goal or args.test or args.python):
        parser.error("--toplevel opens ?-; it takes no -g, --test "
                     "or --python")
    if args.quads and (args.toplevel or program_args):
        parser.error("--quads runs the file's quads; it takes no --toplevel "
                     "and no -- ARGS")
    if args.file is None:
        if args.goal or args.test or args.once or args.quads or program_args:
            parser.error("-g, --once, --test, --quads and -- ARGS need a FILE")
        if args.python:
            from clausal.python_repl import main as repl  # noqa: PLC0415
            repl()
            return EXIT_OK
        import clausal  # noqa: F401,PLC0415 -- installs the import hook
        from clausal.toplevel import main as toplevel, user_module  # noqa: PLC0415
        return toplevel(user_module(), None, args.prolog)
    if args.python:
        parser.error("--python takes no FILE")

    path = args.file
    if not path.endswith(PROGRAM_SUFFIXES):
        parser.error(f"{path}: a program is a "
                     f"{' or '.join(PROGRAM_SUFFIXES)} file")
    if not os.path.isfile(path):
        parser.error(f"{path}: no such file")
    if args.quads and (args.goal or args.once or args.test):
        parser.error("--quads runs the file's quads; it takes no -g, "
                     "--once or --test")
    if args.test and (args.goal or args.once):
        parser.error("--test runs the program's tests; it takes no -g")
    if args.once and not args.goal:
        parser.error("--once applies to -g goals")

    import clausal  # noqa: F401,PLC0415 -- installs the import hook
    from clausal.logic.builtins.flags import set_argv  # noqa: PLC0415
    set_argv(program_args)
    # The program's own directory first, so its use_module of a sibling
    # module resolves as it would for a program run from there.
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))

    if args.test:
        from clausal.testing import main as run_tests  # noqa: PLC0415
        return run_tests([path])

    from clausal.testing import load_clausal_module  # noqa: PLC0415
    try:
        module = load_clausal_module(path)
    except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
        _error(f"{path} did not load: {_describe(exc)}")
        return EXIT_FAILED

    if args.quads:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        from clausal.quad_runner import run_quads  # noqa: PLC0415
        summary = run_quads(module, source, _goal_reader_ops(source), path)
        return EXIT_OK if summary.ok else EXIT_FAILED

    if args.goal:
        with open(path, encoding="utf-8") as f:
            op_table = _goal_reader_ops(f.read())
        for text in args.goal:
            try:
                if not _run_goal(module, text, op_table, args.once):
                    return EXIT_FAILED
            except SyntaxError as exc:
                _error(f"-g {text}: syntax error: {exc}")
                return EXIT_USAGE
            except Exception as exc:  # noqa: BLE001
                _error(f"-g {text}: {_describe(exc)}")
                return EXIT_FAILED
        return EXIT_OK

    from clausal import has_predicate, solve  # noqa: PLC0415
    if args.toplevel or not has_predicate(module, "main", 0):
        if args.toplevel or sys.stdin.isatty():
            from clausal.toplevel import main as toplevel  # noqa: PLC0415
            return toplevel(module, path, args.prolog)
        return EXIT_OK                     # loaded: a load check
    try:
        for _ in solve("main", module=module):
            return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        _error(f"main/0 raised: {_describe(exc)}")
        return EXIT_FAILED
    _error("main/0 failed")
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
