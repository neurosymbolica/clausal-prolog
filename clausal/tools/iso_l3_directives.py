"""L3 directives: ISO directives through the SEAM's own handlers (slice 2).

Plan: ``implementation_plans/native-iso-reader-step2-2026-09-29.md`` §1.5,
§2 and D1(c).  A directive's arguments are READER CELLS; each one is turned
into the Python-ast argument shape the seam's
``EmbedTransformer._handle_directive`` takes (an atom is a ``Name``, ``p/1``
a ``BinOp(Div)``, a list a ``List``), the handler runs on ONE transformer
instance per ``.pl`` file, its statements are spliced into the lowered module
and its ``_module_items`` are the module's.  One implementation of module,
import, flag and table semantics serves both front ends; nothing here
re-implements them.

What is handled, and how (the ISO directive -> the seam's):

    module(M, [p/1, op(P, T, N)])   -module(M, [p/1])  + each op/3 applied to
                                    the reader's table (as Scryer applies it)
    use_module(a/b) / ('a/b')       -import_from(a.b, <a/b's name/arity exports>)
                                    (+ the exported op/3s, into the table)
    use_module(a/b, [p/1])          -import_from(a.b, [p/1]) (+ the op/3s the
                                    list names that a/b exports, and the
                                    exported ops a/b also declares with a
                                    top-level op/3 -- Scryer's rule, measured)
    use_module(py/x[, [p/1]])       a PYTHON module (D32): py/x is py.x, as
                                    in the seam; p/1 CHECKED against
                                    clausal.module_signatures, imported by
                                    bare name; no list = all its predicates
    use_module(m, [])               Scryer's remove_module/2 (D27): drops the
                                    names imported from module m, loads nothing
    use_module(library(L)[, Is])    lists/apply/dif/...: built in, nothing
                                    clpz: clausal.logic.clpfd + clpz's ops;
                                    label/1 from clausal.stdlib.clpz (Scryer's)
                                    reif: clausal.stdlib.reif; clpq: built in
                                    lambda: built in + its +\\ operator
    dynamic/discontiguous/table(PIs)  the same-named seam directive
    meta_predicate(Heads)           -meta_predicate
    set_prolog_flag(F, V)           -set_prolog_flag; double_quotes is kept
                                    HERE, per literal (chars/codes/atom)
    op(P, T, N)                     already applied by the reader; nothing
    end_module(M)                   ISO 13211-2: checked (names the module/2
                                    module, last item: clausal.end_module);
                                    nothing.  set_prolog_flag(
                                    require_end_module, B) is file-local
    constructors([pt(x, y)])        -private([pt(x, y)]): OPTIONAL, gives a
                                    data functor its FIELD NAMES; an exported
                                    one (pt/2 in the module/2 list) goes to
                                    -module as the template pt(x, y) instead

Every atom and data functor a file USES is auto-declared (ruling
2026-09-30: Clausal Prolog is not strict; there is no ``atoms/1``): see
:meth:`DirectiveContext.auto_declare`.

REFUSED, each naming the directive's ``.pl`` line: ``initialization/1``
(D12), a ``./`` or ``../`` relative path (D10), import aliasing with ``as``
(D10: SWI-only), and every directive not in the table above (the error names
it).  A bare atom in a ``use_module/2`` list (D11(a)) is ACCEPTED during the
transition: atoms are global by spelling, so the entry imports nothing, and
one warning per file gives their count and names.

A qualified goal ``m:G`` (D10) is lowered by ``iso_l3`` to the seam's
qualified call ``a.b.g(...)``; :attr:`DirectiveContext.module_aliases` maps
the module name ``m`` to the dotted path an import here named.

"""
from __future__ import annotations

import ast
import keyword
import os
import re
from typing import Any

from clausal.end_module import SURFACE_CLAUSAL_PROLOG as _SURFACE_CLAUSAL_PROLOG
from clausal.tools.prolog_reader import VarRef

#: Libraries whose predicates the engine provides natively: importing one
#: brings nothing into scope (the translator's list, so the two front ends
#: agree on what "built in" means).
_BUILTIN_LIBRARIES = frozenset({
    "lists", "apply", "dif", "between", "error", "pairs", "when", "freeze",
    "iso_ext",
})

#: library(L) -> the Clausal module that holds what the engine does NOT
#: provide globally.  ``None``: every predicate of the library is global.
_LIBRARY_MODULES: dict[str, "str | None"] = {
    "clpz": "clausal.logic.clpfd",
    "clpfd": "clausal.logic.clpfd",
    "reif": "clausal.stdlib.reif",
    "clpq": None,
    "tabling": None,
    # (\)/1..8, (^)/3..10 and (+\)/2..9 are engine builtins
    # (clausal.logic.builtins.lambda_lib); the import adds the +\ operator.
    "lambda": None,
}

#: What ``use_module(library(L))`` (no list) imports from L's module: the
#: names in it that are not global builtins.
_LIBRARY_EXPORTS: dict[str, tuple[str, ...]] = {
    # Scryer's reif.pl exports if_/3, (=)/3, (',')/3, (;)/3, cond_t/3,
    # dif/3, memberd_t/3, tfilter/3, tmember/2, tmember_t/3, tpartition/4:
    # if_ and the (,)/(;) conditions are lowered here (iso_l3), =/3 and dif/3
    # are engine builtins, tfilter/tpartition are overrides (below).
    "reif": ("memberd_t", "tmember", "tmember_t", "cond_t"),
}

#: Names a library's import list may give that the COMPILER lowers itself
#: (they are no registered builtin, so ``_engine_has_goal`` does not see
#: them): nothing to import.
_COMPILER_GOALS = frozenset({"if_", "{}", ",", ";"})

#: library(clpz)'s operators (Scryer ``clpz.pl``'s module/2 export list).
CLPZ_OPS: tuple[tuple[int, str, str], ...] = (
    (760, "yfx", "#<==>"), (750, "xfy", "#==>"), (750, "yfx", "#<=="),
    (740, "yfx", "#\\/"), (730, "yfx", "#\\"), (720, "yfx", "#/\\"),
    (710, "fy", "#\\"), (700, "xfx", "#>"), (700, "xfx", "#<"),
    (700, "xfx", "#>="), (700, "xfx", "#=<"), (700, "xfx", "#="),
    (700, "xfx", "#\\="), (700, "xfx", "in"), (700, "xfx", "ins"),
    (450, "xfx", ".."), (150, "fx", "#"),
)

#: library(lambda)'s operator (Scryer ``lambda.pl``'s module/2 export list).
LAMBDA_OPS: tuple[tuple[int, str, str], ...] = ((201, "xfx", "+\\"),)

_LIBRARY_OPS: dict[str, tuple] = {"clpz": CLPZ_OPS, "clpfd": CLPZ_OPS,
                                  "lambda": LAMBDA_OPS}

#: The library ops an import installs even when its list does not name them:
#: Scryer's rule for an op a module both EXPORTS and declares with a
#: top-level ``:- op/3`` (measured: ``use_module(library(clpz), [label/1])``
#: makes ``#<==>`` an operator; ``use_module(library(lambda), [(\)/2])``
#: does not make ``+\`` one -- lambda.pl only exports it).
_LIBRARY_STICKY_OPS: dict[str, tuple] = {"clpz": CLPZ_OPS, "clpfd": CLPZ_OPS}

#: Library predicates whose Scryer meaning differs from the engine builtin
#: of the same name, or that must not be a global builtin at all: an import
#: of the library takes the name from the module given (clpz's label/1 is
#: leftmost-first; the engine's is first-fail, a different answer order).
#: clpz's sum/3 is no global builtin (a global ``sum`` would shadow Python's
#: inside a seam ``++`` escape), so only an importer of library(clpz)
#: resolves it.  ONE module per name: a file that defines one of the names
#: itself drops that module's import (:meth:`DirectiveContext.
#: drop_shadowed_overrides`), which must not take the others with it.
_CLPZ_OVERRIDES: dict[str, str] = {
    "label": "clausal.stdlib.clpz",
    "sum": "clausal.stdlib.clpz_sum",
}
_LIBRARY_OVERRIDES: dict[str, dict[str, str]] = {
    "clpz": _CLPZ_OVERRIDES,
    "clpfd": _CLPZ_OVERRIDES,
    # Scryer's reif tfilter/3 and tpartition/4 give EVERY answer; the engine
    # builtins commit to each call's first truth value.
    "reif": {"tfilter": "clausal.stdlib.reif",
             "tpartition": "clausal.stdlib.reif"},
}
_OVERRIDE_ARITIES = {"label": ("label", 1), "sum": ("sum", 3),
                     "tfilter": ("tfilter", 3),
                     "tpartition": ("tpartition", 4)}

_OP_SPECIFIERS = ("xfx", "xfy", "yfx", "fy", "fx", "xf", "yf")

_AS_REFUSED = ("import aliasing with `as` is refused (it is SWI-only: not "
               "ISO, and Scryer cannot read it); resolve a name clash with a "
               "module-qualified call, m:p(X)")

_DOUBLE_QUOTES = ("chars", "codes", "atom")


