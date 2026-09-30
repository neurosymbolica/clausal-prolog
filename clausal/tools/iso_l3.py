"""L3: lower ISO ReaderItems to the SAME transformed Python AST the seam produces.

Plan: ``implementation_plans/native-iso-reader-step2-2026-09-29.md`` (D1 = (c)
hybrid: clauses are lowered HERE to the transformed AST; directives go through
the seam's own handlers, ``iso_l3_directives``).  Scope today is slices 0-6:
facts, rules, every ISO term shape, the control constructs ``,``
``;`` ``\\+`` ``true`` ``fail``/``false`` and ``call/N``, module-qualified
goals ``m:G``, clpq's goal ``{C}`` (lowered to the seam's
``clpq.rational(C)``), library(reif)'s ``if_/3`` (slice 4, see ``_if``), the
data-position truth values (``true``/``false``/``undefined`` ARE
``True``/``False``/``Undefined``, D35), ``constant(Name)`` (folded at compile time), the
directives of ``iso_l3_directives`` (module/2, use_module/1,2, dynamic,
discontiguous, table, meta_predicate, set_prolog_flag, op, constructors, and
the constants/units family), and the auto-declaration of every atom and data
functor a file uses (slice 3).  clpz's predicates need nothing here: they are
engine builtins under Scryer's names (``clausal.logic.builtins.clpz_names``).
Whatever is
outside that scope -- an unknown directive, ``initialization/1``, a DCG rule,
a reader ``SyntaxIssue``, and by design ``!``, ``->`` and ``*->`` -- is
REFUSED, never half-handled, so a gap is a loud import error and not a
silently skipped clause.

WHY THE TRANSFORMED AST IS THE JOIN (plan §2): ``compile_module``'s
``module_dict`` is the name-resolution environment for the whole compile.
Producing the same (``ast.Module``, ``module_items``) pair the seam produces
inherits module semantics by construction; from ``exec`` onward the native
``.pl`` path and the seam are the same code.

TWO REPRESENTATIONS:

    reader output   ('f', 1, 'foo', VarRef(0))    functor-first TUPLES; atoms are str
    lowered AST     $head(f, arg_0=1, ...) / $Call(func=$LoadName(name='g'), args=[...])

HOW EACH ISO SHAPE LOWERS (the ISO meaning is explicit here, in one place):

* A DATA term (a head argument, a goal argument) lowers to the Python
  expression that builds the runtime term itself: an atom is its ``str``, a
  compound is its functor-first CELL (a tuple), a proper list a ``list``, a
  partial list the seam's ``[H, *T]`` display, ``"..."`` the chars carrier.
  A compound is never routed through ``$LoadName``: name resolution there
  is how the seam's surface meanings reach a term (``max`` would be looked
  up, ``^`` would be xor).  An ISO compound is just data.
* A GOAL lowers by its ISO NAME, always: ``$Call(func=$LoadName(name=f))``.
  ``==`` never becomes ``$ArithEq`` (the seam's ``==`` evaluates), ``is``
  never becomes ``$Unify``, ``^`` is never ``$BitXor`` in a term.  The only
  structural nodes are the control constructs: ``$TupleLiteral`` (``,``),
  ``$Or`` (``;``), ``$Not`` (``\\+``), ``True``/``False`` -- and, inside the
  goal of ``bagof``/``setof``, the ``V^G`` prefix, which the engine's
  grouping reads as ``$BitXor`` (``control_constructs._compile_find_all_core``).
* A VARIABLE GOAL is ``call(G)`` (ISO 7.6.2 body conversion), including a
  variable in a meta-argument position the compiler lowers as a goal
  (``findall/3``'s second argument, and the rest of
  ``ir.META_GOAL_POSITIONS``).

``_fields`` SPELLING (P1 decision 1, 2026-09-14; unchanged): L3 emits
positional ``arg_0..arg_{n-1}``.  The seam derives field names from the
argument expression, which has no stable ISO analogue.  A mismatch between the
two front ends is unreachable within a module; across modules the predicate
travels via import, so field names never meet.  Pinned by test.
"""
from __future__ import annotations

import ast
import bisect
from typing import Any

from clausal.tools.prolog_reader import VarRef

#: The front end's id: the value ``CLAUSAL_PL_FRONTEND`` selects it by, and the
#: salt that keeps its cached bytecode apart from the translator's.
FRONTEND_ID = "native"


class LoweringRefused(Exception):
    """A construct the native front end does not lower.  Raised, never skipped
    -- a silently dropped clause is the failure mode the plan's §8.4 ('print
    the denominator') exists for.  *span* is the ``(start, end)`` character
    offset of the refused item in the ``.pl`` text, when known."""

    def __init__(self, message: str, span=None):
        super().__init__(message)
        self.span = span


# ── cut-free ruling ──────────────────────────────────────────────────────────

_CUT_FREE = ("Clausal is cut-free with no committed choice, by design "
             "(ruling): !, -> and *-> are refused")

#: Control constructs refused by design, and what each one is.
_REFUSED_CONTROL = {
    "!": "`!` (cut)",
    "->": "`->` (if-then)",
    "*->": "`*->` (soft-cut)",
}

#: Goal-argument positions the compiler lowers AS GOALS (``terms_to_goalop``
#: turns these calls into a ``MetaCall``; ``ir.META_GOAL_POSITIONS``), by
#: ``(name, arity)`` -> 0-based argument indexes.  A variable there is
#: refused at compile time (``BareGoalVariableError``), so it is lowered as
#: ``call(G)`` -- the ISO body conversion of a variable goal.
_META_GOAL_ARGS: dict[tuple[str, int], tuple[int, ...]] = {
    ("once", 1): (0,),
    ("call_nth", 2): (0,),
    ("count_all", 2): (0,),
    ("setup_call_cleanup", 3): (0, 1, 2),
    ("call_cleanup", 2): (0, 1),
    ("freeze", 2): (1,),
    ("when", 2): (1,),
    ("findall", 3): (1,),
    ("findall", 4): (1,),
    ("bagof", 3): (1,),
    ("setof", 3): (1,),
    ("catch", 3): (0, 2),
    ("forall", 2): (0, 1),
}

#: clpq's ``{C}``: each comparison -> the seam's node for it (``=`` and
#: ``=:=`` are both equality in library(clpq)).
_CLPQ_COMPARISONS = {"=": "ArithEq", "=:=": "ArithEq", "=\\=": "ArithNeq",
                     "<": "Lt", ">": "Gt", "=<": "LtE", ">=": "GtE"}
_CLPQ_BINARY = {"+": "Add", "-": "Sub", "*": "Mult", "/": "Div"}

#: Goals whose second argument is an ISO iterated goal term, ``V^G``.
_ITERATED_GOAL = {("bagof", 3), ("setof", 3)}

#: ISO-legal predicate names the engine cannot hold: ``ast.Name`` cannot carry
#: them, and the compiler's codegen raises on them (``'True'``/``'False'`` are
#: also the seam's reserved truth values).  Refused with the ``.pl`` line.
_UNREPRESENTABLE_NAMES = ("True", "False", "None")

