"""Module export filtering + discontiguous emission (Tasks 4-5).

Scryer raises permission_error(...module_does_not_contain_claimed_export...)
when a :- module export has no clauses backing it (signature-only kernels,
term constructors like cite/1, 0-arity atoms) — Task 4 filters those dead
exports out.

Scryer also silently OVERWRITES a clause run that gets interrupted by
another predicate's clauses unless a :- discontiguous directive names it —
Task 5 emits that directive automatically.
"""

import pytest

from clausal.tools.clausal_to_prolog import (
    UntranslatableConstructError,
    clausal_source_to_prolog,
    clausal_source_to_prolog_ast,
    module_export_signature,
)

KERNEL_SRC = """-module(kernel, [ai_act_verdict(S, L, E, C), met, unmet])
"""

MIXED_SRC = """-module(citations, [cite(C), citation(A, M), some_atom])
citation(a1, meta1),
citation(a2, meta2),
"""


def test_signature_only_module_exports_nothing():
    out = clausal_source_to_prolog(KERNEL_SRC, strict=True)
    assert ":- module(kernel, [])." in out


def test_declaration_only_names_dropped_from_exports():
    out = clausal_source_to_prolog(MIXED_SRC, strict=True)
    assert ":- module(citations, [citation/2])." in out


def test_module_export_signature_helper():
    pmod = clausal_source_to_prolog_ast(MIXED_SRC)
    assert module_export_signature(pmod) == {("citation", 2)}


DISCONTIG_SRC = """exception_a(P) <- get(P, k1, true)
other(x),
exception_a(P) <- get(P, k2, true)
"""


def test_discontiguous_directive_emitted():
    out = clausal_source_to_prolog(DISCONTIG_SRC, strict=True)
    assert ":- discontiguous(exception_a/1)." in out
    # contiguous predicates get no directive
    assert ":- discontiguous(other/0)." not in out


# A hand-written -discontiguous(...) for the same predicate the
# interruption tracker would ALSO flag must not be duplicated.
DUPLICATE_DISCONTIG_SRC = """-module(m, [Foo(X)])
-discontiguous(Foo(X))
Foo(1),
Bar(2),
Foo(3),
"""


def test_discontiguous_directive_not_duplicated_when_hand_written():
    out = clausal_source_to_prolog(DUPLICATE_DISCONTIG_SRC, strict=True)
    assert out.count(":- discontiguous(foo/1).") == 1


# Two DCG rules of one nonterminal interrupted by an ordinary clause —
# the emitted indicator carries the +2 hidden difference-list state args
# (the same arity module_export_signature would report for this rule).
DCG_INTERRUPTED_SRC = """greeting >> (["hi"])
other(x),
greeting >> (["yo"])
"""

DCG_CONTIGUOUS_SRC = """greeting >> (["hi"])
greeting >> (["yo"])
"""


def test_discontiguous_directive_emitted_for_interrupted_dcg_run():
    out = clausal_source_to_prolog(DCG_INTERRUPTED_SRC, strict=True)
    assert ":- discontiguous(greeting/2)." in out


def test_no_discontiguous_directive_for_contiguous_dcg_run():
    out = clausal_source_to_prolog(DCG_CONTIGUOUS_SRC, strict=True)
    assert ":- discontiguous(greeting/2)." not in out


# ── Task 6: relative use_module paths + filtered name/arity import lists ──
#
# Scryer resolves a consulted file path RELATIVE to the consulting file, so a
# module three packages deep must reach a root library as '../../../lib', and
# an import list naming a predicate the target does not actually export raises
# existence_error at load time — both are what these lock down.

IMPORTER_SRC = """-module(prohibition, [limb_status(A, B, C, D)])
-import_from(eu.ai_act.prohibited_practices.kernel, [ai_act_verdict])
-import_from(eu.ai_act.prohibited_practices.citations, [cite, eu_reg_x])
-import_from(formalize_lib, [check_gte])
-import_from(clausal.stdlib.kleene, [and3, or3])
limb_status(a, b, c, d),
"""

SIGS = {
    "eu.ai_act.prohibited_practices.kernel": set(),          # signature-only
    "eu.ai_act.prohibited_practices.citations": {("citation", 2)},
    "formalize_lib": {("check_gte", 5)},
    "clausal.stdlib.kleene": {("and3", 3), ("or3", 3)},
}