class Uses:
    """What a file's clauses use, by position (ISO 7.6.2): ``atoms`` and
    ``functors`` (name -> arities) seen in DATA positions, ``goal_names``
    called as goals, and the clause ``heads`` (name, arity).  Filled from
    the reader cells, so the cache-hit path (no clause is lowered) sees the
    same population as a full lowering."""

    __slots__ = ("atoms", "functors", "goal_names", "heads", "transition",
                 "reif")

    def __init__(self):
        self.atoms: set[str] = set()
        self.functors: dict[str, set[int]] = {}
        self.goal_names: set[str] = set()
        self.heads: set[tuple[str, int]] = set()
        #: D13: the transition constructs' goal-position sites, per key.
        self.transition: dict[str, int] = dict.fromkeys(TRANSITION_KEYS, 0)
        #: library(reif)'s if_/3 is in scope (the file imported it): an
        #: ``if_`` goal's arms are goals, its condition a reified closure.
        self.reif = False

    def clause(self, term) -> None:
        if type(term) is tuple and len(term) == 3 and term[0] == ":-":
            head, body = term[1], term[2]
        else:
            head, body = term, None
        if type(head) is str:
            self.heads.add((head, 0))
        elif type(head) is tuple and head and type(head[0]) is str:
            self.heads.add((head[0], len(head) - 1))
            for a in head[1:]:
                self.data(a)
        if body is not None:
            self.goal(body)

    def data(self, t) -> None:
        stack = [t]
        while stack:
            t = stack.pop()
            if type(t) is str:
                # D35: a data ``true``/``false``/``undefined`` is the truth
                # VALUE (iso_l3 folds it), not an atom to declare.
                from clausal.tools.iso_l3 import _TRUTH_DATA  # noqa: PLC0415
                if t not in _TRUTH_DATA:
                    self.atoms.add(t)
            elif type(t) is list:
                stack.extend(t)
            elif type(t) is tuple and t and type(t[0]) is str:
                if t[0] == "$chars":
                    continue
                if t[0] == "constant" and len(t) == 2:
                    # D8's compile-time fold, not a data term: neither
                    # ``constant`` nor the constant's name is an atom use.
                    continue
                if t[0] != ".":
                    self.functors.setdefault(t[0], set()).add(len(t) - 1)
                stack.extend(t[1:])

    def goal(self, g) -> None:
        if type(g) is str:
            self.goal_names.add(g)
            return
        if not (type(g) is tuple and g and type(g[0]) is str):
            return
        name, args = g[0], g[1:]
        if name == "\\+" and len(args) == 1:
            self.transition["\\+/1"] += 1
        if name in (",", ";", "->", "*->") and len(args) == 2 \
                or name == "\\+" and len(args) == 1:
            for a in args:
                self.goal(a)
            return
        if name == ":" and len(args) == 2:
            self.goal(args[1])
            return
        self.goal_names.add(name)
        key = (name, len(args))
        tkey = _TRANSITION_GOALS.get(key)
        if tkey is not None and (key != ("findall", 3)
                                 or args[2] == "[]" or args[2] == []):
            self.transition[tkey] += 1
        if key == ("if_", 3) and self.reif:
            self._reif_condition(args[0])
            self.goal(args[1])
            self.goal(args[2])
            return
        from clausal.tools.iso_l3 import _META_GOAL_ARGS  # noqa: PLC0415
        meta = _META_GOAL_ARGS.get(key, ())
        for i, a in enumerate(args):
            if i in meta:
                while (type(a) is tuple and len(a) == 3 and a[0] == "^"):
                    self.data(a[1])
                    a = a[2]
                self.goal(a)
            elif i == 0 and key in _PROCEDURE_ARGS:
                self._procedure(a)
            elif i == 0 and name == "call":
                # A closure names a procedure, not data.
                self._closure(a)
            else:
                self.data(a)

    def _reif_condition(self, c) -> None:
        """An ``if_/3`` condition: (',')/3 and (;)/3 over conditions, (=)/3
        and dif/3 over data, else a closure called with one more argument."""
        if type(c) is tuple and len(c) == 3 and c[0] in (",", ";"):
            self._reif_condition(c[1])
            self._reif_condition(c[2])
        elif type(c) is tuple and len(c) == 3 and c[0] in ("=", "dif"):
            self.goal_names.add(c[0])
            self.data(c[1])
            self.data(c[2])
        else:
            self._closure(c)

    def _procedure(self, t) -> None:
        """assertz(C), retract(C), clause(H, B): a CLAUSE, not data -- its
        head is a procedure (which assertz may create), its body goals."""
        if type(t) is tuple and len(t) == 3 and t[0] == ":-":
            self._closure(t[1])
            self.goal(t[2])
        else:
            self._closure(t)

    def _closure(self, t) -> None:
        if type(t) is str:
            self.goal_names.add(t)
        elif type(t) is tuple and t and type(t[0]) is str and t[0] != "$chars":
            self.goal_names.add(t[0])
            for a in t[1:]:
                self.data(a)


#: D13 (operator ruling 2026-09-30): the transition constructs, ACCEPTED on
#: the native path and COUNTED (never refused by the loader: a ban is a
#: gate's job).  One key per construct, as a gate reads them from
#: ``l3_stats["transition_constructs"]``: ``\+/1``, once/1, forall/2,
#: memberchk/2, the ``findall(_, G, [])`` backdoor (a findall/3 whose bag is
#: the empty list) and make_quantity/3 (every quantity should be a declared
#: constant).  A site is a GOAL position (ISO 7.6.2, including a
#: meta-argument the compiler runs as a goal and a qualified ``m:G``); a
#: closure passed as data (``maplist(memberchk(X), Ls)``) is not counted.
from clausal._transition_constructs import TRANSITION_KEYS  # noqa: E402
_TRANSITION_GOALS = {("once", 1): "once/1", ("forall", 2): "forall/2",
                     ("memberchk", 2): "memberchk/2",
                     ("findall", 3): "findall/3_empty",
                     ("make_quantity", 3): "make_quantity/3"}

#: Builtins whose first argument is a clause or a clause head.
_PROCEDURE_ARGS = frozenset({
    ("assertz", 1), ("asserta", 1), ("assert", 1), ("retract", 1),
    ("retractall", 1), ("clause", 2),
})


def _engine_names(name: str) -> bool:
    """True when the engine gives *name* a meaning of its own -- a goal it
    runs under that spelling, or an arithmetic evaluable at any arity -- so
    a module binding of the name would shadow it."""
    from clausal.tools.prolog_to_clausal import _engine_has_goal  # noqa: PLC0415
    if _engine_has_goal(name):
        return True
    return name in _evaluable_names()


def is_auto_declarable_atom(name: str) -> bool:
    """True when the native ``.pl`` front end would auto-declare *name* --
    bind a data atom of that spelling as a module attribute -- if a file
    used it as data and gave it no other meaning.

    This is the NAME-LEVEL half of the rule only: a spelling a declaration
    can bind (:func:`_is_declarable`: a lowercase identifier, no Python
    keyword, no reserved name such as ``true`` or ``[]``) that the engine
    gives no meaning of its own (:func:`_engine_names`: no builtin goal and
    no arithmetic evaluable under that name).  The PER-FILE half -- the
    names the file itself takes: clause heads, goals, constructors,
    constants, imports and the names directive specs declare -- is applied
    by :meth:`DirectiveContext.auto_declare`; the names a given file
    actually got are ``lower_source(...).context.auto_atoms``.

    The test is ARITY-BLIND: an atom whose spelling is a builtin or an
    evaluable at ANY arity is excluded (``max``, ``pi``, ``halt``),
    because the module binding would shadow that name whatever arity the
    file uses it at.  The control constructs ``fail`` and ``repeat`` are
    not builtins here, so a file that uses them only as DATA declares
    them (a file that calls them takes them, per file).

    It describes the NATIVE ``.pl`` front end only
    (``CLAUSAL_PL_FRONTEND=native``); the translator and seam files do not
    auto-declare."""
    return _is_declarable(name) and not _engine_names(name)


_EVALUABLE_NAMES: "frozenset | None" = None


def _evaluable_names() -> frozenset:
    global _EVALUABLE_NAMES
    if _EVALUABLE_NAMES is None:
        from clausal.logic.exact_arith import EVALUABLE  # noqa: PLC0415
        _EVALUABLE_NAMES = frozenset(k[0] if type(k) is tuple else k
                                     for k in EVALUABLE)
    return _EVALUABLE_NAMES


