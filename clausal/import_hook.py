"""import_hook.py — Import hook for Prolog-style predicate modules.

Modules whose first line starts with:

    # predicates

are intercepted by this hook, which:

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
import sys
import ast
import warnings

from .pythonic_ast import nodes as simple_ast
from .templating.term_rewriting import EmbedTransformer
from .logic.database import Module as LogicModule, head_key
from .logic.compiler import compile_predicate
from .logic.variables import Var, Trail, unify, deref, walk
from .terms import Compound, KWTerm


# ── Runtime support ──────────────────────────────────────────────────────────


def _define_predicate(predicate_node, logic_module):
    """Assert a clause from a Predicate node and (re)compile the predicate.

    Called as ``$define_predicate(predicate_node, $module)`` at module load
    time for each ``head <- body`` definition in the source.

    Steps:
      1. ``logic_module.define_predicate`` — assertz the clause + register
         keyword signature from the head's field names.
      2. ``compile_predicate`` — compile all current clauses for this
         predicate and install the dispatch function on the PredicateTable.
    """
    logic_module.define_predicate(predicate_node)
    functor, arity = head_key(predicate_node.head)
    clauses = logic_module.db.clauses_for(functor, arity)
    compile_predicate(functor, arity, clauses, logic_module.db)


def _assert_fact(term, logic_module):
    """Assert a ground fact term and (re)compile the predicate.

    Called as ``$assert_fact(term)`` at module load time for each trailing-
    comma expression statement (the Prolog fact notation).

    Steps:
      1. ``logic_module.assert_fact`` — assertz a unit clause with no body.
      2. ``compile_predicate`` — recompile the predicate with the new clause.
    """
    logic_module.assert_fact(term)
    functor, arity = head_key(term)
    clauses = logic_module.db.clauses_for(functor, arity)
    compile_predicate(functor, arity, clauses, logic_module.db)


# ── Builtins injected into every predicate module ────────────────────────────

predicate_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}
# '$'-prefixed names cannot be typed as normal Python identifiers, so user code
# cannot accidentally shadow them.  Do not remove the '$' prefix.
predicate_builtins["$define_predicate"] = _define_predicate
# '$ast' gives generated code access to the stdlib ast module without risking a
# name collision with user-defined variables named 'ast'.
predicate_builtins["$ast"] = ast
# Runtime types needed by functor class generation (_make_functor_class_ast uses
# Var()) and by compiled predicate bodies.  These are injected so that user code
# in predicate modules can use them without explicit imports.
predicate_builtins["Var"] = Var
predicate_builtins["Compound"] = Compound
predicate_builtins["Trail"] = Trail
predicate_builtins["unify"] = unify
predicate_builtins["deref"] = deref
predicate_builtins["walk"] = walk
# '$assert_fact' is set per-module in exec_module (needs a closure over the
# per-module LogicModule), so it is NOT added to this shared dict.


# ── Loader ───────────────────────────────────────────────────────────────────


class PredicateLoader(Loader):
    def exec_module(loader, module):
        filename = module.__file__
        sys.modules[module.__name__] = module
        source = open(filename).read()
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)
        # Create a LogicModule (database.Module) for this Python module.
        # This is the $module that predicate clauses are asserted into and
        # compiled against.  It is distinct from the Python module object.
        logic_module = LogicModule(module.__name__)
        module_dict["$module"] = logic_module
        # '$assert_fact' is module-specific (needs to know which logic_module
        # to assert facts into), so it is set here as a closure.
        # '$' prefix prevents user code from accidentally overriding it.
        module_dict["$assert_fact"] = lambda term: _assert_fact(term, logic_module)
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
        for other_finder in sys.meta_path[sys.meta_path.index(finder) + 1:]:
            spec = other_finder.find_spec(fullname, path, target)
            if spec:
                origin = spec.origin
                if origin and origin.endswith(".py"):
                    try:
                        first_line = open(origin).readline()
                    except FileNotFoundError:
                        pass
                    else:
                        if first_line.startswith("# predicates"):
                            spec.loader = _predicate_loader
                            return spec
                return spec


sys.meta_path[:] = [PredicateFinder(), *sys.meta_path]


# ── IPython integration ───────────────────────────────────────────────────────

_simple_ast_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}
# '$'-prefixed names cannot be typed as normal Python identifiers, so user code
# cannot accidentally shadow them.  Do not remove the '$' prefix.
_simple_ast_builtins["$ast"] = ast
# Inject runtime types so that functor class code (which calls Var()) works in
# IPython cells.
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