#: The truth values' ISO spellings, folded in a DATA position (D35):
#: ``Clausal Prolog``'s ``true``/``false``/``undefined`` ARE the values.
_TRUTH_DATA = frozenset({"true", "false", "undefined"})

#: Python names a lowered program must never bind or read by accident.
_DOLLAR = "$"


# ── positions ────────────────────────────────────────────────────────────────


class _Positions:
    """``(start, end)`` character offsets in the ``.pl`` text -> the seam's
    ``(line, col, end_line, end_col)`` (1-based lines, 0-based columns)."""

    def __init__(self, source: "str | None"):
        self._starts = None
        self.source = source
        if source is not None:
            starts = [0]
            for i, ch in enumerate(source):
                if ch == "\n":
                    starts.append(i + 1)
            self._starts = starts

    def line_col(self, offset: int) -> tuple[int, int]:
        i = bisect.bisect_right(self._starts, offset) - 1
        return i + 1, offset - self._starts[i]

    def of(self, span) -> "tuple | None":
        if self._starts is None or not _is_leaf_span(span) or span[0] < 0:
            return None
        line, col = self.line_col(span[0])
        end_line, end_col = self.line_col(span[1])
        return (line, col, end_line, end_col)

    def line(self, span) -> "int | None":
        if self._starts is None or not _is_leaf_span(span) or span[0] < 0:
            return None
        return self.line_col(span[0])[0]


def _is_leaf_span(s) -> bool:
    return (type(s) is tuple and len(s) == 2
            and type(s[0]) is int and type(s[1]) is int)


def _top_span(s):
    """The ``(start, end)`` of a span-tree node (prolog_reader's contract:
    a leaf is the pair itself; a compound/list/curly node leads with it)."""
    if _is_leaf_span(s):
        return s
    if type(s) is tuple and s:
        return _top_span(s[0])
    return None


def _arg_spans(s, n: int) -> list:
    """The argument span subtrees of a compound node, padded to *n*."""
    if type(s) is tuple and len(s) == n + 1 and not _is_leaf_span(s):
        return list(s[1:])
    return [None] * n


def _list_spans(s, n: int) -> list:
    if (type(s) is tuple and len(s) == 2 and type(s[1]) is list
            and len(s[1]) == n):
        return list(s[1])
    return [None] * n


# ── AST building blocks ──────────────────────────────────────────────────────


def _name(ident: str) -> ast.Name:
    return ast.Name(id=ident, ctx=ast.Load())


def _node(kind: str, *args: ast.expr, **kw: ast.expr) -> ast.Call:
    """``$<kind>(*args, **kw)``: a seam node constructor call."""
    return ast.Call(func=_name(_DOLLAR + kind), args=list(args),
                    keywords=[ast.keyword(arg=k, value=v) for k, v in kw.items()])


def _const(value) -> ast.Constant:
    return ast.Constant(value=value)


def _pos_expr(pos) -> ast.expr:
    if pos is None:
        return _const(None)
    return ast.Tuple(elts=[_const(int(x)) for x in pos], ctx=ast.Load())


def _is_callable_name(f) -> bool:
    return type(f) is str


# ── one clause ───────────────────────────────────────────────────────────────