class DirectiveContext:
    """The per-file state directive lowering shares with clause lowering.

    ``dq_mode`` is the ``double_quotes`` flag in force at the current item
    (position-sensitive: it governs the literals BELOW the directive);
    ``module_aliases`` maps a module name to the dotted path of a module this
    file imported; ``import_remap`` is the seam transformer's local-name ->
    ``dotted.name`` map, which a goal consults exactly as the seam's
    ``visit_Name`` does."""

    def __init__(self, *, source: "str | None", filename: str, positions,
                 op_table=None, source_path: "str | None" = None,
                 module_name: "str | None" = None,
                 surface: str = "pl"):
        self._source = source
        self._filename = filename
        #: The file's surface (``clausal.end_module.surface_of``'s name):
        #: under ``clausal_prolog`` a Python module is no import target.
        self.surface = surface
        #: The importing file's full path and dotted module name (both from
        #: the loader): a use_module path resolves beside the file first.
        self.source_path = source_path
        self.module_name = module_name
        self._pos = positions
        self.op_table = op_table
        self.dq_mode = "chars"
        self._dq_engine_mode = "chars"
        self._dq_explicit = False
        self.dq_modes_used: set[str] = set()
        self.module_aliases: dict[str, str] = {}
        self.bare_atom_imports: list[tuple[str, int | None]] = []
        #: The bare import entries that name something their module offers
        #: as name/N (a Python module's predicate, a Prolog module's
        #: module/2 export): warned with the others (D11), but not a use of
        #: the atom -- see :meth:`auto_declare`.
        self.bare_predicate_names: set[str] = set()
        self.directives = 0
        #: Other source files whose CONTENT this lowering baked in (a
        #: use_module/1 export list, a declared module name a qualified
        #: goal resolves through).  Non-empty: the loader does not cache the
        #: bytecode, since the cache key covers this file only.
        self.depends_on: set[str] = set()
        self._imports: dict[str, list] = {}
        #: ids of import statements a ``use_module(M, [])`` dropped, and the
        #: ``dotted.name`` remap keys it dropped (see :meth:`drop_imports`).
        self.dead_stmts: set[int] = set()
        self.load_only: dict[int, ast.stmt] = {}
        self.dropped_keys: set[str] = set()
        #: A constant's declaring directive span, and each predicate a
        #: constants table defines (the constant-name clash check).
        self.constant_spans: dict = {}
        self.table_heads: dict = {}
        #: The module's own name, from its module/2 (``own:G`` is local).
        self.own_module: "str | None" = None
        #: ``(module, {(name, arity)})`` of each library override imported
        #: (see :data:`_LIBRARY_OVERRIDES`): a procedure the file defines
        #: itself is its own, so :meth:`drop_shadowed_overrides` drops the
        #: import.
        self.override_imports: list[tuple[str, frozenset]] = []
        #: library(clpq) was imported: a goal ``{C}`` is clpq's (else it is
        #: an ordinary call of ``{}/1``, as in Scryer).
        self.clpq = False
        #: library(reif)'s if_/3 was imported: a goal ``if_(C, T, E)`` is
        #: reif's, lowered by iso_l3 (else an ordinary call of if_/3, as in
        #: Scryer, where it exists only by that import).
        self.reif = False
        #: constructors/1 templates found by :func:`prescan_constructors`
        #: BEFORE lowering: module/2 comes first, and an exported
        #: constructor must reach -module as its template, not as name/N.
        self.prescanned: "dict[tuple[str, int], tuple[str, ...]]" = {}
        #: (name, arity) -> field names, as constructors/1 declared them.
        self.constructors: "dict[tuple[str, int], tuple[str, ...]]" = {}
        #: (name, arity) -> the span of the constructors/1 that declared it.
        self.constructor_spans: dict = {}
        #: The (name, arity) module/2 exported as a constructor template.
        self.exported_constructors: "set[tuple[str, int]]" = set()
        #: The (name, arity) module/2 exported as a PREDICATE (name/N).
        self.exported_predicates: "set[tuple[str, int]]" = set()
        #: What :meth:`auto_declare` declared: atoms, and data functors as
        #: (name, arity) -- each bound by name.
        self.auto_atoms: list = []
        self.auto_functors: list = []
        #: The end_module/1 checks (``clausal.end_module``), and the file's
        #: own set_prolog_flag(require_end_module, V).
        from clausal.end_module import EndModuleCheck  # noqa: PLC0415
        self.end_module = EndModuleCheck()
        self._t = None

    # ── the seam transformer, one per file ──

    @property
    def transformer(self):
        if self._t is None:
            from clausal.templating.term_rewriting import EmbedTransformer  # noqa: PLC0415
            lines = (self._source or "").splitlines(keepends=True)
            self._t = EmbedTransformer(source_lines=lines,
                                       filename=self._filename,
                                       prolog_singletons=True)
        return self._t

    @property
    def import_remap(self) -> dict:
        return self._t._import_remap if self._t is not None else {}

    def module_items(self) -> list:
        items = list(self._t._module_items) if self._t is not None else []
        if self._dq_explicit:
            from clausal.pythonic_ast.nodes import DoubleQuotesMode  # noqa: PLC0415
            items.append(DoubleQuotesMode(
                mode=self._dq_engine_mode, explicit=True,
                modes_used=tuple(sorted(self.dq_modes_used)),
                flag=self.dq_mode))
        return items

    def alias(self, name: str, dotted: str) -> None:
        """Record that ``name:G`` means the module *dotted*; a name two
        different imports claim is AMBIGUOUS (``None``), and a qualified goal
        through it is refused rather than resolved by import order."""
        if self.module_aliases.get(name, dotted) != dotted:
            self.module_aliases[name] = None
        elif name not in self.module_aliases:
            self.module_aliases[name] = dotted

    def resolve_module(self, name: str) -> "tuple[str | None, str]":
        """``m`` of ``m:G`` -> (dotted path or None, why-not)."""
        if name in self.module_aliases:
            dotted = self.module_aliases[name]
            if dotted is None:
                return None, (f"`{name}` names two imported modules, so "
                              f"{name}:G is ambiguous")
            return dotted, ""
        if name == self.own_module:
            return "", ""
        if not all(p.isidentifier() for p in name.split(".")):
            return None, f"`{name}` is no module name"
        # As in Scryer, a module nothing imported is resolved when the goal
        # RUNS: an existence_error then unless some module has loaded it.
        return name, ""

    def imported(self, dotted: str, stmts: list) -> list:
        """Record the import statements an import of *dotted* emitted (a
        later ``use_module(M, [])`` drops them); a re-import undoes a drop."""
        self._imports.setdefault(dotted, []).extend(stmts)
        for s in stmts:
            if isinstance(s, ast.ImportFrom):
                for a in s.names:
                    self.dropped_keys.discard(f"{dotted}.{a.name}")
        return stmts

    def drop_imports(self, dotted: str, names: "set | None" = None) -> None:
        """Undo every import of *dotted* so far: its statements, its module
        items and its remap entries.  A goal already lowered through the
        remap is re-spelled by ``iso_l3`` at the end (:attr:`dropped_keys`).
        With *names*, only those local names are undone (a library override
        the file defines itself, where the library's other names stay)."""
        if names is not None:
            self._drop_import_names(dotted, names)
            return
        stmts = self._imports.pop(dotted, [])
        for s in stmts:
            self.dead_stmts.add(id(s))
            if isinstance(s, ast.ImportFrom):
                # The module STAYS loaded (Scryer: m:G still reaches it): the
                # import runs, binding no name here.
                keep = ast.Expr(value=ast.Call(
                    func=ast.Name(id="__import__", ctx=ast.Load()),
                    args=[ast.Constant(value=s.module)], keywords=[]))
                ast.copy_location(keep, s)
                self.load_only[id(s)] = keep
        if self._t is None:
            return
        remap = self._t._import_remap
        for local, key in list(remap.items()):
            if key.startswith(dotted + ".") and "." not in key[len(dotted) + 1:]:
                del remap[local]
                self._t._imported_functors.discard(local)
                self.dropped_keys.add(key)
        items = self._t._module_items
        items[:] = [i for i in items
                    if not (type(i).__name__ == "ImportFromDirective"
                            and getattr(i, "module", None) == dotted)]

    def _drop_import_names(self, dotted: str, names: set) -> None:
        for s in self._imports.get(dotted, []):
            if not isinstance(s, ast.ImportFrom):
                continue
            cur = self.load_only.get(id(s), s)
            if not isinstance(cur, ast.ImportFrom):
                continue
            kept = [a for a in cur.names if (a.asname or a.name) not in names]
            if len(kept) == len(cur.names):
                continue
            self.dead_stmts.add(id(s))
            repl: ast.stmt = (
                ast.ImportFrom(module=cur.module, names=kept, level=cur.level)
                if kept else ast.Expr(value=ast.Call(
                    func=ast.Name(id="__import__", ctx=ast.Load()),
                    args=[ast.Constant(value=cur.module)], keywords=[])))
            ast.copy_location(repl, s)
            self.load_only[id(s)] = repl
        if self._t is None:
            return
        remap = self._t._import_remap
        for local in names:
            key = remap.get(local)
            if key is not None and key == f"{dotted}.{local}":
                del remap[local]
                self._t._imported_functors.discard(local)
                self.dropped_keys.add(key)
        items = self._t._module_items
        for i in list(items):
            if (type(i).__name__ == "ImportFromDirective"
                    and getattr(i, "module", None) == dotted):
                i.names = [n for n in i.names
                           if (n[1] if isinstance(n, tuple) else n) not in names]
                if not i.names:
                    items.remove(i)

    def drop_shadowed_overrides(self, defined: set) -> None:
        """A library override (Scryer's ``label/1``) the file defines itself
        (same name AND arity) is the file's: as for any builtin, a local
        definition wins (Scryer too: it warns and uses the local
        clauses).  A local definition at another arity is refused: the
        engine keys the import by name, so dropping it would silently turn
        the file's ``label/1`` calls into the engine's first-fail one.  A
        name with no global builtin behind it (``sum``) is dropped instead:
        the file's own ``sum/2`` loads, and a ``sum/3`` call is an
        existence_error rather than another predicate's answer."""
        for module, pis in self.override_imports:
            if pis & defined:
                self.drop_imports(module, {n for n, _a in pis & defined})
                continue
            names = {m for m, _ in pis}
            clash = sorted(f"{n}/{a}" for n, a in defined if n in names)
            if clash and not any(_engine_goal(n) for n in names):
                # No global of that name to fall back to (clpz's sum/3):
                # dropping the import cannot turn a call into another
                # predicate silently -- a sum/3 call then has no
                # definition and raises existence_error, loudly.
                self.drop_imports(module)
                continue
            if clash:
                raise _refused(
                    f"{', '.join(clash)} is defined here and "
                    f"{', '.join(f'{n}/{a}' for n, a in sorted(pis))} is "
                    f"imported from {module}; one name at "
                    f"two arities across an import is not supported -- "
                    f"rename the local predicate", None)

    def note_literal(self) -> str:
        """The mode a ``"..."`` literal read now takes (and record it)."""
        if self.dq_mode != "codes":
            self.dq_modes_used.add(self.dq_mode)
        return self.dq_mode

    # ── one directive ──

    def lower(self, cell: Any, spans, span) -> list:
        """A directive's body cell -> the statements to splice in.  Raises
        :class:`DirectiveRefused` (with a span) on anything refused."""
        self.directives += 1
        if type(cell) is str:
            key, args, arg_spans = (cell, 0), (), ()
        elif (type(cell) is tuple and cell and type(cell[0]) is str
              and cell[0] != "$chars"):
            key, args = (cell[0], len(cell) - 1), cell[1:]
            arg_spans = _arg_spans(spans, len(args))
        else:
            raise _refused(f"a directive must be callable, got {_show(cell)} "
                           f"(ISO type_error(callable))", span)
        handler = _DIRECTIVES.get(key)
        if handler is None:
            raise _refused(_unknown(key), span)
        return handler(self, args, arg_spans, span)

    def auto_declare(self, uses: "Uses", span=None) -> list:
        """Declare every atom and data functor the file USES (ruling
        2026-09-30: Clausal Prolog is not strict), through the seam's
        ``-private`` handler -- the same declaration a seam file writes --
        and return its statements, for the END of the module body.

        What a declaration buys a ``.pl`` module is its import surface: the
        name is bound to its spelling, so ``-import_from(m, [red])`` in a
        seam file (or a Python ``from m import red``) finds it.  A data term
        builds with or without one (L3 lowers it to its cell).

        A data functor is declared by NAME, as an atom, and gets no field
        signature: a signature would make it a declared data functor, and
        ``assertz`` of a term of it would then be refused (ISO lets any
        callable term be asserted).  Field names come from constructors/1
        only.

        Left out, because the name already means something here and binding
        it would shadow that: a clause head, a goal, a name a directive
        declares (dynamic, table, a name/N export ...), an imported name
        (a Python module's value included), a constructor, a constant (a
        constant's name is its module global; ``constant(Name)`` is folded,
        not data -- :class:`Uses` skips it), a predicate a constants table
        defines, an engine builtin or evaluable (clpz's and clpq's names
        among them), and any spelling a declaration cannot bind
        (:func:`_is_declarable`).

        A bare entry of a use_module/2 list is a use of its atom (D11(a):
        it imports nothing) UNLESS the module offers that name: a Python
        module's value is imported instead, and a name the module offers as
        ``name/N`` (a Python module's predicate, a Prolog module's export)
        is neither imported nor declared -- binding that spelling to an
        atom here would only hide the missing ``name/N``.

        Raises :class:`DirectiveRefused` for a constructor that is also
        defined by clauses here: a constructor is data."""
        for key, where in self.constructor_spans.items():
            if key in uses.heads:
                raise _refused(
                    f"constructors(...): {key[0]}/{key[1]} is declared a "
                    f"constructor (data) and is also defined by clauses in "
                    f"this file; a name/arity is one or the other", where)
        taken = set(uses.goal_names) | {n for n, _a in uses.heads}
        taken |= {n for n, _a in self.constructors}
        taken |= set(self.constant_spans) | set(self.table_heads)
        if self._t is not None:
            taken |= set(getattr(self._t, "_constants", ()))
            taken |= set(self._t._import_remap)
            taken |= set(getattr(self._t, "_imported_functors", ()))
            for item in self._t._module_items:
                for spec in getattr(item, "specs", None) or ():
                    if type(spec) is tuple and spec and type(spec[0]) is str:
                        taken.add(spec[0])
        wanted = set(uses.atoms) | set(uses.functors)
        wanted |= {n for n, _line in self.bare_atom_imports
                   if n not in self.bare_predicate_names}
        names = sorted(n for n in wanted - taken
                       if is_auto_declarable_atom(n))
        self.auto_atoms = [n for n in names if n not in uses.functors]
        self.auto_functors = sorted(
            (n, a) for n in names if n in uses.functors
            for a in sorted(uses.functors[n]))
        if not names:
            return []
        return self.seam("private", [_list([_name(n) for n in names])],
                         span, "auto-declaration")

    def warn_bare_atom_imports(self) -> None:
        """D11(a): ONE warning per file, with the count and the names."""
        if not self.bare_atom_imports:
            return
        import warnings  # noqa: PLC0415
        from clausal.lint_warnings import ClausalBareAtomImportWarning  # noqa: PLC0415
        names = ", ".join(n for n, _ in self.bare_atom_imports)
        lines = sorted({ln for _, ln in self.bare_atom_imports if ln})
        n = len(self.bare_atom_imports)
        where = f"{self._filename}:{lines[0]}" if lines else self._filename
        warnings.warn(
            f"{where}: {n} bare atom entr{'y' if n == 1 else 'ies'} in "
            f"use_module/2 import lists ({names}): an atom is global by "
            f"spelling, so the entry imports nothing. Drop it; an ISO import "
            f"list holds name/arity",
            ClausalBareAtomImportWarning, stacklevel=4)

    # ── helpers ──

    def _anchor(self, span) -> ast.stmt:
        """A statement the handler copies its location from: the directive's
        ``.pl`` position."""
        pos = self._pos.of(span) or (1, 0, 1, 0)
        stmt = ast.Expr(value=ast.Constant(value=None))
        stmt.lineno, stmt.col_offset, stmt.end_lineno, stmt.end_col_offset = pos
        return stmt

    def _line(self, span) -> "int | None":
        return self._pos.line(span)

    def seam(self, name: str, args: list, span, what: str) -> list:
        """Run the seam's handler for ``-name(args)``; its SyntaxError is a
        refusal naming the ISO directive."""
        try:
            out = self.transformer._handle_directive(name, args,
                                                     self._anchor(span))
        except SyntaxError as e:
            raise _refused(f"{what}: {e.msg or e}", span) from None
        outs = out if isinstance(out, list) else [out]
        stmts = []
        for s in outs:
            if isinstance(s, ast.Pass):
                continue
            ast.fix_missing_locations(s)
            stmts.append(s)
        return stmts

    def apply_op(self, prec: Any, spec: Any, names: Any, span, what: str):
        """``op(P, T, N)`` checked as ISO 8.14.3 checks it, then applied to
        the reader's table (when the reader has one to share)."""
        if type(prec) is not int or not 0 <= prec <= 1200:
            raise _refused(f"{what}: the priority must be an integer 0..1200 "
                           f"(ISO domain_error(operator_priority)), got "
                           f"{_show(prec)}", span)
        if spec not in _OP_SPECIFIERS:
            raise _refused(f"{what}: {_show(spec)} is not an operator "
                           f"specifier (ISO domain_error(operator_specifier))",
                           span)
        ns = names if type(names) is list else [names]
        if not ns or any(type(n) is not str for n in ns):
            raise _refused(f"{what}: the operator must be an atom or a list "
                           f"of atoms, got {_show(names)}", span)
        if self.op_table is not None:
            for n in ns:
                self.op_table.define(prec, spec, n)


