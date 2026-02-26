"""import_hook.py — Import hook for Prolog-style predicate modules.

Modules whose first line starts with:

    # predicates

are intercepted by this hook, which:

  1. Injects predicate builtins (all simple_ast names) plus the hidden
     globals ``$module`` and ``$define_predicate`` into the module namespace.
  2. Transforms the module's AST via EmbedTransformer, which rewrites
     module-level ``a<-b`` statements into
     ``$define_predicate(Predicate(head=…, body=…), $module)`` calls.

This mirrors the mechanism in logython/__init__.py from prolog_in_python.
"""

from importlib.abc import MetaPathFinder, Loader
import sys
import ast

import simple_ast
from term_rewriting import EmbedTransformer


# ── Runtime support ──────────────────────────────────────────────────────────


def _define_predicate(predicate, module):
    """Register a Predicate node with its module's predicate registry."""
    try:
        registry = module.__predicates__
    except AttributeError:
        module.__predicates__ = registry = []
    registry.append(predicate)


# ── Builtins injected into every predicate module ────────────────────────────

predicate_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}
predicate_builtins["$define_predicate"] = _define_predicate


# ── Loader ───────────────────────────────────────────────────────────────────


class PredicateLoader(Loader):
    def exec_module(loader, module):
        filename = module.__file__
        sys.modules[module.__name__] = module
        source = open(filename).read()
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)
        module_dict["$module"] = module
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
