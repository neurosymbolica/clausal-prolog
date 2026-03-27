"""import_hook.py — Import hook for ``.clausal`` predicate modules.

Files with the ``.clausal`` extension are intercepted by this hook, which:

  1. Injects predicate builtins (all simple_ast names, Var, Compound, unify,
     deref, Trail, walk) plus the hidden globals ``$module``,
     ``$define_predicate``, ``$assert_fact``, and ``$ast`` into the module
     namespace.  Names starting with ``$`` are intentionally not valid Python
     identifiers in normal source, so user code cannot accidentally shadow them.
  2. Transforms the module's AST via EmbedTransformer, which rewrites
     module-level ``a<-b`` statements into
     ``$define_predicate(Predicate(head=…, body=…), $module)`` calls, and
     trailing-comma expression statements into ``$assert_fact(term)`` calls.
  3. Compilation is deferred: ``$define_predicate`` and ``$assert_fact`` only
     assert clauses during module exec.  After all clauses are asserted,
     ``_compile_all_pending`` compiles each predicate once (O(N) per predicate
     instead of O(N²)).
  4. ``PredicateLoader`` extends ``importlib.abc.SourceLoader``, which
     provides automatic ``.pyc`` caching via ``get_code()``.  On subsequent
     imports, the parsed+transformed bytecode is loaded from
     ``__pycache__/*.pyc``, skipping parsing and AST transformation entirely.

``$module`` (the value of the ``$module`` name in the module namespace) is a
``clausal.logic.database.Module`` instance, not the Python module object.
The Python module object is the standard ``sys.modules[name]`` entry.
"""

from importlib.abc import MetaPathFinder, SourceLoader
from importlib.machinery import ModuleSpec
import importlib.util
import sys
import ast
import os
import warnings

from .pythonic_ast import nodes as simple_ast
from .templating.term_rewriting import EmbedTransformer, TermTransformer
from .logic.database import Module as LogicModule, head_key
from .logic.compiler import compile_predicate_trampoline, compile_predicate_shallow
from .logic.predicate import PredicateMeta
from .logic.variables import Var, Trail, unify, deref, walk
from .terms import Compound, KWTerm, DictTerm, SetTerm

# Pipeline selection flag.  Set to True to use the new pipeline-split path.
_USE_V2_PIPELINE = True


# ── Runtime support ──────────────────────────────────────────────────────────


def _fact_to_predicate_node(term):
    """Wrap a ground fact term as a Predicate(head=term, body=True) node."""
    return simple_ast.Predicate(head=term, body=simple_ast.BoolLiteral(value=True))


def _run_v2_pipeline(loader, module, module_dict, filename, recover_module_items_fn):
    """Shared V2 pipeline: exec bytecode, collect predicate_nodes, compile.

    Parameters
    ----------
    loader : SourceLoader
        The loader instance (PredicateLoader or PrologLoader).
    module : ModuleType
        The module being loaded.
    module_dict : dict
        module.__dict__.
    filename : str
        Source file path.
    recover_module_items_fn : callable(path: str) -> list
        Called on .pyc cache hit to recover module_items from source.
        For .clausal files: re-parse the .clausal source.
        For .pl files: re-translate .pl → .clausal, then parse.
    """
    from clausal.logic.compiler_v2 import compile_module

    predicate_nodes = []
    dummy_logic_module = LogicModule(module.__name__, module_dict=module_dict)
    module_dict["$module"] = dummy_logic_module
    module_dict["$define_predicate"] = (
        lambda pred, lm: predicate_nodes.append(pred)
    )
    module_dict["$assert_fact"] = (
        lambda term: predicate_nodes.append(_fact_to_predicate_node(term))
    )
    code = loader.get_code(module.__name__)

    # _last_transformer is set by source_to_code.  If the code came
    # from .pyc cache, source_to_code didn't run, so use the recovery fn.
    transformer = getattr(loader, '_last_transformer', None)
    if transformer is not None:
        module_items = transformer._module_items
    else:
        module_items = recover_module_items_fn(filename)

    _preseed_py_submodules(module_items)
    exec(code, module_dict)

    logic_module = compile_module(
        predicate_nodes, module_items, module_dict, module.__name__,
    )
    module_dict["$module"] = logic_module
    module.__clausal_module__ = logic_module