# ── the directives ───────────────────────────────────────────────────────────


def _module(ctx: DirectiveContext, args, spans, span):
    name, exports = args
    what = f"module({_show(name)}, ...)"
    if type(name) is not str:
        raise _refused(f"{what}: the module name must be an atom", span)
    if type(exports) is not list:
        raise _refused(f"{what}: the export list must be a proper list, got "
                       f"{_show(exports)}", span)
    entries = []
    for e, s in zip(exports, _list_spans(spans[1], len(exports))):
        pi = _indicator(e)
        if pi is not None and pi in ctx.prescanned:
            # An exported constructor: -module's template entry is what
            # exports a DATA functor with its fields (a name/N entry
            # exports a predicate).
            entries.append(_template_ast(pi[0], ctx.prescanned[pi]))
            ctx.exported_constructors.add(pi)
            continue
        if pi is not None:
            entries.append(_pi_ast(*pi))
            ctx.exported_predicates.add(pi)
            continue
        if type(e) is tuple and len(e) == 4 and e[0] == "op":
            ctx.apply_op(e[1], e[2], e[3], _top(s) or span, what)
            continue
        raise _refused(f"{what}: the export entry {_show(e)} is not a "
                       f"predicate indicator name/N (or name//N) or an "
                       f"op/3", _top(s) or span)
    ctx.own_module = name
    return ctx.seam("module", [_name(name), _list(entries)], span, what)


def _use_module(ctx: DirectiveContext, args, spans, span):
    spec = args[0]
    imports = args[1] if len(args) == 2 else None
    what = f"use_module({_show(spec)}{', [...]' if len(args) == 2 else ''})"
    entries = None
    listed_ops: list = []
    if imports == []:
        return _remove_module(ctx, spec, span, what)
    bare: list = []
    if imports is not None:
        entries, listed_ops, bare = _import_list(ctx, imports, spans[1],
                                                 span, what)
    facade = None
    if type(spec) is tuple and len(spec) == 2 and spec[0] == "library":
        facade = _library_facade(_slash_path(spec[1]))
        if facade is None:
            _warn_bare(ctx, bare)
            return _use_library(ctx, spec[1], entries, span, what,
                                listed_ops)
    if facade is not None:
        # library(datetime): the .seam facade clausal/library/datetime.seam,
        # imported as the module file it is.
        path = f"library({_slash_path(spec[1])})"
        dotted = facade
    else:
        path = _slash_path(spec)
        if path is None:
            raise _refused(f"{what}: the module is not an atom, an a/b path "
                           f"or library(Name), so it names no module to "
                           f"import", span)
        dotted = (_sibling_dotted(ctx, path, span, what)
                  or _dotted(path, span, what))
    target = _engine_module_path(dotted)
    found = _module_source(target)
    via_alias = False
    if found is None:
        # The seam's import aliases: a currency jurisdiction
        # (``european_union``) names ``clausal.modules.countries.<it>``, as
        # ``-import_from(european_union, [euro])`` resolves it.
        target = _resolve_import_path(dotted)
        found = _module_source(target)
        via_alias = target != dotted
    if found is None:
        raise _refused(f"{what}: no module {dotted} on sys.path (a slash "
                       f"path a/b names the dotted module a.b)", span)
    if ctx.surface == _SURFACE_CLAUSAL_PROLOG and _is_python_module(found):
        # Clausal Prolog reaches Python only through a .seam module.  A
        # module NAME the seam's aliases resolve (european_union, units,
        # date_time) is no Python path: it names the module's facade.  A
        # Python path (py/datetime, clausal/modules/units) is refused.
        alias_facade = _facade_for(target) if via_alias else None
        if alias_facade is None:
            raise _refused(_python_import_refusal(what, dotted, target),
                           span)
        dotted = target = alias_facade
        found = _module_source(target)
    if _is_python_module(found):
        mod = _import_python_module(dotted, target, span, what)
        # A Python module (a currency's units, say) is no Prolog module: a
        # bare name that is one of its VALUES imports that value, exactly as
        # the seam's ``-import_from`` does; a bare predicate name stays D11
        # (see _python_bare).
        values = _python_bare(ctx, mod, bare)
        from clausal.logic.predicate import namespace_db  # noqa: PLC0415
        if namespace_db(vars(mod)) is None:
            return _use_python_module(ctx, dotted, mod, found, entries,
                                      span, what, values)
        if values:
            entries = list(entries or ()) + [(n, None) for n in values]
    elif dotted.startswith(_FACADE_PACKAGE + "."):
        # A facade re-exports its Python module's VALUES too: a bare name
        # imports one exactly as it does from the module itself.
        values = _facade_bare(ctx, _import_python_module(dotted, target, span,
                                                         what), bare)
        if values:
            entries = list(entries or ()) + [(n, None) for n in values]
    else:
        _warn_bare(ctx, bare)
    for n, a in entries or ():
        if not n.isidentifier():
            raise _refused(
                f"{what}: {n}/{a} cannot be imported by name (the name is no "
                f"identifier); call it qualified, m:'{n}'(...)", span)
    declared, exports, ops, sticky = _declared_exports(found)
    if exports and bare:
        # A bare entry naming one of the module's name/N exports is not a
        # use of the atom (see DirectiveContext.auto_declare).
        exported = {n for n, _a in exports}
        ctx.bare_predicate_names.update(
            n for n, _line in bare if n in exported)
    last = dotted.rsplit(".", 1)[-1]
    ctx.alias(last, dotted)
    if declared and declared != last:
        ctx.alias(declared, dotted)
        ctx.depends_on.add(found)
    if entries is None:
        ctx.depends_on.add(found)
        if exports is None:
            raise _refused(
                f"{what}: {found} declares no module/2 export list, so "
                f"use_module/1 has nothing to import; name the imports: "
                f"use_module({path}, [p/1, ...])", span)
        for op in ops:
            ctx.apply_op(*op, span, what)
        entries = exports
    else:
        # Scryer (measured): an import list installs the op/3s it NAMES
        # that the module EXPORTS -- an op the module does not export is
        # not installed -- plus every exported op the module also declares
        # with a top-level op/3, named or not.
        wanted = _op_triples(listed_ops, _op_triples(ops)) + list(sticky)
        if wanted or ops:
            ctx.depends_on.add(found)
        for op in wanted:
            ctx.apply_op(*op, span, what)
    if not entries:
        if imports is None:
            # D26b: a listless import of a module that exports nothing still
            # LOADS it, so ``m:G`` reaches it (Scryer: use_module/1 always
            # loads the module).
            return ctx.imported(dotted, ctx.seam(
                "import_module", [_dotted_ast(dotted)], span, what))
        return []
    return ctx.imported(dotted, ctx.seam(
        "import_from",
        [_dotted_ast(dotted),
         _list([_name(n) if a is None else _pi_ast(n, a)
                for n, a in entries])],
        span, what))


#: The package of the ``library(<lib>)`` facades (``clausal/library``).
_FACADE_PACKAGE = "clausal.library"


#: The package of the engine's Python modules the facades wrap.
_MODULES_PACKAGE = "clausal.modules"


def _library_facade(lib) -> "str | None":
    """The dotted ``.seam`` facade ``library(<lib>)`` names
    (``library(datetime)`` -> ``clausal.library.datetime``,
    ``library(countries/european_union)`` ->
    ``clausal.library.countries.european_union``), or None: *lib* is no
    atom or a/b path, is a library the front end already knows (built in,
    or mapped in :data:`_LIBRARY_MODULES` -- never shadowed), or has no
    facade file."""
    if (type(lib) is not str or lib in _BUILTIN_LIBRARIES
            or lib in _LIBRARY_MODULES):
        return None
    parts = lib.split("/")
    if not all(p.isidentifier() and not keyword.iskeyword(p)
               for p in parts):
        return None
    dotted = ".".join((_FACADE_PACKAGE, *parts))
    found = _module_source(dotted)
    if found is None or not found.endswith(".seam"):
        return None
    return dotted


def _facade_lib(target: str) -> "str | None":
    """The ``library(...)`` path of the facade over the engine module
    *target* (``clausal.modules.py.datetime`` -> ``datetime``,
    ``clausal.modules.countries.european_union`` ->
    ``countries/european_union``, ``clausal.modules.py.os`` -> ``py_os``:
    a Scryer library name takes the ``py_`` prefix), whether or not one
    ships; None for a
    module outside ``clausal.modules``."""
    prefix = _MODULES_PACKAGE + "."
    if not target.startswith(prefix):
        return None
    rest = target[len(prefix):]
    if rest.startswith("py."):
        rest = rest[3:]
    from clausal.library import facade_path  # noqa: PLC0415
    return facade_path(rest.replace(".", "/"))


