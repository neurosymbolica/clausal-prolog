"""Answer sets from Scryer's CLP(Q) and Clausal's, compared by equivalence.

* :func:`oracle_answers` runs a program and goal on Scryer (the oracle),
* :func:`clausal_answers` runs them on Clausal with a chosen CLP(Q) solver,
* :func:`same_solution_sets` compares two answer lists in order.

An :class:`Answer` is the shown variables' bindings and the residual
constraints left on them, as strings such as ``X+Y=<3`` (``N rdiv D`` and
``N/D`` both spell a rational).  Two residuals are equal when z3 proves
them equivalent over the shown variables; variables whose names start with
``_`` are internal and are existentially closed on each side.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from collections import namedtuple
from fractions import Fraction

import pytest
import z3

from tests._oracles import SCRYER, run_scryer

Answer = namedtuple("Answer", "bindings residual")

_RELATIONS = {"=<": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
              "<": lambda a, b: a < b, ">": lambda a, b: a > b,
              "=": lambda a, b: a == b, "=:=": lambda a, b: a == b,
              "=\\=": lambda a, b: a != b}
_SPLIT = re.compile(r"(=<|>=|=:=|=\\=|<|>|=)")
_RATIONAL = re.compile(r"(?<![\w.])(\d+)\s*/\s*(\d+)")
_NAME = re.compile(r"\b[A-Z_][A-Za-z0-9_]*\b")
_MAKE_RATIONAL = "__rational__"


def _normal(text):
    """*text* with ``rdiv`` spelt ``/``, ``^`` spelt ``**`` and no blanks."""
    return re.sub(r"\s+", "", text.replace(" rdiv ", "/").replace("^", "**"))


def _expression(text, names):
    """A residual side (``2*X + 1/3 - Y``) as a z3 term over *names*."""
    text = _RATIONAL.sub(rf"({_MAKE_RATIONAL}(\1,\2))", _normal(text))
    return eval(text, {_MAKE_RATIONAL: z3.Q, "__builtins__": {}}, names)  # noqa: S307


def _formula(residual, names):
    parts = []
    for constraint in residual:
        constraint = constraint.strip().strip("{}")
        left, relation, right = _SPLIT.split(constraint, maxsplit=1)
        parts.append(_RELATIONS[relation](_expression(left, names),
                                          _expression(right, names)))
    return z3.And(parts) if parts else z3.BoolVal(True)


def _names(*residuals):
    found = set()
    for residual in residuals:
        for constraint in residual:
            found.update(_NAME.findall(constraint))
    return {n: z3.Real(n) for n in found}


def _closed(residual, names):
    """The residual's formula with its internal (``_``) variables existential."""
    mentioned = set()
    for constraint in residual:
        mentioned.update(_NAME.findall(constraint))
    inner = [names[n] for n in sorted(mentioned) if n.startswith("_")]
    body = _formula(residual, names)
    return z3.Exists(inner, body) if inner else body


def _equivalent(first, second):
    """``(True, "")``, or ``(False, why)`` when z3 finds no proof of equivalence."""
    # Each side's internal names are renamed apart, so `_A` on the left and
    # `_A` on the right are different variables.
    first = [re.sub(r"\b(_[A-Za-z0-9_]*)", r"\1__left", c) for c in first]
    second = [re.sub(r"\b(_[A-Za-z0-9_]*)", r"\1__right", c) for c in second]
    names = _names(first, second)
    solver = z3.Solver()
    solver.add(z3.Not(_closed(first, names) == _closed(second, names)))
    verdict = solver.check()
    if verdict == z3.unsat:
        return True, ""
    if verdict == z3.sat:
        model = solver.model()
        shown = {str(d): str(model[d]) for d in model.decls()
                 if not str(d).startswith("_")}
        return False, f"they differ at {shown}"
    return False, f"z3 could not decide ({solver.reason_unknown()})"


def same_solution_sets(left, right):
    """Compare two answer lists in order: ``(True, "")`` or ``(False, why)``."""
    if len(left) != len(right):
        return False, f"{len(left)} answers against {len(right)}"
    for i, (a, b) in enumerate(zip(left, right)):
        if a.bindings != b.bindings:
            return False, f"answer {i}: bindings {a.bindings} against {b.bindings}"
        ok, why = _equivalent(a.residual, b.residual)
        if not ok:
            return False, f"answer {i}: residual {a.residual} against {b.residual}: {why}"
    return True, ""


# ---- values ---------------------------------------------------------------

_NUMBER = re.compile(r"^(-?)\(?(-?\d+)(?:/(\d+))?\)?$")


def _value(text):
    """A printed binding as a Fraction, or the text itself when it is not a number."""
    found = _NUMBER.match(_normal(text))
    if not found:
        return text.strip()
    sign, numerator, denominator = found.groups()
    number = Fraction(int(numerator), int(denominator or 1))
    return -number if sign else number


def _skip_without_scryer():
    if not pathlib.Path(SCRYER).exists():
        pytest.skip(f"needs the Scryer CLP(Q) build at {SCRYER}")


# ---- Scryer ---------------------------------------------------------------

