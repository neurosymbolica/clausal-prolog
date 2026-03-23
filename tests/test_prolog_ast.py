"""Tests for Prolog AST nodes, visitor, transformer, and builders."""
import pytest
from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PQuery, PModule,
    PrologVisitor, PrologTransformer,
    atom, var, anon, compound, op, prefix, plist, cons,
    fact, rule, dcg_rule, directive, module,
    variables, functors, is_ground, term_size, subterms,
)


class TestNodeConstruction:
    def test_atom(self):
        a = PAtom("foo")
        assert a.name == "foo"
        assert a.quoted is False

    def test_atom_quoted(self):
        a = PAtom("Hello World", quoted=True)
        assert a.quoted is True

    def test_var(self):
        v = PVar("X")
        assert v.name == "X"

    def test_number_int(self):
        n = PNumber(42)
        assert n.value == 42

    def test_number_float(self):
        n = PNumber(3.14)
        assert n.value == 3.14

    def test_compound(self):
        c = PCompound("foo", (PAtom("a"), PVar("X")))
        assert c.functor == "foo"
        assert len(c.args) == 2

    def test_list_proper(self):
        l = PList((PNumber(1), PNumber(2), PNumber(3)))
        assert l.tail is None

    def test_list_partial(self):
        l = PList((PVar("H"),), tail=PVar("T"))
        assert l.tail == PVar("T")

    def test_clause_fact(self):
        c = PClause(head=PCompound("edge", (PNumber(1), PNumber(2))))
        assert c.body is None

    def test_clause_rule(self):
        c = PClause(
            head=PCompound("reach", (PVar("X"), PVar("Y"))),
            body=PCompound("edge", (PVar("X"), PVar("Y")))
        )
        assert c.body is not None

    def test_dcg_rule(self):
        r = PDCGRule(
            head=PAtom("greeting"),
            body=PList((PAtom("hello"), PAtom("world")))
        )
        assert r.head == PAtom("greeting")

    def test_directive(self):
        d = PDirective(PCompound("dynamic", (PAtom("foo"),)))
        assert isinstance(d.body, PCompound)

    def test_query(self):
        q = PQuery(PCompound("member", (PVar("X"), PList((PNumber(1), PNumber(2))))))
        assert isinstance(q.body, PCompound)

    def test_module(self):
        m = PModule(items=(
            PClause(head=PCompound("edge", (PNumber(1), PNumber(2)))),
        ), source_path="test.pl")
        assert len(m.items) == 1
        assert m.source_path == "test.pl"

    def test_string(self):
        s = PString("hello")
        assert s.value == "hello"

    def test_curly(self):
        c = PCurly(PCompound(">", (PVar("X"), PNumber(0))))
        assert isinstance(c.body, PCompound)

    def test_frozen(self):
        a = PAtom("foo")
        with pytest.raises(AttributeError):
            a.name = "bar"  # type: ignore

    def test_compound_frozen(self):
        c = PCompound("f", (PAtom("a"),))
        with pytest.raises(AttributeError):
            c.functor = "g"  # type: ignore


class TestBuilders:
    def test_atom_builder(self):
        assert atom("foo") == PAtom("foo")

    def test_var_builder(self):
        assert var("X") == PVar("X")

    def test_anon_builder(self):
        assert anon() == PVar("_")

    def test_compound_builder(self):
        c = compound("foo", atom("a"), var("X"))
        assert c == PCompound("foo", (PAtom("a"), PVar("X")))

    def test_op_builder(self):
        o = op(",", atom("a"), atom("b"))
        assert o == PCompound(",", (PAtom("a"), PAtom("b")))

    def test_prefix_builder(self):
        p = prefix("\\+", atom("a"))
        assert p == PCompound("\\+", (PAtom("a"),))

    def test_plist_builder(self):
        l = plist(PNumber(1), PNumber(2), PNumber(3))
        assert l == PList((PNumber(1), PNumber(2), PNumber(3)))

    def test_plist_with_tail(self):
        l = plist(var("H"), tail=var("T"))
        assert l == PList((PVar("H"),), tail=PVar("T"))

    def test_cons_builder(self):
        c = cons(var("H"), var("T"))
        assert c == PList((PVar("H"),), tail=PVar("T"))

    def test_fact_builder(self):
        f = fact(compound("edge", PNumber(1), PNumber(2)))
        assert isinstance(f, PClause)
        assert f.body is None

    def test_rule_builder(self):
        r = rule(compound("reach", var("X"), var("Y")),
                 compound("edge", var("X"), var("Y")))
        assert isinstance(r, PClause)
        assert r.body is not None

    def test_dcg_rule_builder(self):
        r = dcg_rule(atom("greeting"), plist(atom("hello"), atom("world")))
        assert isinstance(r, PDCGRule)

    def test_directive_builder(self):
        d = directive(compound("dynamic", atom("foo")))
        assert isinstance(d, PDirective)

    def test_module_builder(self):
        m = module(fact(atom("a")), source_path="test.pl")
        assert isinstance(m, PModule)
        assert len(m.items) == 1
        assert m.source_path == "test.pl"