def test_relative_paths_and_filtered_import_lists():
    out = clausal_source_to_prolog(
        IMPORTER_SRC, strict=True,
        module_path="eu.ai_act.prohibited_practices.prohibition",
        module_signatures=SIGS,
    )
    # same package → bare sibling name; kernel exports nothing → skipped
    assert "use_module('kernel'" not in out
    assert "% skipped:" in out
    # citations: cite/1 not exported → dropped; nothing importable remains
    assert "use_module('citations'" not in out
    # root libraries: relative climb from a 3-deep package
    assert ":- use_module('../../../formalize_lib', [check_gte/5])." in out
    assert ":- use_module('../../../clausal_kleene', [and3/3, or3/3])." in out


def test_no_signatures_falls_back_to_listless_use_module():
    out = clausal_source_to_prolog(
        IMPORTER_SRC, strict=True,
        module_path="eu.ai_act.prohibited_practices.prohibition",
    )
    assert ":- use_module('kernel')." in out
    assert ":- use_module('../../../formalize_lib')." in out


PASCAL_IMPORTER_SRC = """-import_from(eu.ai_act.prohibited_practices.kernel, [AiActVerdict])
noop(a),
"""


def test_pascal_case_requested_names_match_snake_case_exports():
    """`[AiActVerdict]` must find the exported ("ai_act_verdict", 4)."""
    out = clausal_source_to_prolog(
        PASCAL_IMPORTER_SRC, strict=True,
        module_path="eu.ai_act.prohibited_practices.prohibition",
        module_signatures={
            "eu.ai_act.prohibited_practices.kernel": {("ai_act_verdict", 4)},
        },
    )
    assert ":- use_module('kernel', [ai_act_verdict/4])." in out


IMPORT_MODULE_SRC = """-import_module(eu.ai_act.prohibited_practices.kernel)
-import_module(clausal.stdlib.kleene)
noop(a),
"""


def test_import_module_gets_the_same_relative_path_treatment():
    out = clausal_source_to_prolog(
        IMPORT_MODULE_SRC, strict=True,
        module_path="eu.ai_act.prohibited_practices.prohibition",
    )
    assert ":- use_module('kernel')." in out
    assert ":- use_module('../../../clausal_kleene')." in out


def test_absolute_paths_and_bare_import_lists_without_module_path():
    """No module_path → today's behaviour is unchanged."""
    out = clausal_source_to_prolog(IMPORTER_SRC, strict=True)
    assert (":- use_module('eu/ai_act/prohibited_practices/kernel', "
            "[ai_act_verdict])." in out)
    assert ":- use_module('clausal/stdlib/kleene', [and3, or3])." in out


PY_IMPORT_SRC = """-import_from(py.datetime, [now])
noop(a),
"""


def test_python_only_import_still_raises_under_strict():
    """A py.* import has no Prolog equivalent — it must reach _add_warning."""
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog(
            PY_IMPORT_SRC, strict=True,
            module_path="eu.ai_act.prohibited_practices.prohibition",
            module_signatures=SIGS,
        )


CROSS_PACKAGE_SRC = """-import_from(eu.gdpr.kernel, [Consent])
noop(a),
"""


def test_relative_path_climbs_only_to_the_common_package():
    out = clausal_source_to_prolog(
        CROSS_PACKAGE_SRC, strict=True,
        module_path="eu.ai_act.prohibited_practices.prohibition",
        module_signatures={"eu.gdpr.kernel": {("consent", 2)}},
    )
    assert ":- use_module('../../gdpr/kernel', [consent/2])." in out


LIBRARY_IMPORT_SRC = """-import_from(clausal.logic.clpfd, [Label])
noop(a),
"""


def test_dialect_libraries_keep_library_form_in_relative_mode():
    """A dialect library is not a file in the export tree — no relpath, no filter."""
    from clausal.tools.prolog_dialect import Dialect
    out = clausal_source_to_prolog(
        LIBRARY_IMPORT_SRC, strict=True, dialect=Dialect.scryer(),
        module_path="eu.ai_act.prohibited_practices.prohibition",
        module_signatures={},
    )
    assert "use_module(library(clpz)" in out
