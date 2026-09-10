"""Surface-syntax desugaring — a pure ``ast`` → ``ast`` normalisation pass.

WHAT THIS MODULE IS FOR
-----------------------
Clausal source is Python surface syntax.  A few constructs are *sugar*: they
have no independent meaning, they are exactly equal to a longer spelling that
the rest of the toolchain already understands.  ``P.key`` is one — it is
defined to be ``P[key]``, nothing more.

Two front ends parse Clausal source today:

* the engine's ``TermTransformer`` (``clausal/templating/term_rewriting.py``),
  which lowers the AST to the Terms IR and runs it, and
* a second front end — an independent SMT-based checker maintained by a
  downstream consumer — which builds its OWN clause IR from the raw ``ast``
  and translates it to Z3.

The prover re-implements the engine's *semantics* on purpose: it exists to be
an INDEPENDENT cross-check, so if it consumed the engine's analysis an engine
bug would become invisible to it.  Sugar, however, carries no semantics — it
is a spelling.  Duplicating the spelling table in two places just means a new
sugar silently reads as something else (or as nothing) in the prover.

So this module is the ONE place a surface sugar is expanded, and it is
deliberately kept to the narrowest possible job:

    **Syntax only.**  This pass rewrites spellings.  It performs NO semantic
    modelling, NO name resolution, NO atom minting, NO type or arity analysis,
    NO module loading, and it reads no engine state.  Semantic modelling is
    NOT shared between the engine and the prover, and must not be added here
    — that separation is what makes the prover an independent check.

Properties every rewrite in here must hold to:

* Pure: no I/O, no globals, no engine imports.  ``ast`` in, ``ast`` out.
* Position-preserving: every synthesised node carries the source position of
  the construct it replaces (the prover reports counterexample locations by
  line number, and the engine's ``<-`` arrow detection reads source columns).
* Total: any shape not explicitly recognised is returned untouched, so a
  consumer that does not model it still reaches its own "unsupported" path.
  Never guess.

WHAT IS NOT HERE
----------------
The engine's read-once *hoisting* pass (``_lower_dict_reads`` in
``term_rewriting.py``) is a separate, engine-only lowering: it mints implicit
variables and reorders goals so a dict read happens once per solution.  That
is an evaluation strategy, not a spelling, and the prover neither wants nor
needs it — it models the inline ``P[key]`` read directly.  Keep it out.
"""

import ast

__all__ = ["desugar_surface", "dotted_attr_chain", "is_dict_attr_access"]


def _is_logic_var_name(identifier: str) -> bool:
    """True for a Clausal logic-variable name (``P``, ``FOO_BAR``, ``_x``).

    Mirrors ``term_rewriting._is_logic_var_name``; kept local so this module
    stays free of engine imports.  ``term_rewriting`` is the caller, not the
    provider, so there is no cycle to invert.  No dunder exclusion here
    (sugar-recognition context) — pinned by test_var_classifier_conformance,
    which also pins the constant-shape exclusion below.
    """
    if identifier.startswith("_"):
        return True
    # Capital initial (ISO): ``X``, ``FOO``, ``Foo``.  ``Foo`` joined
    # this class on 2026-09-10 -- see term_rewriting._is_logic_var_name,
    # which is the copy that carries the full rationale.  All five
    # copies move together (test_var_classifier_conformance).
    return identifier[:1].isupper()


def dotted_attr_chain(attr_node):
    """Split a dotted expression into ``(base Name node, [attr names])``.

    ``P.a.b`` → ``(Name('P'), ['a', 'b'])`` — attribute names in source order,
    outermost last.  Returns ``None`` when the chain does not bottom out in a
    plain ``Name`` (e.g. ``f(x).a``, ``{...}.a``).
    """
    parts = []
    node = attr_node
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.reverse()
    return node, parts


def is_dict_attr_access(node, excluded=frozenset()) -> bool:
    """True for ``VAR.key`` dict attribute-access sugar (a logic-variable base).

    False for a qualified name (``mod.pred``, ``currency.euro``) — a dotted
    module path is a different, pre-existing feature and must stay untouched.

    *excluded* names bases that are spelled like variables but which the
    calling file does not READ as variables — since 2026-09-10 that is
    ``Undefined`` and the ``-import_from`` names, all TitleCase.  Without it
    ``Undefined.k`` flipped from a qualified reference to dict-subscript
    sugar and began demanding that ``k`` be a declared atom.  It defaults to
    empty so this module stays usable standalone (the SMT prover runs the
    very same function on its own parse and has no such bindings); the
    engine passes its clause-scope exclusions.

    See docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md.
    """
    if not isinstance(node, ast.Attribute):
        return False
    chain = dotted_attr_chain(node)
    return (chain is not None
            and chain[0].id not in excluded
            and _is_logic_var_name(chain[0].id))