class TestIntrospection:
    def test_variables_simple(self):
        t = PCompound("foo", (PVar("X"), PAtom("a"), PVar("Y")))
        assert variables(t) == {"X", "Y"}

    def test_variables_excludes_anon(self):
        t = PCompound("foo", (PVar("_"), PVar("X")))
        assert variables(t) == {"X"}

    def test_variables_nested(self):
        t = PCompound(",", (
            PCompound("foo", (PVar("X"),)),
            PCompound("bar", (PVar("Y"), PVar("X")))
        ))
        assert variables(t) == {"X", "Y"}

    def test_variables_in_list(self):
        t = PList((PVar("H"),), tail=PVar("T"))
        assert variables(t) == {"H", "T"}

    def test_functors(self):
        t = PCompound(",", (
            PCompound("edge", (PVar("X"), PVar("Z"))),
            PCompound("reach", (PVar("Z"), PVar("Y")))
        ))
        assert ("edge", 2) in functors(t)
        assert ("reach", 2) in functors(t)
        assert (",", 2) in functors(t)

    def test_functors_no_compounds(self):
        t = PVar("X")
        assert functors(t) == set()

    def test_is_ground_true(self):
        assert is_ground(PCompound("foo", (PNumber(1), PAtom("a"))))

    def test_is_ground_false(self):
        assert not is_ground(PCompound("foo", (PVar("X"),)))

    def test_is_ground_anon_false(self):
        assert not is_ground(PCompound("foo", (PVar("_"),)))

    def test_is_ground_atom(self):
        assert is_ground(PAtom("hello"))

    def test_is_ground_number(self):
        assert is_ground(PNumber(42))

    def test_is_ground_list(self):
        assert is_ground(PList((PNumber(1), PNumber(2))))

    def test_is_ground_list_with_tail_var(self):
        assert not is_ground(PList((PNumber(1),), tail=PVar("T")))

    def test_term_size(self):
        t = PCompound("f", (PAtom("a"), PCompound("g", (PNumber(1),))))
        assert term_size(t) == 4  # f, a, g, 1

    def test_term_size_atom(self):
        assert term_size(PAtom("x")) == 1

    def test_term_size_list(self):
        t = PList((PNumber(1), PNumber(2), PNumber(3)))
        assert term_size(t) == 4  # list + 3 elements

    def test_subterms(self):
        t = PCompound("f", (PAtom("a"), PNumber(1)))
        subs = list(subterms(t))
        assert subs == [t, PAtom("a"), PNumber(1)]

    def test_subterms_nested(self):
        inner = PCompound("g", (PNumber(1),))
        t = PCompound("f", (PAtom("a"), inner))
        subs = list(subterms(t))
        assert subs == [t, PAtom("a"), inner, PNumber(1)]


class TestVisitor:
    def test_collects_atoms(self):
        class AtomCollector(PrologVisitor):
            def __init__(self):
                self.atoms = []
            def visit_PAtom(self, node):
                self.atoms.append(node.name)

        t = PCompound("foo", (PAtom("a"), PAtom("b")))
        v = AtomCollector()
        v.visit(t)
        assert v.atoms == ["a", "b"]

    def test_collects_vars(self):
        class VarCollector(PrologVisitor):
            def __init__(self):
                self.vars = []
            def visit_PVar(self, node):
                self.vars.append(node.name)

        t = PCompound(",", (
            PCompound("foo", (PVar("X"),)),
            PCompound("bar", (PVar("Y"),))
        ))
        v = VarCollector()
        v.visit(t)
        assert v.vars == ["X", "Y"]

    def test_visits_list_elements(self):
        class NumCollector(PrologVisitor):
            def __init__(self):
                self.nums = []
            def visit_PNumber(self, node):
                self.nums.append(node.value)

        t = PList((PNumber(1), PNumber(2)), tail=PNumber(3))
        v = NumCollector()
        v.visit(t)
        assert v.nums == [1, 2, 3]

    def test_visits_curly(self):
        class AtomCollector(PrologVisitor):
            def __init__(self):
                self.atoms = []
            def visit_PAtom(self, node):
                self.atoms.append(node.name)

        t = PCurly(PAtom("goal"))
        v = AtomCollector()
        v.visit(t)
        assert v.atoms == ["goal"]

    def test_visits_clause(self):
        class VarCollector(PrologVisitor):
            def __init__(self):
                self.vars = []
            def visit_PVar(self, node):
                self.vars.append(node.name)

        c = PClause(
            head=PCompound("foo", (PVar("X"),)),
            body=PCompound("bar", (PVar("Y"),))
        )
        v = VarCollector()
        v.visit(c)
        assert set(v.vars) == {"X", "Y"}

    def test_visits_module(self):
        class ClauseCounter(PrologVisitor):
            def __init__(self):
                self.count = 0
            def visit_PClause(self, node):
                self.count += 1
                self.generic_visit(node)

        m = PModule(items=(
            PClause(head=PAtom("a")),
            PClause(head=PAtom("b")),
        ))
        v = ClauseCounter()
        v.visit(m)
        assert v.count == 2