def _facade_for(target: str) -> "str | None":
    """The dotted facade over the engine module *target*, or None."""
    lib = _facade_lib(target)
    return None if lib is None else _library_facade(lib)


def _facade_bare(ctx, facade, bare) -> list:
    """The bare names of an import list that name a VALUE the *facade*
    re-exports (a unit, a currency, a number): imported, as from the Python
    module itself (:func:`_python_bare`).  Any other bare name is an atom,
    D11."""
    if not bare:
        return []
    from clausal.library import is_value  # noqa: PLC0415
    ns = vars(facade)
    values, atoms = [], []
    for n, line in bare:
        if not n.startswith("_") and n in ns and is_value(ns[n]):
            values.append(n)
        else:
            atoms.append((n, line))
    _warn_bare(ctx, atoms)
    return values


def _is_known_library(name: str) -> bool:
    """Whether ``library(<name>)`` names a library Clausal provides: built
    in, mapped to an engine module, or a ``.seam`` facade."""
    return (name in _BUILTIN_LIBRARIES or name in _LIBRARY_MODULES
            or _library_facade(name) is not None)


def _unknown_library(what: str, name: str) -> str:
    """The refusal of an unknown ``library(<name>)``, shared by both .pl
    front ends: Scryer's library names Clausal does not provide (``os``,
    ``charsio``) and plain misspellings alike.  Never read as a module of
    that name -- ``library(os)`` would otherwise be Python's ``os``."""
    return (f"{what}: library({name}) is not a library the native front end "
            f"knows (built in: {', '.join(sorted(_BUILTIN_LIBRARIES))}; "
            f"mapped: {', '.join(sorted(_LIBRARY_MODULES))}; facades: "
            f"library(L) for each L in clausal._py_facades.PY_FACADE_LIBS)")


def _python_import_refusal(what: str, dotted: str, target: str) -> str:
    """The message refusing a Python import target in Clausal Prolog,
    naming the ``library(...)`` facade when one ships."""
    head = (f"{what}: permission_error(access, python_module, {dotted}) -- "
            f"Clausal Prolog reaches Python only through a .seam module")
    lib = _facade_lib(target)
    if lib is not None and _library_facade(lib) is not None:
        return (f"{head}; import the facade library({lib}) instead: "
                f":- use_module(library({lib}), [...]).")
    if lib is not None:
        return (f"{head}; {dotted} has no library({lib}) facade -- generate "
                f"one with clausal/tools/gen_library_facades.py, or write a "
                f".seam wrapper and import that")
    return f"{head}; write a .seam wrapper over {dotted} and import that"


def _import_python_module(dotted, target, span, what):
    """Import the module *dotted* names; *target* is the path it resolved
    to (the ``py.X`` redirect, or a seam import alias)."""
    import importlib  # noqa: PLC0415
    try:
        return importlib.import_module(target)
    except ImportError as e:
        raise _refused(f"{what}: {dotted} could not be imported: {e}",
                       span) from None


def _use_python_module(ctx, dotted, mod, found, entries, span, what,
                       values=()):
    """D32: ``use_module(py/datetime, [date_add/3, ...])`` -- a module whose
    predicates are PYTHON adapters, with no Clausal source and so no module/2
    export list.  Its offer is ``clausal.module_signatures`` (D28): each
    ``name/N`` entry is CHECKED against it, and an unknown name or an arity
    the module does not register is a load error listing what it has (as
    Scryer's ``use_module(M, [p/N])`` refuses an indicator M does not
    export).  No list imports every predicate it has.

    The seam's ``-import_from`` takes a Python module's names BARE (an
    indicator against one is its own refusal, compiler_v2), so the checked
    entries are handed over as bare names: an adapter is one object, and the
    import binds it with every arity it registers."""
    from clausal.logic.solve import module_signatures  # noqa: PLC0415
    sig = module_signatures(mod)
    # An adapter whose arity cannot be read (empty set) is offered as n/?.
    offer = ", ".join(f"{n}/{a}" for n in sig
                      for a in (sorted(sig[n]) or ["?"])) or "no predicates"
    last = dotted.rsplit(".", 1)[-1]
    ctx.alias(last, dotted)
    if entries is None:
        ctx.depends_on.add(found)
        names = list(sig)
    else:
        names = []
        for n, a in entries:
            have = sig.get(n)
            if have is None or (have and a not in have):
                at = (f"{dotted} has {n} as "
                      + ", ".join(f"{n}/{x}" for x in sorted(have))
                      if have else f"{dotted} has no predicate {n}")
                raise _refused(
                    f"{what}: existence_error(procedure, {n}/{a}) -- {at}; "
                    f"{dotted} offers {offer}", span)
            if n not in names:
                names.append(n)
    # The bare VALUE names of the list (_python_bare): imported as the seam
    # imports them, unchecked against the predicate offer.
    names.extend(n for n in values if n not in names)
    if not names:
        return []
    return ctx.imported(dotted, ctx.seam(
        "import_from", [_dotted_ast(dotted), _list([_name(n) for n in names])],
        span, what))


def _remove_module(ctx, spec, span, what):
    """``use_module(M, [])`` is Scryer's ``remove_module/2`` (ruling D27,
    measured against Scryer's ``src/loader.pl``): M must be an atom naming a
    MODULE (``library(Name)`` or the name from its module/2), never a path
    -- ``pk/m`` is ``domain_error(module_specifier, pk/m)``.  It does NOT
    load M.  It drops every name this module imported from M, for the whole
    module (Scryer resolves a call when it runs, so a clause above the
    directive loses it too); a later import brings it back.  A module name
    nothing here imported is a no-op; ``M:G`` then reaches M only if some
    other module loaded it, else it is an existence_error when called."""
    if type(spec) is tuple and len(spec) == 2 and spec[0] == "library":
        raise _refused(
            f"{what}: Scryer reads this as remove_module/2, which drops the "
            f"library's predicates from this module; Clausal's library "
            f"predicates are global builtins and cannot be dropped, so the "
            f"directive is refused rather than ignored", span)
    if type(spec) is not str:
        raise _refused(
            f"{what}: use_module(M, []) is remove_module/2, which takes a "
            f"module NAME (Scryer: domain_error(module_specifier, "
            f"{_show(spec)}))", span)
    if spec in ctx.module_aliases:
        dotted, why = ctx.resolve_module(spec)
        if dotted is None:
            raise _refused(f"{what}: {why}", span)
        ctx.drop_imports(dotted)
    return []


def _use_library(ctx, lib, entries, span, what, listed_ops=()):
    name = _slash_path(lib)
    if name is None:
        raise _refused(f"{what}: the library name is not an atom", span)
    lib_ops = _LIBRARY_OPS.get(name, ())
    if entries is None:
        install = list(lib_ops)
    else:
        # The same rule as for a module file (see _use_module).
        install = (_op_triples(listed_ops, _op_triples(lib_ops))
                   + list(_LIBRARY_STICKY_OPS.get(name, ())))
    for op in install:
        ctx.apply_op(*op, span, what)
    if name in ("clpq", "clpr"):
        ctx.clpq = True
    if name == "reif" and (entries is None
                           or any(n == "if_" for n, _a in entries)):
        ctx.reif = True
    if name in _BUILTIN_LIBRARIES:
        return []
    if name not in _LIBRARY_MODULES:
        raise _refused(_unknown_library(what, name), span)
    module = _LIBRARY_MODULES[name]
    over_names = _LIBRARY_OVERRIDES.get(name, {})
    overridden: list = []
    if entries is None:
        wanted = [(n, None) for n in _LIBRARY_EXPORTS.get(name, ())]
        overridden = [(n, None) for n in over_names]
    else:
        wanted = []
        for n, arity in entries:
            if n in over_names:
                overridden.append((n, arity))
                continue
            if _engine_goal(n):
                continue
            if module is not None and _module_has(module, n):
                wanted.append((n, arity))
                continue
            raise _refused(
                f"{what}: library({name})'s {n}/{arity} is not available in "
                f"Clausal (neither an engine builtin nor defined in "
                f"{module or 'the engine'})", span)
    groups: list = [(module, wanted)]
    for n, arity in overridden:
        over_module = over_names[n]
        ctx.override_imports.append(
            (over_module, frozenset([_OVERRIDE_ARITIES[n]])))
        groups.append((over_module, [(n, arity)]))
    out: list = []
    for mod, names in groups:
        if names:
            out.extend(ctx.imported(mod, ctx.seam(
                "import_from",
                [_dotted_ast(mod),
                 _list([_name(n) if a is None else _pi_ast(n, a)
                        for n, a in names])],
                span, what)))
    return out


def _op_triples(ops, allowed=None) -> list:
    """``op(P, T, Names)`` argument triples -> one ``(P, T, Name)`` per
    name, keeping only those in *allowed* (a list of triples) when given."""
    out = []
    for p, t, names in ops:
        for n in (names if type(names) is list else [names]):
            if allowed is None or (p, t, n) in allowed:
                out.append((p, t, n))
    return out


def _predspec(directive: str):
    def lower(ctx, args, spans, span):
        what = f"{directive}(...)"
        pis = []
        for e, s in _sequence(args[0], spans[0]):
            pi = _indicator(e)
            if pi is None:
                raise _refused(f"{what}: {_show(e)} is not a predicate "
                               f"indicator name/N", _top(s) or span)
            pis.append(_pi_ast(*pi))
        return ctx.seam(directive, pis, span, what)
    return lower


def _meta_predicate(ctx, args, spans, span):
    what = "meta_predicate(...)"
    heads = []
    for e, s in _sequence(args[0], spans[0]):
        if not (type(e) is tuple and len(e) > 1 and type(e[0]) is str):
            raise _refused(f"{what}: {_show(e)} is not a head like "
                           f"p(0, ?, :)", _top(s) or span)
        heads.append(ast.Call(func=_name(e[0]),
                              args=[ast.Constant(value=a) for a in e[1:]],
                              keywords=[]))
    return ctx.seam("meta_predicate", heads, span, what)