#: Loaded after the program.  Prints each answer as ``answer``, then one
#: ``binding<TAB>Name<TAB>Value`` line per bound shown variable and one
#: ``constraint<TAB>C`` line per residual constraint, then ``end``.  dump/3
#: refuses a bound variable, so it gets only the unbound ones; the internal
#: variables left in its constraints are named `_I1`, `_I2`, ... .
_SCRYER_HELPER = r"""
:- use_module(library(clpq)).
:- use_module(library(lists)).
:- use_module(library(iso_ext)).

'$clpq_oracle_split'([], [], [], [], []).
'$clpq_oracle_split'([V|Vs], [N|Ns], Free, FreeNames, Bound) :-
    (   var(V)
    ->  Free = [V|Free1], FreeNames = [N|FreeNames1], Bound = Bound1
    ;   Free = Free1, FreeNames = FreeNames1, Bound = [N-V|Bound1]
    ),
    '$clpq_oracle_split'(Vs, Ns, Free1, FreeNames1, Bound1).

'$clpq_oracle_answer'(Vs, Ns, Copy-Cs) :-
    '$clpq_oracle_split'(Vs, Ns, Free, FreeNames, Bound),
    dump(Free, FreeNames, Cs0),
    copy_term(Bound-Cs0, Copy-Cs, _),
    term_variables(Cs, Inner),
    '$clpq_oracle_name'(Inner, 1).

'$clpq_oracle_name'([], _).
'$clpq_oracle_name'([V|Vs], I) :-
    number_codes(I, Codes), atom_codes(A, [0'_, 0'I|Codes]), V = A,
    J is I + 1, '$clpq_oracle_name'(Vs, J).

'$clpq_oracle_print'(L) :-
    member(Bound-Cs, L),
    write(answer), nl,
    (   member(N-V, Bound), write(binding), put_char('\t'), write(N),
        put_char('\t'), write(V), nl, fail ; true ),
    (   member(C, Cs), write(constraint), put_char('\t'), write(C), nl,
        fail ; true ),
    fail.
'$clpq_oracle_print'(_) :- write(end), nl.
"""


def _prolog_atom(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def oracle_goal(goal, variables):
    """The one query put to Scryer for *goal* over the shown *variables*."""
    shown = "[" + ", ".join(variables) + "]"
    names = "[" + ", ".join(_prolog_atom(v) for v in variables) + "]"
    return (f"\\+ \\+ (findall(A, (({goal}), '$clpq_oracle_answer'({shown}, {names}, A)), L), "
            f"'$clpq_oracle_print'(L))")


def _parse_oracle(stdout):
    answers, current, ended = [], None, False
    for line in stdout.splitlines():
        kind, _, rest = line.partition("\t")
        if kind == "answer":
            current = Answer({}, [])
            answers.append(current)
        elif kind == "binding":
            name, _, value = rest.partition("\t")
            current.bindings[name] = _value(value)
        elif kind == "constraint":
            current.residual.append(rest)
        elif kind == "end":
            ended = True
    if not ended:
        raise RuntimeError(f"Scryer did not finish the query:\n{stdout}")
    return answers


def oracle_answers(program_text: str, goal: str, variables: list) -> list:
    """Every answer of *goal* on Scryer's CLP(Q), in Scryer's order."""
    _skip_without_scryer()
    with tempfile.TemporaryDirectory() as directory:
        program = pathlib.Path(directory, "program.pl")
        program.write_text(program_text)
        helper = pathlib.Path(directory, "clpq_oracle_helper.pl")
        helper.write_text(_SCRYER_HELPER)
        result = run_scryer([str(program), str(helper)], [oracle_goal(goal, variables)],
                            cwd=directory)
    return _parse_oracle(result.stdout)


# ---- Clausal --------------------------------------------------------------

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _top_level_items(line):
    """*line* split at the commas outside brackets and quotes."""
    items, depth, start, quote = [], 0, 0, None
    for i, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(line[start:i].strip())
            start = i + 1
    items.append(line[start:].strip())
    return [item for item in items if item]


def _parse_clausal_line(line, variables):
    """One ``-g`` answer line (``X = 1 rdiv 2, {X + Y >= 2}.``) as an Answer."""
    line = line.strip()
    if line.endswith("."):
        line = line[:-1]
    answer = Answer({}, [])
    if line == "true":
        return answer
    for item in _top_level_items(line):
        if item.startswith("{") and item.endswith("}"):
            answer.residual.extend(_top_level_items(item[1:-1]))
            continue
        name, equals, value = item.partition(" = ")
        if not equals:
            raise ValueError(f"unparsed answer item {item!r} in {line!r}")
        if name.startswith("_") or name not in variables:
            continue
        answer.bindings[name] = _value(value)
    return answer


def clausal_argv(goal):
    return [sys.executable, "-m", "clausal", "-g", goal]


def clausal_answers(program_text: str, goal: str, variables: list, solver: str) -> list:
    """Every answer of *goal* on Clausal with ``CLAUSAL_CLPQ=solver``, in order."""
    _skip_without_scryer()
    environment = dict(os.environ, CLAUSAL_PL_FRONTEND="native", CLAUSAL_CLPQ=solver,
                       PYTHONPATH=str(_ROOT))
    with tempfile.TemporaryDirectory() as directory:
        program = pathlib.Path(directory, "program.pl")
        program.write_text(program_text)
        result = subprocess.run(
            [*clausal_argv(goal), str(program)], cwd=_ROOT, env=environment,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if lines == ["false."]:
        return []
    if result.returncode != 0:
        raise RuntimeError(f"clausal exited {result.returncode}:\n"
                           f"{result.stdout}\n{result.stderr}")
    return [_parse_clausal_line(line, variables) for line in lines]
