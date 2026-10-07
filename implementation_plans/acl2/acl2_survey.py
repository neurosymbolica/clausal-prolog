"""Survey ACL2's sources: what would an interpreter have to provide?

A tolerant Common Lisp reader (comments, strings, #\\chars, quote family,
#+/#- feature conditionals tagged, |syms|, pkg::syms, #. #' #( #x ...), and
a walker that tallies operator heads with binding forms handled, so let
variables are not mistaken for operators.
"""
from __future__ import annotations

import collections
import os
import re
import sys

sys.setrecursionlimit(100000)


class Sym(str):
    pass


class Cond:                       # #+feat X / #-feat X
    def __init__(self, sign, feat, form):
        self.sign, self.feat, self.form = sign, feat, form


class Reader:
    def __init__(self, text):
        self.s, self.i = text, 0

    def ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n\f":
                self.i += 1
            elif c == ";":
                j = s.find("\n", self.i)
                self.i = len(s) if j < 0 else j + 1
            elif s.startswith("#|", self.i):
                depth, self.i = 1, self.i + 2
                while depth and self.i < len(s):
                    if s.startswith("#|", self.i):
                        depth += 1; self.i += 2
                    elif s.startswith("|#", self.i):
                        depth -= 1; self.i += 2
                    else:
                        self.i += 1
            else:
                return

    def forms(self):
        while True:
            self.ws()
            if self.i >= len(self.s):
                return
            yield self.read()

    def token(self):
        s, j = self.s, self.i
        out = []
        while j < len(s) and s[j] not in " \t\r\n\f()\"';`,":
            if s[j] == "|":
                k = s.index("|", j + 1)
                out.append(s[j + 1:k]); j = k + 1
            elif s[j] == "\\":
                out.append(s[j + 1]); j += 2
            else:
                out.append(s[j].lower()); j += 1
        self.i = j
        return "".join(out)

    def read(self):
        self.ws()
        s = self.s
        c = s[self.i]
        if c == "(":
            self.i += 1
            items = []
            while True:
                self.ws()
                if s[self.i] == ")":
                    self.i += 1
                    return items
                if s[self.i] == "." and s[self.i + 1] in " \t\n":
                    self.i += 1; items.append(Sym(".")); continue
                items.append(self.read())
        if c == ")":
            self.i += 1
            return Sym("<stray-paren>")
        if c == '"':
            j = self.i + 1
            while s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            self.i = j + 1
            return ("$string",)
        if c == "'":
            self.i += 1; return [Sym("quote"), self.read()]
        if c == "`":
            self.i += 1; return [Sym("backquote"), self.read()]
        if c == ",":
            self.i += 1
            if s[self.i] in "@.":
                self.i += 1
            return [Sym("unquote"), self.read()]
        if c == "#":
            d = s[self.i + 1]
            if d == "\\":
                self.i += 2
                self.i += 1
                while self.i < len(s) and s[self.i] not in " \t\r\n()":
                    self.i += 1
                return ("$char",)
            if d == "'":
                self.i += 2; return [Sym("function"), self.read()]
            if d in "+-":
                self.i += 2
                feat = self.read()
                return Cond(d, feat, self.read())
            if d == ".":
                self.i += 2; return [Sym("read-eval"), self.read()]
            if d == "(":
                self.i += 1; return [Sym("vector-literal"), *self.read()]
            if d in "xXbBoO":
                self.i += 2; self.token(); return 0
            if d == "!":
                self.i += 2; self.token(); return Sym("#!")
            if d.isdigit():           # #1= #1# #2A(...)
                j = self.i + 1
                while s[j].isdigit():
                    j += 1
                self.i = j + 1
                if s[j] in "=Aa":
                    return self.read()
                return Sym("<label-ref>")
            if d == ":":
                self.i += 2; return Sym(self.token())
            self.i += 2
            return Sym("#" + d)
        tok = self.token()
        if re.fullmatch(r"[+-]?\d+(/\d+)?\.?", tok) or re.fullmatch(r"[+-]?\d*\.\d+(e[+-]?\d+)?", tok):
            return 0
        if "::" in tok:
            tok = tok.split("::", 1)[1]
        elif ":" in tok[1:]:
            tok = tok.split(":", 1)[1]
        return Sym(tok)


DEF_RE = re.compile(r"def")
BINDERS = {"let", "let*", "mv-let", "multiple-value-bind", "destructuring-bind",
           "flet", "labels", "macrolet", "symbol-macrolet", "lambda", "do", "do*",
           "dolist", "dotimes", "er-let*", "state-global-let*", "with-open-file",
           "with-output-to-string", "with-input-from-string", "prog", "prog*",
           "b*", "handler-case"}
SPECIAL_OPS = set("""block catch eval-when flet function go if labels let let*
load-time-value locally macrolet multiple-value-call multiple-value-prog1 progn
progv quote return-from setq symbol-macrolet tagbody the throw
unwind-protect""".split())


