"""The string-in-catch-pattern lint (``ClausalStringInCatchPatternWarning``).

The engine's error terms carry ATOMS, so under ``-double_quotes(chars)`` (the
default) ``catch(G, error(type_error("atom", _), _), R)`` compares a STRING
with the atom ``date``, never matches, and nothing raises: the error just
propagates.  The lint fires at load and suggests the quoted atom ``'date'``.
"""
import sys
import textwrap
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.lint_warnings import (
    ClausalLintWarning,
    ClausalStringInCatchPatternWarning,
)
from tests._suffix import SEAM


def _load(tmp_path, monkeypatch, name, body):
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(textwrap.dedent(body).lstrip())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    hits = [w for w in caught
            if isinstance(w.message, ClausalStringInCatchPatternWarning)]
    return mod, hits


# atom_length(1, _) raises the engine's own error(type_error(atom, 1), atom_length/2).
PROGRAM = """
    {mode}
    -private([caught, atom, x, my_ball(B)])
    guarded(R) <- ({form})

    def go():
        return [R for R in --guarded(R)]
"""


def test_is_a_visible_lint_warning():
    assert issubclass(ClausalStringInCatchPatternWarning, ClausalLintWarning)
    assert issubclass(ClausalStringInCatchPatternWarning, UserWarning)
    assert not issubclass(ClausalStringInCatchPatternWarning, DeprecationWarning)


def test_a_string_in_the_formal_warns_and_suggests_the_atom(tmp_path, monkeypatch):
    mod, hits = _load(tmp_path, monkeypatch, "scp_fires", PROGRAM.format(
        mode="",
        form='catch(atom_length(1, _), error(type_error("atom", _), _), R is caught)'))
    assert len(hits) == 1
    text = str(hits[0].message)
    assert "'atom'" in text and "catch/3" in text and f"scp_fires{SEAM}" in text
    # The hazard is real: the pattern does not catch, the error propagates.
    with pytest.raises(Exception) as info:
        mod.go()
    assert "type_error" in str(info.value)


@pytest.mark.parametrize("form", [
    'catch_recover(atom_length(1, _), error(type_error("atom", _), _), R is caught)',
    'catch_error(atom_length(1, _), error(type_error("integer", _), _)), R is x',
])
def test_the_other_catch_forms_are_judged(tmp_path, monkeypatch, form):
    name = "scp_other_" + form.split("(")[0]
    _, hits = _load(tmp_path, monkeypatch, name, PROGRAM.format(mode="", form=form))
    assert len(hits) == 1


@pytest.mark.parametrize("lit", ["atom", "'atom'"])
def test_an_atom_does_not_warn_and_catches(tmp_path, monkeypatch, lit):
    name = "scp_atom_" + ("q" if lit.startswith("'") else "b")
    mod, hits = _load(tmp_path, monkeypatch, name, PROGRAM.format(
        mode="",
        form=f"catch(atom_length(1, _), error(type_error({lit}, _), _), R is caught)"))
    assert hits == []
    assert mod.go() == ["caught"]


def test_no_warning_under_double_quotes_atom(tmp_path, monkeypatch):
    mod, hits = _load(tmp_path, monkeypatch, "scp_atom_mode", PROGRAM.format(
        mode="-double_quotes(atom)",
        form='catch(atom_length(1, _), error(type_error("atom", _), _), R is caught)'))
    assert hits == []
    # ...because there "atom" IS the atom, and the pattern matches.
    assert mod.go() == ["caught"]


def test_a_string_culprit_does_not_warn(tmp_path, monkeypatch):
    # The culprit IS the offending term, and here it is the string itself.
    mod, hits = _load(tmp_path, monkeypatch, "scp_culprit", """
        -private([caught])
        guarded(R) <- catch(atom_length("hello", _),
                            error(type_error(atom, "hello"), _), R is caught)

        def go():
            return [R for R in --guarded(R)]
    """)
    assert hits == []
    assert mod.go() == ["caught"]


def test_permission_error_judges_action_and_type(tmp_path, monkeypatch):
    _, hits = _load(tmp_path, monkeypatch, "scp_perm", PROGRAM.format(
        mode="",
        form='catch(atom_length(1, _), error(permission_error("modify", "static_procedure", _), _), R is caught)'))
    assert len(hits) == 2


def test_reflection_does_not_judge(tmp_path, monkeypatch):
    from clausal.reflection import reify_source
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        reify_source('g(R) <- catch(atom_length(1, _), '
                     'error(type_error("atom", _), _), R is caught)\n')
    assert not [w for w in caught
                if isinstance(w.message, ClausalStringInCatchPatternWarning)]


def test_a_string_outside_error_formal_does_not_warn(tmp_path, monkeypatch):
    _, hits = _load(tmp_path, monkeypatch, "scp_outside", PROGRAM.format(
        mode="",
        form='catch(atom_length(1, _), my_ball("x"), R is caught)'))
    assert hits == []


def test_identical_sites_each_show_under_the_default_filter(tmp_path):
    """Three identical catch sites in one file print THREE warnings under
    the interpreter's DEFAULT filters (no -W, no PYTHONWARNINGS).  The default
    action dedups on (message, category, module, lineno), and every firing is
    attributed to the same Python frame, so each message must carry its own
    .clausal file:line:column to stay distinct."""
    import os
    import pathlib
    import subprocess
    repo = pathlib.Path(__file__).resolve().parent.parent
    site = ('catch(atom_length(1, _), error(type_error("atom", _), _), '
            'R is caught)')
    (tmp_path / f"scp_three{SEAM}").write_text(
        "-private([caught])\n"
        + "".join(f"g{i}(R) <- {site}\n" for i in (1, 2, 3)))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONWARNINGS"}
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(repo)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run([sys.executable, "-c", "import clausal; import scp_three"],
                       capture_output=True, text=True, env=env, timeout=120,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert r.stderr.count("ClausalStringInCatchPatternWarning") == 3, r.stderr
    for line in (2, 3, 4):
        assert f"scp_three{SEAM}:{line}:" in r.stderr, r.stderr
