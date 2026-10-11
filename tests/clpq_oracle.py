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
import ast
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
_VARIABLE = re.compile(r"^[A-Z_][A-Za-z0-9_]*$")


_NEGATIVE = "__negative_literal_"
_NEGATIVE_NAME = re.compile(rf"^{_NEGATIVE}(\d+)$")
_PREFIX_POSITION = set("(,=<>*/+-^[{|\\")
_MAX_EXPONENT = 10_000


def _mark_negative_literals(text):
    """Each ``-`` that Prolog reads as the sign of a number becomes one token.

    That is a ``-`` in prefix position (at the start, or after an operator
    or an opening bracket), then optional layout, then an integer: Scryer
    and Trealla read ``- 2`` as the integer -2 (``integer(- 1)`` succeeds,
    ``- 2^2`` is 4), while ``X - 2`` is infix subtraction and ``- (2)`` a
    compound.  Python's ast cannot tell ``-2**2`` from ``-(2**2)``, so this
    is decided on the text (test_a_negative_literal_is_read_from_the_source_text,
    test_a_sign_then_blanks_then_a_number_is_the_number).

    The digits must end the token: ``-1_000``, ``-0x10``, ``-1e3`` and
    ``-2j`` are not marked, so the later checks refuse them instead of the
    marker becoming an internal variable that is existentially closed away
    (test_a_malformed_negative_number_is_refused_not_dropped).
    """
    def mark(found):
        before = text[:found.start()].rstrip()
        if before and before[-1] not in _PREFIX_POSITION:
            return found.group(0)
        return _NEGATIVE + found.group(1)
    return re.sub(r"-\s*(\d+)(?![\w.])", mark, text)


def _marked_negative(identifier):
    """The int a marker token stands for; ValueError for a name that only
    starts with the marker prefix; None for any other name."""
    if not identifier.startswith(_NEGATIVE):
        return None
    negative = _NEGATIVE_NAME.match(identifier)
    if not negative:
        raise ValueError(f"not a negative literal: {identifier!r}")
    return -int(negative.group(1))


def _normal(text):
    """*text* with ``rdiv`` spelt ``/``, ``^`` spelt ``**``, negative
    literals marked, and no blanks.

    Blanks between two word characters (``X mod 2``) are refused: removing
    them would merge two tokens into one name
    (test_blanks_that_separate_two_words_are_refused).
    """
    text = re.sub(r"\s+rdiv\s+", "/", text)
    text = _mark_negative_literals(text).replace("^", "**")
    if re.search(r"(?<!\w)\d[\d_]*_", text) or re.search(r"(?<!\w)0[xob']", text):
        raise ValueError(f"not a Prolog number in {text!r}")
    if re.search(r"[\w.]\s+[\w.]", text):
        raise ValueError(f"blanks between two words in {text!r}")
    return re.sub(r"\s+", "", text)


# ---- arithmetic: an ast whitelist, never eval ------------------------------
#
# Python's + - * / ** have Prolog's precedence and associativity for the
# operators a residual uses (*, / and rdiv are all 400 yfx; ^ binds tighter),
# so `X/2/3` parses as (X/2)/3 on both (test_division_keeps_prolog_precedence).

class _NotConstant(Exception):
    pass


def _parse(text):
    try:
        return ast.parse(_normal(text), mode="eval").body
    except SyntaxError as error:
        raise ValueError(f"not an arithmetic expression: {text!r}") from error


def _is_int(node):
    return (isinstance(node, ast.Constant) and type(node.value) is int)


def _integer(node):
    """*node*'s value when it is an int literal or a marked negative one."""
    if _is_int(node):
        return node.value
    if isinstance(node, ast.Name):
        return _marked_negative(node.id)
    return None


