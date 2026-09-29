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
    use_module(a/b, [p/1])          -import_from(a.b, [p/1])
    use_module(m, [])               Scryer's remove_module/2 (D27): drops the
                                    names imported from module m, loads nothing
    use_module(library(L)[, Is])    lists/apply/dif/...: built in, nothing
                                    clpz: clausal.logic.clpfd + clpz's ops
                                    reif: clausal.stdlib.reif; clpq: built in
                                    lambda: built in + its +\\ operator
    dynamic/discontiguous/table(PIs)  the same-named seam directive
    meta_predicate(Heads)           -meta_predicate
    set_prolog_flag(F, V)           -set_prolog_flag; double_quotes is kept
                                    HERE, per literal (chars/codes/atom)
    op(P, T, N)                     already applied by the reader; nothing

REFUSED, each naming the directive's ``.pl`` line: ``initialization/1``
(D12), a ``./`` or ``../`` relative path (D10), import aliasing with ``as``
(D10: SWI-only), and every directive not in the table above (the error names
it).  A bare atom in a ``use_module/2`` list (D11(a)) is ACCEPTED during the
transition: atoms are global by spelling, so the entry imports nothing, and
one warning per file gives their count and names.

A qualified goal ``m:G`` (D10) is lowered by ``iso_l3`` to the seam's
qualified call ``a.b.g(...)``; :attr:`DirectiveContext.module_aliases` maps
the module name ``m`` to the dotted path an import here named.

