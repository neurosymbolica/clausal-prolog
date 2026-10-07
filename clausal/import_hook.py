"""import_hook.py — Import hook for Clausal source modules.

Seam files (``.seam``, the ``CLAUSAL_SUFFIXES``) are intercepted by this hook,
which:

  1. Injects predicate builtins (all simple_ast names, Var, unify,
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

Prolog-syntax files -- Clausal Prolog (``.clausal``) and ISO Prolog (``.pl``)
-- are found by the same finder and compiled by the Prolog loaders
(``NativePrologLoader``, ``PrologLoader``); see ``_prolog_loader_class_for``.
"""

from importlib.abc import MetaPathFinder, SourceLoader
from importlib.machinery import ModuleSpec
import importlib.util
import sys
import ast
import hashlib
import os
import warnings

from . import _suffixes as _sfx
from ._suffixes import CLAUSAL_SUFFIXES
from .end_module import SURFACE_CLAUSAL_PROLOG, SURFACE_SEAM, surface_of
from .pythonic_ast import nodes as simple_ast
from .atom_diagnostics import truth_literal_hint_lines
from .import_diagnostics import exec_with_import_diagnostics
from .syntax_diagnostics import clausal_syntax_diagnostics
from .templating.term_rewriting import EmbedTransformer, TermTransformer
from .logic.database import Module as LogicModule
from .logic.predicate import (
    begin_loading_declarations, end_loading_declarations,
)
from .logic.constants import (
    check_constant_ground,
    check_currency_unit,
    decimal_value,
    constant_functor_term,
    register_module_constant,
    register_constant_units,
)
from .logic.variables import Var, Trail, unify, deref, walk
from .logic.atoms import (
    is_atom as _term_is_atom,
    mint as _mint_atom,
    spelling as _atom_spelling,
)
from .terms import DictTerm, SetTerm
from .logic.generated_names import with_dollar_twins


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


def _unseed_foreign_pool_atoms(module_dict, module_items):
    """Take back, before the body runs, the pool atoms that ``exec_module``
    seeded into *module_dict* but THIS module's own vocabulary does not
    vouch for.

    The seed copies the WHOLE process-wide ``predicate_builtins`` pool into
    every module namespace.  The strict-atom checks already distrust a
    seeded entry for a bare atom or a dict key (the leaked-pool-atom shape,
    see ``_make_intern_atom``), but a name in CALL position -- ``cite(X)`` in
    a clause body or ``REF = cite(a)`` at module level -- is resolved by
    Python itself: once any earlier module had declared ``cite``, the
    undeclared use found the atom str (``'str' object is not callable``, or
    ``existence_error(procedure, cite/1)``) instead of raising NameError,
    and the sibling-export diagnostic was lost.  Order-dependent: the same
    file answered differently depending on what was loaded first.

    Kept: every name this module declares or imports
    (``_locally_declared_names``), and everything in a module that opts
    into auto-accepted atoms (the interactive loose item), whose bare atoms
    resolve through the pool by design.  Only an entry that is still
    exactly the seeded pool atom is removed."""
    from clausal.logic.compiler_v2 import _locally_declared_names
    from clausal.pythonic_ast.nodes import ImplicitAtomsDeclaration

    if any(isinstance(it, ImplicitAtomsDeclaration) for it in module_items):
        return
    local = _locally_declared_names(module_items)
    for name, atom in list(predicate_builtins.items()):
        if name in local or name in runtime_builtins:
            continue
        if module_dict.get(name) is atom:
            del module_dict[name]


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
    own ``effective_strict = not implicit_mode`` rule.  Only the interactive
    profile's loose item disables strict mode and allows auto-accept, so a
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

    # Strict is the default; only the interactive loose item re-enables auto-accept.
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