def _exponent(node):
    """An exponent: a constant expression with an integer value.  Python's
    ``**`` is right-associative like ISO's ``^`` (200 xfy), so ``X^2^2`` is
    X^(2^2) (test_a_power_is_right_associative).  An exponent beyond
    ±_MAX_EXPONENT is refused before it is raised to, so ``X^9^9^9`` fails
    fast (test_a_huge_exponent_is_refused)."""
    def variable(identifier):
        raise ValueError(f"exponent is not an integer: {ast.unparse(node)}")
    value = _arithmetic(node, variable, Fraction, Fraction)
    if value.denominator != 1:
        raise ValueError(f"exponent is not an integer: {ast.unparse(node)}")
    if abs(value) > _MAX_EXPONENT:
        raise ValueError(f"exponent is too large: {ast.unparse(node)}")
    return int(value)


def _arithmetic(node, name, number, rational):
    """Walk *node*: *name(id)* for a variable, *number(int)* for a constant,
    *rational(n, d)* for an int/int division; anything else is refused."""
    if isinstance(node, ast.Constant):
        if type(node.value) is not int:
            raise ValueError(f"constant is not an integer: {node.value!r}")
        return number(node.value)
    if isinstance(node, ast.Name):
        negative = _marked_negative(node.id)
        if negative is not None:
            return number(negative)
        return name(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _arithmetic(node.operand, name, number, rational)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        if (isinstance(node.op, ast.Div) and _integer(node.left) is not None
                and _is_int(node.right)):
            return rational(_integer(node.left), node.right.value)
        if isinstance(node.op, ast.Pow):
            return _arithmetic(node.left, name, number, rational) ** _exponent(node.right)
        left = _arithmetic(node.left, name, number, rational)
        right = _arithmetic(node.right, name, number, rational)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
    raise ValueError(f"not allowed in a residual: {ast.unparse(node)}")


def _expression(text, names):
    """A residual side (``2*X + 1/3 - Y``) as a z3 term; variables go in *names*."""
    def variable(identifier):
        if identifier not in names:
            names[identifier] = z3.Real(identifier)
        return names[identifier]
    return _arithmetic(_parse(text), variable, z3.RealVal, z3.Q)


def _constant(text):
    """*text* as an exact Fraction; _NotConstant when it mentions a variable."""
    def variable(identifier):
        raise _NotConstant(identifier)
    return _arithmetic(_parse(text), variable, Fraction, Fraction)


def _sides(constraint):
    constraint = constraint.strip()
    if constraint.startswith("{") and constraint.endswith("}"):
        constraint = constraint[1:-1]
    # Split the text as printed; each side is normalised once, by _parse
    # (test_text_is_normalised_once).
    left, relation, right = _SPLIT.split(constraint, maxsplit=1)
    return left.strip(), relation, right.strip()


def _formula(residual, names):
    """The conjunction of *residual*, and the variable names it mentions."""
    parts, mentioned = [], {}
    for constraint in residual:
        left, relation, right = _sides(constraint)
        parts.append(_RELATIONS[relation](_expression(left, mentioned),
                                          _expression(right, mentioned)))
    for identifier, variable in mentioned.items():
        names.setdefault(identifier, variable)
    return (z3.And(parts) if parts else z3.BoolVal(True)), set(mentioned)


def _closed(residual, names):
    """The residual's formula with its internal (``_``) variables existential."""
    body, mentioned = _formula(residual, names)
    inner = [names[n] for n in sorted(mentioned) if n.startswith("_")]
    return z3.Exists(inner, body) if inner else body


def _rename_internal(residual, side):
    return [re.sub(r"\b(_[A-Za-z0-9_]*)", rf"\1__{side}", c) for c in residual]


def _equivalent(first, second, bindings=None):
    """``(True, "")``, or ``(False, why)`` when z3 finds no proof of equivalence.

    *bindings* (the shown variables' values, equal on both sides) are
    conjoined to both residuals, so ``Y >= X`` with ``X = 3`` is ``Y >= 3``.
    """
    # Each side's internal names are renamed apart, so `_A` on the left and
    # `_A` on the right are different variables.
    first = _rename_internal(first, "left")
    second = _rename_internal(second, "right")
    known = [f"{name}={value.numerator}/{value.denominator}"
             for name, value in (bindings or {}).items() if _is_rational(value)]
    names = {}
    solver = z3.Solver()
    solver.add(z3.Not(_closed(first + known, names) == _closed(second + known, names)))
    verdict = solver.check()
    if verdict == z3.unsat:
        return True, ""
    if verdict == z3.sat:
        model = solver.model()
        shown = {str(d): str(model[d]) for d in model.decls()
                 if not str(d).startswith("_")}
        return False, f"they differ at {shown}"
    return False, f"z3 could not decide ({solver.reason_unknown()})"


# ---- normal form before comparing (ruling R9) ------------------------------

def _is_rational(value):
    return type(value) in (int, Fraction)


def _binding_key(value):
    """Bindings compare by kind and value: 1 == Fraction(1), but 0.5 != 1/2."""
    if _is_rational(value):
        return ("rational", Fraction(value))
    return (type(value).__name__, value)


def _shown(text):
    return bool(_VARIABLE.match(text)) and not text.startswith("_")


def _equality(first, second):
    first, second = sorted((first, second))
    return f"{first}={second}"


def _normalised(answer):
    """*answer* in one form for both systems.

    A residual ``X = c`` (shown variable, constant) becomes the binding
    ``X = c``; an equality of two shown variables, whether printed as a
    binding (``Y = X``) or a constraint, becomes the one constraint
    ``X=Y`` with the names sorted.
    """
    bindings, residual = {}, []
    for name, value in answer.bindings.items():
        if isinstance(value, str) and _shown(value.strip()):
            residual.append(_equality(name, value.strip()))
        else:
            bindings[name] = value
    for constraint in answer.residual:
        left, relation, right = _sides(constraint)
        if relation == "=" and _shown(left) and _shown(right):
            residual.append(_equality(left, right))
            continue
        if relation in ("=", "=:="):
            for variable, other in ((left, right), (right, left)):
                if _shown(variable) and variable not in bindings:
                    try:
                        bindings[variable] = _constant(other)
                        break
                    except _NotConstant:
                        pass
            else:
                residual.append(constraint)
            continue
        residual.append(constraint)
    return Answer(bindings, residual)


def same_solution_sets(left, right):
    """Compare two answer lists in order: ``(True, "")`` or ``(False, why)``."""
    if len(left) != len(right):
        return False, f"{len(left)} answers against {len(right)}"
    for i, (a, b) in enumerate(zip(left, right)):
        a, b = _normalised(a), _normalised(b)
        a_keys = {n: _binding_key(v) for n, v in a.bindings.items()}
        b_keys = {n: _binding_key(v) for n, v in b.bindings.items()}
        if a_keys != b_keys:
            return False, f"answer {i}: bindings {a.bindings} against {b.bindings}"
        ok, why = _equivalent(a.residual, b.residual, a.bindings)
        if not ok:
            return False, f"answer {i}: residual {a.residual} against {b.residual}: {why}"
    return True, ""


# ---- values ---------------------------------------------------------------

def _rational_literal(node):
    """``N/D`` (or ``N rdiv D``) as Prolog prints a rational: two int
    literals, D > 1, in lowest terms; else None."""
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
        return None
    numerator, denominator = _integer(node.left), node.right
    if numerator is None or not _is_int(denominator) or denominator.value <= 1:
        return None
    value = Fraction(numerator, denominator.value)
    return value if value.denominator == denominator.value else None


def _literal(node):
    """*node* as a Fraction when it is a number as Prolog prints one: an int
    literal (``-3`` included), a rational ``N/D`` in lowest terms, or a
    negated rational ``-(N/D)`` with N a positive int; else None.  Nothing
    else is evaluated, so ``1+1``, ``4/2``, ``- (1)`` and ``-(-1/2)`` stay
    text (test_a_binding_is_not_evaluated,
    test_a_binding_rational_is_printed_in_lowest_terms,
    test_a_negated_rational_literal_needs_a_positive_numerator)."""
    integer = _integer(node)
    if integer is not None:
        return Fraction(integer)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = node.operand
        if isinstance(operand, ast.BinOp) and not _is_int(operand.left):
            return None
        value = _rational_literal(operand)
        return None if value is None else -value
    return _rational_literal(node)


_FLOAT = re.compile(r"^-?\d+\.\d+([eE][+-]?\d+)?$")


def _value(text):
    """A printed binding: a Fraction for an exact number, a float for a float
    literal, otherwise the text itself."""
    text = text.strip()
    try:
        value = _literal(_parse(text))
    except ValueError:
        value = None
    if value is not None:
        return value
    if _FLOAT.match(text):
        return float(text)
    return text


def _skip_without_scryer():
    if not pathlib.Path(SCRYER).exists():
        pytest.skip(f"needs the Scryer CLP(Q) build at {SCRYER}")


# ---- Scryer ---------------------------------------------------------------

#: Loaded after the program.  Prints each answer as ``answer``, then one
#: ``binding<TAB>Name<TAB>Value`` line per bound shown variable and one
#: ``constraint<TAB>C`` line per residual constraint, then ``end``.
#:
#: dump/3 raises on a bound variable and FAILS when two of its variables are
#: the same variable (`a(X, Y) :- X = Y`), so it gets one representative of
#: each group of unbound shown variables, and the others are printed as
#: ``R=N`` equalities (test_aliased_shown_variables_keep_their_answer).  A
#: dump that still fails throws, so an answer is never dropped
#: (test_a_failing_dump_raises_instead_of_dropping_the_answer).  The internal
#: variables left in its constraints are named `_I1`, `_I2`, ... .
_SCRYER_HELPER = r"""
:- use_module(library(clpq)).
:- use_module(library(lists)).
:- use_module(library(iso_ext)).

'$clpq_oracle_split'([], [], _, [], [], [], []).
'$clpq_oracle_split'([V|Vs], [N|Ns], Seen, Free, FreeNames, Bound, Aliases) :-
    (   nonvar(V)
    ->  Free = Free1, FreeNames = FreeNames1, Bound = [N-V|Bound1],
        Aliases = Aliases1, Seen1 = Seen
    ;   '$clpq_oracle_seen'(Seen, V, R)
    ->  Free = Free1, FreeNames = FreeNames1, Bound = Bound1,
        Aliases = [R=N|Aliases1], Seen1 = Seen
    ;   Free = [V|Free1], FreeNames = [N|FreeNames1], Bound = Bound1,
        Aliases = Aliases1, Seen1 = [V-N|Seen]
    ),
    '$clpq_oracle_split'(Vs, Ns, Seen1, Free1, FreeNames1, Bound1, Aliases1).

'$clpq_oracle_seen'([W-R|_], V, R) :- W == V, !.
'$clpq_oracle_seen'([_|Seen], V, R) :- '$clpq_oracle_seen'(Seen, V, R).

'$clpq_oracle_answer'(Vs, Ns, Copy-Cs) :-
    '$clpq_oracle_split'(Vs, Ns, [], Free, FreeNames, Bound, Aliases),
    (   dump(Free, FreeNames, Cs0)
    ->  true
    ;   throw(clpq_oracle(dump_failed, Ns))
    ),
    append(Aliases, Cs0, Cs1),
    copy_term(Bound-Cs1, Copy-Cs, _),
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
    if "clpq_oracle(dump_failed" in stdout:
        raise RuntimeError(f"Scryer's dump/3 failed (dump_failed):\n{stdout}")
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
        name = name.strip()
        if not equals or not _VARIABLE.match(name):
            raise ValueError(f"answer item {item!r} is not a binding, in {line!r}")
        if name.startswith("_"):
            continue
        if name not in variables:
            raise ValueError(f"answer binds {name}, which is not among {variables}")
        answer.bindings[name] = _value(value)
    return answer


def clausal_argv(goal):
    return [sys.executable, "-m", "clausal", "-g", goal]


def clausal_answers(program_text: str, goal: str, variables: list, solver: str) -> list:
    """Every answer of *goal* on Clausal with ``CLAUSAL_CLPQ=solver``, in order."""
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
