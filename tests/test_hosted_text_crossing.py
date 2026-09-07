"""Text crossings in Python hosted by a ``.clausal`` file.

Where Python makes text explicitly — ``str(x)`` and f-string interpolation —
the rewriter routes the value through an atom-aware helper: an atom gives
its SPELLING, everything else is plain ``str``.  Without this the common
idiom ``str(answer)`` on an atom cell yields the tuple repr ``"('x',)"``
and a comparison against text scores a wrong answer with no error.
"""
import os
import tempfile

from clausal.import_hook import _load_module


def _load_inline(name: str, source: str):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.clausal")
        with open(path, "w") as fh:
            fh.write(source)
        return _load_module(name, path)


class TestStrOfAnAtom:
    def test_str_of_an_atom_is_its_spelling(self):
        mod = _load_inline("_txt_str", (
            "-module(_txt_str, [ok])\n"
            "-double_quotes(chars)\n"
            "def text():\n"
            "    return str(ok)\n"
        ))
        assert mod.text() == "ok"

    def test_str_of_anything_else_is_plain_str(self):
        mod = _load_inline("_txt_plain", (
            "-module(_txt_plain, [pair(A, B)])\n"
            "-double_quotes(chars)\n"
            "def texts():\n"
            "    return (str(42), str(\"s\"), str([1, 2]), str(--pair(1, 2)))\n"
        ))
        assert mod.texts() == ("42", "s", "[1, 2]", "('pair', 1, 2)")

    def test_an_fstring_interpolates_the_spelling(self):
        mod = _load_inline("_txt_fstr", (
            "-module(_txt_fstr, [ok])\n"
            "-double_quotes(chars)\n"
            "def text(n):\n"
            "    return f\"status={ok} n={n} r={ok!r} w={n:>3}\"\n"
        ))
        assert mod.text(7) == "status=ok n=7 r=('ok',) w=  7"

    def test_a_module_that_binds_str_itself_is_left_alone(self):
        mod = _load_inline("_txt_shadow", (
            "-module(_txt_shadow, [ok])\n"
            "-double_quotes(chars)\n"
            "def str(x):\n"
            "    return 'mine'\n"
            "def text():\n"
            "    return str(ok)\n"
        ))
        assert mod.text() == "mine"


class TestBoundaries:
    def test_a_clause_body_is_untouched(self):
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, deref
        mod = _load_inline("_txt_clause", (
            "-module(_txt_clause, [ok, label(X, S)])\n"
            "-double_quotes(chars)\n"
            "label(X, S) <- (S is f\"v={X}\")\n"
        ))
        s = Var()
        for _ in call("label", ("ok",), s, module=mod.__dict__["$module"]):
            assert deref(s) == "v=ok"
            break
        else:
            raise AssertionError("no solution")

    def test_reified_source_does_not_grow_helper_calls(self):
        from clausal.reflection import reify_source
        src = "-module(_txt_reify, [ok])\ndef text():\n    return str(ok)\n"
        # Reflection models Python code by SOURCE POSITION (a PythonCode
        # item), never by rewritten AST, so the helper cannot leak into a
        # rendering; pin that the item is still there and carries no helper.
        items = reify_source(src)
        dumped = "\n".join(repr(vars(i)) if hasattr(i, "__dict__") else repr(i) for i in items)
        assert "PythonCode(kind='function', name='text'" in dumped
        assert "$text" not in dumped