#: The ``$`` names ``_run_v2_pipeline`` binds per module (beside
#: ``runtime_builtins``): together they are every engine name generated code
#: may reference (``clausal.seam_audit`` allows exactly these).
PER_MODULE_RUNTIME_NAMES = frozenset({
    "$module", "$define_predicate", "$assert_fact", "$check_constant_ground",
    "$check_currency_unit", "$decimal_value", "$constant_functor_term",
    "$register_module_constant", "$register_constant_units", "$intern_atom",
})


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
        For seam files: re-parse the seam source.
        For .pl files: re-translate .pl → seam, then parse.
    """
    from clausal.logic.compiler_v2 import (
        compile_module, mark_import_placeholder)

    predicate_nodes = []
    # MARKED: compile_module replaces exactly this object as ``$module``
    # before its first step (compiler_v2._install_real_module).
    dummy_logic_module = mark_import_placeholder(
        LogicModule(module.__name__, module_dict=module_dict))
    module_dict["$module"] = dummy_logic_module
    module_dict["$define_predicate"] = (
        lambda pred, lm: predicate_nodes.append(pred)
    )
    module_dict["$assert_fact"] = (
        lambda term: predicate_nodes.append(_fact_to_predicate_node(term))
    )
    module_dict["$check_constant_ground"] = check_constant_ground
    module_dict["$check_currency_unit"] = check_currency_unit
    module_dict["$decimal_value"] = decimal_value
    module_dict["$constant_functor_term"] = constant_functor_term
    module_dict["$register_module_constant"] = register_module_constant
    module_dict["$register_constant_units"] = register_constant_units
    code = loader.get_code(module.__name__)
    assert {"$module", "$define_predicate", "$assert_fact",
            "$check_constant_ground", "$check_currency_unit",
            "$decimal_value", "$constant_functor_term",
            "$register_module_constant", "$register_constant_units",
            } <= PER_MODULE_RUNTIME_NAMES

    # _last_transformer is set by source_to_code.  If the code came
    # from .pyc cache, source_to_code didn't run, so use the recovery fn.
    transformer = getattr(loader, '_last_transformer', None)
    if transformer is not None:
        module_items = transformer._module_items
    else:
        module_items = recover_module_items_fn(filename)

    if isinstance(loader, PrologLoader):
        # The .pl export list, for importers' private-procedure check
        # (clausal/pl_data_imports.py), read now so nobody re-lowers the
        # source later (a re-lowering resets the native loader's l3_stats).
        from clausal.pl_data_imports import record_pl_exports  # noqa: PLC0415
        record_pl_exports(module, module_items)
    module_dict["$intern_atom"] = _make_intern_atom(module_dict, module_items,
                                                    module.__name__)
    _unseed_foreign_pool_atoms(module_dict, module_items)

    _preseed_py_submodules(module_items)
    # A failed `-import_from` surfaces here as CPython's stock ImportError,
    # which names the file but not its vocabulary.  This is the raise site at
    # which the Clausal context is known, so enrich it here.
    # The body's ``$declare_head`` record (W4b-3 slice 5): started empty for
    # every run, and retired at compile_module's step 4a-bis -- or here, if
    # the load fails before it gets there.
    begin_loading_declarations(module_dict)
    try:
        exec_with_import_diagnostics(code, module_dict, module_items, filename)
        # The SOURCE clauses, before compile_module's term/goal expansion
        # rewrites them (the transition counter below reads these).
        source_nodes = list(predicate_nodes)

        logic_module = compile_module(
            predicate_nodes, module_items, module_dict, module.__name__,
        )
    finally:
        end_loading_declarations(module_dict)
    if isinstance(loader, PredicateLoader):
        _count_seam_transition_constructs(loader, source_nodes,
                                          logic_module.db, filename)
    # -constants directives register into $module.constants (see
    # register_module_constant, clausal/logic/constants.py) WHILE the
    # module body execs — i.e. onto dummy_logic_module, the placeholder.
    # compile_module swaps the real LogicModule in as $module and
    # __clausal_module__ BEFORE its first step, carrying those
    # registrations (compiler_v2._install_real_module: mid-compile a handle
    # to this module must not resolve to the placeholder's empty store).
    # These two writes are therefore no-ops on the normal path.
    module_dict["$module"] = logic_module
    module.__clausal_module__ = logic_module


def _count_seam_transition_constructs(loader, source_nodes, db, filename):
    """D13 on the seam: count the load's transition constructs (``not``,
    once/1, forall/2, memberchk/2, ``findall(_, G, [])``, make_quantity/3)
    into ``loader.l3_stats["transition_constructs"]`` -- the native ``.pl``
    loader's key and shape, so one consumer reads both -- and log the
    ``.pl`` front end's one line.  Counted from the clauses exec built, so a
    bytecode-cache hit counts the same as a fresh compile.  A ratchet's
    instrument, never a refusal."""
    from clausal.logic.compiler.terms_to_goalop import (  # noqa: PLC0415
        count_transition_constructs, log_transition_constructs)
    try:
        counts = count_transition_constructs(
            (getattr(p, "body", None) for p in source_nodes), db=db)
    except Exception as e:  # noqa: BLE001 -- a count never fails a load
        warnings.warn(f"{filename}: transition constructs not counted: "
                      f"{type(e).__name__}: {e}", RuntimeWarning,
                      stacklevel=2)
        return
    loader.l3_stats = {"transition_constructs": counts}
    log_transition_constructs(counts, filename)


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
#   rewrite emits ``$Predicate(head=…, body=…)`` calls, for example) or
#   at query-compile time (``INJECTED_RUNTIME_BUILTINS``, below).  NOT an
#   atom vocabulary — never consulted by the strictness check.
#
# ``predicate_builtins`` — the §1b/R2 GLOBAL ATOM pool ONLY.  Starts EMPTY
#   at process bootstrap; grows only via a legitimate atom declaration
#   (-module/-private, ``_process_declarations``), auto-accept
#   (the interactive loose item, ``_process_bare_atom_refs``/``$intern_atom``), or
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
# ``tests/fixtures/tagged_shapes.seam``).  A module that DOES want to
# declare that spelling as its own atom still gets it correctly:
# ``_process_declarations`` runs AFTER this seeding and unconditionally
# rebinds its own declared names, regardless of what seeding left there.
# 2026-09-09 ruling: generated code references each node class through its
# ``$`` twin (``$Predicate``, ``$Call``, ``$Add``, ...) so a user predicate
# spelled like one can never shadow it; the bare aliases stay bound for the
# deprecation window.  ONE table -- ``clausal/logic/generated_names.py``.
runtime_builtins = with_dollar_twins(
    {name: getattr(simple_ast, name) for name in simple_ast.__all__}
)

# '$'-prefixed names cannot be typed as normal Python identifiers, so user code
# cannot accidentally shadow them.  Do not remove the '$' prefix.
# Note: $define_predicate and $assert_fact are set per-module in exec_module
# (they need closures over the per-module LogicModule and module_dict).
#
# The runtime *value* bindings injected into every predicate module —
# ``$ast``, ``PredicateMeta``, ``Var``, ``DictTerm``, ``SetTerm``,
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
runtime_builtins.update(INJECTED_RUNTIME_BUILTINS)  # already twinned
runtime_builtins["$unterminated_fact_error"] = _unterminated_fact_error
# The builtins MODULE-LEVEL generated code reaches (``$globals()``,
# ``$__import__(...)``, ``except $ImportError``), ``$``-only for the reason
# ``generated_names.GENERATED_CODE_BUILTINS`` gives: a module's own atom
# ``globals`` must not become the registry plumbing's ``globals``.
from clausal.logic.generated_names import MODULE_CODE_BUILTINS  # noqa: E402
runtime_builtins.update(MODULE_CODE_BUILTINS)

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
    # kleene.seam`` (a bare ``Undefined`` reference), cascading into
    # ~163 unrelated test failures across files that transitively load it.
    "Undefined",
})

# The GLOBAL ATOM pool (§1b/R2) — see the module-level comment above.  Starts
# empty; ``compiler_v2._process_declarations``/``_process_bare_atom_refs`` and
# ``_make_intern_atom`` below are its only writers.
predicate_builtins: dict = {}


def _preseed_py_submodules(module_items) -> None:
    """Ensure ``sys.modules["py.X"]`` entries exist for any ``py.*`` imports.

    when a seam file uses ``-import_from(py.re, …)``, the generated
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
# reported mtime so a clausal upgrade invalidates every cached seam/Prolog
# .pyc. BUMP THIS whenever EmbedTransformer / the codegen output changes.
#
# 7 -> 8 (P3-2 Task 2, THE FLIP): the transformer's output changed three ways
# -- ``-tagged_terms`` is no longer a directive it accepts, ``-module``/
# ``-private`` accept ISO ``name/arity`` entries and mint a class for them
# (R6b), and a declared data functor's name binds its interned spelling
# instead of a generated class.  A stale pre-flip ``.pyc`` against the new
# runtime calls that spelling: ``TypeError: 'str' object is not callable``
# from inside generated code.
# 8 -> 9 (atoms-as-cells Stage B): atom Constants are ("bar",) cells; a stale
# .pyc binds foo = 'foo', a STRING.
# 9 -> 10 (Task 15 fix round 1, item 2): a source-written ``'[]'`` compiles to
# a list DISPLAY, not the Constant ("[]",) -- the nil atom IS the empty list
# (ISO; Scryer round-trips it).  A stale tag-9 .pyc still carries the cell,
# which compares unequal to the ``[]`` every runtime path now produces.
# 10 -> 11 (Task 15 fix round 4, item 4): a ``-constants`` dict key the
# compiler cannot decide statically is emitted wrapped in ``$dict_key(...)``,
# so a constant REFERENCE that evaluates to nil folds to the same key the
# literal spellings do.  A stale tag-10 .pyc carries the bare key expression
# and still raises the raw ``TypeError`` the fix removes.
# 11 -> 12 (Task 15 fix round 5, item 1): an ``in`` goal in KEY mode emitted a
# bare ``$deref(coll)`` and let the ``for`` loop use Python's own iteration;
# it emits ``$in_iter($deref(coll), False)`` now, so both modes fold a plain
# dict's nil keys and read a ``str`` as its char atoms.  A stale tag-11 .pyc
# still carries the bare iteration and still gives the pre-fix answers.
# 12 -> 13 (2026-09-11): FIFTY-FIVE transformer commits landed between the
# 11->12 bump (b4875ba9, 2026-09-07) and this one with no bump at all, and at
# least one of them demonstrably changes emitted code: 7a4d7407, where a seam
# no longer collects a name through a ``++`` escape or an f-string slot. A
# stale tag-12 .pyc still emits the walrus that made such a name local to the
# whole enclosing function, and still raises the UnboundLocalError that fix
# removes -- from a traceback pointing at the wrong line.
#
# The gap was found from the other end: a lane's re-measurement read stale
# bytecode, and the first diagnosis was "the cache ignores the engine". It
# does not -- this tag IS the engine version, and the defect was that nothing
# turns it. See todo/clausal-bytecode-tag-is-manual-and-goes-stale-2026-09-11.md
# for making it automatic, which is the real fix; this bump only closes the
# accumulated gap.
CLAUSAL_BYTECODE_TAG = 14

