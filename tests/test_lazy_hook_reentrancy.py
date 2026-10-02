"""Regression tests for ``_LazyHookFinder`` re-entrancy.

Condition 2 of the stub finder in ``clausal/_lazy_hook.py`` probes
``clausal.modules.<bare name>`` with ``importlib.util.find_spec``.  That call
imports the dotted name's *parents* to read their ``__path__``.  When
``clausal`` is not in ``sys.modules`` — a test that asserted "we did not import
clausal" cleared it, or an ``import clausal`` failed after the stub was
installed — the parent import comes back through ``sys.meta_path`` as the bare
name ``clausal``, which re-enters Condition 2 and probes
``clausal.modules.clausal``, which imports ``clausal`` again, and so on until
``RecursionError`` takes the whole process down (pytest reports
``INTERNALERROR``, so an entire suite reports nothing).
"""
import importlib.util
import os
import subprocess
import sys
import textwrap

import pytest
from tests._suffix import SEAM

CLONE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The shape of the real-world trigger: clear every ``clausal*`` entry from
# sys.modules while the stub finder stays on sys.meta_path.
_CLEAR_CLAUSAL = """
    import clausal
    for _name in [n for n in sys.modules if n == "clausal" or n.startswith("clausal.")]:
        del sys.modules[_name]
    assert any(type(f).__name__ == "_LazyHookFinder" for f in sys.meta_path)
"""


def _run(body, timeout=90):
    code = (f"import sys\nsys.path.insert(0, {CLONE!r})\n"
            + textwrap.dedent(_CLEAR_CLAUSAL) + textwrap.dedent(body))
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=timeout)


@pytest.mark.timeout(120)
def test_absent_bare_module_reports_module_not_found_not_recursion():
    """A genuinely missing module fails with the normal ModuleNotFoundError.

    Before the re-entrancy guard this recursed through the Condition-2 probe
    until RecursionError.
    """
    r = _run("""
        try:
            import lazyhook_absent_module_zzz  # noqa: F401
        except RecursionError:
            print("RECURSED")
        except ModuleNotFoundError as exc:
            print("MODULENOTFOUND", exc.name)
        else:
            print("IMPORTED")
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "MODULENOTFOUND lazyhook_absent_module_zzz", \
        r.stdout + r.stderr


@pytest.mark.timeout(120)
def test_stdlib_bare_import_survives_cleared_clausal():
    """A real stdlib module still imports; the stub declines it as before."""
    r = _run("""
        import wave
        print(wave.__name__)
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "wave", r.stdout + r.stderr


@pytest.mark.timeout(120)
def test_clausal_source_module_still_activates_hook(tmp_path):
    """Declining a re-entrant probe must not stop Condition 3 from activating.

    Clearing ``clausal`` from sys.modules makes ``clausal/__init__`` re-execute
    during activation; idempotent installation reuses the stub already on
    sys.meta_path instead of inserting a fresh one, and the activating stub
    then removes itself.  What matters here is that the real finders are
    installed and the .clausal source actually loaded.
    """
    moddir = tmp_path / "lazyreentry"
    moddir.mkdir()
    (moddir / f"lazyhook_reentry_facts{SEAM}").write_text("p(1),\np(2),\n")
    r = _run(f"""
        sys.path.insert(0, {str(moddir)!r})
        import lazyhook_reentry_facts as m
        lm = m.__dict__["$module"]
        real = any(type(f).__name__ == "PredicateFinder" for f in sys.meta_path)
        print(len(lm.db.clauses_for("p", 1)), real)
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "2 True", r.stdout + r.stderr


@pytest.mark.timeout(120)
def test_repeated_sweeps_do_not_accumulate_stub_finders():
    """A suite that sweeps ``clausal*`` from sys.modules in a loop re-executes
    ``_lazy_hook`` on every re-import; installation must reuse the stub already
    on sys.meta_path instead of inserting one per sweep (each duplicate adds a
    nested Condition-2 probe layer for every failing bare import)."""
    r = _run("""
        for _ in range(5):
            for _name in [n for n in sys.modules
                          if n == "clausal" or n.startswith("clausal.")]:
                del sys.modules[_name]
            import clausal  # noqa: F811 — deliberate re-import after sweep
        stubs = [f for f in sys.meta_path
                 if type(f).__name__ == "_LazyHookFinder"]
        print(len(stubs))
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "1", r.stdout + r.stderr


# ── unit-level guard behaviour ────────────────────────────────────────────────

def _finder():
    import clausal._lazy_hook as lazy_hook
    return lazy_hook._LazyHookFinder()


def test_reentrant_probe_of_the_same_name_is_declined(monkeypatch):
    """The cycle's exact shape: the probe's parent import asks for the same
    bare name.  The second ask must be declined instead of probing again.

    The fake probe refuses to run twice for one name, so an unguarded finder
    fails this test cleanly instead of recursing the runner to death.
    """
    finder = _finder()
    probed = []

    def fake_find_spec(name, package=None):
        probed.append(name)
        if probed.count(name) > 1:
            raise AssertionError(f"Condition-2 probe re-entered for {name}")
        if name == "clausal.modules.spin":
            # Stand-in for the parent import of ``clausal.modules.spin``
            # arriving back at sys.meta_path as the bare name it started from.
            assert finder.find_spec("spin", None) is None
        return None

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    assert finder.find_spec("spin", None) is None
    assert probed.count("clausal.modules.spin") == 1


def test_nested_probe_of_a_different_name_still_runs(monkeypatch):
    """Nesting: while ``outer`` is in flight, ``inner`` must get its own probe.

    The guard declines only the name it is already resolving, so module A's
    load triggering module B's still resolves B.
    """
    finder = _finder()
    probed = []

    def fake_find_spec(name, package=None):
        probed.append(name)
        if name == "clausal.modules.outer":
            assert finder.find_spec("inner", None) is None
        return None

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    assert finder.find_spec("outer", None) is None
    assert "clausal.modules.inner" in probed
    assert not finder._in_flight()


def test_probe_failure_does_not_leak_the_in_flight_marker(monkeypatch):
    """An exception out of the probe must still clear the marker, or the name
    would be permanently un-probeable for the rest of the process."""
    finder = _finder()
    probed = []

    def exploding_find_spec(name, package=None):
        probed.append(name)
        raise RuntimeError("probe blew up")

    monkeypatch.setattr(importlib.util, "find_spec", exploding_find_spec)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="probe blew up"):
            finder.find_spec("boomname", None)
    assert probed == ["clausal.modules.boomname"] * 2
    assert not finder._in_flight()


@pytest.mark.timeout(120)
def test_seam_source_module_activates_hook(tmp_path):
    """Condition 3 recognises the ``.seam`` alias extension, not only ``.clausal``.

    Before the real finders are installed the stub is the only thing on
    ``sys.meta_path`` that knows about predicate modules; if it declines a
    ``.seam`` file the import fails with ModuleNotFoundError before the real
    finders ever get a look.
    """
    moddir = tmp_path / "lazyseam"
    moddir.mkdir()
    (moddir / "lazyhook_seam_facts.seam").write_text("p(1),\np(2),\n")
    r = _run(f"""
        sys.path.insert(0, {str(moddir)!r})
        import lazyhook_seam_facts as m
        lm = m.__dict__["$module"]
        real = any(type(f).__name__ == "PredicateFinder" for f in sys.meta_path)
        print(len(lm.db.clauses_for("p", 1)), real)
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "2 True", r.stdout + r.stderr