class TestTransformer:
    def test_rename_vars(self):
        class VarRenamer(PrologTransformer):
            def visit_PVar(self, node):
                return PVar(node.name + "_renamed")

        t = PCompound("foo", (PVar("X"), PAtom("a")))
        result = VarRenamer().visit(t)
        assert result == PCompound("foo", (PVar("X_renamed"), PAtom("a")))

    def test_identity(self):
        t = PCompound("foo", (PAtom("a"), PNumber(1)))
        result = PrologTransformer().visit(t)
        assert result is t  # unchanged → same object

    def test_transform_nested(self):
        class DoubleNumbers(PrologTransformer):
            def visit_PNumber(self, node):
                return PNumber(node.value * 2)

        t = PCompound("f", (PNumber(1), PCompound("g", (PNumber(2),))))
        result = DoubleNumbers().visit(t)
        assert result == PCompound("f", (PNumber(2), PCompound("g", (PNumber(4),))))

    def test_transform_list(self):
        class DoubleNumbers(PrologTransformer):
            def visit_PNumber(self, node):
                return PNumber(node.value * 2)

        t = PList((PNumber(1), PNumber(2)), tail=PNumber(3))
        result = DoubleNumbers().visit(t)
        assert result == PList((PNumber(2), PNumber(4)), tail=PNumber(6))

    def test_transform_clause(self):
        class VarRenamer(PrologTransformer):
            def visit_PVar(self, node):
                return PVar(node.name.lower())

        c = PClause(
            head=PCompound("foo", (PVar("X"),)),
            body=PCompound("bar", (PVar("Y"),))
        )
        result = VarRenamer().visit(c)
        assert result == PClause(
            head=PCompound("foo", (PVar("x"),)),
            body=PCompound("bar", (PVar("y"),))
        )

    def test_transform_module_delete_item(self):
        class RemoveFacts(PrologTransformer):
            def visit_PClause(self, node):
                if node.body is None:
                    return None  # delete facts
                return self.generic_visit(node)

        m = PModule(items=(
            PClause(head=PAtom("a")),
            PClause(head=PAtom("b"), body=PAtom("c")),
            PClause(head=PAtom("d")),
        ))
        result = RemoveFacts().visit(m)
        assert len(result.items) == 1
        assert result.items[0].head == PAtom("b")

    def test_transform_curly(self):
        class VarRenamer(PrologTransformer):
            def visit_PVar(self, node):
                return PVar(node.name + "2")

        t = PCurly(PVar("X"))
        result = VarRenamer().visit(t)
        assert result == PCurly(PVar("X2"))

    def test_transform_dcg_rule(self):
        class VarRenamer(PrologTransformer):
            def visit_PVar(self, node):
                return PVar(node.name + "2")

        r = PDCGRule(
            head=PCompound("digit", (PVar("D"),)),
            body=PList((PVar("D"),))
        )
        result = VarRenamer().visit(r)
        assert result == PDCGRule(
            head=PCompound("digit", (PVar("D2"),)),
            body=PList((PVar("D2"),))
        )

    def test_transform_directive(self):
        class AtomRenamer(PrologTransformer):
            def visit_PAtom(self, node):
                return PAtom(node.name.upper())

        d = PDirective(PCompound("dynamic", (PAtom("foo"),)))
        result = AtomRenamer().visit(d)
        # PCompound.functor is a str field, not visited — only PAtom args change
        assert result == PDirective(PCompound("dynamic", (PAtom("FOO"),)))