def _define_predicate_deferred(predicate_node, logic_module, module_dict,
                               pending):
    """Assert a clause without compiling.  Record for deferred compilation."""
    logic_module.define_predicate(predicate_node)
    functor, arity = head_key(predicate_node.head)

    # Sync to PredicateMeta class — use the normalized clause from the DB.
    pred_cls = module_dict.get(functor)
    if isinstance(pred_cls, PredicateMeta):
        db_clauses = logic_module.db.clauses_for(functor, arity)
        pred_cls._clauses[:] = db_clauses
        if pred_cls._signature is None:
            pred_cls._signature = pred_cls._fields

    pending[(functor, arity)] = pred_cls if isinstance(pred_cls, PredicateMeta) else None


def _assert_fact_deferred(term, logic_module, module_dict, pending):
    """Assert a ground fact without compiling.  Record for deferred compilation."""
    logic_module.assert_fact(term)
    functor, arity = head_key(term)

    # Sync to PredicateMeta class — use the normalized clause from the DB.
    pred_cls = module_dict.get(functor)
    if isinstance(pred_cls, PredicateMeta):
        db_clauses = logic_module.db.clauses_for(functor, arity)
        pred_cls._clauses[:] = db_clauses
        if pred_cls._signature is None:
            pred_cls._signature = pred_cls._fields

    pending[(functor, arity)] = pred_cls if isinstance(pred_cls, PredicateMeta) else None


def _compile_all_pending(pending, db, module_dict):
    """Compile each pending predicate once (after all clauses asserted).

    Shallow predicates (declared via ``-shallow``) are compiled in short-stack
    mode.  Tabled predicates are compiled in trampoline mode and wrapped with
    the SLG tabling wrapper.  All other predicates use the standard trampoline
    compilation.
    """
    for (functor, arity), pred_cls in pending.items():
        clauses = db.clauses_for(functor, arity)
        if db.is_shallow(functor, arity):
            compile_predicate_shallow(functor, arity, clauses, db,
                                      globals_=module_dict, pred_cls=pred_cls)
        else:
            compile_predicate_trampoline(functor, arity, clauses, db,
                                         globals_=module_dict, pred_cls=pred_cls)

    # Wrap tabled predicates AFTER all compilation (so cross-predicate
    # references are resolved before wrapping).
    for (functor, arity), pred_cls in pending.items():
        if db.is_tabled(functor, arity):
            from clausal.logic.tabling import make_tabled_wrapper_trampoline
            original_fn = (pred_cls._get_dispatch() if pred_cls is not None
                           else db.get_dispatch(functor, arity))
            wrapped = make_tabled_wrapper_trampoline(
                original_fn, functor, arity, db.table_store)
            if pred_cls is not None:
                pred_cls._dispatch_fn = wrapped
            db.set_dispatch(functor, arity, wrapped)


# ── Builtins injected into every predicate module ────────────────────────────

predicate_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}
# '$'-prefixed names cannot be typed as normal Python identifiers, so user code
# cannot accidentally shadow them.  Do not remove the '$' prefix.
# Note: $define_predicate and $assert_fact are set per-module in exec_module
# (they need closures over the per-module LogicModule and module_dict).
# '$ast' gives generated code access to the stdlib ast module without risking a
# name collision with user-defined variables named 'ast'.
predicate_builtins["$ast"] = ast
# Runtime types needed by functor class generation (_make_functor_class_ast uses
# Var()) and by compiled predicate bodies.  These are injected so that user code
# in predicate modules can use them without explicit imports.
predicate_builtins["PredicateMeta"] = PredicateMeta
predicate_builtins["Var"] = Var
predicate_builtins["Compound"] = Compound
predicate_builtins["DictTerm"] = DictTerm
predicate_builtins["SetTerm"] = SetTerm
predicate_builtins["Trail"] = Trail
predicate_builtins["unify"] = unify
predicate_builtins["deref"] = deref
predicate_builtins["walk"] = walk
from clausal.terms import PyThunk, FStringThunk, Quantity
predicate_builtins["PyThunk"] = PyThunk
predicate_builtins["FStringThunk"] = FStringThunk  # alias for PyThunk
predicate_builtins["Quantity"] = Quantity
from clausal.logic.clpb import BoolEq, BoolImpl
predicate_builtins["BoolEq"] = BoolEq
predicate_builtins["BoolImpl"] = BoolImpl


