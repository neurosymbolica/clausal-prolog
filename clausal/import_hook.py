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
  3. Each ``$define_predicate`` call asserts the clause into a
     ``clausal.logic.database.Module`` and immediately recompiles the predicate
     via ``clausal.logic.compiler.compile_predicate``.  The compiled dispatch
     function is installed on the ``PredicateTable`` so that subsequent
     predicate calls (and cross-predicate calls from compiled bodies) resolve
     via ``_db.table_for(...).get_dispatch()``.

``$module`` (the value of the ``$module`` name in the module namespace) is a
``clausal.logic.database.Module`` instance, not the Python module object.
The Python module object is the standard ``sys.modules[name]`` entry.
"""

from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec
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


def _define_predicate(predicate_node, logic_module, module_dict):
    """Assert a clause from a Predicate node and (re)compile the predicate.

    Called as ``$define_predicate(predicate_node, $module)`` at module load
    time for each ``head <- body`` definition in the source.

    Steps:
      1. Assert the clause to both the Database (for backward compat) and
         directly to the PredicateMeta class (if available in module_dict).
      2. Set ``pred_cls._signature`` from ``pred_cls._fields`` if not yet set.
      3. ``compile_predicate`` — compile all current clauses for this
         predicate, passing ``module_dict`` as globals so the compiler can
         resolve cross-predicate references directly from module namespace.
    """
    logic_module.define_predicate(predicate_node)
    functor, arity = head_key(predicate_node.head)

    # Sync to PredicateMeta class — use the normalized clause from the DB.
    pred_cls = module_dict.get(functor)
    if isinstance(pred_cls, PredicateMeta):
        db_clauses = logic_module.db.clauses_for(functor, arity)
        # Replace pred_cls._clauses with DB clauses (authoritative source).
        pred_cls._clauses[:] = db_clauses
        if pred_cls._signature is None:
            pred_cls._signature = pred_cls._fields

    clauses = logic_module.db.clauses_for(functor, arity)
    compile_predicate(functor, arity, clauses, logic_module.db,
                      globals_=module_dict, pred_cls=pred_cls
                      if isinstance(pred_cls, PredicateMeta) else None)


def _assert_fact(term, logic_module, module_dict):
    """Assert a ground fact term and (re)compile the predicate.

    Called as ``$assert_fact(term)`` at module load time for each trailing-
    comma expression statement (the Prolog fact notation).

    Steps:
      1. Assert to the Database; normalize to Var+Is form if needed.
      2. Sync to the PredicateMeta class (if available).
      3. ``compile_predicate`` — recompile with module globals.
    """
    logic_module.assert_fact(term)
    functor, arity = head_key(term)

    # Sync to PredicateMeta class — use the normalized clause from the DB.
    pred_cls = module_dict.get(functor)
    if isinstance(pred_cls, PredicateMeta):
        db_clauses = logic_module.db.clauses_for(functor, arity)
        pred_cls._clauses[:] = db_clauses
        if pred_cls._signature is None:
            pred_cls._signature = pred_cls._fields

    clauses = logic_module.db.clauses_for(functor, arity)
    compile_predicate(functor, arity, clauses, logic_module.db,
                      globals_=module_dict,
                      pred_cls=pred_cls
                      if isinstance(pred_cls, PredicateMeta) else None)


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


class PredicateLoader(Loader):
    def create_module(loader, spec):
        return None  # use default module semantics

    def exec_module(loader, module):
        filename = module.__spec__.origin
        module.__file__ = filename
        sys.modules[module.__name__] = module
        source = open(filename).read()
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)
        # Create a LogicModule (database.Module) for this Python module.
        # This is the $module that predicate clauses are asserted into and
        # compiled against.  It is distinct from the Python module object.
        logic_module = LogicModule(module.__name__, module_dict=module_dict)
        module_dict["$module"] = logic_module
        # '$define_predicate' and '$assert_fact' are module-specific closures
        # that capture both the LogicModule and module_dict.  This lets the
        # import hook sync clauses to PredicateMeta classes and pass module
        # globals to the compiler for cross-predicate resolution.
        module_dict["$define_predicate"] = (
            lambda pred, lm: _define_predicate(pred, lm, module_dict)
        )
        module_dict["$assert_fact"] = (
            lambda term: _assert_fact(term, logic_module, module_dict)
        )
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="'str' object is not callable",
                                    category=SyntaxWarning)
            tree = ast.parse(source)
            tree = EmbedTransformer().visit(tree)
            ast.fix_missing_locations(tree)
            exec(
                compile(tree, filename=filename, mode="exec"),
                module_dict,
            )


_predicate_loader = PredicateLoader()


# ── Finder ───────────────────────────────────────────────────────────────────


class PredicateFinder(MetaPathFinder):
    def find_spec(finder, fullname, path, target=None):
        # Search for a .clausal file matching the module name.
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for dir_entry in search_dirs:
            candidate = os.path.join(dir_entry, tail + ".clausal")
            if os.path.isfile(candidate):
                return ModuleSpec(fullname, _predicate_loader, origin=candidate)


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