class _ClauseLowering:
    """Lowers ONE clause: owns its variable table (first occurrence is the
    seam's walrus ``(X := $Var())``, in Python's evaluation order, which is
    the order the AST is built in) and its singleton census."""

    def __init__(self, var_names: dict, positions: _Positions, ctx=None):
        self._var_names = var_names
        self._pos = positions
        # The file's directive state (``iso_l3_directives.DirectiveContext``):
        # the double_quotes mode in force, the import remap, module aliases.
        self._ctx = ctx
        self._bound: set[int] = set()
        self.occurrences: dict[str, int] = {}
        self._if_n = 0          # if_/3 truth-value variables minted so far

    # ── variables ──

    @staticmethod
    def py_name(iso_name: str) -> str:
        # ``$v_`` keeps an ISO variable out of the module's own names:
        # ``__name__``, ``True`` and ``Var`` are all legal ISO variables.
        return f"{_DOLLAR}v_{iso_name}"

    def var(self, ref: VarRef) -> ast.expr:
        name = self._var_names.get(ref.i, "_")
        if name == "_":
            return _node("Var")
        self.occurrences[name] = self.occurrences.get(name, 0) + 1
        ident = self.py_name(name)
        if ref.i in self._bound:
            return _name(ident)
        self._bound.add(ref.i)
        return ast.NamedExpr(target=ast.Name(id=ident, ctx=ast.Store()),
                             value=_node("Var"))

    # ── data terms ──

    def term(self, t: Any, sp=None) -> ast.expr:
        if type(t) is VarRef:
            return self.var(t)
        if isinstance(t, bool):
            raise LoweringRefused(f"unexpected bool {t!r} from the reader",
                                  _top_span(sp))
        if type(t) in (int, float):
            return _const(t)
        if type(t) is str:
            # ISO/Scryer: '[]' is the empty list, as the seam compiles it.
            if t == "[]":
                return ast.List(elts=[], ctx=ast.Load())
            if t in _TRUTH_DATA:
                return self._truth_value(t, sp)
            return _const(t)
        if type(t) is list:
            spans = _list_spans(sp, len(t))
            return ast.List(elts=[self.term(x, s) for x, s in zip(t, spans)],
                            ctx=ast.Load())
        if type(t) is tuple and t and _is_callable_name(t[0]):
            if t[0] == "$chars" and len(t) == 2 and type(t[1]) is str:
                return self._double_quoted(t[1])
            if t[0] == "constant" and len(t) == 2:
                return self._constant(t[1], sp)
            if t[0] == "." and len(t) == 3:
                return self._cons(t, sp)
            spans = _arg_spans(sp, len(t) - 1)
            return ast.Tuple(
                elts=[_const(t[0])]
                + [self.term(a, s) for a, s in zip(t[1:], spans)],
                ctx=ast.Load())
        if isinstance(t, _embedded_class()):
            return t.expr               # iso_l3_directives' prepared cell
        raise LoweringRefused(f"unsupported term {t!r}", _top_span(sp))

    def _truth_value(self, t: str, sp) -> ast.expr:
        """D35 (operator ruling 2026-09-30): in a DATA position ``true``,
        ``false`` and ``undefined`` are the truth values themselves --
        Python ``True``/``False`` and the engine's ``Undefined`` -- exactly
        as the seam folds them (``term_rewriting._TRUTH_ALIASES``), so a
        reified ``T`` bound by ``memberd_t/3`` unifies with a written
        ``true``.  ``undefined`` is the seam's ``$LoadName('Undefined')``,
        the injected runtime binding."""
        if t == "undefined":
            return _node("LoadName", name=_const("Undefined"),
                         position=_pos_expr(self._pos.of(_top_span(sp))))
        return _const(t == "true")

    # ── constants (D8): the compile-time fold ──

    def _constant(self, name: Any, sp) -> ast.expr:
        """``constant(Name)`` -> the declared value, by TERM EXPANSION at
        compile time, exactly as the seam lowers it since 2026-09-11: a
        ``$PyThunk`` over the module global the declaration bound (the
        builder the seam's ``constant()`` ends in).  The name must be
        declared ABOVE, or imported; anything else is a load error naming
        the ``.pl`` line, as the seam refuses it."""
        pos = self._pos.of(_top_span(sp))
        if type(name) is not str:
            raise LoweringRefused(
                f"constant() takes the name of a declared constant, not "
                f"{_show_cell(name)}: the argument is a name, never an "
                f"expression. Write constant(max_fine)", _top_span(sp))
        if not self._constant_in_scope(name):
            raise LoweringRefused(
                f"constant({name}): nothing declares `{name}`. Declare it "
                f"with :- constant_value({name}, <value>). or "
                f":- constant_number_units({name}, <number>, <units>). above "
                f"this clause, or import it", _top_span(sp))
        return _thunk(_name(name), pos)

    def _constant_in_scope(self, name: str) -> bool:
        t = getattr(self._ctx, "_t", None)
        return t is not None and (name in t._constants
                                  or name in t._import_remap)

    def _constant_units_goal(self, args: tuple, spans: list, sp, pos):
        """``constant_number_units(Name, N, U)`` -> the seam's COMPILE-TIME
        MODULE INSERTION (``module_constant_units(Module, Name, N, U)``): the
        module is the name's owner -- this module for a declared name, the
        declaring module for an imported one."""
        name, n, u = args
        if type(name) is str:
            t = getattr(self._ctx, "_t", None)
            if t is not None and name in t._constants:
                mod_expr: ast.expr = _name(_DOLLAR + "module")
            elif t is not None and name in t._import_remap:
                owner = t._import_remap[name].rsplit(".", 1)[0]
                mod_expr = ast.Call(
                    func=_name("__import__"), args=[_const(owner)],
                    keywords=[ast.keyword(arg="fromlist", value=ast.List(
                        elts=[_const("_")], ctx=ast.Load()))])
            else:
                raise LoweringRefused(
                    f"constant_number_units({name}, ...): `{name}` is not a "
                    f"constant in this module. Declare it with "
                    f":- constant_number_units({name}, <number>, <units>). "
                    f"or import it from the module that does",
                    _top_span(sp))
            name_term = _thunk(_const(name), pos)
        else:
            mod_expr = _name(_DOLLAR + "module")
            name_term = self.term(name, spans[0])
        lowered = [_thunk(mod_expr, pos), name_term,
                   self.term(n, spans[1]), self.term(u, spans[2])]
        head_pos = self._pos.of(_functor_span(sp, "constant_number_units",
                                              self._pos.source))
        return self._call("module_constant_units", lowered, head_pos, pos)

    def _double_quoted(self, text: str) -> ast.expr:
        """``"..."`` under the ``double_quotes`` flag in force (ISO
        7.11.2.5): ``chars`` (the default) is the chars carrier, exactly as
        the seam emits it; ``codes`` the list of character codes; ``atom``
        the atom."""
        mode = self._ctx.note_literal() if self._ctx is not None else "chars"
        if mode == "codes":
            return ast.List(elts=[_const(ord(c)) for c in text],
                            ctx=ast.Load())
        if mode == "atom":
            return self.term(text)
        return ast.Tuple(elts=[_const("$chars"), _const(text)],
                         ctx=ast.Load())

    def _cons(self, t: tuple, sp) -> ast.expr:
        """A cons chain ``'.'(H, T)`` -> the seam's ``[H, ..., *T]`` display
        (Scryer reads ``'.'(a, [])`` as ``[a]``).

        Only a tail that can BE a list is spliced: a variable, a list, a
        double-quoted literal.  Any other tail -- ``[b|foo]``, ``[b|1]``,
        ``[b|f(x)]`` -- makes an IMPROPER list, which ISO represents as the
        cons cell ``'.'(H, T)``; it is lowered as that compound, a
        ``('.', H, T)`` tuple (ruled 2026-09-30).  Spliced as ``*foo`` the
        seam would read the atom as its chars (``[b|foo]`` = ``[b,f,o,o]``),
        a silently different term."""
        heads: list[tuple] = []
        while type(t) is tuple and len(t) == 3 and t[0] == ".":
            spans = _arg_spans(sp, 2)
            heads.append((t[1], spans[0]))
            t, sp = t[2], spans[1]
        if not self._list_tail(t):
            # Lowered in READING order: a variable's first occurrence is
            # the one that binds it (``var``), and Python evaluates the
            # nested tuple left to right.
            lowered = [self.term(h, s) for h, s in heads]
            out = self.term(t, sp)
            for h in reversed(lowered):
                out = ast.Tuple(elts=[_const("."), h, out], ctx=ast.Load())
            return out
        elts = [self.term(h, s) for h, s in heads]
        if type(t) is list:
            spans = _list_spans(sp, len(t))
            elts.extend(self.term(x, s) for x, s in zip(t, spans))
        elif not (type(t) is str and t == "[]"):
            elts.append(_node("StarUnpack", value=self.term(t, sp),
                              position=_pos_expr(self._pos.of(_top_span(sp)))))
        return ast.List(elts=elts, ctx=ast.Load())

    def _list_tail(self, t: Any) -> bool:
        """Whether a cons chain's tail can be a list: a variable, a list,
        ``[]``, a double-quoted literal read as chars or codes, a
        ``constant(Name)`` (its value is only known at load), or a prepared
        directive cell.  Every other tail -- an atom, a number, a compound,
        a ``"..."`` read as an atom -- ends an improper list."""
        if type(t) is VarRef or type(t) is list:
            return True
        if type(t) is str:
            return t == "[]"
        if type(t) is tuple and len(t) == 2 and t[0] == "$chars" \
                and type(t[1]) is str:
            return getattr(self._ctx, "dq_mode", "chars") != "atom"
        if type(t) is tuple and len(t) == 2 and t[0] == "constant":
            return True
        return isinstance(t, _embedded_class())

    # ── goals ──

    def goal(self, g: Any, sp=None) -> ast.expr:
        """ISO 7.6.2 body conversion, to the seam's goal nodes."""
        pos = self._pos.of(_top_span(sp))
        if type(g) is VarRef:
            return self._call("call", [self.var(g)], pos, pos)
        if type(g) is str:
            if g in _REFUSED_CONTROL:
                raise LoweringRefused(
                    f"{_REFUSED_CONTROL[g]} is refused: {_CUT_FREE}",
                    _top_span(sp))
            if g == "true":
                return _const(True)
            if g in ("fail", "false"):
                return _const(False)
            self._check_goal_name(g, sp)
            return self._call(g, [], pos, pos)
        if type(g) is tuple and g and _is_callable_name(g[0]) and g[0] != "$chars":
            name, args = g[0], g[1:]
            spans = _arg_spans(sp, len(args))
            if name in _REFUSED_CONTROL and len(args) == 2:
                raise LoweringRefused(
                    f"{_REFUSED_CONTROL[name]} is refused: {_CUT_FREE}",
                    _top_span(sp))
            if name == "," and len(args) == 2:
                elts: list[ast.expr] = []
                while (type(g) is tuple and len(g) == 3 and g[0] == ","):
                    s2 = _arg_spans(sp, 2)
                    elts.append(self.goal(g[1], s2[0]))
                    g, sp = g[2], s2[1]
                elts.append(self.goal(g, sp))
                return _node("TupleLiteral",
                             elements=ast.List(elts=elts, ctx=ast.Load()),
                             position=_pos_expr(pos))
            if name == ";" and len(args) == 2:
                left = args[0]
                if (type(left) is tuple and len(left) == 3
                        and left[0] in ("->", "*->")):
                    raise LoweringRefused(
                        f"{_REFUSED_CONTROL[left[0]]} is refused (as the "
                        f"condition of a `;`): {_CUT_FREE}",
                        _top_span(spans[0]) or _top_span(sp))
                return _node("Or", left=self.goal(args[0], spans[0]),
                             right=self.goal(args[1], spans[1]),
                             position=_pos_expr(pos))
            if name == "\\+" and len(args) == 1:
                return _node("Not", operand=self.goal(args[0], spans[0]),
                             position=_pos_expr(pos))
            if name == ":" and len(args) == 2:
                return self._qualified(args, spans, sp, pos)
            if (name == "{}" and len(args) == 1 and self._ctx is not None
                    and self._ctx.clpq):
                return self._clpq(args[0], spans[0], sp, pos)
            if (name == "if_" and len(args) == 3 and self._ctx is not None
                    and self._ctx.reif):
                return self._if(args, spans, sp, pos)
            self._check_goal_name(name, sp)
            if name == "constant_number_units" and len(args) == 3:
                return self._constant_units_goal(args, spans, sp, pos)
            lowered = self._goal_args(name, args, spans)
            head_pos = self._pos.of(_functor_span(sp, name, self._pos.source))
            remap = self._ctx.import_remap if self._ctx is not None else {}
            return self._call(remap.get(name, name), lowered, head_pos, pos)
        # ISO 7.6.2: a number (or anything else) is not callable.
        raise LoweringRefused(
            f"{g!r} is not callable (ISO type_error(callable, {g!r}))",
            _top_span(sp))

    def _goal_args(self, name: str, args: tuple, spans: list) -> list:
        """A goal's arguments: a meta-argument position is a goal (ISO body
        conversion), every other one a data term."""
        key = (name, len(args))
        goal_args = _META_GOAL_ARGS.get(key, ())
        lowered = []
        for i, (a, s) in enumerate(zip(args, spans)):
            if i in goal_args:
                if key in _ITERATED_GOAL:
                    lowered.append(self._iterated_goal(a, s))
                else:
                    lowered.append(self.goal(a, s))
            else:
                if name == "call" and i == 0:
                    self._refuse_control_in(a, s)
                lowered.append(self.term(a, s))
        return lowered

    def _qualified(self, args: tuple, spans: list, sp, pos) -> ast.expr:
        """``m:G`` (D10) -> the seam's qualified call ``a.b.g(...)``: a name
        clash is resolved by qualification, never by an import alias.  *m*
        is a module name this file imported (its dotted path), a dotted path
        itself, or a built-in library (``lists:append/3`` is the builtin)."""
        m, g = args
        m_sp, g_sp = spans
        if type(m) is not str:
            raise LoweringRefused(
                f"the module of a qualified goal must be an atom at load, "
                f"got {m!r}", _top_span(m_sp) or _top_span(sp))
        if type(g) is str:
            gname, gargs, gspans = g, (), []
        elif (type(g) is tuple and g and type(g[0]) is str
              and g[0] != "$chars"):
            gname, gargs = g[0], g[1:]
            gspans = _arg_spans(g_sp, len(gargs))
        else:
            raise LoweringRefused(
                f"{m}:{g!r} -- the goal of a qualified call must be callable "
                f"at load (ISO type_error(callable))",
                _top_span(g_sp) or _top_span(sp))
        if gname in (",", ";", "\\+", ":", "->", "*->", "!") or (
                gname in ("true", "fail", "false") and not gargs):
            raise LoweringRefused(
                f"{m}:{gname}/{len(gargs)} -- qualify each goal, not a "
                f"control construct", _top_span(sp))
        aliases = self._ctx.module_aliases if self._ctx is not None else {}
        if m not in aliases and m in _builtin_libraries():
            return self.goal(g, g_sp)
        if self._ctx is not None:
            dotted, why = self._ctx.resolve_module(m)
            if dotted is None:
                raise LoweringRefused(f"{m}:{gname}/{len(gargs)}: {why}",
                                      _top_span(m_sp) or _top_span(sp))
            if dotted == "":            # the file's own module
                return self.goal(g, g_sp)
        else:
            dotted = m
        self._check_goal_name(gname, g_sp)
        mpos = _pos_expr(self._pos.of(_top_span(m_sp)))
        parts = dotted.split(".")
        obj = _node("LoadName", name=_const(parts[0]), position=mpos)
        for p in parts[1:]:
            obj = _node("LoadAttr", object=obj, attr=_const(p), position=mpos)
        func = _node("LoadAttr", object=obj, attr=_const(gname),
                     position=_pos_expr(pos))
        return _node(
            "Call", func=func,
            args=ast.List(elts=self._goal_args(gname, gargs, gspans),
                          ctx=ast.Load()),
            kwargs=ast.List(elts=[], ctx=ast.Load()),
            position=_pos_expr(pos))

    def _clpq(self, c: Any, c_sp, sp, pos) -> ast.expr:
        """The clpq goal ``{C}`` -> the seam's ``clpq.rational(C)``: one
        comparison node, or a ``$TupleLiteral`` of them for a conjunction,
        over the seam's arithmetic nodes -- the AST the seam's own
        ``clpq.rational((X + Y == 10, X - Y <= 4))`` lowers to."""
        parts: list = []
        while type(c) is tuple and len(c) == 3 and c[0] == ",":
            s2 = _arg_spans(c_sp, 2)
            parts.append((c[1], s2[0]))
            c, c_sp = c[2], s2[1]
        parts.append((c, c_sp))
        nodes = [self._clpq_constraint(p, s) for p, s in parts]
        arg = nodes[0] if len(nodes) == 1 else _node(
            "TupleLiteral", elements=ast.List(elts=nodes, ctx=ast.Load()),
            position=_pos_expr(self._pos.of(_top_span(c_sp))))
        mpos = _pos_expr(self._pos.of(_top_span(sp)))
        func = _node("LoadAttr",
                     object=_node("LoadName", name=_const("clpq"),
                                  position=mpos),
                     attr=_const("rational"), position=mpos)
        return _node("Call", func=func,
                     args=ast.List(elts=[arg], ctx=ast.Load()),
                     kwargs=ast.List(elts=[], ctx=ast.Load()),
                     position=_pos_expr(pos))

    def _clpq_constraint(self, c: Any, sp) -> ast.expr:
        if (type(c) is tuple and len(c) == 3 and type(c[0]) is str
                and c[0] in _CLPQ_COMPARISONS):
            s2 = _arg_spans(sp, 2)
            return _node(_CLPQ_COMPARISONS[c[0]],
                         left=self._clpq_expr(c[1], s2[0]),
                         right=self._clpq_expr(c[2], s2[1]),
                         position=_pos_expr(self._pos.of(_top_span(sp))))
        raise LoweringRefused(
            f"{{}}/1 (clpq): {c!r} is not a constraint; the braces hold "
            f"comparisons (=, =:=, =\\=, <, >, =<, >=) joined by `,`",
            _top_span(sp))

    def _clpq_expr(self, e: Any, sp) -> ast.expr:
        if type(e) is VarRef:
            return self.var(e)
        if type(e) in (int, float):
            return _const(e)
        if type(e) is tuple and len(e) == 3 and e[0] in _CLPQ_BINARY:
            s2 = _arg_spans(sp, 2)
            return _node(_CLPQ_BINARY[e[0]],
                         left=self._clpq_expr(e[1], s2[0]),
                         right=self._clpq_expr(e[2], s2[1]),
                         position=_pos_expr(self._pos.of(_top_span(sp))))
        if type(e) is tuple and len(e) == 2 and e[0] == "-":
            return _node("Negate",
                         operand=self._clpq_expr(e[1], _arg_spans(sp, 1)[0]),
                         position=_pos_expr(self._pos.of(_top_span(sp))))
        if type(e) is tuple and len(e) == 2 and e[0] == "+":
            return self._clpq_expr(e[1], _arg_spans(sp, 1)[0])
        if type(e) is tuple and len(e) == 2 and e[0] == "constant":
            # D8's compile-time fold, as in any other term position (the
            # seam's ``{Q == 100 * constant(one_euro)}`` folds it too).
            return self._constant(e[1], sp)
        raise LoweringRefused(
            f"{{}}/1 (clpq): {e!r} is not a linear arithmetic expression "
            f"(numbers, variables, + - * /)", _top_span(sp))

    # ── library(reif)'s if_/3 ──

    def _if(self, args: tuple, spans: list, sp, pos) -> ast.expr:
        """``if_(If_1, Then_0, Else_0)`` with Scryer's library(reif) meaning:
        ``call(If_1, T)``, then Then_0 when T is true, Else_0 when false
        (instantiation_error unbound, type_error(boolean, T) otherwise).

        * ``X = Y`` -> the seam's reified branch, ``$IfExpr`` over
          ``$Unify`` (reif's (=)/3: true, X = Y first, then false,
          dif(X, Y)); ``dif(X, Y)`` -> the same with the arms swapped
          (reif's dif/3 is =/3 negated, false first).
        * ``(A, B)`` / ``(A ; B)`` -> reif's (',')/3 and (;)/3 unfolded:
          ``if_(A, if_(B, Then, Else), Else)`` and
          ``if_(A, Then, if_(B, Then, Else))``.
        * anything else (a closure, a variable) ->
          ``call(If_1, T), must_be(boolean, T), $IfExpr(T = true, ...)``.

        The arms are lowered in the order the built AST evaluates them, so a
        variable's first occurrence (the walrus) is the one evaluated
        first."""
        c, th, el = args
        c_sp, th_sp, el_sp = spans
        top = _top_span(sp)
        ppos = _pos_expr(pos)
        if type(c) is tuple and len(c) == 3 and c[0] in (",", ";"):
            a_sp, b_sp = _arg_spans(c_sp, 2)
            if c[0] == ",":
                inner = ("if_", c[2], th, el), (top, b_sp, th_sp, el_sp)
                return self._if((c[1], inner[0], el),
                                [a_sp, inner[1], el_sp], sp, pos)
            inner = ("if_", c[2], th, el), (top, b_sp, th_sp, el_sp)
            return self._if((c[1], th, inner[0]),
                            [a_sp, th_sp, inner[1]], sp, pos)
        if type(c) is tuple and len(c) == 3 and c[0] in ("=", "dif"):
            l_sp, r_sp = _arg_spans(c_sp, 2)
            test = _node("Unify", left=self.term(c[1], l_sp),
                         right=self.term(c[2], r_sp),
                         position=_pos_expr(self._pos.of(_top_span(c_sp))))
            if c[0] == "=":
                body, orelse = self.goal(th, th_sp), self.goal(el, el_sp)
            else:
                body = self.goal(el, el_sp)
                orelse = self.goal(th, th_sp)
            return _node("IfExpr", test=test, body=body, orelse=orelse,
                         position=ppos)
        self._refuse_control_in(c, c_sp)
        self._if_n += 1
        t_ident = f"{_DOLLAR}if_T{self._if_n}"
        t_first = ast.NamedExpr(target=ast.Name(id=t_ident, ctx=ast.Store()),
                                value=_node("Var"))
        call_c = self._call("call", [self.term(c, c_sp), t_first], pos, pos)
        check = self._call("must_be", [_const("boolean"), _name(t_ident)],
                           pos, pos)
        branch = _node("IfExpr",
                       test=_node("Unify", left=_name(t_ident),
                                  right=_const(True), position=ppos),
                       body=self.goal(th, th_sp), orelse=self.goal(el, el_sp),
                       position=ppos)
        return _node("TupleLiteral",
                     elements=ast.List(elts=[call_c, check, branch],
                                       ctx=ast.Load()),
                     position=ppos)

    def _iterated_goal(self, g: Any, sp) -> ast.expr:
        """``V1^V2^G`` in bagof/setof -> ``$BitXor(left=V1, right=...)``, the
        shape the compiler strips the existential prefix from."""
        if type(g) is tuple and len(g) == 3 and g[0] == "^":
            spans = _arg_spans(sp, 2)
            return _node("BitXor", left=self.term(g[1], spans[0]),
                         right=self._iterated_goal(g[2], spans[1]),
                         position=_pos_expr(self._pos.of(_top_span(sp))))
        return self.goal(g, sp)

    def _refuse_control_in(self, g: Any, sp) -> None:
        """A goal written as ``call/N``'s first argument is still a goal: the
        cut-free refusal applies to what is visible of it at load time."""
        if type(g) is str and g in _REFUSED_CONTROL:
            raise LoweringRefused(
                f"{_REFUSED_CONTROL[g]} is refused: {_CUT_FREE}", _top_span(sp))
        if type(g) is tuple and g and type(g[0]) is str:
            if g[0] in _REFUSED_CONTROL and len(g) == 3:
                raise LoweringRefused(
                    f"{_REFUSED_CONTROL[g[0]]} is refused: {_CUT_FREE}",
                    _top_span(sp))
            if g[0] in (",", ";") and len(g) == 3 or g[0] == "\\+" and len(g) == 2:
                for a, s in zip(g[1:], _arg_spans(sp, len(g) - 1)):
                    self._refuse_control_in(a, s)

    def _check_goal_name(self, name: str, sp) -> None:
        if name in _UNREPRESENTABLE_NAMES:
            raise LoweringRefused(_unrepresentable(name), _top_span(sp))
        if name.startswith(_DOLLAR):
            raise LoweringRefused(
                f"`{name}` is a reserved name: a `$`-prefixed predicate is "
                f"the engine's own", _top_span(sp))

    def _call(self, name: str, args: list, name_pos, pos) -> ast.expr:
        return _node(
            "Call",
            func=_node("LoadName", name=_const(name), position=_pos_expr(name_pos)),
            args=ast.List(elts=args, ctx=ast.Load()),
            kwargs=ast.List(elts=[], ctx=ast.Load()),
            position=_pos_expr(pos))