def _preseed_py_submodules(module_items) -> None:
    """Ensure ``sys.modules["py.X"]`` entries exist for any ``py.*`` imports.

    When a .clausal file uses ``-import_from(py.re, …)``, the generated
    bytecode contains ``from py.re import …``.  Python's import machinery
    checks ``sys.modules["py"].__path__`` before invoking meta-path finders,
    so if pytest's single-file ``py.py`` is already cached in sys.modules the
    import fails with "'py' is not a package".

    This helper pre-seeds the relevant entries from ``clausal.modules.py.*``
    before ``exec()`` runs, bypassing the stale cache problem.
    """
    from clausal.pythonic_ast.nodes import ImportFromDirective, ImportModuleDirective

    _MODULES_PKG = "clausal.modules"
    needs_py_pkg = False

    for item in module_items:
        mod_path = None
        if isinstance(item, ImportFromDirective):
            mod_path = item.module
        elif isinstance(item, ImportModuleDirective):
            mod_path = item.module
        if mod_path and mod_path.startswith("py.") and "." not in mod_path[3:]:
            needs_py_pkg = True
            subname = mod_path[3:]
            full_key = mod_path          # e.g. "py.re"
            qualified = f"{_MODULES_PKG}.py.{subname}"
            if full_key not in sys.modules:
                try:
                    mod = importlib.import_module(qualified)
                    sys.modules[full_key] = mod
                except (ImportError, ModuleNotFoundError):
                    pass

    if needs_py_pkg and not hasattr(sys.modules.get("py"), "__path__"):
        try:
            sys.modules["py"] = importlib.import_module(f"{_MODULES_PKG}.py")
        except (ImportError, ModuleNotFoundError):
            pass


# ── Loader ───────────────────────────────────────────────────────────────────


class _ClausalSourceLoader(SourceLoader):
    """Common file I/O for .clausal and .pl loaders.

    Extends ``importlib.abc.SourceLoader`` to get automatic ``.pyc`` caching.
    Subclasses must implement ``source_to_code``, ``exec_module``, and
    ``_recover_module_items``.
    """

    def __init__(self, fullname, path):
        self._fullname = fullname
        self._path = path

    def get_filename(self, fullname):
        return self._path

    def get_data(self, path):
        with open(path, "rb") as f:
            return f.read()

    def path_stats(self, path):
        st = os.stat(path)
        return {"mtime": int(st.st_mtime), "size": st.st_size}

    def set_data(self, path, data):
        # Write .pyc file; create __pycache__/ dir if needed.
        try:
            dir_ = os.path.dirname(path)
            os.makedirs(dir_, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        except OSError:
            pass  # silently skip if we cannot write cache


def _parse_clausal_source(source, filename):
    """Parse + EmbedTransformer a .clausal source string.

    Returns ``(code_object, transformer)`` — the transformer carries
    ``_module_items`` needed by the V2 pipeline.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=filename)
        source_lines = source.splitlines(keepends=True)
        transformer = EmbedTransformer(source_lines=source_lines)
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)
        code = compile(tree, filename=filename, mode="exec")
        return code, transformer


def _extract_module_items(source, filename):
    """Re-parse .clausal source text just to recover module_items (cache-hit path)."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=filename)
        source_lines = source.splitlines(keepends=True)
        transformer = EmbedTransformer(source_lines=source_lines)
        transformer.visit(tree)
        return transformer._module_items


class PredicateLoader(_ClausalSourceLoader):
    """SourceLoader for .clausal predicate modules.

    ``source_to_code`` performs the EmbedTransformer rewrite; the resulting
    bytecode is cached in ``__pycache__/`` so subsequent imports skip parsing
    and AST transformation.
    """

    def source_to_code(self, data, path="<string>"):
        source = data.decode("utf-8")
        code, transformer = _parse_clausal_source(source, path)
        # Store the transformer so _exec_module_v2 can access _module_items.
        self._last_transformer = transformer
        return code

    def exec_module(self, module):
        filename = self._path
        module.__file__ = filename
        sys.modules[module.__name__] = module
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)

        if _USE_V2_PIPELINE:
            _run_v2_pipeline(self, module, module_dict, filename,
                             self._recover_module_items)
        else:
            self._exec_module_v1(module, module_dict)

    def _exec_module_v1(self, module, module_dict):
        """Original pipeline: exec bytecode → $define_predicate → compile."""
        logic_module = LogicModule(module.__name__, module_dict=module_dict)
        module_dict["$module"] = logic_module
        module.__clausal_module__ = logic_module
        pending = {}
        module_dict["$define_predicate"] = (
            lambda pred, lm: _define_predicate_deferred(
                pred, lm, module_dict, pending)
        )
        module_dict["$assert_fact"] = (
            lambda term: _assert_fact_deferred(
                term, logic_module, module_dict, pending)
        )
        code = self.get_code(module.__name__)
        exec(code, module_dict)
        _compile_all_pending(pending, logic_module.db, module_dict)
        for obj in module_dict.values():
            if isinstance(obj, PredicateMeta) and hasattr(obj, '_fields'):
                key = (obj.__name__, len(obj._fields))
                if not logic_module.db.is_dynamic(*key):
                    obj._lock()

    def _recover_module_items(self, path):
        """Cache-hit path: re-parse .clausal source to recover module_items."""
        source = self.get_data(path).decode("utf-8")
        return _extract_module_items(source, path)