class Survey:
    def __init__(self):
        self.defined = set()
        self.heads = {"logic": collections.Counter(), "raw": collections.Counter()}
        self.toplevel = collections.Counter()
        self.forms = {"logic": 0, "raw": 0}

    def define(self, form):
        if isinstance(form, list) and form and isinstance(form[0], Sym):
            h = form[0]
            if (h.startswith("def") or h in ("defun-one-output",)) and len(form) > 1 \
                    and isinstance(form[1], Sym):
                self.defined.add(form[1])
                if h == "defrec":
                    pass
            if h in ("mutual-recursion", "progn", "encapsulate", "when", "eval-when",
                     "local", "with-output", "skip-proofs", "verify-termination-boot-strap"):
                for f in form[1:]:
                    self.define(f)
        elif isinstance(form, Cond):
            self.define(form.form)

    def walk(self, form, mode, quoted=False):
        if isinstance(form, Cond):
            raw = form.sign == "-" and form.feat == "acl2-loop-only"
            self.walk(form.form, "raw" if raw else mode, quoted)
            return
        if not isinstance(form, list) or not form:
            return
        h = form[0]
        if quoted:
            for x in form:
                if isinstance(x, list) and x and x[0] == "unquote":
                    self.walk(x[1], mode)
                elif isinstance(x, (list, Cond)):
                    self.walk(x, mode, True)
            return
        if not isinstance(h, Sym):
            for x in form:
                self.walk(x, mode)
            return
        if h in ("quote", "declare"):
            return
        if h == "backquote":
            self.walk(form[1], mode, True)
            return
        if h == "function":
            if isinstance(form[1], Sym):
                self.heads[mode][form[1]] += 1
            else:
                self.walk(form[1], mode)
            return
        self.heads[mode][h] += 1
        args = form[1:]
        if h.startswith("def") and len(args) >= 2 and isinstance(args[0], Sym):
            for x in args[2:]:
                self.walk(x, mode)           # skip name and lambda list
            return
        if h in BINDERS and args:
            b = args[0]
            if isinstance(b, list):
                for item in b:
                    if isinstance(item, list):
                        rest = item[1:]
                        if h in ("flet", "labels", "macrolet"):
                            rest = item[2:]
                        for x in rest:
                            self.walk(x, mode)
            for x in args[1:]:
                self.walk(x, mode)
            return
        if h in ("cond",):
            for clause in args:
                if isinstance(clause, list):
                    for x in clause:
                        self.walk(x, mode)
            return
        if h in ("case", "ecase", "typecase", "etypecase", "ccase", "case-match"):
            self.walk(args[0], mode)
            for clause in args[1:]:
                if isinstance(clause, list):
                    for x in clause[1:]:
                        self.walk(x, mode)
            return
        for x in args:
            self.walk(x, mode)


def main(paths):
    sv = Survey()
    per_file = []
    parsed = {}
    for p in paths:
        text = open(p, encoding="utf-8", errors="replace").read()
        try:
            forms = list(Reader(text).forms())
        except Exception as exc:  # noqa: BLE001
            print("PARSE FAIL", p, type(exc).__name__, exc)
            continue
        parsed[p] = forms
        for f in forms:
            sv.define(f)
    for p, forms in parsed.items():
        name = os.path.basename(p)
        raw_file = "raw" in name or name in ("acl2-fns.lisp", "acl2-init.lisp", "acl2.lisp")
        mode = "raw" if raw_file else "logic"
        for f in forms:
            top = f.form if isinstance(f, Cond) else f
            if isinstance(top, list) and top and isinstance(top[0], Sym):
                sv.toplevel[top[0]] += 1
            m = mode
            if isinstance(f, Cond) and f.sign == "-" and f.feat == "acl2-loop-only":
                m = "raw"
            sv.forms[m] += 1
            sv.walk(f, mode)
        per_file.append((name, len(forms), mode))
    return sv, per_file


if __name__ == "__main__":
    sv, per_file = main(sys.argv[1:])
    print("files:", len(per_file), " top-level forms:", sv.forms)
    print("defined names:", len(sv.defined))
    print("top-level form kinds:", sv.toplevel.most_common(25))
    for mode in ("logic", "raw"):
        undefined = {h: n for h, n in sv.heads[mode].items() if h not in sv.defined}
        print(f"\n[{mode}] operator heads: {len(sv.heads[mode])} distinct, "
              f"{sum(sv.heads[mode].values())} uses; NOT defined in the sources: "
              f"{len(undefined)} distinct, {sum(undefined.values())} uses")
        top = sorted(undefined.items(), key=lambda kv: -kv[1])
        print("  ", " ".join(f"{h}:{n}" for h, n in top[:160]))