def _thunk(expr: ast.expr, pos) -> ast.expr:
    """``$PyThunk(lambda: expr, [], _position=pos)``: the seam's
    ``_build_py_thunk_ast`` with no captured logic variables."""
    lam = ast.Lambda(args=ast.arguments(posonlyargs=[], args=[], vararg=None,
                                        kwonlyargs=[], kw_defaults=[],
                                        kwarg=None, defaults=[]),
                     body=expr)
    return ast.Call(func=_name(_DOLLAR + "PyThunk"),
                    args=[lam, ast.List(elts=[], ctx=ast.Load())],
                    keywords=[ast.keyword(arg="_position",
                                          value=_pos_expr(pos))])


def _show_cell(t) -> str:
    from clausal.tools.iso_l3_directives import _show  # noqa: PLC0415
    return _show(t)


def _embedded_class():
    from clausal.tools.iso_l3_directives import Embedded  # noqa: PLC0415
    return Embedded


def _builtin_libraries() -> frozenset:
    from clausal.tools.iso_l3_directives import _BUILTIN_LIBRARIES  # noqa: PLC0415
    return _BUILTIN_LIBRARIES


def _unrepresentable(name: str) -> str:
    return (f"`{name}` cannot name a predicate in Clausal (ISO allows it; the "
            f"engine reserves True/False/None): rename the predicate")


