"""Queries for the exact comparison with Scryer's library(clpq), and the
batch driver that puts many of them to one Scryer process.

A query is the text of a Prolog conjunction over X0..X{n-1} (Clausal's
reader and Scryer read the same text), with the variables to show.  The
port's side is ``port_answers`` of tests/clpq_port/test_against_oracle.py
(the Python-API driver: Clausal's reader, nf.pl's ``{}/1``, the engine's
unify for ``=``); Scryer's is ``oracle_goal`` of tests/clpq_oracle.py,
dump/3 on the shown variables.  oracle_answers runs one Scryer process per
query (about 0.3 s each); :func:`scryer_batch` runs a few dozen per
process, each between its own markers.
"""
import pathlib
import random
import re
import tempfile
from fractions import Fraction

from tests._oracles import run_scryer
from tests.clpq_oracle import _SCRYER_HELPER, _parse_oracle, oracle_goal


def _coefficient(rng):
    while True:
        value = rng.randint(-4, 4)
        if value:
            if rng.random() < 0.1:
                return Fraction(value, rng.randint(2, 3))
            return Fraction(value)


def _number_text(value):
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _linear(terms):
    """``2*X0 - 1/2*X3 + X5``, every coefficient written out in front."""
    parts = []
    for index, coefficient in terms:
        sign = "-" if coefficient < 0 else "+"
        magnitude = abs(coefficient)
        if magnitude == 1:
            body = f"X{index}"
        elif magnitude.denominator == 1:
            body = f"{magnitude.numerator}*X{index}"
        else:
            body = f"({magnitude.numerator}/{magnitude.denominator})*X{index}"
        parts.append((sign, body))
    text = ("-" if parts[0][0] == "-" else "") + parts[0][1]
    for sign, body in parts[1:]:
        text += f" {sign} {body}"
    return text


def query(seed, size):
    """(id, text, shown) of one seeded query over *size* variables: a box
    on most variables, sparse rows (band or random), a few equations and
    disequations, bindings and aliases between the posts, then one of an
    optimum (sup/inf into S), bb_inf/5 with its vertex, or nothing; shown
    are all variables, or for a band sometimes a subset (a projection).
    Every row holds at a hidden integer point, so most queries have an
    answer; a binding or alias agrees with the point."""
    rng = random.Random(f"scryer:{size}:{seed}")
    point = [rng.randint(0, 6) for _ in range(size)]
    goals = []
    banded = rng.random() < 0.5
    width = rng.randint(2, 3)
    for i in range(size):
        if rng.random() < 0.85:
            low, high = rng.randint(-3, 0), rng.randint(6, 12)
            goals.append(f"{{X{i} >= {low}, X{i} =< {high}}}")
    rows = size + rng.randint(0, size // 2)
    for r in range(rows):
        if banded:
            start = r % max(1, size - width + 1)
            indices = list(range(start, min(size, start + width)))
        else:
            indices = sorted(rng.sample(range(size), rng.randint(2, min(4, size))))
        terms = [(i, _coefficient(rng)) for i in indices]
        at_point = sum(c * point[i] for i, c in terms)
        k = rng.random()
        if k < 0.08:
            relation, constant = "=:=", at_point
        elif k < 0.12:
            relation, constant = "=\\=", at_point + rng.choice([-2, -1, 1, 2])
        else:
            relation = rng.choice(["=<", "<", ">=", ">", "=<"])
            slack = rng.randint(0, 4) + (1 if relation in ("<", ">") else 0)
            constant = at_point + (slack if relation in ("=<", "<") else -slack)
        goals.append(f"{{{_linear(terms)} {relation} {_number_text(constant)}}}")
        if rng.random() < 0.06:
            i = rng.randrange(size)
            goals.append(f"X{i} = {point[i]}")
        elif rng.random() < 0.06:
            i = rng.randrange(size)
            twins = [j for j in range(size) if j != i and point[j] == point[i]]
            if twins:
                goals.append(f"X{i} = X{rng.choice(twins)}")
    text = ", ".join(goals)
    shown = [f"X{i}" for i in range(size)
             if re.search(rf"\bX{i}\b", text)]
    k = rng.random()
    if k < 0.3:
        terms = [(i, _coefficient(rng)) for i in
                 sorted(rng.sample(range(size), rng.randint(1, 4)))]
        goals.append(f"{rng.choice(['sup', 'inf'])}({_linear(terms)}, S)")
        shown.append("S")
    elif k < 0.45:
        integers = sorted(rng.sample(range(size), rng.randint(1, 3)))
        terms = [(i, _coefficient(rng)) for i in integers]
        vertex = [f"V{i}" for i in range(len(integers))]
        goals.append(f"bb_inf([{', '.join(f'X{i}' for i in integers)}], "
                     f"{_linear(terms)}, I, [{', '.join(vertex)}], 0)")
        shown += ["I"] + vertex
    if banded and rng.random() < 0.3:
        keep = sorted(rng.sample(range(size), rng.randint(max(1, size - 3), size)))
        shown = [n for n in shown if not n.startswith("X") or int(n[1:]) in keep]
    return f"scryer-{size}-{seed}", ", ".join(goals), shown


def queries(full=False):
    """The default set: 40 queries of 10 to 25 variables (about ten
    seconds of Scryer); the full set (CLPQ_DIFFERENTIAL=full): 300 of 10
    to 40 (about four minutes)."""
    if full:
        sizes, count = (10, 12, 15, 20, 25, 30, 40), 300
    else:
        sizes, count = (10, 12, 15, 20, 25), 40
    return [query(seed, sizes[seed % len(sizes)]) for seed in range(count)]


def scryer_batch(batch, timeout=900):
    """Scryer's answers to each (id, text, shown) of *batch*, one process
    for the lot: {id: [Answer, ...]} or {id: ("error", text)} for a query
    that raised or did not finish."""
    program_text = ":- use_module(library(clpq)).\n"
    goals = []
    for index, (_, text, shown) in enumerate(batch):
        goals.append(f"write('@@begin {index}'), nl, "
                     f"catch(({oracle_goal(text, shown)}), E, "
                     f"(write('@@error '), writeq(E), nl))")
    with tempfile.TemporaryDirectory() as directory:
        program = pathlib.Path(directory, "program.pl")
        program.write_text(program_text)
        helper = pathlib.Path(directory, "clpq_oracle_helper.pl")
        helper.write_text(_SCRYER_HELPER)
        result = run_scryer([str(program), str(helper)], goals, cwd=directory,
                            timeout=timeout)
    chunks = {}
    current = None
    for line in result.stdout.splitlines():
        if line.startswith("@@begin "):
            current = int(line.split()[1])
            chunks[current] = []
        elif current is not None:
            chunks[current].append(line)
    answers = {}
    for index, (name, _, _) in enumerate(batch):
        lines = chunks.get(index)
        if lines is None:
            answers[name] = ("error", "no output")
            continue
        text = "\n".join(lines)
        if "@@error" in text:
            answers[name] = ("error", text)
            continue
        try:
            answers[name] = _parse_oracle(text)
        except RuntimeError as error:
            answers[name] = ("error", str(error))
    return answers
