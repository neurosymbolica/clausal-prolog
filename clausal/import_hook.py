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
from .logic.compiler import compile_predicate
from .logic.predicate import PredicateMeta
from .logic.variables import Var, Trail, unify, deref, walk
from .terms import Compound, KWTerm


# ── Runtime support ──────────────────────────────────────────────────────────


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
    """Compile each pending predicate once (after all clauses asserted)."""
    for (functor, arity), pred_cls in pending.items():
        clauses = db.clauses_for(functor, arity)
        compile_predicate(functor, arity, clauses, db,
                          globals_=module_dict, pred_cls=pred_cls)


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
            tree = EmbedTransformer().visit(tree)
            ast.fix_missing_locations(tree)
            return compile(tree, filename=path, mode="exec")

    def exec_module(self, module):
        filename = self._path
        module.__file__ = filename
        sys.modules[module.__name__] = module
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)
        # Create a LogicModule (database.Module) for this Python module.
        logic_module = LogicModule(module.__name__, module_dict=module_dict)
        module_dict["$module"] = logic_module
        # Deferred compilation: assert clauses during exec, compile once after.
        pending = {}
        module_dict["$define_predicate"] = (
            lambda pred, lm: _define_predicate_deferred(
                pred, lm, module_dict, pending)
        )
        module_dict["$assert_fact"] = (
            lambda term: _assert_fact_deferred(
                term, logic_module, module_dict, pending)
        )
        # get_code() handles .pyc caching via SourceLoader protocol.
        code = self.get_code(module.__name__)
        exec(code, module_dict)
        # Compile all predicates once (deferred from individual assertions).
        _compile_all_pending(pending, logic_module.db, module_dict)
        # Lock all non-dynamic predicates after module load.
        for obj in module_dict.values():
            if isinstance(obj, PredicateMeta) and hasattr(obj, '_fields'):
                key = (obj.__name__, len(obj._fields))
                if not logic_module.db.is_dynamic(*key):
                    obj._lock()


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


sys.meta_path[:] = [PredicateFinder(), *sys.meta_path]


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
