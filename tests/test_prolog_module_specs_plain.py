"""`module_specs="plain"`: use_module targets for the engine's own layout.

The default ("relative") spells a target as a path relative to the consuming
file, after flattening the libraries to an export tree's root. That is what an
export tree needs, and it names no file when the library is instead found
through a SECOND sys.path entry: a module two packages deep that imports a
library by its bare name climbs `'../../lib'` to a directory that has no such
file. "plain" spells the dotted path itself (`lib`, `a/b/c`), which the engine's
`.pl` front end resolves through sys.path like any module spec. Because the
engine's use_module/1 imports nothing, every plain import list is explicit.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import clausal
from clausal.tools.clausal_to_prolog import (
    UntranslatableConstructError, clausal_source_to_prolog,
    clausal_source_to_prolog_ast, module_export_signature)

REPO = Path(clausal.__file__).resolve().parents[1]

LIB = "-module(qlib, [twice(X, Y)])\ntwice(X, [X, X]),\n"
USER = "-module(t, [go(Y)])\n-import_from(qlib, [twice])\ngo(Y) <- (twice(1, Y))\n"
SIGS = {"qlib": module_export_signature(clausal_source_to_prolog_ast(LIB))}


def _stage(root: Path, module_specs: str) -> None:
    """qlib lives in vendor/ and is imported by its BARE name (vendor/ is on
    sys.path too); the consumer is vendor.tests.t, two packages deep."""
    for rel, module_path, src in (("vendor/qlib.pl", "vendor.qlib", LIB),
                                  ("vendor/tests/t.pl", "vendor.tests.t", USER)):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(clausal_source_to_prolog(
            src, strict=True, module_path=module_path, module_signatures=SIGS,
            module_specs=module_specs))


def _run_on_engine(root: Path) -> str:
    code = textwrap.dedent(f"""
        import sys
        sys.path[:0] = [{str(root)!r}, {str(root / 'vendor')!r}]
        import importlib
        from clausal import solve
        from clausal.logic.variables import Var, deref
        try:
            m = importlib.import_module("vendor.tests.t")
            Y = Var()
            for _ in solve(("go", Y), m.__dict__.get("$module", m)):
                print("ANSWER", deref(Y))
                break
            else:
                print("NO_ANSWER")
        except Exception as e:
            print("RAISES", type(e).__name__)
    """)
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                          capture_output=True, text=True, timeout=300)
    return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:]


def test_plain_specs_load_and_answer_on_the_engine(tmp_path):
    _stage(tmp_path, "plain")
    assert ":- use_module(qlib, [twice/2])." in (tmp_path / "vendor/tests/t.pl").read_text()
    assert _run_on_engine(tmp_path) == "ANSWER [1, 1]"


def test_control_the_relative_climb_names_no_file_in_this_layout(tmp_path):
    """The same program in the default layout does not load: without this
    control the test above could pass for a reason unrelated to the spec."""
    _stage(tmp_path, "relative")
    assert "use_module('../../qlib'" in (tmp_path / "vendor/tests/t.pl").read_text()
    assert _run_on_engine(tmp_path).startswith("RAISES")


def _plain(src, **kw):
    return clausal_source_to_prolog(src, module_path="app.user", module_specs="plain", **kw)


def test_a_dotted_target_is_a_slash_joined_unquoted_spec():
    out = _plain("-import_from(a.b.c.schema, [f/1])\n")
    assert ":- use_module(a/b/c/schema, [f/1])." in out


def test_no_library_is_flattened():
    """_LIBRARY_REMAP relocates a library to an export tree's root; the engine
    finds it where it is."""
    out = _plain("-import_from(clausal.stdlib.kleene, [and3/3])\n")
    assert "use_module(clausal/stdlib/kleene, [and3/3])" in out


def test_a_bare_name_is_listed_from_its_signature():
    out = _plain("-import_from(qlib, [twice])\n", module_signatures=SIGS)
    assert ":- use_module(qlib, [twice/2])." in out


def test_a_bare_name_with_no_signature_is_refused_not_left_listless():
    with pytest.raises(UntranslatableConstructError, match="arity is unknown"):
        _plain("-import_from(other, [thing])\n", strict=True)
    out = _plain("-import_from(other, [thing])\n")
    assert "use_module(other)" not in out and "use_module(other, [])" not in out


def test_written_arities_need_no_signature():
    out = _plain("-import_from(other, [thing/2, mk(A)])\n", strict=True)
    assert ":- use_module(other, [thing/2, mk/1])." in out


def test_an_import_that_lists_nothing_is_a_comment_never_an_empty_list():
    out = _plain("-import_from(qlib, [not_exported])\n", module_signatures=SIGS)
    assert "use_module(qlib, [])" not in out
    assert "% skipped: qlib exports none of the requested names" in out


def test_import_module_lists_the_whole_export_set():
    out = _plain("-import_module(qlib)\n", module_signatures=SIGS)
    assert ":- use_module(qlib, [twice/2])." in out


def test_import_module_without_a_signature_is_refused():
    with pytest.raises(UntranslatableConstructError, match="import_module"):
        _plain("-import_module(other)\n", strict=True)


def test_a_dialect_library_keeps_its_library_form():
    out = _plain("-import_from(clausal.logic.clpfd, [in_domain, label])\n")
    assert ":- use_module(library(clpz))." in out


def test_relative_stays_the_default():
    out = clausal_source_to_prolog("-import_from(qlib, [twice/2])\n",
                                   module_path="vendor.tests.t")
    # (listless: the relative layout without signatures imports the whole set)
    assert ":- use_module('../../qlib')." in out


def test_an_unknown_layout_is_an_error():
    with pytest.raises(ValueError, match="module_specs"):
        clausal_source_to_prolog("", module_specs="engine")


# ── a file with no -module (a package facade) ─────────────────────────

SUB = "-module(sub, [f(X)])\nf(1),\nf(2),\n"
FACADE = "-import_from(fp.sub, [f])\n"
CONSUMER = "-module(cons, [g(X)])\n-import_from(fp, [f])\ng(X) <- (f(X))\n"
FACADE_SIGS = {"fp.sub": {("f", 1)}, "fp": {("f", 1)}}


def _stage_facade(root: Path, facade_text: str | None = None) -> None:
    files = {"fp/sub.pl": ("fp.sub", SUB), "fp/__init__.pl": ("fp.__init__", FACADE),
             "cons.pl": ("cons", CONSUMER)}
    for rel, (module_path, src) in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(clausal_source_to_prolog(
            src, strict=True, module_path=module_path,
            module_signatures=FACADE_SIGS, module_specs="plain"))
    if facade_text is not None:
        (root / "fp/__init__.pl").write_text(facade_text)


def _consult_consumer(root: Path, frontend: str) -> str:
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(root)!r})
        import importlib
        from clausal import solve
        from clausal.logic.variables import Var, deref
        try:
            m = importlib.import_module("cons")
            X = Var()
            print("ANSWERS", [deref(X) for _ in solve(("g", X), m.__dict__.get("$module", m))])
        except Exception as e:
            print("RAISES", type(e).__name__)
    """)
    env = {**__import__("os").environ, "CLAUSAL_PL_FRONTEND": frontend}
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=300)
    return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:]