def _set_prolog_flag(ctx, args, spans, span):
    flag, value = args
    what = f"set_prolog_flag({_show(flag)}, {_show(value)})"
    if flag == "double_quotes":
        # Honoured HERE, at each literal below (ISO 7.11.2.5: a changeable
        # flag; Scryer too): the seam has no codes mode, and the literal is
        # this front end's to lower.
        if value not in _DOUBLE_QUOTES:
            raise _refused(
                f"{what}: ISO's double_quotes values are chars, codes and "
                f"atom (domain_error(flag_value, double_quotes+"
                f"{_show(value)}))", span)
        ctx.dq_mode = value
        ctx._dq_explicit = True
        if value != "codes":
            ctx._dq_engine_mode = value
        return []
    if flag == "require_end_module":
        # FILE-LOCAL, like double_quotes: it says whether THIS module file
        # must end with end_module/1 (clausal.end_module), and it is
        # decided here, at the end of the lowering -- nothing is left for
        # load time, and no other file is affected.
        from clausal.end_module import parse_flag_value  # noqa: PLC0415
        setting = parse_flag_value(value)
        if setting is None:
            raise _refused(
                f"{what}: the require_end_module values are true and false "
                f"(ISO error(domain_error(flag_value, require_end_module+"
                f"{_show(value)}), set_prolog_flag/2))", span)
        ctx.end_module.file_setting = setting
        return []
    if type(flag) is not str:
        raise _refused(f"{what}: the flag must be an atom", span)
    if type(value) is str:
        v = _name(value)
    elif type(value) is int:
        v = ast.Constant(value=value)
    else:
        raise _refused(f"{what}: the value must be an atom or an integer",
                       span)
    return ctx.seam("set_prolog_flag", [_name(flag), v], span, what)


def _end_module(ctx, args, spans, span):
    """``:- end_module(M).`` (ISO 13211-2): checked by ``clausal.end_module``
    against the module/2 of this file; it lowers to nothing.  That it is
    the LAST item is ``iso_l3.lower_items``' check (it sees every item)."""
    from clausal.end_module import EndModuleError  # noqa: PLC0415
    (arg,) = args
    try:
        ctx.end_module.end_module(arg, ctx.own_module,
                                  is_var=type(arg) is VarRef,
                                  shown=_show(arg), line=ctx._line(span))
    except EndModuleError as e:
        raise _refused(str(e), span) from None
    return []


def _op(ctx, args, spans, span):
    # The reader applied it to its table when it read the directive (ISO
    # 8.14.3); what is left is the check.  Nothing runs at load.
    probe = DirectiveContext(source=None, filename="", positions=ctx._pos)
    probe.apply_op(*args, span, f"op({', '.join(_show(a) for a in args)})")
    return []


def _initialization(ctx, args, spans, span):
    raise _refused(
        f"initialization/{len(args)} is refused (ruling D12): a rulebase has "
        f"no entry point, and a goal run at load is a side effect outside "
        f"the pure subset. Call the goal from the code that loads the module",
        span)


# ── constants (D8) and units (D7) ────────────────────────────────────────────
#
# The seam's own ``-constant_*`` handlers run with synthesized arguments
# (D1(c)), so declaration semantics, the groundness gate, the currency gate,
# ``constant_value/2`` registration and ``constant_number_units/3``'s record
# are ONE implementation.  What is decided HERE is only how an ISO cell reads
# as the handler's argument:
#
#   the name          an atom                       -> the handler's Name
#   the value         a number                      -> the number
#                     an atom (quoted or not)       -> that atom (its str)
#                     "..." under a units directive -> the decimal STRING the
#                                                      seam reads exactly
#                                                      ("292.00" keeps .00)
#                     constant(Earlier)             -> the earlier constant
#                     a list / a compound           -> that term, as DATA
#                                                      (``2*3`` is the term
#                                                      '*'(2, 3): ISO, and
#                                                      ``is/2`` evaluates it)
#   the unit          euro, metre/second, metre^2, metre**2, 2 -> the seam's
#                     unit expression (names must be bound, e.g. imported:
#                     ``:- use_module(european_union, [euro]).``)
#
# ``5*euro`` in a clause is an ordinary ISO term (D7): only a declaration
# gives a number a unit.


def _const_name(ctx, cell, span, what) -> ast.Name:
    if type(cell) is not str:
        raise _refused(f"{what}: the first argument names the constant and "
                       f"must be an atom, got {_show(cell)}", span)
    return _name(cell)


def _const_value(ctx, cell, span, what, *, units: bool) -> ast.expr:
    """An ISO value cell -> the Python-ast RHS the seam's handler takes."""
    if type(cell) is VarRef:
        raise _refused(f"{what}: the value is a variable; a constant's value "
                       f"must be ground", span)
    if isinstance(cell, bool):
        raise _refused(f"{what}: unexpected {cell!r}", span)
    if type(cell) in (int, float):
        return ast.Constant(value=cell)
    if type(cell) is str:
        if units:
            # An atom is no number, even one spelled '292.00': the exact
            # decimal form is the double-quoted STRING, as in the seam.
            raise _refused(f"{what}: {_show(cell)} is an atom, not a "
                           f"number, and only numbers carry units (write "
                           f"an exact decimal as a string, \"292.00\")",
                           span)
        return ast.List(elts=[], ctx=ast.Load()) if cell == "[]" \
            else ast.Constant(value=cell)
    if type(cell) is list:
        return _list([_const_value(ctx, x, span, what, units=False)
                      for x in cell])
    if type(cell) is tuple and cell and type(cell[0]) is str:
        if cell[0] == "$chars" and len(cell) == 2:
            if units:
                return ast.Constant(value=cell[1])
            # The double_quotes flag in force, as for a clause's literal.
            mode = ctx.note_literal()
            if mode == "codes":
                return _list([ast.Constant(value=ord(c)) for c in cell[1]])
            if mode == "atom":
                return ast.Constant(value=cell[1])
            return ast.Tuple(elts=[ast.Constant(value="$chars"),
                                   ast.Constant(value=cell[1])],
                             ctx=ast.Load())
        if cell[0] == "constant" and len(cell) == 2:
            if type(cell[1]) is not str:
                raise _refused(f"{what}: constant() takes the name of a "
                               f"declared constant, got {_show(cell[1])}",
                               span)
            return _name(cell[1])
        return ast.Tuple(
            elts=[ast.Constant(value=cell[0])]
            + [_const_value(ctx, a, span, what, units=False)
               for a in cell[1:]],
            ctx=ast.Load())
    raise _refused(f"{what}: {_show(cell)} is not a constant value", span)


_UNIT_OPS = {"*": ast.Mult, "/": ast.Div, "**": ast.Pow, "^": ast.Pow}


def _unit_expr(cell, span, what) -> ast.expr:
    """A unit cell -> the seam's unit-expression AST: a name, or names
    combined with ``*``, ``/`` and ``**`` (ISO ``^`` too), integer
    exponents."""
    if type(cell) is str and cell.isidentifier():
        return _name(cell)
    if type(cell) is int and not isinstance(cell, bool):
        return ast.Constant(value=cell)
    if (type(cell) is tuple and len(cell) == 3 and cell[0] in _UNIT_OPS):
        return ast.BinOp(left=_unit_expr(cell[1], span, what),
                         op=_UNIT_OPS[cell[0]](),
                         right=_unit_expr(cell[2], span, what))
    raise _refused(f"{what}: {_show(cell)} is not a unit expression -- a "
                   f"unit is a name, or names combined with *, / and ** "
                   f"(or ^)", span)


def _constant_directive(directive: str, arity: int):
    units = arity == 3

    def lower(ctx, args, spans, span):
        what = f"{directive}({', '.join(_show(a) for a in args)})"
        name = _const_name(ctx, args[0], span, what)
        ctx.constant_spans.setdefault(name.id, span)
        seam_args = [name, _const_value(ctx, args[1], span, what,
                                        units=units)]
        if units:
            seam_args.append(_unit_expr(args[2], span, what))
        anchor = ctx._anchor(span)
        for a in seam_args:
            # The handler copies locations FROM its arguments.
            for n in ast.walk(a):
                if "lineno" in n._attributes:
                    ast.copy_location(n, anchor)
        return ctx.seam(directive, seam_args, span, what)
    return lower


#: The table family's column keyword, per directive (the seam's
#: ``TABLE_DIRECTIVES``: ``number_at(N)`` / ``money_at(N)``).
_TABLE_COLUMN = {"constants_number_units": ("number_at", False),
                 "constants_number_currency": ("money_at", True)}


class Embedded:
    """A data-term slot whose lowering is a ready-made Python AST (a table
    row's quantity cell).  ``iso_l3``'s term lowering emits ``.expr``."""

    __slots__ = ("expr",)

    def __init__(self, expr: ast.expr):
        self.expr = expr


def _table_rows(rows, span, what) -> list:
    """The rows argument: a list of rows, each a list ``[1, 29200]`` or a
    parenthesised sequence ``(1, 29200)``."""
    if type(rows) is not list:
        raise _refused(f"{what}: the second argument is the list of rows, "
                       f"got {_show(rows)}", span)
    out = []
    for r in rows:
        if type(r) is list:
            out.append(list(r))
            continue
        cells = []
        while type(r) is tuple and len(r) == 3 and r[0] == ",":
            cells.append(r[1])
            r = r[2]
        cells.append(r)
        out.append(cells)
    return out


def _constant_table(directive: str):
    column_kw, is_money = _TABLE_COLUMN[directive]

    def lower(ctx, args, spans, span):
        from clausal.templating.term_rewriting import (  # noqa: PLC0415
            _decimal_string, _decimal_value_call, _literal_number)
        from clausal.tools.iso_l3 import (  # noqa: PLC0415
            LoweringRefused, _thunk, lower_clause)
        indicator, rows, unit, at = args
        what = f"{directive}({_show(indicator)}, ...)"
        example = (f"{directive}(snap_max/2, [[1, 29200], [2, 53600]], "
                   f"{'usd_cent' if is_money else 'metre'}, {column_kw}(2))")
        pi = _indicator(indicator)
        if pi is None or indicator[0] != "/":
            raise _refused(f"{what}: the first argument is a predicate "
                           f"indicator name/arity: {example}", span)
        pred, arity = pi
        if not (type(at) is tuple and len(at) == 2 and at[0] == column_kw
                and type(at[1]) is int and not isinstance(at[1], bool)):
            raise _refused(f"{what}: the fourth argument names the column as "
                           f"{column_kw}(N), 1-based, got {_show(at)}: "
                           f"{example}", span)
        col = at[1]
        if not 1 <= col <= arity:
            raise _refused(f"{what}: {column_kw}({col}) is out of range for "
                           f"{pred}/{arity} -- the column is 1-based", span)
        unit_ast = _unit_expr(unit, span, what)
        out: list = []
        if is_money:
            # The seam's one-per-table currency gate, at load.
            out.append(ast.Expr(value=ast.Call(
                func=_name("$check_currency_unit"),
                args=[ast.Constant(value=f"{pred}/{arity}"), unit_ast,
                      ast.Constant(value=f"-{directive}")],
                keywords=[])))
        for row in _table_rows(rows, span, what):
            if len(row) != arity:
                raise _refused(
                    f"{what}: row {_show(row)} has {len(row)} columns but "
                    f"{pred}/{arity} takes {arity}", span)
            money = row[col - 1]
            # Only a double-quoted STRING is an exact decimal; an atom (even
            # '292.00') is no number, as for the single-value directives.
            node = (ast.Constant(value=money[1])
                    if type(money) is tuple and len(money) == 2
                    and money[0] == "$chars" else None)
            if node is not None:
                ast.copy_location(node, ctx._anchor(span))
            text = _decimal_string(node) if node is not None else None
            if text is None and (type(money) not in (int, float)
                                 or isinstance(money, bool)
                                 or _literal_number(
                                     ast.Constant(value=money)) is None):
                raise _refused(
                    f"{what}: column {col} of {_show(row)} is {_show(money)}, "
                    f"which is not a number literal: a table row is data, "
                    f"and only numbers carry units", span)
            magnitude = (_decimal_value_call(node, text) if text is not None
                         else ast.Constant(value=money))
            # What the seam's ``29200(usd_cent)`` cell lowers to: a thunk
            # building the Quantity where the fact is compiled.
            quantity = ast.Call(func=_name("$Quantity"),
                                args=[magnitude, unit_ast], keywords=[])
            row[col - 1] = Embedded(_thunk(quantity, ctx._pos.of(span)))
            ctx.table_heads.setdefault(pred, span)
            try:
                out.extend(lower_clause((pred, *row), None, {}, ctx._pos,
                                        None, ctx))
            except LoweringRefused as e:
                raise _refused(f"{what}: {e}", span) from None
        for s in out:
            ast.copy_location(s, ctx._anchor(span))
        return out
    return lower


