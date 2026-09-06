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
     collect predicate nodes during module exec.  After the body has run,
     ``compiler_v2.compile_module`` compiles each predicate once (O(N) per
     predicate instead of O(N²)).
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
from .atom_diagnostics import truth_literal_hint_lines
from .import_diagnostics import exec_with_import_diagnostics
from .syntax_diagnostics import clausal_syntax_diagnostics
from .templating.term_rewriting import EmbedTransformer, TermTransformer
from .logic.database import Module as LogicModule
from .logic.constants import (
    check_constant_ground,
    constant_functor_term,
    register_module_constant,
)
from .logic.variables import Var, Trail, unify, deref, walk
from .logic.atoms import (
    is_atom as _term_is_atom,
    mint as _mint_atom,
    spelling as _atom_spelling,
)
from .terms import Compound, KWTerm, DictTerm, SetTerm


def _spelling_or_self(value):
    """*value*'s spelling if it is an ATOM, otherwise *value* unchanged.

    Two lines rather than a shared helper (2026-09-06-atoms-as-cells-strings,
    Task 9): the leaked-pool-atom shape test below is the only consumer here
    and the same two lines live beside the sibling test in ``compiler_v2``.
    """
    return _atom_spelling(value) if _term_is_atom(value) else value

# ── Runtime support ──────────────────────────────────────────────────────────


def _fact_to_predicate_node(term):
    """Wrap a ground fact term as a Predicate(head=term, body=True) node."""
    return simple_ast.Predicate(head=term, body=simple_ast.BoolLiteral(value=True))


def _unterminated_fact_error(name, lineno, src):
    """Raised when a bare, comma-less clause's functor is undefined — almost
    always a bodyless fact missing its trailing ',' (see the comma-optional
    fact rule in EmbedTransformer).  Emitted from generated guard code."""
    where = f"{src!r} (line {lineno})" if src else f"line {lineno}"
    raise NameError(
        f"name {name!r} is not defined — {where} looks like a bodyless fact "
        f"missing its trailing ','; add a comma to make it a fact, or declare "
        f"the predicate (-module/-dynamic)."
    ) from None