#: Engine sources whose CONTENT decides emitted code. Narrow on purpose: every
#: file here invalidates every user's cached bytecode when it changes, so a
#: module that only affects RUNTIME behaviour must not be listed -- a runtime
#: change that makes old bytecode wrong is what the manual tag above is for.
#:
#: THE RULE: every module whose content can change emitted code is listed,
#: including data tables the transformer reads at compile time and, for
#: ``.pl`` files, the translator ``PrologLoader.source_to_code`` runs before
#: compiling (D18(a), 2026-09-29). Widening costs only cache misses; missing
#: one lets two engines share a stale entry. Each entry outside the original
#: compiler roots is proven by a positive control in
#: tests/test_pycache.py::test_every_module_that_decides_bytecode_is_fingerprinted
#: -- add a row there when adding one here.
_COMPILATION_ROOTS = (
    "templating", "pythonic_ast", "logic/compiler",
    # the .pl tokenizer (tools/prolog_tokenizer.py) is generated from a spec
    # by this package
    "tools/toklex",
)
_COMPILATION_FILES = (
    "logic/compiler_v2.py",
    # Tables the transformer reads at compile time:
    "logic/exact_arith.py",          # EVALUABLE (_mark_arith_position_names)
    "modules/units.py",              # _DEPRECATED_UNIT_NAMES (-import_from)
    "modules/countries/_data.py",    # JURISDICTIONS (_resolve_import_path)
    "logic/generated_names.py",      # dollar_name: $-twin spelling of names
    "terms.py",                      # quote_atom/quote_string (.pl translator)
    # The .pl translator, whose output is what gets compiled and cached:
    "tools/prolog_to_clausal.py",
    "tools/prolog_parser.py",
    "tools/prolog_tokenizer.py",
    "tools/prolog_operators.py",
    "tools/prolog_dialect.py",
    "tools/prolog_ast.py",
    "tools/toklex/specs/iso.toklex.pl",  # the spec load_lexer() compiles
)

_FINGERPRINT_CACHE: "int | None" = None


def _compilation_fingerprint() -> int:
    """A digest of the engine sources that decide emitted code.

    Computed LAZILY and memoised: it is only needed when a seam or Prolog
    file is actually compiled, so a process that imports ``clausal``
    without loading Clausal source pays nothing, and one that loads a thousand
    pays once.

    Hashes CONTENT, not mtimes. An mtime walk is ~15x cheaper, but ``git
    checkout`` rewrites mtimes without changing content, so it would discard
    every user's cache on any branch switch -- frequent, and invisible enough
    that the cost would be blamed on something else.

    Returns 0 if the sources cannot be read, which leaves ``CLAUSAL_BYTECODE_
    TAG`` alone in charge. Degrading to the manual tag is the safe direction:
    it is what the behaviour was before this existed.
    """
    global _FINGERPRINT_CACHE
    if _FINGERPRINT_CACHE is not None:
        return _FINGERPRINT_CACHE
    package = os.path.dirname(os.path.abspath(__file__))
    paths = []
    try:
        for rel in _COMPILATION_ROOTS:
            root = os.path.join(package, *rel.split("/"))
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                paths += [os.path.join(dirpath, f)
                          for f in filenames if f.endswith(".py")]
        paths += [os.path.join(package, *rel.split("/"))
                  for rel in _COMPILATION_FILES]
        digest = hashlib.blake2b(digest_size=4)
        for path in sorted(paths):
            # The path goes in RELATIVE to the package, so moving or
            # reinstalling the engine does not by itself change the answer.
            digest.update(os.path.relpath(path, package).encode("utf-8"))
            with open(path, "rb") as handle:
                digest.update(handle.read())
        _FINGERPRINT_CACHE = int.from_bytes(digest.digest(), "big")
    except OSError:
        _FINGERPRINT_CACHE = 0
    return _FINGERPRINT_CACHE


def _effective_bytecode_tag() -> int:
    """The tag cached bytecode is actually validated against.

    The hand-maintained tag XOR the automatic fingerprint, so a manual bump
    still forces invalidation on its own -- which a content fingerprint cannot
    do for a RUNTIME change that leaves the compiler untouched.
    """
    return CLAUSAL_BYTECODE_TAG ^ _compilation_fingerprint()


