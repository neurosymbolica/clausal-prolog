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
from .templating.term_rewriting import EmbedTransformer
from .logic.database import Module as LogicModule, head_key
from .logic.compiler import compile_predicate_trampoline, compile_predicate_shallow
from .logic.predicate import PredicateMeta
from .logic.variables import Var, Trail, unify, deref, walk
from .terms import Compound, KWTerm

# Pipeline selection flag.  Set to True to use the new pipeline-split path.
_USE_V2_PIPELINE = True


# ── Runtime support ──────────────────────────────────────────────────────────


def _fact_to_predicate_node(term):
    """Wrap a ground fact term as a Predicate(head=term, body=True) node."""
    return simple_ast.Predicate(head=term, body=simple_ast.BoolLiteral(value=True))


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
predicate_builtins["Trail"] = Trail
predicate_builtins["unify"] = unify
predicate_builtins["deref"] = deref
predicate_builtins["walk"] = walk
from clausal.terms import PyThunk, FStringThunk
predicate_builtins["PyThunk"] = PyThunk
predicate_builtins["FStringThunk"] = FStringThunk  # alias for PyThunk


# ── Loader ───────────────────────────────────────────────────────────────────


class PredicateLoader(SourceLoader):
    """SourceLoader subclass for .clausal predicate modules.

    Extends ``importlib.abc.SourceLoader`` to get automatic ``.pyc`` caching.
    ``source_to_code`` performs the EmbedTransformer rewrite; the resulting
    bytecode is cached in ``__pycache__/`` so subsequent imports skip parsing
    and AST transformation.
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

    def source_to_code(self, data, path="<string>"):
        source = data.decode("utf-8")
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="'str' object is not callable",
                category=SyntaxWarning,
            )
            tree = ast.parse(source, filename=path)
            transformer = EmbedTransformer()
            tree = transformer.visit(tree)
            ast.fix_missing_locations(tree)
            # Store the transformer so _exec_module_v2 can access _module_items.
            self._last_transformer = transformer
            return compile(tree, filename=path, mode="exec")

    def exec_module(self, module):
        filename = self._path
        module.__file__ = filename
        sys.modules[module.__name__] = module
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)

        if _USE_V2_PIPELINE:
            self._exec_module_v2(module, module_dict, filename)
        else:
            self._exec_module_v1(module, module_dict)

    def _exec_module_v1(self, module, module_dict):
        """Original pipeline: exec bytecode → $define_predicate → compile."""
        logic_module = LogicModule(module.__name__, module_dict=module_dict)
        module_dict["$module"] = logic_module
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

    def _exec_module_v2(self, module, module_dict, filename):
        """New pipeline: parse → EmbedTransformer → collect items → compile_module."""
        from clausal.logic.compiler_v2 import compile_module

        # Phase A: get_code() runs source_to_code (which stores
        # _last_transformer with _module_items) and handles .pyc caching.
        predicate_nodes = []
        # Provide dummy $module and collection closures for bytecode exec.
        dummy_logic_module = LogicModule(module.__name__, module_dict=module_dict)
        module_dict["$module"] = dummy_logic_module
        module_dict["$define_predicate"] = (
            lambda pred, lm: predicate_nodes.append(pred)
        )
        module_dict["$assert_fact"] = (
            lambda term: predicate_nodes.append(
                _fact_to_predicate_node(term)
            )
        )
        code = self.get_code(module.__name__)
        exec(code, module_dict)

        # _last_transformer is set by source_to_code.  If the code came
        # from .pyc cache, source_to_code didn't run, so we need to
        # re-parse to get _module_items.
        transformer = getattr(self, '_last_transformer', None)
        if transformer is not None:
            module_items = transformer._module_items
        else:
            # .pyc cache hit — re-parse source just for module_items.
            source = self.get_data(self._path).decode("utf-8")
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", message="'str' object is not callable",
                    category=SyntaxWarning,
                )
                tree = ast.parse(source, filename=filename)
                transformer = EmbedTransformer()
                transformer.visit(tree)
                module_items = transformer._module_items

        # Phase B: compile from collected ModuleAST.
        logic_module = compile_module(
            predicate_nodes, module_items, module_dict, module.__name__,
        )
        module_dict["$module"] = logic_module


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


# ── Finder ───────────────────────────────────────────────────────────────────


class PredicateFinder(MetaPathFinder):
    def find_spec(finder, fullname, path, target=None):
        # Search for a .clausal file matching the module name.
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for dir_entry in search_dirs:
            candidate = os.path.join(dir_entry, tail + ".clausal")
            if os.path.isfile(candidate):
                loader = PredicateLoader(fullname, candidate)
                return ModuleSpec(fullname, loader, origin=candidate)


class ModulesFinder(MetaPathFinder):
    """Redirect bare module names to ``clausal.modules.<name>``.

    When a ``.clausal`` file uses ``-import_from(regex, [Match])`` or
    ``-import_module(regex)``, the generated bytecode contains
    ``from regex import Match``.  This finder intercepts that and
    redirects to ``clausal.modules.regex`` so the standard library
    modules ship with clausal without polluting the top-level namespace.
    """

    _MODULES_PKG = "clausal.modules"

    def find_spec(self, fullname, path, target=None):
        # Only redirect top-level names (no dots) that we actually provide.
        if "." in fullname:
            return None
        qualified = f"{self._MODULES_PKG}.{fullname}"
        spec = importlib.util.find_spec(qualified)
        if spec is None:
            return None
        # Load the qualified module and alias it under the bare name.
        mod = importlib.import_module(qualified)
        sys.modules[fullname] = mod
        return ModuleSpec(fullname, spec.loader, origin=spec.origin)


sys.meta_path[:] = [PredicateFinder(), ModulesFinder(), *sys.meta_path]


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
# In IPython there is no per-session logic module, so '$assert_fact' collects
# facts in a shared list.  For module-backed predicate files, exec_module
# overrides this with a module-specific closure.
_ipython_facts: list = []
_simple_ast_builtins["$assert_fact"] = _ipython_facts.append


class _FreshEmbedTransformer(ast.NodeTransformer):
    """Applies a fresh EmbedTransformer to each IPython cell.

    Exceptions are caught and printed rather than propagated, so IPython
    does not unregister this transformer on a bad cell.
    """

    def visit(self, tree):
        try:
            return EmbedTransformer().visit(tree)
        except Exception:
            import traceback
            traceback.print_exc()
            return tree


def enable_ipython(ipython_globals, shell=None):
    """Enable the embedding DSL in an IPython session.

    Call once from an IPython cell or startup script:

        from import_hook import enable_ipython
        enable_ipython(globals())

    After this:
    - The ``--expr`` syntax rewrites terms into simple_ast constructor calls.
    - All simple_ast names (LoadName, Call, IntLiteral, …) are in scope.
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
