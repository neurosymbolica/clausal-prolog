"""import_hook.py — Import hook for Prolog-style predicate modules.

Modules whose first line starts with:

    # predicates

are intercepted by this hook, which:

  1. Injects predicate builtins (all simple_ast names) plus the hidden
     globals ``$module``, ``$define_predicate``, ``$assert_fact``, and
     ``$ast`` into the module namespace.  Names starting with ``$`` are
     intentionally not valid Python identifiers in normal source, so user
     code cannot accidentally shadow them.
  2. Transforms the module's AST via EmbedTransformer, which rewrites
     module-level ``a<-b`` statements into
     ``$define_predicate(Predicate(head=…, body=…), $module)`` calls, and
     trailing-comma expression statements into ``$assert_fact(term)`` calls.

This mirrors the mechanism in logython/__init__.py from prolog_in_python.
"""

from importlib.abc import MetaPathFinder, Loader
import sys
import ast
import warnings

from .pythonic_ast import nodes as simple_ast
from .templating.term_rewriting import EmbedTransformer


# ── Runtime support ──────────────────────────────────────────────────────────


def _define_predicate(predicate, module):
    """Register a Predicate node with its module's predicate registry."""
    try:
        registry = module.__predicates__
    except AttributeError:
        module.__predicates__ = registry = []
    registry.append(predicate)


def _assert_fact(term, module):
    """Store a fact term in the module's __facts__ list."""
    try:
        facts = module.__facts__
    except AttributeError:
        module.__facts__ = facts = []
    facts.append(term)


# ── Builtins injected into every predicate module ────────────────────────────

predicate_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}
# '$'-prefixed names cannot be typed as normal Python identifiers, so user code
# cannot accidentally shadow them.  Do not remove the '$' prefix.
predicate_builtins["$define_predicate"] = _define_predicate
# '$ast' gives generated code access to the stdlib ast module without risking a
# name collision with user-defined variables named 'ast'.
predicate_builtins["$ast"] = ast
# '$assert_fact' is set per-module in exec_module (needs a closure over 'module'),
# so it is NOT added to this shared dict.


# ── Loader ───────────────────────────────────────────────────────────────────


class PredicateLoader(Loader):
    def exec_module(loader, module):
        filename = module.__file__
        sys.modules[module.__name__] = module
        source = open(filename).read()
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)
        module_dict["$module"] = module
        # '$assert_fact' is module-specific (needs to know which module to store
        # facts in), so it is set here as a closure rather than in predicate_builtins.
        # '$' prefix prevents user code from accidentally overriding it.
        module_dict["$assert_fact"] = lambda term: _assert_fact(term, module)
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
# In IPython there is no per-session module, so '$assert_fact' collects facts in a
# shared list.  For module-backed predicate files, exec_module overrides this with
# a module-specific closure.
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