# ── The .pl front end (plan native-iso-reader-step2, D3(a)) ─────────────────
#
# ``CLAUSAL_PL_FRONTEND=native|translator`` selects how a ``.pl`` file becomes
# code: ``translator`` (the default until slice 8) is ``prolog_to_clausal`` ->
# seam text -> EmbedTransformer; ``native`` is the ISO reader -> ``iso_l3``,
# which lowers clauses straight to the transformed AST.  The two write the
# SAME ``__pycache__`` file name, so the front end is part of the cache key
# (R2): the native loader XORs a NONZERO salt into the key the translator
# uses unchanged -- a cache written with the variable unset stays valid, and
# no entry one front end wrote can ever validate for the other.

#: The environment variable that selects the ``.pl`` front end.
PL_FRONTEND_ENV = "CLAUSAL_PL_FRONTEND"
_PL_FRONTENDS = ("translator", "native")

#: Engine sources only the NATIVE front end compiles with (the rest -- the
#: toklex lexer, the Pratt parser, the operator tables -- are in the shared
#: fingerprint already).  Hashed into the native salt, so an edit to one
#: invalidates native bytecode and leaves the translator's cache alone.
_NATIVE_FRONTEND_FILES = (
    "tools/iso_l3.py",
    "tools/iso_l3_directives.py",
    "tools/prolog_reader.py",
)

_NATIVE_SALT_CACHE: "int | None" = None


def pl_frontend() -> str:
    """The ``.pl`` front end ``CLAUSAL_PL_FRONTEND`` selects, read at each
    lookup.  Unset or empty is ``translator``; an unknown value is an
    ``ImportError``, never a silent default (a typo would otherwise run the
    front end its author did not ask for).

    In the sandbox (:mod:`clausal.sandbox`) it is always ``native``
    (operator ruling S1): the translator lowers float evaluables to
    Python's ``math``, which the sandbox's audit refuses."""
    if _sandbox_state.ACTIVE:
        return "native"
    value = os.environ.get(PL_FRONTEND_ENV, "").strip()
    if not value:
        return "translator"
    if value not in _PL_FRONTENDS:
        raise ImportError(
            f"{PL_FRONTEND_ENV}={value!r} is not a .pl front end; use one of "
            f"{', '.join(_PL_FRONTENDS)} (unset means translator)")
    return value


_SUFFIX_SALTS: dict = {}


def _suffix_salt(path) -> int:
    """The source's part of the bytecode cache key, keyed on its SURFACE
    (:func:`clausal.end_module.surface_of`) and its suffix.

    0 only for SEAM source spelled ``.clausal`` (the key caches written
    before the extension flip used); any other seam or ``.pl`` suffix is a
    NONZERO digest of the suffix alone (unchanged, so their caches stay
    valid); a
    Clausal Prolog file is a NONZERO digest of the surface AND the suffix.
    So two same-stem sources in one directory never share a key, and since
    the extension flip moved ``.clausal`` to the Clausal Prolog surface, a
    seam ``.pyc`` written under 0 is never served for a Prolog file."""
    suffix = os.path.splitext(os.fspath(path))[1]
    surface = surface_of(path)
    key = (surface, suffix)
    salt = _SUFFIX_SALTS.get(key)
    if salt is None:
        if surface == SURFACE_SEAM and suffix == ".clausal":
            salt = 0
        else:
            if surface == SURFACE_CLAUSAL_PROLOG:
                tag = b"clausal-source-surface:" + surface.encode("utf-8") + b":"
            else:
                tag = b"clausal-source-suffix:"
            digest = hashlib.blake2b(tag + suffix.encode("utf-8"),
                                     digest_size=4)
            salt = int.from_bytes(digest.digest(), "big") or 1
        _SUFFIX_SALTS[key] = salt
    return salt


def _native_frontend_salt() -> int:
    """The native front end's part of the cache key: a digest of its id and
    of :data:`_NATIVE_FRONTEND_FILES`, NONZERO in the low 32 bits that
    importlib keeps (a zero there would share the translator's key)."""
    global _NATIVE_SALT_CACHE
    if _NATIVE_SALT_CACHE is not None:
        return _NATIVE_SALT_CACHE
    package = os.path.dirname(os.path.abspath(__file__))
    digest = hashlib.blake2b(b"clausal-pl-frontend:native", digest_size=4)
    for rel in _NATIVE_FRONTEND_FILES:
        digest.update(rel.encode("utf-8"))
        try:
            with open(os.path.join(package, *rel.split("/")), "rb") as handle:
                digest.update(handle.read())
        except OSError:
            pass
    salt = int.from_bytes(digest.digest(), "big") & 0xFFFFFFFF
    _NATIVE_SALT_CACHE = salt or 1
    return _NATIVE_SALT_CACHE


# ── One source file → one compilation ────────────────────────────────────────
#
# Maps a resolved source path to the dotted name it was first imported under.
# A source file is reachable under more than one dotted name whenever both a
# package directory and its parent sit on sys.path (``pkg/soledom.seam`` is
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


from clausal import _sandbox_state  # noqa: E402 -- dependency-free


class _ClausalSourceLoader(SourceLoader):
    """Common file I/O for the seam and Prolog loaders.

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

    def get_code(self, fullname):
        # The sandbox (clausal.sandbox): a module of the user's is compiled
        # from its source, read once, and its final generated tree audited
        # before it runs -- never from the bytecode cache.
        if _sandbox_state.ACTIVE:
            from clausal.sandbox import sandboxed_code  # noqa: PLC0415
            code = sandboxed_code(self, fullname)
            if code is not None:
                return code
        return super().get_code(fullname)

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
        # The source SUFFIX is part of the key too: a same-directory
        # ``twin.pl`` and ``twin.seam`` share ``__pycache__/twin.*.pyc``,
        # and with equal size and mtime_ns each would be served the other's
        # bytecode.
        return {"mtime": (st.st_mtime_ns ^ _effective_bytecode_tag()
                          ^ _suffix_salt(path)) & 0xFFFFFFFF,
                "size": st.st_size}

    def set_data(self, path, data):
        """Write a ``.pyc`` ATOMICALLY; create ``__pycache__/`` if needed.

        Several engines may share one ``__pycache__`` (parallel lanes over a
        shared downstream tree), so the bytes go to a uniquely named temp
        file in the SAME directory and ``os.replace`` swaps it in: a reader
        sees the old file or the complete new one, never a torn one. This
        mirrors CPython's ``importlib._bootstrap_external._write_atomic``.
        The temp file is removed on any failure, and a failure is swallowed:
        the cache is an optimisation, never a reason to fail an import.
        """
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            return
        # pid + random: unique across the processes sharing the directory
        # and across threads of one process; O_EXCL refuses any collision.
        path_tmp = f"{path}.{os.getpid()}.{os.urandom(4).hex()}.tmp"
        try:
            fd = os.open(path_tmp, os.O_EXCL | os.O_CREAT | os.O_WRONLY, 0o666)
        except OSError:
            return
        try:
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
            finally:
                os.close(fd)
            os.replace(path_tmp, path)
        except BaseException as exc:
            # ANY failure (an interrupt too) removes the temp file; only an
            # OSError is swallowed.
            try:
                os.unlink(path_tmp)
            except OSError:
                pass
            if not isinstance(exc, OSError):
                raise


def transform_seam_source(source, filename, prolog_singletons=False):
    """Parse + EmbedTransformer a seam source string, executing nothing.

    Returns ``(tree, transformer)``: *tree* is the FINAL generated Python
    module the import hook compiles to bytecode (``clausal.seam_audit``
    audits exactly this tree), the transformer carries ``_module_items``.
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
            source_lines=source_lines, filename=filename,
            prolog_singletons=prolog_singletons)
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)
        return tree, transformer