def _constructors(ctx, args, spans, span):
    """``constructors([pt(x, y), ...])``: give data functors FIELD NAMES
    (ruling 2026-09-30).  Optional -- a data functor needs no declaration
    -- and routed to the seam's ``-private`` template entry, which is what
    gives a seam constructor its fields (``signature/3``,
    ``unbound_keys/2``).  An entry module/2 exported as ``pt/2`` already
    went to ``-module`` as its template (:func:`prescan_constructors`)."""
    what = "constructors(...)"
    templates = []
    for e, s in _sequence(args[0], spans[0]):
        where = _top(s) or span
        name, fields = _constructor_template(e, where, what)
        key = (name, len(fields))
        if key in ctx.constructors:
            if ctx.constructors[key] != fields:
                raise _refused(
                    f"{what}: {name}/{len(fields)} is declared twice with "
                    f"different field names ({', '.join(ctx.constructors[key])}"
                    f" and {', '.join(fields)})", where)
            continue
        if key in ctx.exported_predicates:
            # module/2 routed it before this directive was known: the
            # prescan missed it (it cannot, for a file that reads).
            raise _refused(
                f"{what}: {name}/{len(fields)} was exported by module/2 as a "
                f"predicate before this declaration was seen", where)
        ctx.constructors[key] = fields
        ctx.constructor_spans[key] = where
        if key not in ctx.exported_constructors:
            templates.append(_template_ast(name, fields))
    if not templates:
        return []
    return ctx.seam("private", [_list(templates)], span, what)


def _constructor_template(e, where, what) -> "tuple[str, tuple[str, ...]]":
    """``pt(x, y)`` -> ('pt', ('x', 'y')); anything else is refused."""
    if type(e) is str:
        raise _refused(
            f"{what}: {_show(e)} has no fields; an atom needs no "
            f"declaration (every atom a file uses is declared), and a "
            f"constructor is written with its field names, pt(x, y)", where)
    ind = _indicator(e)
    if ind is not None:
        raise _refused(
            f"{what}: {_show(e)} gives no field names; write the template "
            f"{ind[0]}({', '.join(f'f{i + 1}' for i in range(ind[1]))}) "
            f"with the names of its fields", where)
    if not (type(e) is tuple and len(e) > 1 and type(e[0]) is str
            and e[0] != "$chars"):
        raise _refused(f"{what}: {_show(e)} is not a template like "
                       f"pt(x, y)", where)
    name, fields = e[0], e[1:]
    if not _is_declarable(name):
        raise _refused(f"{what}: {_show(name)} cannot name a constructor "
                       f"(a lowercase identifier that is no Python keyword or "
                       f"reserved name is required)", where)
    for f in fields:
        if type(f) is not str or not _is_declarable(f):
            raise _refused(
                f"{what}: in {_show(e)}, the field name {_show(f)} is not a "
                f"lowercase identifier atom (a Python keyword and a reserved "
                f"name such as true cannot name a field)", where)
    if len(set(fields)) != len(fields):
        raise _refused(f"{what}: {_show(e)} repeats a field name", where)
    return name, tuple(fields)


_DIRECTIVES = {
    ("constant_value", 2): _constant_directive("constant_value", 2),
    ("constant_number_units", 3): _constant_directive(
        "constant_number_units", 3),
    ("constant_number_currency", 3): _constant_directive(
        "constant_number_currency", 3),
    ("constants_number_units", 4): _constant_table("constants_number_units"),
    ("constants_number_currency", 4): _constant_table(
        "constants_number_currency"),
    ("module", 2): _module,
    ("end_module", 1): _end_module,
    ("use_module", 1): _use_module,
    ("use_module", 2): _use_module,
    ("dynamic", 1): _predspec("dynamic"),
    ("discontiguous", 1): _predspec("discontiguous"),
    ("table", 1): _predspec("table"),
    ("meta_predicate", 1): _meta_predicate,
    ("set_prolog_flag", 2): _set_prolog_flag,
    ("op", 3): _op,
    ("constructors", 1): _constructors,
    ("initialization", 1): _initialization,
    ("initialization", 2): _initialization,
}


def _unknown(key) -> str:
    name, arity = key
    known = ", ".join(f"{n}/{a}" for n, a in sorted(
        k for k in _DIRECTIVES if k[0] != "initialization"))
    return (f"unknown directive {name}/{arity}: the native front end handles "
            f"{known}")


# ── use_module helpers ───────────────────────────────────────────────────────


def _import_list(ctx, imports, spans, span, what):
    if type(imports) is not list:
        raise _refused(f"{what}: the import list must be a proper list, got "
                       f"{_show(imports)}", span)
    entries, ops, bare = [], [], []
    checker = DirectiveContext(source=None, filename="", positions=ctx._pos)
    for e, s in zip(imports, _list_spans(spans, len(imports))):
        where = _top(s) or span
        if type(e) is tuple and len(e) == 3 and e[0] == "as":
            raise _refused(f"{what}: {_AS_REFUSED}", where)
        if type(e) is tuple and len(e) == 4 and e[0] == "op":
            # Checked here; installed by the caller only if the module
            # exports it (Scryer).
            checker.apply_op(e[1], e[2], e[3], where, what)
            ops.append(e[1:])
            continue
        pi = _indicator(e)
        if pi is not None:
            entries.append(pi)
            continue
        if type(e) is str:
            # D11(a) for a Prolog module (the caller decides: see
            # _warn_bare); a Python module's bare name imports its value.
            bare.append((e, ctx._line(where)))
            continue
        raise _refused(f"{what}: the import entry {_show(e)} is not "
                       f"name/N (or name//N)", where)
    return entries, ops, bare


def _warn_bare(ctx, bare) -> None:
    """D11(a): a bare atom in a Prolog module's import list is accepted,
    counted and imports nothing (atoms are global by spelling)."""
    ctx.bare_atom_imports.extend(bare)


def _python_bare(ctx, mod, bare) -> list:
    """The bare names of a Python module's import list that import a VALUE
    (slice 6: ``use_module(european_union, [euro])`` binds the unit).  A
    bare name the module offers as a PREDICATE (``clausal.module_signatures``)
    is a bare atom, D11(a): accepted, counted, imports nothing -- a
    predicate is selected by ``name/N`` (D32).  A name the module does not
    have at all is an atom too, as it is for a Prolog module."""
    if not bare:
        return []
    from clausal.logic.solve import module_signatures  # noqa: PLC0415
    sig = module_signatures(mod)
    values, atoms = [], []
    for n, line in bare:
        if n not in sig and hasattr(mod, n):
            values.append(n)
        else:
            atoms.append((n, line))
            if n in sig:
                ctx.bare_predicate_names.add(n)
    _warn_bare(ctx, atoms)
    return values


def _dotted(path: str, span, what) -> str:
    if path.startswith(("./", "../", "/")) or path in (".", ".."):
        raise _refused(
            f"{what}: a relative or absolute file path is refused (ruling "
            f"D10); name the module by its package path a/b, which is the "
            f"dotted module a.b on sys.path", span)
    if path.endswith(".pl"):
        path = path[:-3]
    parts = path.split("/")
    if not all(p.isidentifier() for p in parts):
        raise _refused(f"{what}: {path!r} is not a module path (each "
                       f"component must be a name)", span)
    return ".".join(parts)


def _sibling_dotted(ctx, path: str, span, what) -> "str | None":
    """The dotted module a ``use_module`` path names BESIDE the importing
    file, or None (then the path is read as a dotted module on
    ``sys.path``).  Scryer resolves a relative path against the importing
    file's own directory, and so does the translator
    (``prolog_to_clausal._resolve_module_path``): inside a package
    ``pk``, ``use_module(sib)`` is ``pk.sib`` when ``pk/sib.pl`` exists,
    whatever top-level ``sib`` ``sys.path`` also holds."""
    if not (ctx.source_path and ctx.module_name):
        return None
    if path.startswith("/") or any(p in (".", "..")
                                    for p in path.split("/")):
        return None     # refused by _dotted (ruling D10)
    from clausal.tools.prolog_to_clausal import (  # noqa: PLC0415
        dotted_for_file, package_root, sibling_module_file)
    if path.endswith(".pl"):
        path = path[:-3]
    cand = sibling_module_file(path, ctx.source_path)
    if cand is None:
        return None
    dotted = dotted_for_file(
        cand, package_root(ctx.source_path, ctx.module_name))
    if dotted is None:
        raise _refused(f"{what}: {path!r} is the file {cand}, which no "
                       f"sys.path entry (nor this module's own package "
                       f"root) contains as a dotted module path, so it "
                       f"cannot be imported", span)
    return dotted


def _module_source(dotted: str) -> "str | None":
    """The source file of the module *dotted* names (its parent packages are
    imported to find it, as any import does), or None."""
    import importlib.util  # noqa: PLC0415
    try:
        spec = importlib.util.find_spec(dotted)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    return spec.origin or "<namespace>"


def _engine_module_path(dotted: str) -> str:
    """The seam's ``py.X`` -> ``clausal.modules.py.X`` redirect
    (``import_hook.ModulesFinder``), applied before a lookup: outside that
    finder, ``py`` can be a non-package module already in ``sys.modules``,
    and ``py.X`` then names nothing."""
    if dotted.startswith("py.") and "." not in dotted[3:]:
        return f"clausal.modules.{dotted}"
    return dotted


def _is_python_module(origin: str) -> bool:
    """True when the module at *origin* is a Python file, not a Clausal
    source a module/2 list can be read from.  (A Python module that carries
    a Clausal database -- one built through the Python API -- is still
    routed as a Clausal module by the caller.)"""
    from clausal._suffixes import SOURCE_SUFFIXES  # noqa: PLC0415
    return origin != "<namespace>" and not origin.endswith(SOURCE_SUFFIXES)


