"""A file's load reports EVERY refusal, not the first (operator ruling
2026-11-02: "like compilers don't stop on first error").  The module still
never loads with a clause missing: one exception carries them all, in
source order."""
from __future__ import annotations

import pytest

from clausal.tools import iso_l3 as L3

THREE = ("a(1).\n"
         "b(X) :- X = .\n"
         "c(2).\n"
         "d(X) :- !, X = 1.\n"
         "e(3).\n"
         "f(X :- 1.\n"
         "g(4).\n")


def test_one_refusal_is_raised_as_before():
    src = "f(1).\n\ng(.\nh(2).\n"
    with pytest.raises(L3.LoweringRefused) as info:
        L3.lower_items(L3.read_iso(src), source=src, filename="m.pl")
    assert not isinstance(info.value, L3.LoweringRefusedMany)
    assert info.value.errors == [info.value]
    assert str(info.value).startswith("m.pl:3: ")


def test_every_refusal_is_collected_in_source_order():
    with pytest.raises(L3.LoweringRefusedMany) as info:
        L3.lower_items(L3.read_iso(THREE), source=THREE,
                       filename="m.clausal")
    e = info.value
    lines = [str(x).split(":", 2)[1] for x in e.errors]
    assert lines == ["2", "4", "6"]
    assert "cut" in str(e.errors[1])
    # The first one's location and ISO term are the exception's own, so a
    # consumer that reads one error still reads the first.
    assert e.span == e.errors[0].span and e.term == e.errors[0].term
    assert str(e).splitlines() == [
        "3 errors", *(str(x) for x in e.errors)]


def test_end_of_file_refusals_follow_the_items():
    src = ":- module(m, [p/0]).\np :- !.\n"     # no end_module/1
    with pytest.raises(L3.LoweringRefusedMany) as info:
        L3.lower_items(L3.read_iso(src), source=src, filename="m.clausal")
    msgs = [str(x) for x in info.value.errors]
    assert msgs[0].startswith("m.clausal:2: ")
    assert "end_module" in msgs[-1]


def test_the_counting_mode_is_unchanged():
    _mod, stats = L3.lower_items(L3.read_iso(THREE), strict=False,
                                 source=THREE, filename="m.clausal")
    assert stats["refused"] == 3


def _load(path):
    from clausal.testing import load_clausal_module  # noqa: PLC0415
    load_clausal_module(path)


def test_the_loader_syntax_error_carries_every_error(tmp_path):
    p = tmp_path / "multi.clausal"
    p.write_text(THREE)
    with pytest.raises(SyntaxError) as info:
        _load(str(p))
    e = info.value
    assert e.lineno == 2
    assert [x.lineno for x in e.errors] == [2, 4, 6]
    # A syntax error keeps its ISO term and a caret at the fault.
    assert e.errors[0].term is not None and e.errors[0].offset == 13
    assert e.errors[2].term is not None and e.errors[2].offset == 5
    assert getattr(e.errors[1], "term", None) is None
    assert all(x.filename == str(p) for x in e.errors)
    assert "3 errors" in e.msg
    prefix = f"Cannot import {p}: "
    assert e.msg.startswith(prefix)
    assert e.msg[len(prefix):].splitlines()[1:] == [
        x.msg[len(prefix):] for x in e.errors]


def test_the_loader_error_for_one_refusal_lists_itself(tmp_path):
    p = tmp_path / "one.clausal"
    p.write_text("a(1).\nb(X) :- X = .\n")
    with pytest.raises(SyntaxError) as info:
        _load(str(p))
    assert info.value.errors == [info.value]


def test_the_runner_names_every_error(tmp_path):
    from clausal.testing import run_file
    p = tmp_path / "multi.clausal"
    p.write_text(THREE + "test(ok) :- a(1).\n")
    res = run_file(p)
    [load] = res.results
    assert load.name == "<load>" and not load.passed
    assert [x.lineno for x in load.error.errors] == [2, 4, 6]


def _broken_package(tmp_path, monkeypatch, top_extra):
    """A package whose ``__init__`` loads a module with two errors, and a
    top file whose ``use_module`` imports that package to find its target
    (the import a module/2 list read needs)."""
    pkg = tmp_path / "allerr_pkg"
    pkg.mkdir()
    (pkg / "__init__.clausal").write_text(":- use_module(allerr_pkg/broken).\n")
    (pkg / "broken.clausal").write_text(
        ":- module(broken, [q/1]).\nq(1).\np(X) :- X = .\n"
        "r(X) :- !, X = 2.\n:- end_module(broken).\n")
    (pkg / "good.clausal").write_text(
        ":- module(good, [g/1]).\ng(1).\n:- end_module(good).\n")
    top = tmp_path / "top.clausal"
    top.write_text(":- use_module(allerr_pkg/good).\na(1).\n" + top_extra
                   + ":- use_module(allerr_pkg/good).\n")   # loads it again
    monkeypatch.syspath_prepend(str(tmp_path))
    import sys  # noqa: PLC0415
    for name in [n for n in sys.modules if n.startswith("allerr_pkg")]:
        monkeypatch.delitem(sys.modules, name)
    return top


def test_a_module_that_fails_to_load_is_collected_with_its_errors(
        tmp_path, monkeypatch):
    top = _broken_package(tmp_path, monkeypatch, "b(X) :- !, X = 1.\n")
    with pytest.raises(SyntaxError) as info:
        _load(str(top))
    e = info.value
    where = [(x.filename.rsplit("/", 1)[-1], x.lineno) for x in e.errors]
    # The dependency's own errors, where the first directive is, once,
    # then this file's.
    assert where == [("broken.clausal", 3), ("broken.clausal", 4),
                     ("top.clausal", 3)]
    assert e.errors[0].term is not None
    assert e.msg.splitlines()[1:] == [
        x.msg.split(": ", 1)[1] for x in e.errors]


def test_a_module_that_fails_to_load_alone_raises_its_own_error(
        tmp_path, monkeypatch):
    top = _broken_package(tmp_path, monkeypatch, "")
    with pytest.raises(SyntaxError) as info:
        _load(str(top))
    e = info.value
    assert e.filename.endswith("broken.clausal") and e.lineno == 3
    assert [x.lineno for x in e.errors] == [3, 4]