def _parse_clausal_source(source, filename, prolog_singletons=False):
    """Parse + EmbedTransformer a seam source string.

    Returns ``(code_object, transformer)`` — the transformer carries
    ``_module_items`` needed by the V2 pipeline.  *prolog_singletons* is the
    ``.pl`` path's (D19): a ``_Name`` variable is no singleton there.
    """
    tree, transformer = transform_seam_source(source, filename,
                                              prolog_singletons)
    with warnings.catch_warnings(), \
            clausal_syntax_diagnostics(source, filename):
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        code = compile(tree, filename=filename, mode="exec")
    return code, transformer


def _extract_module_items(source, filename, prolog_singletons=False):
    """Re-parse seam source text just to recover module_items (cache-hit path)."""
    with warnings.catch_warnings(), \
            clausal_syntax_diagnostics(source, filename):
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=filename)
        source_lines = source.splitlines(keepends=True)
        transformer = EmbedTransformer(
            source_lines=source_lines, filename=filename,
            prolog_singletons=prolog_singletons)
        transformer.visit(tree)
        return transformer._module_items


class PredicateLoader(_ClausalSourceLoader):
    """SourceLoader for seam predicate modules.

    ``source_to_code`` performs the EmbedTransformer rewrite; the resulting
    bytecode is cached in ``__pycache__/`` so subsequent imports skip parsing
    and AST transformation.
    """

    #: The seam's load facts, the native ``.pl`` loader's attribute: here
    #: ONE key, ``"transition_constructs"`` (D13), filled on every load.
    l3_stats: "dict | None" = None

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
        """Cache-hit path: re-parse seam source to recover module_items."""
        source = self.get_data(path).decode("utf-8")
        return _extract_module_items(source, path)


def _prolog_default_items() -> list:
    """The module items every imported ``.pl`` module starts with, AHEAD of
    its own: ``assert_creates_dynamic`` is ``true``, so imported ISO code
    gets ISO's assert -- asserting into a procedure that does not exist
    creates it as dynamic (ISO 7.5.2(2)).  A
    ``:- set_prolog_flag(assert_creates_dynamic, false).`` in the file comes
    later and wins.  An item rather than translated text, so the translation
    itself (and every snapshot of it) is unchanged."""
    from clausal.pythonic_ast.nodes import Directive  # noqa: PLC0415
    return [Directive(name="set_prolog_flag",
                      specs=[("assert_creates_dynamic", "true")])]


class PrologLoader(_ClausalSourceLoader):
    """SourceLoader for .pl Prolog modules — translates to the seam on-the-fly.

    Pipeline: .pl source → prolog_to_clausal() → seam text →
              ast.parse → EmbedTransformer → bytecode (cached as .pyc)

    The module's items start with :func:`_prolog_default_items` (the
    ``assert_creates_dynamic`` flag on).

    All Prolog-specific imports are lazy (inside methods) so loading this
    module doesn't pull in the translator unless a .pl file is actually used.
    """

    def __init__(self, fullname, path, dialect=None):
        super().__init__(fullname, path)
        self._dialect = dialect

    def _translate(self, pl_source):
        """Translate .pl source text to seam source text."""
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        from clausal.tools.prolog_dialect import Dialect
        dialect = self._dialect or Dialect.scryer_reader()
        # The file's path and dotted name resolve a relative use_module
        # path against the file's own directory, as Scryer does.
        return prolog_to_clausal(pl_source, dialect=dialect,
                                 source_path=self._path,
                                 module_name=self._fullname)

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

        code, transformer = _parse_clausal_source(clausal_source, path,
                                                  prolog_singletons=True)
        transformer._module_items[:0] = _prolog_default_items()
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
        # Operator ruling 2026-10-01: an unbound atom-shaped data name read
        # as an attribute is its atom (clausal/pl_data_imports.py).
        from clausal.pl_data_imports import install_attribute_fallback  # noqa: PLC0415
        install_attribute_fallback(module)

    def _recover_module_items(self, path):
        """Cache-hit path: re-translate .pl source, then parse for module_items.
        A refusal is the ``SyntaxError`` :meth:`source_to_code` raises (a
        load-time check such as a required end_module/1 runs here too)."""
        from clausal.tools.prolog_to_clausal import PrologTranslationError
        from clausal.tools.prolog_parser import ParseError
        pl_source = self.get_data(path).decode("utf-8")
        try:
            clausal_source = self._translate(pl_source)
        except (ParseError, PrologTranslationError) as e:
            raise SyntaxError(f"Cannot import {path}: {e}",
                              (path, 0, 0, "")) from e
        return _prolog_default_items() + _extract_module_items(
            clausal_source, path, prolog_singletons=True)


class _NativeItems:
    """What ``_run_v2_pipeline`` reads off ``_last_transformer``: the module
    items.  The native front end has no transformer to hand over."""

    def __init__(self, module_items):
        self._module_items = module_items


