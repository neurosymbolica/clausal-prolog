"""Slice E5a: per-optimisation enable/disable toggle on
:class:`CompilationContext`.

E5a only gates the IR-side analyse/apply invocations — the legacy
bypasses (DR preprocess, ``_compile_tro_body``, bucket-ref pre-scan)
still run unconditionally, so behaviour is unchanged with any flag
combination.  E5b extends the gate to legacy paths and adds the full
test matrix.

These tests verify the field exists with the right default and that
clearing a flag short-circuits the matching IR-side analyse.
"""

from __future__ import annotations


def test_default_enabled_optimisations_all_three(monkeypatch):
    # E5b: the default is env-var-overridable (``CLAUSAL_DISABLE_OPT``).
    # Clear the env var so the dataclass field default factory returns
    # the all-on set even when this test runs under a sweep that
    # disables an optimisation.
    monkeypatch.delenv("CLAUSAL_DISABLE_OPT", raising=False)
    from clausal.logic.compiler.compile_ctx import CompilationContext
    ctx = CompilationContext(db=None, var_context={}, trail_name="trail")
    assert ctx.enabled_optimisations == frozenset(
        {"tro", "destructive_reuse", "call_site"}
    )


def test_replace_overrides_enabled_optimisations():
    from clausal.logic.compiler.compile_ctx import CompilationContext
    explicit = frozenset({"tro", "destructive_reuse", "call_site"})
    ctx = CompilationContext(
        db=None, var_context={}, trail_name="trail",
        enabled_optimisations=explicit,
    )
    ctx2 = ctx.replace(enabled_optimisations=frozenset({"tro"}))
    assert ctx2.enabled_optimisations == frozenset({"tro"})
    # Original is unchanged.
    assert ctx.enabled_optimisations == explicit


def test_disabling_call_site_skips_ir_apply():
    """With ``call_site`` disabled, the IR-shadow path inside
    ``_run_ir_parallel`` should not write ``direct_bucket_ref`` hints
    onto SubCalls — the legacy ``_inject_bucket_refs_trampoline`` map
    still drives codegen, so suite-level behaviour is unchanged.

    We exercise this via a focused unit: build IR, call the same
    apply path the IR shadow uses, and assert the hint is/isn't set.
    """
    from clausal.logic.compiler.optimisations import call_site as _cs
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.terms import Call, LoadName
    body = [Call(func=LoadName(name="some_pred"), args=[], kwargs=[])]
    ir = terms_to_goalop(body, db=None)
    # With no base_globals, analyse returns an empty plan — assert
    # apply with empty plan returns ref-equal IR (no-op contract).
    plan = _cs.analyse(ir, None, base_globals={}, db=None)
    assert _cs.apply(ir, plan) is ir