def _make_intern_atom(module_dict, module_items, module_name):
    """Build the ``$intern_atom`` helper for a module load.

    A bare-atom dict-literal key (``{filing_status: V}``) is resolved to its
    atom **at construction time**, because dict literals are built eagerly
    during ``exec`` — before the bare-atom auto-accept pass runs — so the key
    cannot rely on a later module-global binding.  Atoms are global by
    spelling and mint no class any more (§1b/R2): the helper returns
    ``atoms.mint(name)``, recorded in the process-wide ``predicate_builtins``
    pool that ``compiler_v2._process_bare_atom_refs``/``_process_declarations``
    also write.  That pool is the strict-atoms VOCABULARY — the set of
    declared spellings mapped to their minted atoms — not an identity table:
    2026-09-06-atoms-as-cells-strings §5.2 retires every ``is``-pin on an atom
    in favour of ``==``, and ``mint`` makes no promise to return the same
    object twice.

    Strict atom resolution is the default: an undeclared bare atom must NOT
    be silently accepted (that would pollute ``predicate_builtins`` and
    defeat the strict check), so the helper refuses to accept a name that is
    not already available, mirroring ``compiler_v2._process_bare_atom_refs``'
    own ``effective_strict = not implicit_mode`` rule.  Only files carrying
    ``-implicit_atoms`` disable strict mode and allow auto-accept, so a
    dict-key atom and a value-position atom now resolve under the *same*
    default.  (Atom keys whose atom is declared post-exec via
    ``-module``/``-private`` are a known limitation in strict files —
    declarations are processed after ``exec`` — so strict files should use
    string keys or a declared/imported atom; non-strict files, including the
    profile surface, are unaffected.)

    P3-1 Task 7 fix round 1 (Critical, review-caught): ``existing = module_dict.
    get(name)`` used to trust ANY already-bound name, including one present
    ONLY because ``module_dict`` was pre-seeded at exec start with the
    entire process-wide ``predicate_builtins`` pool -- so a dict-key atom
    undeclared in THIS module silently resolved whenever some OTHER,
    earlier-loaded module had declared (or auto-accepted) the same
    spelling.  Same defect, same fix, as ``compiler_v2._process_bare_atom_
    refs``: trust an already-bound value UNLESS it is specifically the
    leaked-pool-atom shape (an ATOM whose spelling is its own name, still
    EQUAL to the pool's live entry) that THIS module's own declared/
    imported vocabulary (``compiler_v2._locally_declared_names``) does not
    vouch for.  ``global_atom/2``'s mint-on-demand mode also writes the
    pool, but only at query runtime -- irrelevant to this compile-time
    check, same reasoning as the sibling fix.
    """
    from clausal.logic.compiler_v2 import _locally_declared_names
    from clausal.pythonic_ast.nodes import ImplicitAtomsDeclaration

    # Strict is the default; only ``-implicit_atoms`` re-enables auto-accept.
    # Mirrors ``compiler_v2._process_bare_atom_refs``' ``effective_strict``.
    strict = not any(
        isinstance(it, ImplicitAtomsDeclaration) for it in module_items
    )
    local_names = _locally_declared_names(module_items)

    def _intern_atom(name):
        existing = module_dict.get(name)
        if existing is not None:
            # 2026-09-06-atoms-as-cells-strings §5.2: the pin is EQUALITY,
            # never identity — ``mint`` promises an equal atom, not the same
            # object (there is no process-wide atom table), and a constant
            # unmarshalled from a ``.pyc`` is never the minted instance.  The
            # shape test reads the atom through the public API so a cell atom
            # ``("foo",)`` is recognised beside today's str.
            leaked_pool_atom = (
                _term_is_atom(existing)
                and _spelling_or_self(existing) == name
                and predicate_builtins.get(name) == existing
            )
            # Task 8 split: the OTHER leak shape a pre-seeded module_dict can
            # carry is a ``runtime_builtins`` entry still sitting under this
            # name -- e.g. ``{Add: 1}[Add]`` in a module with zero
            # declarations.  Same discipline as leaked_pool_atom: distrust
            # it unless THIS module's own declared/imported vocabulary
            # vouches for the name, OR the name is one of the explicit,
            # reviewed exemptions in ``STRICTNESS_EXEMPT_RUNTIME_NAMES``
            # (Task 8 fix round 1, RULING: the default is distrust-any-
            # runtime-binding, not just ``simple_ast.__all__`` -- see that
            # frozenset's docstring for why).
            leaked_runtime_builtin = (
                not leaked_pool_atom
                and name in runtime_builtins
                and name not in STRICTNESS_EXEMPT_RUNTIME_NAMES
                and runtime_builtins[name] is existing
            )
            if not (leaked_pool_atom or leaked_runtime_builtin) or name in local_names:
                return existing
        elif name in local_names:
            # Declared/imported by this module but not yet reflected in
            # module_dict at this point in exec (e.g. a -module/-private
            # atom whose guarded assignment has not run yet).  Resolve it
            # the same way the auto-mint branch below would.
            return predicate_builtins.setdefault(name, _mint_atom(name))
        if strict:
            message = (
                f"strict_atoms: undeclared atom {name!r} used as a dict key in "
                f"{module_name}; declare it (-module/-private/-import_from) or "
                f"use a string key"
            )
            # `{true: ...}` reaches this site rather than the bare-atom
            # diagnostic, and wants the same steer at the real literal.
            raise NameError(
                "\n".join([message, *truth_literal_hint_lines([name])])
            )
        return predicate_builtins.setdefault(name, _mint_atom(name))

    return _intern_atom


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
    module_dict["$check_constant_ground"] = check_constant_ground
    module_dict["$constant_functor_term"] = constant_functor_term
    module_dict["$register_module_constant"] = register_module_constant
    code = loader.get_code(module.__name__)

    # _last_transformer is set by source_to_code.  If the code came
    # from .pyc cache, source_to_code didn't run, so use the recovery fn.
    transformer = getattr(loader, '_last_transformer', None)
    if transformer is not None:
        module_items = transformer._module_items
    else:
        module_items = recover_module_items_fn(filename)

    module_dict["$intern_atom"] = _make_intern_atom(module_dict, module_items,
                                                    module.__name__)

    _preseed_py_submodules(module_items)
    # A failed `-import_from` surfaces here as CPython's stock ImportError,
    # which names the file but not its vocabulary.  This is the raise site at
    # which the Clausal context is known, so enrich it here.
    exec_with_import_diagnostics(code, module_dict, module_items, filename)

    logic_module = compile_module(
        predicate_nodes, module_items, module_dict, module.__name__,
    )
    # -constants directives register into $module.constants (see
    # register_module_constant, clausal/logic/constants.py) WHILE the
    # module body execs — i.e. onto dummy_logic_module, the placeholder
    # $module that compile_module below then throws away in favour of a
    # freshly-built LogicModule. Carry the registrations across the swap
    # so module_constant/3 sees what the module actually declared.
    logic_module.constants.update(dummy_logic_module.constants)
    module_dict["$module"] = logic_module
    module.__clausal_module__ = logic_module