def _is_python_escape(node) -> bool:
    """True for the ``++(expr)`` Python-escape wrapper.

    ``++`` (two adjacent ``+`` signs, no space) escapes to real Python:
    *expr* is evaluated by the Python interpreter at search time, so inside it
    ``D.value`` is a genuine attribute access on a Python object and Clausal
    surface sugar does NOT apply.  Mirrors the adjacency test in
    ``term_rewriting.TermTransformer.visit_UnaryOp``.
    """
    return (isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.UAdd)
            and isinstance(node.operand, ast.UnaryOp)
            and isinstance(node.operand.op, ast.UAdd)
            # adjacent columns — no space between the two '+' signs
            and node.col_offset == node.operand.col_offset - 1
            and node.lineno == node.operand.lineno)


class _SurfaceDesugarer(ast.NodeTransformer):
    """``P.key`` → ``P[key]``; everything else passes through unchanged."""

    def __init__(self, excluded=frozenset()):
        self._excluded = excluded

    def visit_UnaryOp(self, node):
        if _is_python_escape(node):
            # Not Clausal syntax — do not descend.  ``++(D.value)`` is Python
            # attribute access on a Python object, not a dict read.
            return node
        self.generic_visit(node)
        return node

    def visit_Call(self, node):
        """Rewrite the arguments of a call, but never its ``func``.

        ``P.foo(A)`` is the method-call form.  The engine rejects it outright
        (a dict read yields a value, which is not callable), and the prover
        must not model it either.  Leaving the ``func`` as an ``Attribute``
        is what keeps both of them on their existing rejection paths — if it
        were rewritten to ``P[foo](A)`` the shape would change under them.

        ``mod.pred(A)`` is a qualified predicate call and is likewise a
        ``func`` position; ``visit_Attribute`` leaves it alone anyway.
        """
        if not is_dict_attr_access(node.func, self._excluded):
            node.func = self.visit(node.func)
        node.args = [self.visit(arg) for arg in node.args]
        for kw in node.keywords:
            kw.value = self.visit(kw.value)
        return node

    def visit_Attribute(self, node):
        # Decide on the node AS PARSED: ``generic_visit`` below rewrites the
        # inner links of a chain, and once ``P.a`` has become ``P[a]`` the
        # outer node no longer looks like attribute access on a variable.
        sugar = is_dict_attr_access(node, self._excluded)
        self.generic_visit(node)
        if not sugar:
            # A qualified name (``mod.pred``), or a base this pass does not
            # recognise (``f(x).a``).  Leave the node exactly as parsed.
            return node
        key = ast.copy_location(ast.Name(id=node.attr, ctx=ast.Load()), node)
        return ast.copy_location(
            ast.Subscript(value=node.value, slice=key, ctx=node.ctx), node)


def desugar_surface(tree, excluded=frozenset()):
    """Expand Clausal surface sugar in *tree*, returning the rewritten tree.

    Currently expands exactly one sugar: dict attribute access on a logic
    variable, ``P.key`` → ``P[key]`` (chains fold left to right, so
    ``P.a.b`` → ``P[a][b]``, and ``P.KEY`` → ``P[KEY]`` is a variable key).

    Deliberately NOT rewritten:

    * ``mod.pred`` / ``currency.euro`` — a dotted module path, a different
      pre-existing feature, not sugar.
    * ``P.foo(A)`` — the method-call form.  It is reserved, not sugar; the
      engine raises a ``SyntaxError`` for it and the prover leaves it
      unsupported.  See ``_SurfaceDesugarer.visit_Call``.

    *tree* is rewritten IN PLACE (``ast.NodeTransformer`` semantics) and also
    returned; pass a ``copy.deepcopy`` if the caller shares the tree.
    Source positions are copied from the replaced construct, so line and
    column information survives.
    """
    tree = _SurfaceDesugarer(excluded).visit(tree)
    ast.fix_missing_locations(tree)
    return tree