Room for slice 3: the declarations directives (``atoms/1``,
``constructors/1``) are one more row in :data:`_DIRECTIVES`.
"""
from __future__ import annotations

import ast
import os
from typing import Any

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
    "reif": ("memberd_t",),
}

#: Names a library's import list may give that the COMPILER lowers itself
#: (they are no registered builtin, so ``_engine_has_goal`` does not see
#: them): nothing to import.
_COMPILER_GOALS = frozenset({"if_", "{}"})

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

_OP_SPECIFIERS = ("xfx", "xfy", "yfx", "fy", "fx", "xf", "yf")

_AS_REFUSED = ("import aliasing with `as` is refused (it is SWI-only: not "
               "ISO, and Scryer cannot read it); resolve a name clash with a "
               "module-qualified call, m:p(X)")

_DOUBLE_QUOTES = ("chars", "codes", "atom")


class DirectiveContext:
    """The per-file state directive lowering shares with clause lowering.

    ``dq_mode`` is the ``double_quotes`` flag in force at the current item
    (position-sensitive: it governs the literals BELOW the directive);
    ``module_aliases`` maps a module name to the dotted path of a module this
    file imported; ``import_remap`` is the seam transformer's local-name ->
    ``dotted.name`` map, which a goal consults exactly as the seam's
    ``visit_Name`` does."""

    def __init__(self, *, source: "str | None", filename: str, positions,
                 op_table=None):
        self._source = source
        self._filename = filename
        self._pos = positions
        self.op_table = op_table
        self.dq_mode = "chars"
        self._dq_engine_mode = "chars"
        self._dq_explicit = False
        self.dq_modes_used: set[str] = set()
        self.module_aliases: dict[str, str] = {}
        self.bare_atom_imports: list[tuple[str, int | None]] = []
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
        #: The module's own name, from its module/2 (``own:G`` is local).
        self.own_module: "str | None" = None
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
                modes_used=tuple(sorted(self.dq_modes_used))))
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

    def drop_imports(self, dotted: str) -> None:
        """Undo every import of *dotted* so far: its statements, its module
        items and its remap entries.  A goal already lowered through the
        remap is re-spelled by ``iso_l3`` at the end (:attr:`dropped_keys`)."""
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
        if pi is not None:
            entries.append(_pi_ast(*pi))
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
    if imports == []:
        return _remove_module(ctx, spec, span, what)
    bare: list = []
    if imports is not None:
        entries, bare = _import_list(ctx, imports, spans[1], span, what)
    if type(spec) is tuple and len(spec) == 2 and spec[0] == "library":
        _warn_bare(ctx, bare)
        return _use_library(ctx, spec[1], entries, span, what)
    path = _slash_path(spec)
    if path is None:
        raise _refused(f"{what}: the module is not an atom, an a/b path or "
                       f"library(Name), so it names no module to import",
                       span)
    dotted = _dotted(path, span, what)
    found = _module_source(dotted)
    if found is None:
        # The seam's import aliases: a currency jurisdiction
        # (``european_union``) names ``clausal.modules.countries.<it>``, as
        # ``-import_from(european_union, [euro])`` resolves it.
        found = _module_source(_resolve_import_path(dotted))
    if found is None:
        raise _refused(f"{what}: no module {dotted} on sys.path (a slash "
                       f"path a/b names the dotted module a.b)", span)
    if bare and not found.endswith((".pl", ".seam", ".clausal")):
        # A Python module (a currency's units, say) is no Prolog module: its
        # names are VALUES, not atoms or predicates, so a bare name imports
        # the value by that name, exactly as the seam's ``-import_from``
        # does.  (A ``name/0`` entry is refused by the seam's handler: a
        # Python module has no predicate arities to select.)
        entries = list(entries or ()) + [(n, None) for n, _ in bare]
    else:
        _warn_bare(ctx, bare)
    for n, a in entries or ():
        if not n.isidentifier():
            raise _refused(
                f"{what}: {n}/{a} cannot be imported by name (the name is no "
                f"identifier); call it qualified, m:'{n}'(...)", span)
    declared, exports, ops = _declared_exports(found)
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
    if not entries:
        return []
    return ctx.imported(dotted, ctx.seam(
        "import_from",
        [_dotted_ast(dotted),
         _list([_name(n) if a is None else _pi_ast(n, a)
                for n, a in entries])],
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


def _use_library(ctx, lib, entries, span, what):
    name = _slash_path(lib)
    if name is None:
        raise _refused(f"{what}: the library name is not an atom", span)
    for op in _LIBRARY_OPS.get(name, ()):
        ctx.apply_op(*op, span, what)
    if name in _BUILTIN_LIBRARIES:
        return []
    if name not in _LIBRARY_MODULES:
        raise _refused(
            f"{what}: library({name}) is not a library the native front end "
            f"knows (built in: {', '.join(sorted(_BUILTIN_LIBRARIES))}; "
            f"mapped: {', '.join(sorted(_LIBRARY_MODULES))})", span)
    module = _LIBRARY_MODULES[name]
    if entries is None:
        wanted = [(n, None) for n in _LIBRARY_EXPORTS.get(name, ())]
    else:
        wanted = []
        for n, arity in entries:
            if _engine_goal(n):
                continue
            if module is not None and _module_has(module, n):
                wanted.append((n, arity))
                continue
            raise _refused(
                f"{what}: library({name})'s {n}/{arity} is not available in "
                f"Clausal (neither an engine builtin nor defined in "
                f"{module or 'the engine'})", span)
    if not wanted:
        return []
    return ctx.imported(module, ctx.seam("import_from",
                    [_dotted_ast(module),
                     _list([_name(n) if a is None else _pi_ast(n, a)
                            for n, a in wanted])],
                    span, what))


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
            node = (ast.Constant(value=money[1])
                    if type(money) is tuple and len(money) == 2
                    and money[0] == "$chars"
                    else ast.Constant(value=money)
                    if type(money) is str else None)
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
            try:
                out.extend(lower_clause((pred, *row), None, {}, ctx._pos,
                                        None, ctx))
            except LoweringRefused as e:
                raise _refused(f"{what}: {e}", span) from None
        for s in out:
            ast.copy_location(s, ctx._anchor(span))
        return out
    return lower


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
    ("use_module", 1): _use_module,
    ("use_module", 2): _use_module,
    ("dynamic", 1): _predspec("dynamic"),
    ("discontiguous", 1): _predspec("discontiguous"),
    ("table", 1): _predspec("table"),
    ("meta_predicate", 1): _meta_predicate,
    ("set_prolog_flag", 2): _set_prolog_flag,
    ("op", 3): _op,
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
    entries, bare = [], []
    for e, s in zip(imports, _list_spans(spans, len(imports))):
        where = _top(s) or span
        if type(e) is tuple and len(e) == 3 and e[0] == "as":
            raise _refused(f"{what}: {_AS_REFUSED}", where)
        if type(e) is tuple and len(e) == 4 and e[0] == "op":
            ctx.apply_op(e[1], e[2], e[3], where, what)
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
    return entries, bare


def _warn_bare(ctx, bare) -> None:
    """D11(a): a bare atom in a Prolog module's import list is accepted,
    counted and imports nothing (atoms are global by spelling)."""
    ctx.bare_atom_imports.extend(bare)


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


def _declared_exports(path: str):
    """-> (module name, [(name, arity)] or None, [op triples]) from the
    module/2 declaration of the file at *path* (a ``.pl`` read with the
    native reader, a ``.seam``/``.clausal`` with ``ast``).  ``None`` exports:
    the file declares none (or is no Clausal source)."""
    if path.endswith(".pl"):
        return _pl_exports(path)
    if path.endswith((".seam", ".clausal")):
        return _seam_exports(path)
    return None, None, []


def _pl_exports(path: str):
    from clausal.tools import iso_l3  # noqa: PLC0415
    from clausal.tools.prolog_reader import EOF, NEED_MORE, PrologReader  # noqa: PLC0415
    with open(path, encoding="utf-8") as f:
        text = f.read()
    reader = PrologReader(op_table=iso_l3.reader_op_table())
    reader.feed(text)
    reader.close()
    while True:
        it = reader.read_term()
        if it is EOF or it is NEED_MORE:
            return None, None, []
        kind = type(it).__name__
        if kind != "Directive":
            return None, None, []
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
            return t[1], exports, ops


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
                    if pi not in exports:
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