# ── Builtins injected into every predicate module ────────────────────────────
#
# P3-1/P3-2 Task 8 (pool split; closes
# todo/done/pythonic-ast-names-leak-into-strict-atom-namespace-2026-09-04.md):
# this used to be a SINGLE dict, seeded at process bootstrap with every
# ``simple_ast.__all__`` class object and then grown at runtime with every
# legitimately declared/auto-accepted ATOM.  Because both jobs shared one
# dict, an internal AST-node class name (``Add``, ``Call``, ``Match``, ...)
# was indistinguishable from a declared atom to the strictness check
# (``compiler_v2._process_bare_atom_refs``/``_process_declarations``,
# ``_make_intern_atom`` below) — a bare reference to ``Add`` in a strict
# module with ZERO declarations compiled clean.  The fix splits the one job
# from the other into two dicts:
#
# ``runtime_builtins`` — the compilation-support namespace every generated
#   module needs bound in its own exec-time namespace (EmbedTransformer's
#   rewrite emits bare ``Predicate(head=…, body=…)`` calls, for example) or
#   at query-compile time (``INJECTED_RUNTIME_BUILTINS``, below).  NOT an
#   atom vocabulary — never consulted by the strictness check.
#
# ``predicate_builtins`` — the §1b/R2 GLOBAL ATOM pool ONLY.  Starts EMPTY
#   at process bootstrap; grows only via a legitimate atom declaration
#   (-module/-private, ``_process_declarations``), auto-accept
#   (-implicit_atoms, ``_process_bare_atom_refs``/``$intern_atom``), or
#   ``global_atom/2``'s mint-on-demand.  This is the dict the strictness
#   check's "already resolved" test consults.
#
# Module-exec seeding (``exec_module`` below) applies BOTH — generated code
# still needs the runtime names — with ``predicate_builtins`` seeded FIRST
# and ``runtime_builtins`` layered on top, WINNING any collision.  This is
# the opposite of ``clausal/logic/compiler/predicate.py``'s
# ``base_globals`` precedence (there, a module's own ALREADY-RESOLVED
# globals safely win over the static runtime defaults, because
# ``_process_declarations``/``_process_bare_atom_refs`` have already run
# by that point) — here, seeding runs BEFORE those passes, against the
# RAW, unfiltered, process-wide atom pool.  If an atom pool entry were
# allowed to win here, a name collision with a ``simple_ast.__all__`` class
# (an atom legitimately declared as ``Sub`` in one module, say) would
# clobber EVERY OTHER, unrelated module's ``module_dict["Sub"]`` with a
# plain str — breaking that module's own generated code, which
# unconditionally needs the real class to construct its clause bodies
# (arithmetic/comparison/call nodes compile to bare ``Sub(...)``/``Call(...)``
# constructor references — see the fixture regression this order fixes,
# ``tests/fixtures/tagged_shapes.clausal``).  A module that DOES want to
# declare that spelling as its own atom still gets it correctly:
# ``_process_declarations`` runs AFTER this seeding and unconditionally
# rebinds its own declared names, regardless of what seeding left there.
runtime_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}

# '$'-prefixed names cannot be typed as normal Python identifiers, so user code
# cannot accidentally shadow them.  Do not remove the '$' prefix.
# Note: $define_predicate and $assert_fact are set per-module in exec_module
# (they need closures over the per-module LogicModule and module_dict).
#
# The runtime *value* bindings injected into every predicate module —
# ``$ast``, ``PredicateMeta``, ``Var``, ``Compound``, ``DictTerm``, ``SetTerm``,
# ``Trail``, ``PyThunk``, ``FStringThunk``, ``Quantity``, ``Undefined``,
# ``BoolEq``/``BoolImpl``, and the ``$``-prefixed engine helpers
# ``$walk``/``$deref``/``$unify`` — live in a SINGLE source of truth,
# ``INJECTED_RUNTIME_BUILTINS`` in clausal/logic/compiler/predicate.py.  The
# compiler seeds every predicate's base_globals from the same dict so a name
# term_to_ast_expr can emit resolves on the bare-query path too (whose globals
# derive only from the module dict).  Layering it here keeps module load and
# query compilation in lockstep — a new injected binding cannot regress either.
#
# ``$ast`` gives generated code access to the stdlib ast module without a name
# collision with a user variable named ``ast``.  A12-F004 / A12-D002: the engine
# helpers walk/deref/unify are pure internals referenced under the ``$``-prefix;
# injecting them under their PUBLIC names reserved those names — a user predicate
# ``walk/2``/``deref/2``/``unify/2`` failed at load — so they are ``$``-prefixed
# only, freeing the public names for user code.  ``Undefined`` is the Kleene (K3)
# third truth value, a real binding (not a minted atom) so it resolves in every
# module including ``-strict_atoms`` ones with process-wide identity.
from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
runtime_builtins.update(INJECTED_RUNTIME_BUILTINS)
runtime_builtins["$unterminated_fact_error"] = _unterminated_fact_error