def _declared_exports(path: str):
    """-> (module name, [(name, arity)] or None, [op triples], [sticky op
    triples]) from the module/2 declaration of the file at *path* (a ``.pl``
    read with the native reader, a ``.seam``/``.clausal`` with ``ast``).
    ``None`` exports: the file declares none (or is no Clausal source).  The
    STICKY ops are the exported ops the file also declares with a top-level
    ``op/3`` directive: Scryer installs those in an importer whatever its
    import list names (measured)."""
    from clausal.end_module import SURFACE_SEAM, surface_of  # noqa: PLC0415
    from clausal._suffixes import is_prolog_source  # noqa: PLC0415
    # By SURFACE, not by a spelled suffix: at the extension flip ``.clausal``
    # becomes Prolog syntax, and reading it with ``ast`` would be wrong.
    if is_prolog_source(path):
        return _pl_exports(path)
    if surface_of(path) == SURFACE_SEAM:
        return _seam_exports(path) + ([],)
    return None, None, [], []


def _pl_exports(path: str):
    from clausal.tools import iso_l3  # noqa: PLC0415
    from clausal.tools.prolog_reader import EOF, NEED_MORE, PrologReader  # noqa: PLC0415
    from clausal.tools.prolog_tokenizer import PL_SOURCE_NESTED_COMMENTS  # noqa: PLC0415
    with open(path, encoding="utf-8") as f:
        text = f.read()
    reader = PrologReader(op_table=iso_l3.reader_op_table(),
                          nested_comments=PL_SOURCE_NESTED_COMMENTS)
    reader.feed(text)
    reader.close()
    while True:
        it = reader.read_term()
        if it is EOF or it is NEED_MORE:
            return None, None, [], []
        kind = type(it).__name__
        if kind != "Directive":
            return None, None, [], []
        t = it.term
        if (type(t) is tuple and len(t) == 3 and t[0] == "module"
                and type(t[1]) is str and type(t[2]) is list):
            exports, ops = [], []
            for e in t[2]:
                pi = _indicator(e)
                if pi is not None and pi not in exports:
                    exports.append(pi)
                elif type(e) is tuple and len(e) == 4 and e[0] == "op":
                    ops.append(e[1:])
            return t[1], exports, ops, _sticky_ops(reader, ops)


def _sticky_ops(reader, ops) -> list:
    """The exported *ops* the rest of the file (still in *reader*) also
    declares with a top-level ``op/3`` directive.  Only directives are
    looked at; the exported ops are applied to the reader's table first, so
    the file parses as it does when it is loaded."""
    from clausal.tools.prolog_reader import EOF, NEED_MORE  # noqa: PLC0415
    exported = _op_triples(ops)
    if not exported:
        return []
    for p, t, n in exported:
        try:
            reader.op_table.define(p, t, n)
        except Exception:  # noqa: BLE001 -- a bad op is the loader's to refuse
            pass
    declared = set()
    while True:
        it = reader.read_term()
        if it is EOF or it is NEED_MORE:
            break
        t = it.term if type(it).__name__ == "Directive" else None
        if type(t) is tuple and len(t) == 4 and t[0] == "op":
            declared.update(_op_triples([t[1:]]))
    return [op for op in exported if op in declared]


def _seam_exports(path: str):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        return None, None, []
    for stmt in tree.body:
        v = stmt.value if isinstance(stmt, ast.Expr) else None
        if not (isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub)
                and isinstance(v.operand, ast.Call)
                and isinstance(v.operand.func, ast.Name)):
            continue
        call = v.operand
        if call.func.id != "module":
            continue
        name = call.args[0].id if call.args and isinstance(
            call.args[0], ast.Name) else None
        exports = []
        if len(call.args) == 2 and isinstance(call.args[1], ast.List):
            for e in call.args[1].elts:
                if (isinstance(e, ast.BinOp)
                        and isinstance(e.op, (ast.Div, ast.FloorDiv))
                        and isinstance(e.left, ast.Name)
                        and isinstance(e.right, ast.Constant)
                        and type(e.right.value) is int):
                    extra = 2 if isinstance(e.op, ast.FloorDiv) else 0
                    pi = (e.left.id, e.right.value + extra)
                elif isinstance(e, ast.Name):
                    # A bare name (an atom, or a predicate at every arity):
                    # the seam's -import_from takes it by name (D26b).
                    pi = (e.id, None)
                elif (isinstance(e, ast.Call)
                      and isinstance(e.func, ast.Name)):
                    # A template ``f(x, y)``: the name, imported by name.
                    pi = (e.func.id, None)
                else:
                    continue
                if (pi[0], None) in exports or pi in exports:
                    continue
                if pi[1] is None:
                    # by name covers every arity: drop a name/N seen before
                    exports = [x for x in exports if x[0] != pi[0]]
                exports.append(pi)
        return name, exports, []
    return None, None, []


def _resolve_import_path(dotted: str) -> str:
    from clausal.templating.term_rewriting import _resolve_import_path as f  # noqa: PLC0415
    return f(dotted)


def _engine_goal(name: str) -> bool:
    from clausal.tools.prolog_to_clausal import _engine_has_goal  # noqa: PLC0415
    return name in _COMPILER_GOALS or _engine_has_goal(name)


def _module_has(module: str, name: str) -> bool:
    import importlib  # noqa: PLC0415
    try:
        return hasattr(importlib.import_module(module), name)
    except ImportError:
        return False


# ── cells -> the handler's Python-ast argument shapes ────────────────────────


def _indicator(e) -> "tuple[str, int] | None":
    """``name/N`` -> (name, N); ``name//N`` (a nonterminal) -> (name, N+2)."""
    if (type(e) is tuple and len(e) == 3 and e[0] in ("/", "//")
            and type(e[1]) is str and type(e[2]) is int and e[2] >= 0):
        return e[1], e[2] + (2 if e[0] == "//" else 0)
    return None


def _slash_path(t) -> "str | None":
    if type(t) is str:
        return t
    if type(t) is tuple and len(t) == 3 and t[0] == "/":
        left, right = _slash_path(t[1]), _slash_path(t[2])
        if left is not None and right is not None:
            return f"{left}/{right}"
    return None


def _name(ident: str) -> ast.Name:
    return ast.Name(id=ident, ctx=ast.Load())


def _list(elts: list) -> ast.List:
    return ast.List(elts=elts, ctx=ast.Load())


def _template_ast(name: str, fields) -> ast.Call:
    """``pt(x, y)``: a -module/-private template entry."""
    return ast.Call(func=_name(name), args=[_name(f) for f in fields],
                    keywords=[])


#: Names no declaration may bind: the engine's truth values (a seam
#: declaration of one is a load error) and the reserved empty-list/curly.
_UNDECLARABLE = frozenset({"true", "false", "undefined", "Undefined",
                           "True", "False", "None", "[]", "{}"})


def _is_declarable(name: str) -> bool:
    """A spelling a declaration can bind as a module name: a lowercase
    identifier that is no Python keyword (the translator's rule for a bare
    atom), and no reserved name."""
    return (bool(name) and name[0].islower() and name.isidentifier()
            and not keyword.iskeyword(name) and name not in _UNDECLARABLE)


_CONSTRUCTORS_RE = re.compile(r"\bconstructors\s*\(")


def prescan_constructors(source: str) -> "dict[tuple[str, int], tuple[str, ...]]":
    """The constructors/1 templates of *source*, read ahead of lowering.

    module/2 comes first in a file and constructors/1 after it, but an
    exported constructor must reach the seam's -module as its template
    (that is what exports a DATA functor with its fields), so the export
    list needs the templates when it is lowered.  Only a file whose text
    mentions ``constructors(`` is read twice.  A malformed entry (the checks
    of :func:`_constructor_template`) is left out, so module/2 exports it
    as a predicate and the real directive then refuses it with its line."""
    if not _CONSTRUCTORS_RE.search(source):
        return {}
    from clausal.tools import iso_l3  # noqa: PLC0415
    items, _table = iso_l3.iter_iso(source)
    found: dict = {}
    for it in items:
        if type(it).__name__ != "Directive":
            continue
        t = it.term
        if not (type(t) is tuple and len(t) == 2 and t[0] == "constructors"):
            continue
        for e, _s in _sequence(t[1], None):
            try:
                name, fields = _constructor_template(e, None, "")
            except DirectiveRefused:
                continue
            found.setdefault((name, len(fields)), fields)
    return found


def _pi_ast(name: str, arity: int) -> ast.BinOp:
    return ast.BinOp(left=_name(name), op=ast.Div(),
                     right=ast.Constant(value=arity))


def _dotted_ast(dotted: str) -> ast.expr:
    parts = dotted.split(".")
    node: ast.expr = _name(parts[0])
    for p in parts[1:]:
        node = ast.Attribute(value=node, attr=p, ctx=ast.Load())
    return node


def _sequence(t, sp):
    """A PI argument: one ``p/1``, a list ``[p/1, q/2]`` or an ISO sequence
    ``(p/1, q/2)`` -> [(cell, span)]."""
    if type(t) is list:
        return list(zip(t, _list_spans(sp, len(t))))
    out = []
    while type(t) is tuple and len(t) == 3 and t[0] == ",":
        s = _arg_spans(sp, 2)
        out.append((t[1], s[0]))
        t, sp = t[2], s[1]
    out.append((t, sp))
    return out


def _show(t) -> str:
    """A Prolog-ish rendering of a cell, for a message."""
    if type(t) is VarRef:
        return "_"
    if type(t) is str:
        return t
    if type(t) is list:
        return "[" + ", ".join(_show(x) for x in t) + "]"
    if type(t) is tuple and t and type(t[0]) is str:
        if t[0] == "$chars" and len(t) == 2:
            return '"' + str(t[1]) + '"'
        if len(t) == 3 and t[0] in ("/", "//", ":"):
            return f"{_show(t[1])}{t[0]}{_show(t[2])}"
        return f"{t[0]}(" + ", ".join(_show(a) for a in t[1:]) + ")"
    return repr(t)


class DirectiveRefused(Exception):
    """A directive the native front end refuses; *span* is its ``(start,
    end)`` in the ``.pl`` text.  ``iso_l3.lower_items`` turns it into its
    ``LoweringRefused`` (a module-local class: this module never imports
    ``iso_l3``'s, so the two stay independent)."""

    def __init__(self, message: str, span=None):
        super().__init__(message)
        self.span = span


def _refused(message: str, span):
    return DirectiveRefused(message, span)


def _top(s):
    from clausal.tools.iso_l3 import _top_span  # noqa: PLC0415
    return _top_span(s)


def _arg_spans(s, n):
    from clausal.tools.iso_l3 import _arg_spans as f  # noqa: PLC0415
    return f(s, n)


def _list_spans(s, n):
    from clausal.tools.iso_l3 import _list_spans as f  # noqa: PLC0415
    return f(s, n)