class PrologLoader(_ClausalSourceLoader):
    """SourceLoader for .pl Prolog modules — translates to clausal on-the-fly.

    Pipeline: .pl source → prolog_to_clausal() → .clausal text →
              ast.parse → EmbedTransformer → bytecode (cached as .pyc)

    All Prolog-specific imports are lazy (inside methods) so loading this
    module doesn't pull in the translator unless a .pl file is actually used.
    """

    def __init__(self, fullname, path, dialect=None):
        super().__init__(fullname, path)
        self._dialect = dialect

    def _translate(self, pl_source):
        """Translate .pl source text to .clausal source text."""
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        from clausal.tools.prolog_dialect import Dialect
        dialect = self._dialect or Dialect.swi()
        return prolog_to_clausal(pl_source, dialect=dialect)

    def source_to_code(self, data, path="<string>"):
        from clausal.tools.prolog_to_clausal import PrologTranslationError
        from clausal.tools.prolog_parser import ParseError

        try:
            pl_source = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SyntaxError(
                f"Cannot import {path}: {e} (all .pl files must be UTF-8)",
                (path, 0, 0, ""),
            ) from e
        try:
            clausal_source = self._translate(pl_source)
        except (ParseError, PrologTranslationError) as e:
            raise SyntaxError(
                f"Cannot import {path}: {e}",
                (path, 0, 0, ""),
            ) from e

        code, transformer = _parse_clausal_source(clausal_source, path)
        self._last_transformer = transformer
        return code

    def exec_module(self, module):
        filename = self._path
        module.__file__ = filename
        sys.modules[module.__name__] = module
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)
        _run_v2_pipeline(self, module, module_dict, filename,
                         self._recover_module_items)

    def _recover_module_items(self, path):
        """Cache-hit path: re-translate .pl source, then parse for module_items."""
        pl_source = self.get_data(path).decode("utf-8")
        clausal_source = self._translate(pl_source)
        return _extract_module_items(clausal_source, path)


# Backward-compat alias — prefer _load_module() for new code.
_predicate_loader = None