# Task 8 fix round 1 (RULING, reviewer-caught): the strictness check's
# "already resolved" test must distrust ANY ``runtime_builtins`` entry, not
# just the ``simple_ast.__all__`` subset (fix round 1's ``_SIMPLE_AST_
# NODE_NAMES``, now DELETED as redundant under this general rule) -- the
# reviewer proved the narrower scoping left the todo's "closes the whole
# CLASS of bug" promise undelivered by injecting a synthetic name into
# ``runtime_builtins`` and watching a zero-declaration strict module
# resolve it clean, the identical ``Add`` shape on an instance the narrow
# allowlist could not have anticipated.  A FUTURE ``INJECTED_RUNTIME_
# BUILTINS`` addition must fail LOUD (an undeclared-atom ``NameError``,
# prompting whoever added it to consider whether it belongs here) rather
# than leak SILENT into the atom vocabulary the way ``simple_ast.__all__``
# names did.
#
# This frozenset is the ONE, explicit, reviewed escape hatch: every entry
# is a deliberate decision that this specific runtime name may satisfy
# bare-atom resolution in EVERY module, strict or not, with no declaration
# required.  Adding a name here is a judgment call that needs its own
# one-line justification, not a side effect of adding it to
# ``INJECTED_RUNTIME_BUILTINS``.
STRICTNESS_EXEMPT_RUNTIME_NAMES = frozenset({
    # The Kleene (K3) third truth value.  Pre-existing, deliberate design
    # (see the docstring note above): a real binding, not a minted atom,
    # so it must resolve in every module including ``-strict_atoms`` ones
    # with process-wide identity.  Task 8 fix round 1 (review-caught):
    # narrowing the distrust check to ``simple_ast.__all__`` only (rather
    # than exempting this name explicitly) broke ``clausal/stdlib/
    # kleene.clausal`` (a bare ``Undefined`` reference), cascading into
    # ~163 unrelated test failures across files that transitively load it.
    "Undefined",
})

# The GLOBAL ATOM pool (§1b/R2) — see the module-level comment above.  Starts
# empty; ``compiler_v2._process_declarations``/``_process_bare_atom_refs`` and
# ``_make_intern_atom`` below are its only writers.
predicate_builtins: dict = {}


