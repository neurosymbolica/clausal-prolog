from clausal.logic.variables import Var, Trail, unify, deref


class TestBytesUnifiesWithIntList:
    def test_basic(self):
        # nv
        assert unify(b"abc", [97, 98, 99], Trail())

    def test_symmetric(self):
        # nv
        assert unify([97, 98, 99], b"abc", Trail())

    def test_empty(self):
        # nv
        assert unify(b"", [], Trail())

    def test_length_mismatch_fails(self):
        # nv
        assert not unify(b"abc", [97, 98], Trail())


class TestBytesListVarBinding:
    def test_all_vars(self):
        # nv
        trail = Trail()
        X, Y, Z = Var(), Var(), Var()
        assert unify(b"abc", [X, Y, Z], trail)
        assert deref(X) == 97 and deref(Y) == 98 and deref(Z) == 99

    def test_partial_vars(self):
        # nv
        trail = Trail()
        X = Var()
        assert unify(b"abc", [97, X, 99], trail)
        assert deref(X) == 98


class TestBytesPromiscuityAndGuards:
    def test_out_of_range_int_fails(self):
        # nv  — no byte equals 256; unification fails (not an error)
        assert not unify(b"abc", [256, 98, 99], Trail())

    def test_non_int_element_fails(self):
        # nv
        assert not unify(b"abc", ["a", 98, 99], Trail())

    def test_promiscuity_intentional(self):
        # nv  — documented: a bytes present on one side coerces the match
        assert unify(b"\x01\x02\x03", [1, 2, 3], Trail())

    def test_plain_intlists_stay_intlists(self):
        # nv  — no bytes present → no coercion, still unify as int-lists
        assert unify([1, 2, 3], [1, 2, 3], Trail())


class TestBytesNoCrossWithStr:
    def test_str_does_not_unify_with_bytes(self):
        # nv
        assert not unify("abc", b"abc", Trail())

    def test_charlist_does_not_unify_with_bytes(self):
        # nv
        assert not unify(["a", "b", "c"], b"abc", Trail())


class TestBytesNoFixedPoint:
    def test_byte_decomposes_to_int(self):
        # nv  — b"a" decomposes to [97], not to itself
        assert unify(b"a", [97], Trail())

    def test_byte_does_not_unify_with_singleton_bytes_list(self):
        # nv  — b"a" does not unify with [b"a"]
        assert not unify(b"a", [b"a"], Trail())


from clausal.logic.builtins._helpers import _functor_name, _arity, _nth_arg, _args_list


class TestBytesDecomposition:
    def test_functor_name_nonempty(self):
        # nv
        assert _functor_name(b"abc") == "."

    def test_functor_name_empty(self):
        # nv
        assert _functor_name(b"") == "[]"

    def test_arity_nonempty(self):
        # nv
        assert _arity(b"abc") == 2

    def test_arity_empty(self):
        # nv
        assert _arity(b"") == 0

    def test_nth_arg_head_is_int(self):
        # nv  — codes model: head is an int, no fixed point
        assert _nth_arg(b"abc", 1) == 97

    def test_nth_arg_tail_is_bytes(self):
        # nv
        assert _nth_arg(b"abc", 2) == b"bc"

    def test_args_list(self):
        # nv
        assert _args_list(b"abc") == [97, b"bc"]

    def test_args_list_empty(self):
        # nv
        assert _args_list(b"") == []


class TestBytesTypePreservation:
    def test_bound_var_stays_bytes_and_methods_work(self):
        # nv  — a bytes threaded through unify stays bytes; methods callable
        trail = Trail()
        X = Var()
        assert unify(X, b"\x48\x49", trail)
        v = deref(X)
        assert type(v) is bytes
        assert v.hex() == "4849"
        assert v.decode() == "HI"

    def test_tail_of_bytes_decomposition_stays_bytes(self):
        # nv  — [H, *T] is b"abc": T preserves bytes, supports .decode()
        from clausal.logic.runtime.body_star_unify import _body_star_unify
        trail = Trail()
        H, T = Var(), Var()
        assert _body_star_unify(b"abc", [H], T, [], trail)
        assert deref(T).decode() == "bc"