def test_a_facade_gets_a_module_directive_that_reexports_its_imports():
    out = clausal_source_to_prolog(FACADE + "local(1),\n", module_path="fp.__init__",
                                   module_signatures=FACADE_SIGS, module_specs="plain")
    assert out.startswith(":- module(fp, [local/1, f/1]).")


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_a_facade_reexports_on_the_engine(tmp_path, frontend):
    _stage_facade(tmp_path)
    assert _consult_consumer(tmp_path, frontend) == "ANSWERS [1, 2]"


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_control_a_facade_without_a_module_directive_reexports_nothing(tmp_path, frontend):
    """The old output: the same facade with no :- module/2. Without this
    control the test above could pass for a reason unrelated to the directive."""
    _stage_facade(tmp_path, facade_text=":- use_module(fp/sub, [f/1]).\n")
    assert _consult_consumer(tmp_path, frontend).startswith("RAISES")


def test_the_relative_layout_emits_no_implicit_module():
    out = clausal_source_to_prolog(FACADE, module_path="fp.__init__")
    assert ":- module(" not in out


def test_a_library_import_is_not_reexported():
    out = clausal_source_to_prolog(
        "-import_from(clausal.logic.clpfd, [in_domain])\n-import_from(fp.sub, [f/1])\n",
        module_path="fp.__init__", module_specs="plain")
    assert out.startswith(":- module(fp, [f/1]).")