def _functor_span(sp, name: str, source: "str | None" = None):
    """The span of a goal's functor name when the goal is written in prefix
    form ``f(...)`` -- the source there starts with the name and a ``(`` --
    else the whole goal (an operator goal ``A == B`` starts with its left
    operand, which is not the name)."""
    top = _top_span(sp)
    if top is None:
        return None
    end = top[0] + len(name)
    if source is not None and source[top[0]:end + 1] == name + "(":
        return (top[0], end)
    return top


# ── clauses ──────────────────────────────────────────────────────────────────


def lower_clause(term: Any, spans=None, var_names=None,
                 positions: "_Positions | None" = None,
                 singletons: "list | None" = None, ctx=None) -> list[ast.stmt]:
    """A clause term (a fact, or ``(H :- B)``) -> ``[$declare_head(...),
    $define_predicate(...)]``.

    The declaration is the ``$declare_head`` statement the seam rewriter
    emits for a predicate name (``term_rewriting._make_predicate_decl_ast``),
    and the head is built through ``$head`` exactly as the rewriter builds it.
    *singletons*, when given, receives ``(name, span)`` for each named
    variable that occurs once (a ``_``-prefixed name is exempt: D19)."""
    positions = positions or _Positions(None)
    var_names = var_names or {}
    whole_span = _top_span(spans)
    if type(term) is tuple and len(term) == 3 and term[0] == ":-":
        head, body = term[1], term[2]
        head_sp, body_sp = _arg_spans(spans, 2)
    else:
        head, body = term, None
        head_sp, body_sp = spans, None

    if type(head) is VarRef:
        raise LoweringRefused(
            "a clause head is a variable (ISO instantiation_error)", whole_span)
    if type(head) is str:
        name, args = head, ()
    elif type(head) is tuple and head and type(head[0]) is str \
            and head[0] != "$chars":
        name, args = head[0], head[1:]
    else:
        raise LoweringRefused(
            f"a clause head is not callable: {head!r} (ISO type_error(callable))",
            whole_span)
    if name in _UNREPRESENTABLE_NAMES:
        raise LoweringRefused(_unrepresentable(name), whole_span)
    if name.startswith(_DOLLAR):
        raise LoweringRefused(
            f"`{name}` is a reserved name: a `$`-prefixed predicate is the "
            f"engine's own", whole_span)
    if name in (",", ";", "->", "*->", "!", "\\+", ":-", "call") \
            or (name in ("true", "fail", "false") and not args):
        raise LoweringRefused(
            f"cannot define the control construct {name}/{len(args)} (ISO "
            f"permission_error(modify, static_procedure, {name}/{len(args)}))",
            whole_span)

    lw = _ClauseLowering(var_names, positions, ctx)
    fields = tuple(f"arg_{i}" for i in range(len(args)))
    decl = ast.Expr(value=ast.Call(
        func=_name(_DOLLAR + "declare_head"),
        args=[_const(name), ast.Tuple(elts=[_const(f) for f in fields],
                                      ctx=ast.Load())],
        keywords=[]))
    head_ast = ast.Call(
        func=_name(_DOLLAR + "head"),
        args=[_name(name)],
        keywords=[ast.keyword(arg=f, value=lw.term(a, s))
                  for f, a, s in zip(fields, args, _arg_spans(head_sp, len(args)))])
    body_ast = _const(True) if body is None else lw.goal(body, body_sp)
    define = ast.Expr(value=ast.Call(
        func=_name(_DOLLAR + "define_predicate"),
        args=[_node("Predicate", head=head_ast, body=body_ast,
                    position=_pos_expr(positions.of(whole_span))),
              _name(_DOLLAR + "module")],
        keywords=[]))
    if singletons is not None:
        for vname, count in lw.occurrences.items():
            if count == 1 and not vname.startswith("_"):
                singletons.append((vname, whole_span))
    return [decl, define]