class NativePrologLoader(PrologLoader):
    """SourceLoader for ``.pl`` files through the NATIVE front end
    (``CLAUSAL_PL_FRONTEND=native``; plan native-iso-reader-step2).

    Pipeline: .pl source -> ``PrologReader`` (Scryer's operator table, D2(b))
              -> ``iso_l3`` lowering -> transformed ``ast.Module`` -> bytecode

    Everything from ``exec`` on is the translator's path unchanged
    (``_run_v2_pipeline``): the join is the pair (transformed AST, module
    items).  A refusal -- a construct outside the slices landed so far, a
    reader syntax error, and by design ``!``/``->``/``*->`` -- is a
    ``SyntaxError`` naming the ``.pl`` line; the module does not import.

    ``l3_stats`` holds the last lowering's read/lowered/refused counts (on a
    cache hit too: the recovery path re-lowers), so a caller can see WHICH
    front end ran and over how many items.
    """

    frontend = "native"
    l3_stats: "dict | None" = None

    def path_stats(self, path):
        stats = super().path_stats(path)
        stats["mtime"] = (stats["mtime"] ^ _native_frontend_salt()) & 0xFFFFFFFF
        return stats

    def _op_table(self):
        if self._dialect is not None:
            import copy  # noqa: PLC0415
            # A copy: the reader's op/3 must not mutate the caller's dialect.
            return copy.deepcopy(self._dialect.operator_table)
        return None   # iso_l3's own default: a fresh Scryer table

    def _lower(self, pl_source, path, directives_only=False):
        """Lower *pl_source*; -> (ast.Module, module_items).  Records
        ``l3_stats``; raises ``SyntaxError`` at the refused ``.pl`` line.
        The module items are the seam directive handlers' (slice 2), after
        :func:`_prolog_default_items`.  *directives_only* is the cache-hit
        path: it needs the module items, not the clauses."""
        from clausal.tools import iso_l3  # noqa: PLC0415
        try:
            # The refusal names ``file.pl:N``; the SyntaxError carries the
            # full path.
            low = iso_l3.lower_source(
                pl_source, os.path.basename(path), op_table=self._op_table(),
                directives_only=directives_only, source_path=path,
                module_name=self._fullname)
        except iso_l3.LoweringRefused as e:
            line = iso_l3.line_of(pl_source, e.span) or 0
            # Split on "\n" only: _Positions numbers lines that way, and
            # splitlines() also breaks on \f, \x85, \u2028 ...
            lines = pl_source.split("\n")
            text = lines[line - 1] if 0 < line <= len(lines) else ""
            raise SyntaxError(f"Cannot import {path}: {e}",
                              (path, line, 1, text)) from e
        self.l3_stats = low.stats
        # The bytecode baked in other files' content (a use_module/1 export
        # list, a declared module name): the cache key covers this file
        # only, so such a module is not cached (it is re-lowered each load).
        self._uncacheable = bool(low.context.depends_on)
        iso_l3.warn_singletons(low.singletons, pl_source, path)
        low.context.warn_bare_atom_imports()
        iso_l3.log_auto_declared(low.context, path)
        iso_l3.log_transition_constructs(low.stats, path)
        return low.tree, _prolog_default_items() + low.module_items

    def source_to_code(self, data, path="<string>"):
        try:
            pl_source = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SyntaxError(
                f"Cannot import {path}: {e} (all .pl files must be UTF-8)",
                (path, 0, 0, ""),
            ) from e
        tree, module_items = self._lower(pl_source, path)
        self._last_transformer = _NativeItems(module_items)
        return compile(tree, path, "exec")

    def _cache_bytecode(self, source_path, bytecode_path, data):
        if getattr(self, "_uncacheable", False):
            return None
        return super()._cache_bytecode(source_path, bytecode_path, data)

    def _recover_module_items(self, path):
        """Cache-hit path: re-read the ``.pl`` source and re-lower its
        directives (the module items come from them alone)."""
        pl_source = self.get_data(path).decode("utf-8")
        return self._lower(pl_source, path, directives_only=True)[1]


def _pl_loader_class():
    """The ``.pl`` loader class ``CLAUSAL_PL_FRONTEND`` selects."""
    return NativePrologLoader if pl_frontend() == "native" else PrologLoader


def _prolog_loader_class_for(path):
    """The loader class for the Prolog-syntax file *path*: always the NATIVE
    front end for a Clausal Prolog file (the translator is end-of-life for
    that surface, so ``CLAUSAL_PL_FRONTEND`` is not consulted), else the
    ``.pl`` loader ``CLAUSAL_PL_FRONTEND`` selects."""
    if surface_of(path) == SURFACE_CLAUSAL_PROLOG:
        return NativePrologLoader
    return _pl_loader_class()


def _new_prolog_loader(fullname, path, dialect=None):
    """A loader for the Prolog-syntax file *path* (the finders' factory: the
    class depends on the file's surface)."""
    return _prolog_loader_class_for(path)(fullname, path, dialect=dialect)


# Backward-compat alias — prefer _load_module() for new code.
_predicate_loader = None