def _preseed_py_submodules(module_items) -> None:
    """Ensure ``sys.modules["py.X"]`` entries exist for any ``py.*`` imports.

    when a .clausal file uses ``-import_from(py.re, …)``, the generated
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


# A10-F018: cached .pyc bytecode is the OUTPUT of EmbedTransformer, but the
# default source-loader invalidates only on (mtime, size) + CPython magic — so
# upgrading clausal (new transformer semantics) leaves stale transformed
# bytecode live until the source file itself changes. Fold this tag into the
# reported mtime so a clausal upgrade invalidates every cached .clausal/.pl
# .pyc. BUMP THIS whenever EmbedTransformer / the codegen output changes.
#
# 7 -> 8 (P3-2 Task 2, THE FLIP): the transformer's output changed three ways
# -- ``-tagged_terms`` is no longer a directive it accepts, ``-module``/
# ``-private`` accept ISO ``name/arity`` entries and mint a class for them
# (R6b), and a declared data functor's name binds its interned spelling
# instead of a generated class.  A stale pre-flip ``.pyc`` against the new
# runtime calls that spelling: ``TypeError: 'str' object is not callable``
# from inside generated code.
CLAUSAL_BYTECODE_TAG = 8


# ── One source file → one compilation ────────────────────────────────────────
#
# Maps a resolved source path to the dotted name it was first imported under.
# A .clausal file is reachable under more than one dotted name whenever both a
# package directory and its parent sit on sys.path (``pkg/soledom.clausal`` is
# then both ``soledom`` and ``pkg.soledom``), and CPython's per-name module
# cache would compile it once per name.  For a predicate module that is not
# merely wasteful: each compilation mints its *own* PredicateMeta class for
# every declared compound, so a term built under one name does not unify with a
# pattern built under the other — silently, because the two terms render
# identically and nothing raises.  So the second name aliases the first
# module rather than compiling a parallel copy.
#
# Only imports that came through the finders register here; ``_load_module``
# deliberately compiles a fresh copy each call and stays out of the registry.
#
# The claim is made after exec, and importlib's import lock is per *name*, so
# two threads importing two names for one file at the same moment can still
# both compile it.  That is the pre-existing behaviour rather than a new
# failure mode, and a path-wide lock is not worth its cost for a race that
# needs two dotted names for one file to first load concurrently.
_MODULES_BY_PATH: dict[str, str] = {}


def _canonical_source_key(path):
    """Registry key for a source file: symlinks and ``..`` resolved away."""
    return os.path.normcase(os.path.realpath(path))


class _ClausalSourceLoader(SourceLoader):
    """Common file I/O for .clausal and .pl loaders.

    Extends ``importlib.abc.SourceLoader`` to get automatic ``.pyc`` caching.
    Subclasses must implement ``source_to_code``, ``exec_module``, and
    ``_recover_module_items``.
    """

    #: Set by ``_ExtensionFinder.find_spec`` to the key this load should claim
    #: in ``_MODULES_BY_PATH``.  ``None`` for loaders built directly (e.g. by
    #: ``_load_module``), which must not claim a file they compile privately.
    _canonical_path = None

    def __init__(self, fullname, path):
        self._fullname = fullname
        self._path = path

    def _register_canonical(self, module):
        """Claim this source path for ``module`` if the finder asked us to."""
        if self._canonical_path is not None:
            _MODULES_BY_PATH[self._canonical_path] = module.__name__

    def get_filename(self, fullname):
        return self._path

    def get_data(self, path):
        with open(path, "rb") as f:
            return f.read()

    def path_stats(self, path):
        st = os.stat(path)
        # A10-F018: XOR the transformer-version tag into the mtime so bumping
        # CLAUSAL_BYTECODE_TAG invalidates cached bytecode even when the source
        # file's mtime/size are unchanged (consistent per version → cache hits
        # still work within a version).
        #
        # Use nanosecond mtime (``st_mtime_ns``) rather than ``int(st.st_mtime)``:
        # truncating to whole seconds let a same-size edit within the same integer
        # second serve stale bytecode (the mutation-testing false-green window).
        # importlib stores/compares this field masked with 0xFFFFFFFF, so any
        # deterministic int is valid; masking keeps the value in range and the
        # tag XOR still participates, so a tag bump still invalidates old caches.
        return {"mtime": (st.st_mtime_ns ^ CLAUSAL_BYTECODE_TAG) & 0xFFFFFFFF,
                "size": st.st_size}

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
    # A malformed clause surfaces here as CPython's stock one-liner, whose
    # reported line is where the parse gave up rather than where the mistake
    # is; clausal_syntax_diagnostics attaches the source and a caret so the
    # author can see that for themselves.  See clausal/syntax_diagnostics.py.
    with warnings.catch_warnings(), \
            clausal_syntax_diagnostics(source, filename):
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=filename)
        source_lines = source.splitlines(keepends=True)
        transformer = EmbedTransformer(
            source_lines=source_lines, filename=filename)
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)
        code = compile(tree, filename=filename, mode="exec")
        return code, transformer


def _extract_module_items(source, filename):
    """Re-parse .clausal source text just to recover module_items (cache-hit path)."""
    with warnings.catch_warnings(), \
            clausal_syntax_diagnostics(source, filename):
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=filename)
        source_lines = source.splitlines(keepends=True)
        transformer = EmbedTransformer(
            source_lines=source_lines, filename=filename)
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
        self._register_canonical(module)
        module_dict = module.__dict__
        # Task 8 split: predicate_builtins (the atom pool) FIRST,
        # runtime_builtins (compilation-support names every generated
        # module needs) layered on top and WINNING any collision -- see
        # the pool-split comment above for why this order, not the
        # opposite, is required (a colliding atom declared elsewhere must
        # not break THIS module's own generated-code construction).
        module_dict.update(predicate_builtins)
        module_dict.update(runtime_builtins)

        _run_v2_pipeline(self, module, module_dict, filename,
                         self._recover_module_items)

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
        self._register_canonical(module)
        module_dict = module.__dict__
        # Task 8 split: predicate_builtins (the atom pool) FIRST,
        # runtime_builtins (compilation-support names every generated
        # module needs) layered on top and WINNING any collision -- see
        # the pool-split comment above for why this order, not the
        # opposite, is required (a colliding atom declared elsewhere must
        # not break THIS module's own generated-code construction).
        module_dict.update(predicate_builtins)
        module_dict.update(runtime_builtins)
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


class _AliasLoader:
    """Bind an already-compiled module to a second dotted name.

    ``exec_module`` swapping ``sys.modules[name]`` is the supported way to hand
    importlib a different object than the one it created: ``_bootstrap._load``
    re-reads ``sys.modules[spec.name]`` after ``exec_module`` returns and uses
    *that* as the imported module (the same trick the real loaders here already
    use).  Going through ``exec_module`` rather than ``create_module`` matters —
    a module returned from ``create_module`` gets ``_init_module_attrs``
    applied, which would overwrite the canonical module's ``__name__`` and
    ``__spec__`` with the alias's.
    """

    def __init__(self, canonical_name):
        self._canonical_name = canonical_name

    def create_module(self, spec):
        return None  # let importlib make the throwaway we are about to discard

    def exec_module(self, module):
        sys.modules[module.__name__] = sys.modules[self._canonical_name]


class _ExtensionFinder(MetaPathFinder):
    """Base finder that searches sys.path for files with a given extension."""
    _extension: str = ""
    _loader_cls: type = None

    def _spec_for(self, fullname, source_path, pkg_dir=None):
        """Build the spec for ``fullname``, deduplicating by source path.

        If this exact file is already loaded under another dotted name, alias
        that module instead of compiling a second, term-incompatible copy.
        """
        key = _canonical_source_key(source_path)
        canonical = _MODULES_BY_PATH.get(key)
        if (canonical is not None and canonical != fullname
                and sys.modules.get(canonical) is not None):
            loader = _AliasLoader(canonical)
        else:
            # Either this file is new, or its registry entry is stale because
            # the module was evicted from sys.modules.  Compile, and let the
            # load claim (or reclaim) the path.
            loader = self._loader_cls(fullname, source_path)
            loader._canonical_path = key
        spec = ModuleSpec(fullname, loader, origin=source_path)
        if pkg_dir is not None:
            spec.submodule_search_locations = [pkg_dir]
        return spec

    def find_spec(self, fullname, path, target=None):
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for dir_entry in search_dirs:
            # Flat-file form: ``dir_entry/tail.clausal`` → module ``tail``.
            file_candidate = os.path.join(dir_entry, tail + self._extension)
            is_file = os.path.isfile(file_candidate)
            # Package form: ``dir_entry/tail/__init__.clausal`` → package ``tail``.
            # Reuses Python's __init__ package mechanism so submodule files
            # (``tail/sub.clausal``) then resolve as ``fullname.sub``.  A bare
            # directory *without* an __init__ is left to PathFinder as a PEP-420
            # namespace package (return nothing here), so this must not fire.
            pkg_dir = os.path.join(dir_entry, tail)
            init_candidate = os.path.join(pkg_dir, "__init__" + self._extension)
            is_pkg = os.path.isdir(pkg_dir) and os.path.isfile(init_candidate)

            if not (is_file or is_pkg):
                continue

            # A10-F010 / A10-D002(a): a .clausal/.pl file (or package dir) named
            # after a standard-library module is almost always an accident.
            # These finders run before PathFinder, so shadowing would be silent —
            # defer to the stdlib (return None) and warn loudly instead.
            if tail in sys.stdlib_module_names:
                from clausal.templating.term_rewriting import (
                    ClausalLintWarning,
                )
                shadowed = file_candidate if is_file else init_candidate
                warnings.warn(
                    f"{shadowed!r} is named after the standard-library "
                    f"module {tail!r}; the stdlib module is used instead. "
                    f"Rename the file to avoid shadowing it.",
                    ClausalLintWarning,
                    stacklevel=2,
                )
                return None

            # Flat file takes priority over a same-named package directory so
            # existing flat-module resolution is unchanged.
            if is_file:
                return self._spec_for(fullname, file_candidate)

            # A non-None search-locations list is what marks the module a
            # *package*: importlib sets ``__path__`` from it, so a later
            # find_spec(fullname + ".sub", path=[pkg_dir]) resolves submodules.
            return self._spec_for(fullname, init_candidate, pkg_dir=pkg_dir)


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
    """Redirect ``py.X`` dotted imports to ``clausal.modules.py.X``.

    Bare-name interception has been retired: all ``clausal.modules``
    wrappers now live under ``clausal.modules.py.*``, and compile-time
    aliases (_MODULE_ALIASES / _IMPORT_ALIASES) rewrite bare names in
    generated bytecode before they ever reach this finder.

    The only remaining responsibility is handling ``py.X`` dotted imports,
    which is required because pytest's ``py`` shim (a non-package module)
    may already occupy ``sys.modules["py"]`` by the time clausal is loaded,
    causing ``from py.re import …`` to fail with "'py' is not a package".
    Intercepting dotted ``py.*`` names here bypasses that stale cache entry.
    """

    _MODULES_PKG = "clausal.modules"

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
        return None


def _ensure_source_modules_on_path() -> None:
    """Guarantee the source ``clausal/modules`` directory is on the package path.

    Extension distributions (clausal-torch, clausal-jax, …) installed
    *non-editably* drop bare ``.py`` files into ``site-packages/clausal/modules/``
    with no ``__init__.py``, turning that directory into a PEP 420 namespace
    portion. When a process runs from a working directory that does not put the
    clausal *source* tree on ``sys.path`` (the normal shape for a rulebase plus a
    separate test harness), the stdlib ``PathFinder`` resolves ``clausal.modules``
    to that site-packages portion *before* an editable finder is consulted — and
    that portion lacks the source-only ``py/`` subpackage. The symptom is::

        <load> — No module named 'clausal.modules.py'

    for any ``-import_from(date_time, …)`` (or regex/json/os/…) that compiles to
    ``from clausal.modules.py.<name> import …``.

    This hook runs from the source tree (``clausal.import_hook`` is always
    resolved there), so it can locate the canonical ``clausal/modules`` directory
    relative to itself and splice it onto ``clausal.modules.__path__``, making the
    ``py/`` subpackage discoverable regardless of cwd.
    """
    src_modules = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modules")
    if not os.path.isdir(src_modules):
        return
    try:
        mod = importlib.import_module("clausal.modules")
    except ImportError:
        return
    search = getattr(mod, "__path__", None)
    if search is None:
        return
    if not any(os.path.abspath(p) == os.path.abspath(src_modules) for p in list(search)):
        # Prefer the canonical source location (mirrors the layout seen when the
        # source tree is on sys.path, where it is searched first).
        try:
            search.insert(0, src_modules)
        except (AttributeError, TypeError):
            search.append(src_modules)


_ensure_source_modules_on_path()

sys.meta_path[:] = [PredicateFinder(), PrologFinder(), ModulesFinder(), *sys.meta_path]


# ── IPython integration ───────────────────────────────────────────────────────

# Task 8 split: IPython was already independent of the growing atom pool
# (this dict is a one-shot snapshot at import time, never re-read), so it
# copies ``runtime_builtins`` directly rather than recomputing the same
# simple_ast.__all__ + INJECTED_RUNTIME_BUILTINS merge a second time.
# Inject the runtime types so that functor class code (which calls Var()) and
# compiled goals work in IPython cells: $ast, PredicateMeta, Var/Compound/
# DictTerm/SetTerm, Trail, PyThunk/FStringThunk, Quantity, Undefined,
# BoolEq/BoolImpl, and the $-prefixed engine helpers ($walk/$deref/$unify).
_simple_ast_builtins = dict(runtime_builtins)
# in_ IPython there is no per-session logic module, so '$assert_fact' collects
# facts in a shared list.  For module-backed predicate files, exec_module
# overrides this with a module-specific closure.
_ipython_facts: list = []
_simple_ast_builtins["$assert_fact"] = _ipython_facts.append
# ``-constants`` lowers to ``$check_constant_ground(...)`` + a
# ``$register_module_constant(...)`` call (see ``_handle_constants_directive``).
# The directive itself is rejected interactively (``_FreshEmbedTransformer`` /
# EmbedTransformer's ``interactive`` flag) rather than run to completion, so
# these entries are not reachable via that path today — registered anyway so
# a module-backed reference exec'd in an IPython namespace (e.g. copy-pasted
# compiled output) does not raise a bare NameError.
_simple_ast_builtins["$check_constant_ground"] = check_constant_ground
_simple_ast_builtins["$constant_functor_term"] = constant_functor_term
_simple_ast_builtins["$register_module_constant"] = register_module_constant

from clausal.repl import Solutions as _Solutions, _run_ipython_goal as _run_ipython_goal
_simple_ast_builtins["Solutions"] = _Solutions
_simple_ast_builtins["_run_ipython_goal"] = _run_ipython_goal


_STAR_QUERY_SENTINEL = "_clausal_star_query_"


def _star_query_input_transformer(lines: list[str]) -> list[str]:
    """IPython input transformer: rewrite ``*(...)`` to a valid Python call.

    Runs at the source-text level, *before* ``codeop.Compile`` checks syntax.
    On Python ≥ 3.14 (and some IPython versions), ``*(expr)`` raises a
    ``TypeError`` during the completeness check — before AST transformers get a
    chance to intercept the ``Starred`` node.  By rewriting the text to
    ``_clausal_star_query_(...)``, the source becomes a normal function call
    that survives parsing and compilation.  ``_StarQueryTransformer`` then
    detects the sentinel call at the AST level.
    """
    out = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("*("):
            indent = line[: len(line) - len(stripped)]
            out.append(indent + _STAR_QUERY_SENTINEL + stripped[1:])
        else:
            out.append(line)
    return out


class _StarQueryTransformer(ast.NodeTransformer):
    """Rewrite ``*(goal_expr)`` expression statements to Solutions calls.

    Inside ``*(…)`` the expression is treated as a clause body goal.
    ``TermTransformer`` handles variable allocation (via walrus operators) and
    all operator rewriting (``is`` → ``Unify``, ``and`` → ``And``, etc.).

    ``*(Goal(X))``
        → ``Solutions(_run_ipython_goal(Goal((X:=Var())), {'X': X}, globals()))``

    ``*(A(X), B(X, Y))``
        → ``Solutions(_run_ipython_goal(And(left=A((X:=Var())), right=B(X, (Y:=Var()))), {'X': X, 'Y': Y}, globals()))``

    The ``*(…)`` form is rewritten at the source level by
    ``_star_query_input_transformer`` into ``_clausal_star_query_(…)`` so that
    it survives Python ≥ 3.14 syntax checks.  This AST transformer detects
    both the sentinel call and (for backwards compatibility) the legacy
    ``Expr(Starred(...))`` form.
    """

    def visit_Expr(self, node):
        # Legacy form: Expr(Starred(...)) — may still work on some Python/IPython combos.
        if isinstance(node.value, ast.Starred):
            inner = node.value.value
            return self._rewrite(node, inner)
        # Sentinel form: Expr(Call(func=Name('_clausal_star_query_'), args=[...]))
        if (isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == _STAR_QUERY_SENTINEL):
            args = node.value.args
            if len(args) == 1:
                inner = args[0]
            else:
                # Multiple args: _clausal_star_query_(A(X), B(Y)) → treat as tuple
                inner = ast.Tuple(elts=args, ctx=ast.Load())
                ast.copy_location(inner, node)
            return self._rewrite(node, inner)
        return self.generic_visit(node)

    def _rewrite(self, node, inner):
        # IPython REPL path — not a .clausal module compile, so no shared
        # bare-atom-refs sink to thread through.  Phase 2 auto-mint applies
        # to module compilation in compiler_v2; bare references in REPL
        # goals resolve against the REPL session's globals at exec time.
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
            tree = EmbedTransformer(implicit_atoms_default=True, interactive=True).visit(tree)
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
    # Idempotent: if already enabled on this shell, do nothing. Stacking
    # transformers double-rewrites the AST and breaks *(…) queries.
    if getattr(shell, '_clausal_enabled', False):
        return
    shell._clausal_enabled = True
    # Suppress the "'str' object is not callable" SyntaxWarning that Python
    # emits when it compiles source containing  'op'(args)  syntax.  in_ this
    # DSL that syntax is intentional; the EmbedTransformer and
    # _StringCallableRewriter rewrite it before any bytecode is generated, but
    # tools such as IPython's check_complete() and Jedi compile the raw source
    # before our AST transformer runs, so the warning would otherwise appear.
    warnings.filterwarnings("ignore", message="'str' object is not callable",
                            category=SyntaxWarning)
    shell.ast_transformers.append(_FreshEmbedTransformer())
    # Text-level input transformer: rewrite *(…) → _clausal_star_query_(…)
    # so the source survives Python ≥ 3.14 syntax checks before AST
    # transformers run.
    if hasattr(shell, 'input_transformers_post'):
        shell.input_transformers_post.append(_star_query_input_transformer)
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