def lower_fact(term: Any, span=None) -> list[ast.stmt]:
    """P1's entry point, kept: a fact (or clause) term with no source map."""
    return lower_clause(term, span)


def lower_arg(t: Any, span=None) -> ast.expr:
    """One ISO data term -> the AST that builds it (variables fresh per call)."""
    return _ClauseLowering({}, _Positions(None)).term(t, span)


# ── modules ──────────────────────────────────────────────────────────────────


def _item_span(it):
    span = getattr(it, "span", None)
    if span is not None:
        return span
    return _top_span(getattr(it, "spans", None))


class Lowered:
    """One ``.pl`` file lowered: the transformed ``tree``, its ``stats``
    (read/lowered/refused plus ``directives``), the ``singletons`` census,
    the ``module_items`` the seam's directive handlers produced, and the
    directive ``context`` (for its D11 warning)."""

    __slots__ = ("tree", "stats", "singletons", "module_items", "context")

    def __init__(self, tree, stats, singletons, module_items, context):
        self.tree = tree
        self.stats = stats
        self.singletons = singletons
        self.module_items = module_items
        self.context = context


def lower_items(items, *, strict: bool = True, source: "str | None" = None,
                filename: "str | None" = None,
                singletons: "list | None" = None,
                op_table=None, directives_only: bool = False,
                source_path: "str | None" = None,
                module_name: "str | None" = None,
                surface: "str | None" = None,
                _lowered: "list | None" = None) -> tuple[ast.Module, dict]:
    """ReaderItems -> (ast.Module, stats).  Stats carry the DENOMINATOR (plan
    §8.4): a shrinking population must be visible, not silent.

    *items* may be a lazy iterable: a directive is lowered BEFORE the next
    item is read, so an ``op/3`` it applies to *op_table* (the reader's own
    table) governs the items after it, as in Scryer.

    *strict* (the default) raises :class:`LoweringRefused` on the first item
    it cannot lower -- an unknown or refused directive, a DCG rule, a refused
    control construct, or a reader ``SyntaxIssue`` -- so a module never
    imports with a clause missing.  ``strict=False`` is the explicit counting
    mode for tooling that surveys many files: it skips and counts every
    refusal in ``stats``.

    *directives_only* (the loader's cache-hit path) lowers the directives
    alone -- their module items are what that path needs -- and counts each
    clause as ``skipped``.

    *source* (the ``.pl`` text the items were read from) turns spans into
    seam positions and every refusal message into a ``file:line`` one.

    *source_path* and *module_name* (the file's full path and the dotted
    name it is imported as; the loader passes both) let a ``use_module``
    path resolve against the importing file's own directory first, as
    Scryer does; without them only the dotted reading on ``sys.path``
    is available.

    *surface* (``clausal.end_module.surface_of``'s name for the file's
    surface; default: from *source_path* or *filename*, else ``pl``)
    decides whether a module file must end with ``end_module/1`` when no
    setting says otherwise.  end_module itself is checked whatever the
    surface: the last item, naming the open module."""
    from clausal.end_module import EndModuleError, surface_of  # noqa: PLC0415
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        DirectiveContext, DirectiveRefused, Uses, prescan_constructors)
    if surface is None:
        surface = surface_of(source_path or filename or "") or "pl"
    positions = _Positions(source)
    where_file = filename or "<.pl>"
    ctx = DirectiveContext(source=source, filename=where_file,
                           positions=positions, op_table=op_table,
                           source_path=source_path, module_name=module_name)
    if source is not None:
        ctx.prescanned = prescan_constructors(source)
    uses = Uses()
    body: list[ast.stmt] = []
    stats = {"read": 0, "lowered": 0, "refused": 0, "skipped": 0,
             "directives": 0, "refusals": []}

    def where(span) -> str:
        line = positions.line(span) if span is not None else None
        if line is not None:
            return f"{where_file}:{line}: "
        return f"at {span}: " if span else ""

    def refuse(msg: str, span) -> None:
        if strict:
            raise LoweringRefused(where(span) + msg, span)
        stats["refused"] += 1
        stats["refusals"].append(where(span) + msg)

    defined: set = set()    # (name, arity) of each procedure defined here
    heads: dict = {}        # predicate name -> its first clause's span
    for it in items:
        stats["read"] += 1
        kind = type(it).__name__
        span = _item_span(it)
        if kind == "SyntaxIssue":
            refuse(_syntax_issue_message(it, source), span)
            continue
        if not (kind == "Directive" and _is_end_module(it.term)):
            # end_module/1 is the file's last item (ISO 13211-2): nothing
            # but comments may follow it.
            try:
                ctx.end_module.item(_item_shown(kind, it.term))
            except EndModuleError as e:
                refuse(str(e), span)
                continue
        if kind == "Directive":
            try:
                lowered = ctx.lower(it.term, it.spans, span)
            except DirectiveRefused as e:
                refuse(f"directive: {e}", e.span or span)
                continue
            body.extend(lowered)
            stats["lowered"] += 1
            stats["directives"] += 1
            continue
        if kind != "Clause":
            refuse(f"{kind} is not lowered (DCG is out of scope; a query "
                   f"`?-` is no clause): {it.term!r}", span)
            continue
        defined.add(_head_indicator(it.term))
        uses.reif = ctx.reif
        uses.clause(it.term)
        if directives_only:
            # The clause is not lowered, but the double_quotes modes its
            # literals were read under are module-item facts (the cross-mode
            # lint): note them as the full lowering would.
            if _has_chars(it.term):
                ctx.note_literal()
            stats["skipped"] += 1
            continue
        try:
            lowered = lower_clause(it.term, it.spans, it.var_names, positions,
                                   singletons, ctx)
        except LoweringRefused as e:
            refuse(str(e), e.span or span)
            continue
        body.extend(lowered)
        stats["lowered"] += 1
        heads.setdefault(_head_name(it.term), span)
    try:
        ctx.end_module.finish(ctx.own_module, surface, where_file)
    except EndModuleError as e:
        refuse(str(e), None)
    try:
        ctx.drop_shadowed_overrides(defined)
    except DirectiveRefused as e:
        refuse(str(e), None)
    clash = _constant_clash(ctx, heads)
    if clash is not None:
        refuse(*clash)
    if ctx.dead_stmts or ctx.dropped_keys:
        body = _drop_removed_imports(body, ctx)
    try:
        body.extend(ctx.auto_declare(uses))
    except DirectiveRefused as e:
        refuse(str(e), e.span)
    stats["transition_constructs"] = dict(uses.transition)
    stats["auto_declared"] = {
        "atoms": len(ctx.auto_atoms),
        "functors": len({n for n, _a in ctx.auto_functors}),
        "functor_arities": len(ctx.auto_functors)}
    mod = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(mod)
    if _lowered is not None:
        _lowered.append(ctx)
    return mod, stats