def _load_module(fullname, path):
    """Load a .clausal file as a Python module and return it.

    This is the recommended helper for tests and external callers.
    Each call creates a fresh PredicateLoader and module instance.
    """
    sys.modules.pop(fullname, None)
    loader = PredicateLoader(fullname, path)
    spec = ModuleSpec(fullname, loader, origin=path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = mod
    loader.exec_module(mod)
    return mod


def _load_prolog_module(fullname, path, dialect=None):
    """Load a .pl file as a Clausal module and return it.

    Test/external helper. Each call creates a fresh loader and module.
    """
    sys.modules.pop(fullname, None)
    loader = PrologLoader(fullname, path, dialect=dialect)
    spec = ModuleSpec(fullname, loader, origin=path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = mod
    loader.exec_module(mod)
    return mod


# ── Finder ───────────────────────────────────────────────────────────────────


class _ExtensionFinder(MetaPathFinder):
    """Base finder that searches sys.path for files with a given extension."""
    _extension: str = ""
    _loader_cls: type = None

    def find_spec(self, fullname, path, target=None):
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for dir_entry in search_dirs:
            candidate = os.path.join(dir_entry, tail + self._extension)
            if os.path.isfile(candidate):
                loader = self._loader_cls(fullname, candidate)
                return ModuleSpec(fullname, loader, origin=candidate)


class PredicateFinder(_ExtensionFinder):
    """Find .clausal files and load them via PredicateLoader."""
    _extension = ".clausal"
    _loader_cls = PredicateLoader


class PrologFinder(_ExtensionFinder):
    """Find .pl Prolog files and load them via PrologLoader.

    Registered after PredicateFinder so that .clausal files take priority
    over .pl files when both exist for the same module name.
    """
    _extension = ".pl"
    _loader_cls = PrologLoader


class ModulesFinder(MetaPathFinder):
    """Redirect bare module names to ``clausal.modules.<name>``.

    When a ``.clausal`` file uses ``-import_from(regex, [Match])`` or
    ``-import_module(regex)``, the generated bytecode contains
    ``from regex import Match``.  This finder intercepts that and
    redirects to ``clausal.modules.regex`` so the standard library
    modules ship with clausal without polluting the top-level namespace.
    """

    _MODULES_PKG = "clausal.modules"

    # Map bare import names to module file basenames when they differ
    # (e.g. ``uuid`` → ``uuid_mod`` shim which re-exports from py/uuid.py).
    _ALIASES: dict[str, str] = {
        "uuid": "uuid_mod",
        "sklearn": "py.sklearn",
    }

    # Guard against re-entrant imports (e.g. py/uuid.py does
    # ``_import_stdlib("uuid")`` which would re-enter this finder).
    _resolving: set[str] = set()

    def find_spec(self, fullname, path, target=None):
        # Handle py.X imports directly: redirect to clausal.modules.py.X.
        # This is required because pytest's ``py`` package (a single-file
        # non-package module) may already be in sys.modules by the time
        # clausal's import hook is installed, causing ``from py.re import …``
        # to fail with "'py' is not a package".  Intercepting dotted py.*
        # names here bypasses that stale cache entry.
        if fullname.startswith("py.") and "." not in fullname[3:]:
            subname = fullname[3:]  # e.g. "re", "logging", "sklearn"
            qualified = f"{self._MODULES_PKG}.py.{subname}"
            if fullname in self._resolving:
                return None
            self._resolving.add(fullname)
            try:
                spec = importlib.util.find_spec(qualified)
            except (ModuleNotFoundError, ValueError):
                spec = None
            finally:
                self._resolving.discard(fullname)
            if spec is None:
                return None
            # Ensure sys.modules["py"] is our package so submodule lookup works.
            if not hasattr(sys.modules.get("py"), "__path__"):
                sys.modules["py"] = importlib.import_module(
                    f"{self._MODULES_PKG}.py"
                )
            mod = importlib.import_module(qualified)
            sys.modules[fullname] = mod
            new_spec = ModuleSpec(fullname, spec.loader, origin=spec.origin)
            return new_spec
        # Only redirect top-level names (no dots) that we actually provide.
        if "." in fullname:
            return None
        if fullname in self._resolving:
            return None
        mapped = self._ALIASES.get(fullname, fullname)
        qualified = f"{self._MODULES_PKG}.{mapped}"
        self._resolving.add(fullname)
        try:
            spec = importlib.util.find_spec(qualified)
        finally:
            self._resolving.discard(fullname)
        if spec is None:
            return None
        # Load the qualified module and alias it under the bare name.
        mod = importlib.import_module(qualified)
        sys.modules[fullname] = mod
        new_spec = ModuleSpec(fullname, spec.loader, origin=spec.origin)
        # Propagate submodule_search_locations for packages (e.g. ``py``)
        # so that ``py.sympy``, ``py.uuid``, etc. are resolvable.
        if spec.submodule_search_locations is not None:
            new_spec.submodule_search_locations = list(
                spec.submodule_search_locations
            )
        return new_spec


sys.meta_path[:] = [PredicateFinder(), PrologFinder(), ModulesFinder(), *sys.meta_path]


# ── IPython integration ───────────────────────────────────────────────────────

_simple_ast_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}
# '$'-prefixed names cannot be typed as normal Python identifiers, so user code
# cannot accidentally shadow them.  Do not remove the '$' prefix.
_simple_ast_builtins["$ast"] = ast
# Inject runtime types so that functor class code (which calls Var()) works in
# IPython cells.
_simple_ast_builtins["PredicateMeta"] = PredicateMeta
_simple_ast_builtins["Var"] = Var
_simple_ast_builtins["Compound"] = Compound
_simple_ast_builtins["Trail"] = Trail
_simple_ast_builtins["unify"] = unify
_simple_ast_builtins["deref"] = deref
_simple_ast_builtins["walk"] = walk
_simple_ast_builtins["PyThunk"] = PyThunk
_simple_ast_builtins["FStringThunk"] = FStringThunk  # alias
_simple_ast_builtins["BoolEq"] = BoolEq
_simple_ast_builtins["BoolImpl"] = BoolImpl
# In IPython there is no per-session logic module, so '$assert_fact' collects
# facts in a shared list.  For module-backed predicate files, exec_module
# overrides this with a module-specific closure.
_ipython_facts: list = []
_simple_ast_builtins["$assert_fact"] = _ipython_facts.append

from clausal.repl import Solutions as _Solutions, _run_ipython_goal as _run_ipython_goal
_simple_ast_builtins["Solutions"] = _Solutions
_simple_ast_builtins["_run_ipython_goal"] = _run_ipython_goal


class _StarQueryTransformer(ast.NodeTransformer):
    """Rewrite ``*(goal_expr)`` expression statements to Solutions calls.

    Inside ``*(…)`` the expression is treated as a clause body goal.
    ``TermTransformer`` handles variable allocation (via walrus operators) and
    all operator rewriting (``is`` → ``Unify``, ``and`` → ``And``, etc.).

    ``*(Goal(X))``
        → ``Solutions(_run_ipython_goal(Goal((X:=Var())), {'X': X}, globals()))``

    ``*(A(X), B(X, Y))``
        → ``Solutions(_run_ipython_goal(And(left=A((X:=Var())), right=B(X, (Y:=Var()))), {'X': X, 'Y': Y}, globals()))``

    The form parses as ``Expr(Starred(...))`` which would be a compile-time
    error in normal Python; we intercept it here before compilation.
    ``EmbedTransformer.visit_Expr`` leaves ``Starred`` nodes untouched so that
    ``visit_Name`` (X → X.value) does not mangle names that ``TermTransformer``
    needs to see as plain ``Name`` nodes.
    """

    def visit_Expr(self, node):
        if not isinstance(node.value, ast.Starred):
            return self.generic_visit(node)
        inner = node.value.value
        tt = TermTransformer()

        if isinstance(inner, ast.Tuple):
            elts = [tt.visit(e) for e in inner.elts]
            goal_ast = elts[0]
            for elt in elts[1:]:
                goal_ast = ast.fix_missing_locations(ast.copy_location(
                    ast.Call(
                        func=ast.Name(id='And', ctx=ast.Load()),
                        args=[],
                        keywords=[
                            ast.keyword(arg='left', value=goal_ast),
                            ast.keyword(arg='right', value=elt),
                        ],
                    ), node,
                ))
        else:
            goal_ast = tt.visit(inner)

        names = sorted(tt.seen_vars)
        varnames_ast = ast.Dict(
            keys=[ast.Constant(value=n) for n in names],
            values=[ast.Name(id=n, ctx=ast.Load()) for n in names],
        )
        solutions = ast.Expr(value=ast.Call(
            func=ast.Name(id='Solutions', ctx=ast.Load()),
            args=[ast.Call(
                func=ast.Name(id='_run_ipython_goal', ctx=ast.Load()),
                args=[
                    goal_ast,
                    varnames_ast,
                    ast.Call(func=ast.Name(id='globals', ctx=ast.Load()),
                             args=[], keywords=[]),
                ],
                keywords=[],
            )],
            keywords=[],
        ))
        ast.fix_missing_locations(solutions)
        return solutions


class _FreshEmbedTransformer(ast.NodeTransformer):
    """Applies a fresh EmbedTransformer to each IPython cell.

    Exceptions are caught and printed rather than propagated, so IPython
    does not unregister this transformer on a bad cell.
    """

    def visit(self, tree):
        try:
            tree = EmbedTransformer().visit(tree)
            tree = _StarQueryTransformer().visit(tree)
            ast.fix_missing_locations(tree)
            return tree
        except Exception:
            import traceback
            traceback.print_exc()
            return tree


def _auto_enable_colors(shell) -> None:
    """Enable ANSI term colours if the IPython shell is a colour-capable terminal.

    Only activates for ``TerminalInteractiveShell`` (i.e. the ``ipython``
    command-line REPL, which uses prompt_toolkit).  Jupyter notebook kernels
    don't have ``pt_app`` and shouldn't receive raw ANSI escape codes.
    """
    try:
        # pt_app is present on TerminalInteractiveShell (IPython ≥ 7).
        # It is absent on ZMQInteractiveShell (Jupyter) and plain Python.
        if not hasattr(shell, 'pt_app'):
            return
        # Respect the user's explicit colour preference.
        if getattr(shell, 'colors', 'Linux') == 'NoColor':
            return
        from clausal.terms import set_style, TermStyle, ANSI_COLORS
        set_style(TermStyle(colors=ANSI_COLORS))
    except Exception:
        pass


def enable_ipython(ipython_globals, shell=None):
    """Enable the embedding DSL in an IPython session.

    Call once from an IPython cell or startup script:

        from import_hook import enable_ipython
        enable_ipython(globals())

    After this:
    - The ``--expr`` syntax rewrites terms into simple_ast constructor calls.
    - All simple_ast names (LoadName, Call, IntLiteral, …) are in scope.
    - ANSI term colours are auto-enabled for terminal IPython sessions.

    Colour control
    --------------
    ``set_style``, ``TermStyle``, and ``ANSI_COLORS`` are injected into the
    IPython namespace so you can adjust or disable colours at any time::

        set_style(TermStyle())                       # no colours
        set_style(TermStyle(colors=ANSI_COLORS))     # default colour scheme
        set_style(TermStyle(anon_var='?'))            # custom anon-var symbol
    """
    if shell is None:
        shell = ipython_globals["get_ipython"]()
    # Suppress the "'str' object is not callable" SyntaxWarning that Python
    # emits when it compiles source containing  'op'(args)  syntax.  In this
    # DSL that syntax is intentional; the EmbedTransformer and
    # _StringCallableRewriter rewrite it before any bytecode is generated, but
    # tools such as IPython's check_complete() and Jedi compile the raw source
    # before our AST transformer runs, so the warning would otherwise appear.
    warnings.filterwarnings("ignore", message="'str' object is not callable",
                            category=SyntaxWarning)
    shell.ast_transformers.append(_FreshEmbedTransformer())
    ipython_globals.update(_simple_ast_builtins)
    # Inject colour-control helpers so users can tweak from any cell.
    from clausal.terms import set_style as _set_style, TermStyle as _TermStyle, ANSI_COLORS as _ANSI_COLORS
    ipython_globals['set_style'] = _set_style
    ipython_globals['TermStyle'] = _TermStyle
    ipython_globals['ANSI_COLORS'] = _ANSI_COLORS
    _auto_enable_colors(shell)


def _try_auto_enable_ipython():
    """Auto-enable IPython integration if CLAUSAL_IPYTHON env var is set."""
    import os
    if os.environ.get('CLAUSAL_IPYTHON', '').lower() not in ('1', 'true', 'yes', 'y'):
        return
    try:
        from IPython import get_ipython
        shell = get_ipython()
        if shell is not None:
            enable_ipython(shell.user_ns, shell=shell)
    except Exception:
        pass


_try_auto_enable_ipython()