def _load_module(fullname, path):
    """Load a source file (seam or Prolog) as a Python module and return it.

    This is the recommended helper for tests and external callers.
    Each call creates a fresh loader and module instance: a PredicateLoader,
    or -- for a ``.pl`` path -- the loader :func:`_load_prolog_module` uses
    (the front end ``CLAUSAL_PL_FRONTEND`` selects), so a Prolog file is
    never parsed as Clausal source.  *path* may be any path-like (a
    ``pathlib.Path``): importlib's cache-hit path needs a ``str``.
    """
    path = os.fspath(path)
    if _sfx.is_prolog_source(path):
        return _load_prolog_module(fullname, path)
    sys.modules.pop(fullname, None)
    loader = PredicateLoader(fullname, path)
    spec = ModuleSpec(fullname, loader, origin=path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = mod
    loader.exec_module(mod)
    return mod


def _load_prolog_module(fullname, path, dialect=None):
    """Load a .pl file as a Clausal module and return it.

    Test/external helper. Each call creates a fresh loader and module, of the
    front end ``CLAUSAL_PL_FRONTEND`` selects (the translator when unset) --
    or, for a Clausal Prolog file, always the native one.
    *path* may be any path-like.
    """
    path = os.fspath(path)
    sys.modules.pop(fullname, None)
    loader = _new_prolog_loader(fullname, path, dialect=dialect)
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
    """Base finder that searches sys.path for files with given extensions.

    Resolution is per ``sys.path`` entry, in path order — Python's own
    contract.  Each entry is asked for every suffix *group* the finder claims
    (:meth:`_suffix_groups`, in priority order) before the next entry is
    looked at, so a source module in an earlier entry always beats one in a
    later entry whatever its suffix; the suffix priority only decides between
    files in the *same* entry.  Within one entry, for each group in turn: a
    flat ``tail<suffix>`` file (first suffix of the group that exists) wins,
    then a ``tail/__init__<suffix>`` package; only then is the next group
    tried.

    ``_extensions`` lists the suffixes of the finder's single default group,
    in priority order; ``_extension`` is the single-suffix spelling older
    subclasses use, honoured when ``_extensions`` is left empty.
    """
    _extension: str = ""
    _extensions: tuple[str, ...] = ()
    _loader_cls: type = None

    def _suffixes(self) -> tuple[str, ...]:
        return self._extensions or (self._extension,)

    def _suffix_groups(self):
        """``((suffixes, get_loader_cls), ...)`` in priority order within one
        ``sys.path`` entry.  ``get_loader_cls`` is called only once a file is
        found, so a loader choice that can fail (an invalid
        ``CLAUSAL_PL_FRONTEND``) never breaks an unrelated import."""
        return ((self._suffixes(), lambda: self._loader_cls),)

    def _spec_for(self, fullname, source_path, pkg_dir=None,
                  get_loader_cls=None):
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
            # The loader class is resolved only here, not on the alias path.
            loader_cls = (get_loader_cls() if get_loader_cls is not None
                          else self._loader_cls)
            loader = loader_cls(fullname, source_path)
            loader._canonical_path = key
        spec = ModuleSpec(fullname, loader, origin=source_path)
        if pkg_dir is not None:
            spec.submodule_search_locations = [pkg_dir]
        return spec

    @staticmethod
    def _first_file(candidates):
        return next((c for c in candidates if os.path.isfile(c)), None)

    def _find_in_entry(self, dir_entry, tail, groups):
        """The first source for ``tail`` in one ``sys.path`` entry, as
        ``(path, pkg_dir or None, get_loader_cls)``, or None."""
        pkg_dir = os.path.join(dir_entry, tail)
        pkg_dir_exists = None  # stat the directory at most once per entry
        for suffixes, get_loader_cls in groups:
            # Flat-file form: ``dir_entry/tail.seam`` → module ``tail``.
            # The group's first suffix with a file behind it wins (the Prolog
            # group lists ``.clausal`` before ``.pl``).  A flat file takes
            # priority over a same-named package directory of its own group.
            flat = self._first_file(
                os.path.join(dir_entry, tail + s) for s in suffixes)
            if flat is not None:
                return flat, None, get_loader_cls
            # Package form: ``dir_entry/tail/__init__.seam`` → package
            # ``tail``.  Reuses Python's __init__ package mechanism so
            # submodule files (``tail/sub.seam``) then resolve as
            # ``fullname.sub``.  A bare directory *without* an __init__ is left
            # to PathFinder as a PEP-420 namespace package (return nothing
            # here), so this must not fire.
            if pkg_dir_exists is None:
                pkg_dir_exists = os.path.isdir(pkg_dir)
            if pkg_dir_exists:
                init = self._first_file(
                    os.path.join(pkg_dir, "__init__" + s) for s in suffixes)
                if init is not None:
                    return init, pkg_dir, get_loader_cls
        return None

    def find_spec(self, fullname, path, target=None):
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        groups = self._suffix_groups()
        for dir_entry in search_dirs:
            if not isinstance(dir_entry, str):
                # As CPython's PathFinder: a non-str entry (None, bytes, an
                # int, a Path) is skipped, not a TypeError out of import.
                continue
            found = self._find_in_entry(dir_entry, tail, groups)
            if found is None:
                continue
            source, pkg_dir, get_loader_cls = found

            # A10-F010 / A10-D002(a): a seam or Prolog file (or package dir) named
            # after a standard-library module is almost always an accident.
            # These finders run before PathFinder, so shadowing would be silent —
            # defer to the stdlib (return None) and warn loudly instead.
            # Only a TOP-LEVEL name can shadow: a submodule ``pkg.datetime``
            # is reached by its dotted path and never stands in for the
            # stdlib's ``datetime`` (the ``clausal.library`` facades are named
            # after the Python libraries they wrap, on purpose).
            if "." not in fullname and tail in sys.stdlib_module_names:
                from clausal.templating.term_rewriting import (
                    ClausalLintWarning,
                )
                warnings.warn(
                    f"{source!r} is named after the standard-library "
                    f"module {tail!r}; the stdlib module is used instead. "
                    f"Rename the file to avoid shadowing it.",
                    ClausalLintWarning,
                    stacklevel=2,
                )
                return None

            # A non-None search-locations list is what marks the module a
            # *package*: importlib sets ``__path__`` from it, so a later
            # find_spec(fullname + ".sub", path=[pkg_dir]) resolves submodules.
            return self._spec_for(fullname, source, pkg_dir=pkg_dir,
                                  get_loader_cls=get_loader_cls)
        return None


class PredicateFinder(_ExtensionFinder):
    """Find predicate-module source on sys.path: SEAM source (the
    ``CLAUSAL_SUFFIXES``) via PredicateLoader, then Prolog source
    (``_suffixes.prolog_suffixes()``: ``.pl`` through the loader
    ``CLAUSAL_PL_FRONTEND`` selects, a Clausal Prolog file through the
    native one).

    This is the one source finder on ``sys.meta_path``: a single scan walks
    the path entries in order and asks each for the seam group, then the
    Prolog group, so an earlier entry's Prolog module beats a later entry's
    seam one, and a seam file beats a Prolog file (``name.seam`` beats
    ``name.pl``) only within the same entry -- before and after the
    extension flip alike.  ``_extensions`` stays the seam group alone.
    """
    # Informational snapshot (import time); lookups read _suffixes() below.
    _extensions = CLAUSAL_SUFFIXES
    _loader_cls = PredicateLoader

    def _suffixes(self):
        # Read through the module, at each lookup: the extension flip edits
        # the tuples (and a test simulates it by patching them).
        return _sfx.CLAUSAL_SUFFIXES

    def _suffix_groups(self):
        return ((self._suffixes(), lambda: self._loader_cls),
                (_sfx.prolog_suffixes(), lambda: _new_prolog_loader))


class PrologFinder(_ExtensionFinder):
    """Find Prolog-syntax files only -- ``.pl`` via the
    ``CLAUSAL_PL_FRONTEND`` loader, and a Clausal Prolog file via the
    native one.

    Not installed on ``sys.meta_path``: :class:`PredicateFinder` covers .pl
    in the same per-entry scan (a separate finder scanning the whole path
    after it would let a later entry's .seam beat an earlier entry's .pl).
    Kept for callers that want a .pl-only finder.
    """
    # Informational snapshot (import time); lookups read _suffixes() below.
    _extensions = _sfx.prolog_suffixes()

    def _suffixes(self):
        return _sfx.prolog_suffixes()

    @property
    def _loader_cls(self):
        # A factory choosing the class per file: the front end is
        # CLAUSAL_PL_FRONTEND's at import, or native for Clausal Prolog.
        return _new_prolog_loader


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

# One source finder: .clausal/.seam and .pl are resolved in a single per-entry
# walk of sys.path (see PredicateFinder); PrologFinder is not installed.
sys.meta_path[:] = [PredicateFinder(), ModulesFinder(), *sys.meta_path]


# ── IPython integration ───────────────────────────────────────────────────────

# Task 8 split: IPython was already independent of the growing atom pool
# (this dict is a one-shot snapshot at import time, never re-read), so it
# copies ``runtime_builtins`` directly rather than recomputing the same
# simple_ast.__all__ + INJECTED_RUNTIME_BUILTINS merge a second time.
# Inject the runtime types so that functor class code (which calls Var()) and
# compiled goals work in IPython cells: $ast, PredicateMeta, Var/
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
_simple_ast_builtins["$check_currency_unit"] = check_currency_unit
_simple_ast_builtins["$decimal_value"] = decimal_value
_simple_ast_builtins["$constant_functor_term"] = constant_functor_term
_simple_ast_builtins["$register_module_constant"] = register_module_constant
_simple_ast_builtins["$register_constant_units"] = register_constant_units

from clausal.repl import Solutions as _Solutions, _run_ipython_goal as _run_ipython_goal
_simple_ast_builtins["Solutions"] = _Solutions
_simple_ast_builtins["_run_ipython_goal"] = _run_ipython_goal


_STAR_QUERY_SENTINEL = "_clausal_star_query_"

# The text of the cell IPython is about to parse, recorded by
# ``_star_query_input_transformer`` and consumed by ``_FreshEmbedTransformer``.
# IPython hands an AST transformer only a tree, but the quote map (spec §7)
# has to be built from the token stream — this is the one place the two paths
# can meet.  ``None`` between cells; a consumer clears it after reading.
_LAST_CELL_LINES: list[str] | None = None


def _star_query_input_transformer(lines: list[str]) -> list[str]:
    """IPython input transformer: rewrite ``*(...)`` to a valid Python call.

    Runs at the source-text level, *before* ``codeop.Compile`` checks syntax.
    On Python ≥ 3.14 (and some IPython versions), ``*(expr)`` raises a
    ``TypeError`` during the completeness check — before AST transformers get a
    chance to intercept the ``Starred`` node.  By rewriting the text to
    ``_clausal_star_query_(...)``, the source becomes a normal function call
    that survives parsing and compilation.  ``_StarQueryTransformer`` then
    detects the sentinel call at the AST level.

    It also records the lines it returns in ``_LAST_CELL_LINES``.  Being the
    LAST ``input_transformers_post`` entry Clausal registers, what it returns
    is (barring another extension appending after it) exactly the text
    ``ast.parse`` sees, so the columns line up with the tree
    ``_FreshEmbedTransformer`` is then handed.  If they ever do not, the map
    misses and every literal is read as an ATOM whatever its quotes — so a
    ``"…"`` string, a char list by default, silently becomes an atom.  That
    is a wrong answer, not a refusal.
    """
    global _LAST_CELL_LINES
    out = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("*("):
            indent = line[: len(line) - len(stripped)]
            out.append(indent + _STAR_QUERY_SENTINEL + stripped[1:])
        else:
            out.append(line)
    _LAST_CELL_LINES = list(out)
    return out


class _StarQueryTransformer(ast.NodeTransformer):
    """Rewrite ``*(goal_expr)`` expression statements to Solutions calls.

    Inside ``*(…)`` the expression is treated as a clause body goal.
    ``TermTransformer`` handles variable allocation (via walrus operators) and
    all operator rewriting (``is`` → ``Unify``, ``and`` → ``And``, etc.).

    ``*(Goal(X))``
        → ``Solutions(_run_ipython_goal(Goal((X:=Var())), {'X': X}, globals()))``

    ``*(A(X), B(X, Y))``
        → ``Solutions(_run_ipython_goal($And(left=A((X:=$Var())), right=B(X, (Y:=$Var()))), {'X': X, 'Y': Y}, globals()))``

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
            # The conjuncts are several outermost roots sharing ONE variable
            # scope, so note them all before visiting any.  ``visit``'s
            # auto-note fires per root and accumulates, which made a thunk in
            # conjunct 1 decided before conjunct 2's names were known:
            # ``*(bar(f"{Node}"), tree(Node))`` captured nothing and formatted
            # the module-namespace class, while the same query written the
            # other way round captured ``Node`` and formatted the binding.
            tt.note_clause_scope(*inner.elts)
            elts = [tt.visit(e) for e in inner.elts]
            goal_ast = elts[0]
            for elt in elts[1:]:
                goal_ast = ast.fix_missing_locations(ast.copy_location(
                    ast.Call(
                        func=ast.Name(id='$And', ctx=ast.Load()),
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
                    ast.Call(func=ast.Name(id='$globals', ctx=ast.Load()),
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

    *source_lines* is the cell's text, ``splitlines(keepends=True)``.  It is
    what ``EmbedTransformer`` tokenizes to recover each string literal's
    QUOTE CHARACTER (spec §7): ``ast`` erases it, so without the lines the
    quote map is empty, every ``"…"`` looks like ``'…'``, and the
    ``chars`` reading of ``"…"`` (the default) is silently lost — a cell
    would disagree with a file that says the same thing.  The two ``python_repl`` call
    sites pass it directly; under IPython the AST transformer is handed only
    a tree, so the lines come from ``_star_query_input_transformer``, the
    last input transformer to touch the text before it is parsed.
    """

    def __init__(self, source_lines=None):
        self._source_lines = source_lines

    def visit(self, tree):
        global _LAST_CELL_LINES
        source_lines = self._source_lines
        if source_lines is None:
            # The IPython path: consume the lines the input transformer
            # recorded for THIS cell, and clear them, so a later tree built
            # programmatically is never read against a stale cell's columns.
            source_lines, _LAST_CELL_LINES = _LAST_CELL_LINES, None
        try:
            tree = EmbedTransformer(source_lines=source_lines,
                                    implicit_atoms_default=True,
                                    interactive=True).visit(tree)
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