def _is_end_module(term) -> bool:
    return type(term) is tuple and len(term) == 2 and term[0] == "end_module"


def _item_shown(kind: str, term) -> str:
    if kind == "Directive":
        return f"the directive :- {_show_cell(term)}"
    if kind == "Clause":
        return f"the clause {_show_cell(term)}"
    return f"a {kind}"


def _head_indicator(term) -> "tuple | None":
    """``(name, arity)`` of the procedure a clause term defines (None when
    it has none)."""
    if type(term) is tuple and len(term) == 3 and term[0] == ":-":
        term = term[1]
    if type(term) is str:
        return term, 0
    if type(term) is tuple and term and type(term[0]) is str:
        return term[0], len(term) - 1
    return None


def _head_name(term) -> "str | None":
    if type(term) is tuple and len(term) == 3 and term[0] in (":-", "-->"):
        term = term[1]
    if type(term) is str:
        return term
    if type(term) is tuple and term and type(term[0]) is str:
        return term[0]
    return None


def _constant_clash(ctx, heads: dict):
    """The seam's ``_check_constant_name_is_free``, for ``.pl``: a constant
    declaration writes a module global, so a predicate (or an imported
    name) of the same spelling would be overwritten by the value.  Checked
    once the whole file is lowered, as the seam checks it.  -> (message,
    span) or None."""
    t = getattr(ctx, "_t", None)
    if t is None or not t._constants:
        return None
    taken = {n: ("a predicate defined in this file", s)
             for n, s in heads.items() if n is not None}
    for n, s in ctx.table_heads.items():
        taken.setdefault(n, ("a predicate a constants table defines", s))
    for n in t._imported_functors:
        # No clause to point at: name the constant's own declaration.
        taken.setdefault(n, ("an imported name", ctx.constant_spans.get(n)))
    clashes = sorted(n for n in t._constants if n in taken)
    if not clashes:
        return None
    first = clashes[0]
    what, span = taken[first]
    return (f"constant `{first}` is already bound by {what}: a constant "
            f"declaration writes a module global, so the predicate would be "
            f"overwritten by the value. Rename the constant (an ATOM of the "
            f"same spelling is fine)", span)


def _drop_removed_imports(body: list, ctx) -> list:
    """``use_module(M, [])`` (D27): drop M's import statements, and re-spell
    every goal lowered through a dropped import (``$LoadName('m.p')``) as
    the plain local name, which no longer resolves -- Scryer's
    existence_error when it is called."""
    body = [ctx.load_only.get(id(s), s) for s in body
            if id(s) not in ctx.dead_stmts or id(s) in ctx.load_only]
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == _DOLLAR + "LoadName"):
            for kw in node.keywords:
                if (kw.arg == "name" and isinstance(kw.value, ast.Constant)
                        and kw.value.value in ctx.dropped_keys):
                    kw.value = _const(kw.value.value.rsplit(".", 1)[1])
    return body


def _has_chars(t) -> bool:
    if type(t) is tuple:
        if len(t) == 2 and t[0] == "$chars":
            return True
        return any(_has_chars(a) for a in t[1:])
    if type(t) is list:
        return any(_has_chars(a) for a in t)
    return False


def _syntax_issue_message(it, source) -> str:
    msg = f"syntax error (SyntaxIssue): {it.message}"
    if source is not None and _is_leaf_span(it.span):
        import re  # noqa: PLC0415
        text = source[it.span[0]:it.span[1] + 1]
        if re.search(r"\buse_module\b", text) and re.search(r"\bas\b", text):
            from clausal.tools.iso_l3_directives import _AS_REFUSED  # noqa: PLC0415
            msg = f"{_AS_REFUSED} ({msg})"
    return msg


def reader_op_table():
    """The operator table the native front end reads with (D2(b)): Scryer's
    table with no library loaded, ``Dialect.scryer_reader()``'s -- a FRESH
    one per call, since ``op/3`` directives mutate the reader's table."""
    from clausal.tools.prolog_dialect import Dialect
    return Dialect.scryer_reader().operator_table


def read_iso(source: str, op_table=None) -> list:
    """ISO source text -> ReaderItems (L0+L1+L2, unchanged -- plan §2), read
    with :func:`reader_op_table` unless *op_table* is given.

    The reader is CLOSED after the source is fed, as ``read_module`` does:
    an end ``.`` is one only when layout or EOF follows it, so without the
    close a last clause with no trailing newline stayed pending and was lost
    (2026-09-29).  ``SyntaxIssue`` items are returned like any other."""
    from clausal.tools.prolog_reader import read_module
    return read_module(source, op_table=op_table or reader_op_table())


def iter_iso(source: str, op_table=None):
    """-> (items, table): ReaderItems read LAZILY, one per ``next``, from a
    reader over *op_table* (a fresh :func:`reader_op_table` by default) --
    so a directive lowered between two reads can change the table the
    next item is parsed with (``use_module(library(clpz))``'s ops)."""
    from clausal.tools.prolog_reader import EOF, NEED_MORE, PrologReader  # noqa: PLC0415
    table = op_table if op_table is not None else reader_op_table()
    reader = PrologReader(op_table=table)
    reader.feed(source)
    reader.close()

    def items():
        while True:
            it = reader.read_term()
            if it is EOF:
                return
            if it is NEED_MORE:
                raise RuntimeError("lexer returned NEED_MORE after close()")
            yield it
    return items(), table


def lower_source(source: str, filename: "str | None" = None, *,
                 op_table=None, directives_only: bool = False,
                 source_path: "str | None" = None,
                 module_name: "str | None" = None,
                 surface: "str | None" = None) -> Lowered:
    """``.pl`` text -> :class:`Lowered`, strict: the native loader's one
    call.  Raises :class:`LoweringRefused` with a ``file:line`` message on
    the first item it cannot lower."""
    singletons: list = []
    items, table = iter_iso(source, op_table)
    ctxs: list = []
    mod, stats = lower_items(items, source=source, filename=filename,
                             singletons=singletons, op_table=table,
                             directives_only=directives_only,
                             source_path=source_path, module_name=module_name,
                             surface=surface, _lowered=ctxs)
    ctx = ctxs[0]
    return Lowered(mod, stats, singletons, ctx.module_items(), ctx)


def lower_module(source: str, filename: "str | None" = None, *,
                 op_table=None) -> tuple[ast.Module, dict, list]:
    """``.pl`` text -> (ast.Module, stats, singletons): :func:`lower_source`
    without the module items."""
    low = lower_source(source, filename, op_table=op_table)
    return low.tree, low.stats, low.singletons


def line_of(source: str, span) -> "int | None":
    """The 1-based ``.pl`` line of a span's start (None when unknown)."""
    return _Positions(source).line(span) if span is not None else None


#: The logger the native front end reports load-time facts on (INFO): not a
#: warning -- nothing is wrong -- but a denominator a reader can ask for.
LOGGER_NAME = "clausal.pl_frontend"


def log_auto_declared(ctx, filename: str) -> None:
    """ONE info line per load: how many atoms and data functors the file's
    use declared (the ruling of 2026-09-30: Clausal Prolog is not strict),
    then, at DEBUG, the names."""
    import logging  # noqa: PLC0415
    log = logging.getLogger(LOGGER_NAME)
    atoms, functors = ctx.auto_atoms, ctx.auto_functors
    names = len({n for n, _a in functors})
    log.info("%s: auto-declared %d names (%d atoms, %d data functors at "
             "%d name/arity)", filename, len(atoms) + names, len(atoms),
             names, len(functors))
    if log.isEnabledFor(logging.DEBUG) and (atoms or functors):
        log.debug("%s: auto-declared atoms: %s; data functors: %s", filename,
                  ", ".join(atoms) or "-",
                  ", ".join(f"{n}/{a}" for n, a in functors) or "-")


def log_transition_constructs(stats: dict, filename: str) -> None:
    """D13: ONE info line per load that has any transition construct -- the
    goal-position sites of each (``l3_stats["transition_constructs"]``
    holds the same counts, every key present, for a gate to read)."""
    counts = stats.get("transition_constructs") or {}
    total = sum(counts.values())
    if not total:
        return
    import logging  # noqa: PLC0415
    logging.getLogger(LOGGER_NAME).info(
        "%s: transition constructs: %d sites (%s)", filename, total,
        ", ".join(f"{k}: {n}" for k, n in counts.items() if n))


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
