"""Tests for Z3 bitvector constraints — Phase 6."""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    in_z3_bv, label_z3_bv, z3_check,
    bv_add, bv_sub, bv_mul, bv_udiv, bv_sdiv, bv_urem, bv_srem,
    bv_and, bv_or, bv_xor, bv_not,
    bv_shl, bv_lshr, bv_ashr,
    bv_eq, bv_ne, bv_slt, bv_sle, bv_sgt, bv_sge,
    bv_ult, bv_ule, bv_ugt, bv_uge,
    bv_concat, bv_extract, bv_zext, bv_sext,
    get_z3_state, z3_push,
)


def _sols(gen_fn, *vars):
    """Collect (deref(v) for v in vars) for each solution from gen_fn()."""
    results = []
    for _ in gen_fn():
        results.append(tuple(deref(v) for v in vars))
    return results


class TestInZ3Bv:
    def test_registers_bvsortt(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_bv(x, 8, trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.BitVecSort(8)

    def test_width_32(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_bv(x, 32, trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].size() == 32

    def test_list_of_vars(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        assert in_z3_bv([x, y], 8, trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.BitVecSort(8)
        assert state.var_map[id(y)].sort() == z3.BitVecSort(8)

    def test_ground_int_passes(self):
        # nv
        trail = Trail()
        assert in_z3_bv([42], 8, trail)

    def test_wrong_type_raises(self):
        # nv
        trail = Trail()
        with pytest.raises(TypeError):
            in_z3_bv(["not_a_var"], 8, trail)


class TestLabelZ3Bv:
    def test_unconstrained_8bit_all_values(self):
        """Unconstrained 8-bit var has 256 solutions."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_bv(x, 4, trail)  # 4-bit for speed: 16 solutions
        solutions = []
        for _ in label_z3_bv([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 16
        assert sorted(solutions) == list(range(16))

    def test_all_ground_yields_one(self):
        # nv
        trail = Trail()
        assert len(list(label_z3_bv([5, 3], trail))) == 1

    def test_unregistered_var_raises(self):
        # nv
        trail = Trail()
        x = Var()
        with pytest.raises(ValueError, match="not registered"):
            list(label_z3_bv([x], trail))

    def test_vars_unbound_after(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_bv(x, 4, trail)
        bv_eq(x, 5, trail)
        for _ in label_z3_bv([x], trail):
            pass
        assert is_var(deref(x))


class TestBvArithmetic:
    def test_add_no_overflow(self):
        # nv
        trail = Trail()
        x, y, r = Var(), Var(), Var()
        in_z3_bv([x, y, r], 8, trail)
        bv_add(x, y, r, trail)
        bv_eq(x, 10, trail)
        bv_eq(y, 20, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [30]

    def test_add_wraparound(self):
        """8-bit: 200 + 100 = 44 (mod 256)."""
        # nv
        trail = Trail()
        x, y, r = Var(), Var(), Var()
        in_z3_bv([x, y, r], 8, trail)
        bv_add(x, y, r, trail)
        bv_eq(x, 200, trail)
        bv_eq(y, 100, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [44]

    def test_sub(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_sub(x, 3, r, trail)
        bv_eq(x, 10, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [7]

    def test_mul(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_mul(x, 3, r, trail)
        bv_eq(x, 5, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [15]

    def test_udiv(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_udiv(x, 3, r, trail)
        bv_eq(x, 12, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [4]

    def test_urem(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_urem(x, 5, r, trail)
        bv_eq(x, 13, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [3]

    def test_sdiv(self):
        """Signed division: -128 / 2 = -64 (= 192 unsigned in 8-bit)."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_sdiv(x, 2, r, trail)
        bv_eq(x, 128, trail)  # 128 = -128 signed in 8-bit
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [192]  # -64 unsigned = 192

    def test_srem(self):
        """Signed remainder: -7 % 3 = -1 (= 255 unsigned in 8-bit)."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_srem(x, 3, r, trail)
        bv_eq(x, 249, trail)  # 249 = -7 signed in 8-bit
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [255]  # -1 unsigned = 255


class TestBvBitwise:
    def test_and(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_and(x, 0b1100, r, trail)
        bv_eq(x, 0b1010, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0b1000]

    def test_or(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_or(x, 0b1100, r, trail)
        bv_eq(x, 0b1010, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0b1110]

    def test_xor(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_xor(x, 0b1100, r, trail)
        bv_eq(x, 0b1010, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0b0110]

    def test_not(self):
        """8-bit NOT: ~10 = 245."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_not(x, r, trail)
        bv_eq(x, 10, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [245]


class TestBvShifts:
    def test_shl(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_shl(x, 2, r, trail)
        bv_eq(x, 3, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [12]

    def test_lshr(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_lshr(x, 1, r, trail)
        bv_eq(x, 10, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [5]

    def test_ashr_positive(self):
        """Arithmetic shift right preserves sign: 0b01100000 >> 2 = 0b00011000."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_ashr(x, 2, r, trail)
        bv_eq(x, 0b01100000, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0b00011000]

    def test_ashr_negative(self):
        """Arithmetic shift right sign-extends: 0b10000000 >> 2 = 0b11100000."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_ashr(x, 2, r, trail)
        bv_eq(x, 0b10000000, trail)  # -128 signed
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0b11100000]  # -32 signed = 224 unsigned


class TestBvComparisons:
    def test_bv_eq_constrain(self):
        """bv_eq posts equality as a constraint."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_bv(x, 8, trail)
        bv_eq(x, 42, trail)
        sols = []
        for _ in label_z3_bv([x], trail):
            sols.append(deref(x))
        assert sols == [42]

    def test_bv_ne(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_bv(x, 2, trail)  # 2-bit: values 0-3
        bv_ne(x, 2, trail)
        sols = []
        for _ in label_z3_bv([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [0, 1, 3]

    def test_bv_ult_unsigned(self):
        """Unsigned: 255 < 0 is False (unsigned 255 is 255, not -1)."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_bv([x, y], 8, trail)
        bv_eq(x, 255, trail)
        bv_eq(y, 0, trail)
        # x <_u y → unsat since 255 >_u 0
        bv_ult(x, y, trail)
        assert not z3_check(trail)

    def test_bv_slt_signed(self):
        """Signed: -1 (= 255 in 8-bit) < 0 is True."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_bv([x, y], 8, trail)
        bv_eq(x, 255, trail)  # -1 signed
        bv_eq(y, 0, trail)
        bv_slt(x, y, trail)   # x < y signed → True
        assert z3_check(trail)

    def test_bv_ult_vs_slt_differ(self):
        """Confirms unsigned and signed comparisons differ for high values."""
        # nv
        trail1 = Trail()
        x1, y1 = Var(), Var()
        in_z3_bv([x1, y1], 8, trail1)
        bv_eq(x1, 200, trail1)
        bv_eq(y1, 50, trail1)
        bv_ult(x1, y1, trail1)
        assert not z3_check(trail1)  # 200 >=_u 50

        trail2 = Trail()
        x2, y2 = Var(), Var()
        in_z3_bv([x2, y2], 8, trail2)
        bv_eq(x2, 200, trail2)  # signed: -56
        bv_eq(y2, 50, trail2)
        bv_slt(x2, y2, trail2)
        assert z3_check(trail2)     # -56 <_s 50

    def test_bv_sle(self):
        """Signed <=: -1 (255) <= 0 is True."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_bv([x, y], 8, trail)
        bv_eq(x, 255, trail)
        bv_eq(y, 0, trail)
        bv_sle(x, y, trail)
        assert z3_check(trail)

    def test_bv_sge(self):
        """Signed >=: 0 >= -1 (255) is True."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_bv([x, y], 8, trail)
        bv_eq(x, 0, trail)
        bv_eq(y, 255, trail)
        bv_sge(x, y, trail)
        assert z3_check(trail)

    def test_bv_ule(self):
        """Unsigned <=: 5 <= 10 is True."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_bv([x, y], 8, trail)
        bv_eq(x, 5, trail)
        bv_eq(y, 10, trail)
        bv_ule(x, y, trail)
        assert z3_check(trail)

    def test_bv_ule_fails(self):
        """Unsigned <=: 10 <= 5 is False."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_bv([x, y], 8, trail)
        bv_eq(x, 10, trail)
        bv_eq(y, 5, trail)
        bv_ule(x, y, trail)
        assert not z3_check(trail)

    def test_bv_uge(self):
        """Unsigned >=: 255 >= 200 is True."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_bv([x, y], 8, trail)
        bv_eq(x, 255, trail)
        bv_eq(y, 200, trail)
        bv_uge(x, y, trail)
        assert z3_check(trail)


class TestBvStructural:
    def test_extract_upper_nibble(self):
        """Extract bits [7:4] of 8-bit value 0xAB → 0xA."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv(x, 8, trail)
        bv_eq(x, 0xAB, trail)
        bv_extract(7, 4, x, r, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0xA]

    def test_extract_lower_nibble(self):
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv(x, 8, trail)
        bv_eq(x, 0xAB, trail)
        bv_extract(3, 0, x, r, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0xB]

    def test_concat_two_4bit(self):
        """Concat 4-bit 0xA and 0xB → 8-bit 0xAB."""
        # nv
        trail = Trail()
        x, y, r = Var(), Var(), Var()
        in_z3_bv([x, y], 4, trail)
        bv_eq(x, 0xA, trail)
        bv_eq(y, 0xB, trail)
        bv_concat(x, y, r, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0xAB]

    def test_zext(self):
        """Zero-extend 4-bit 5 to 8-bit → 5."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv(x, 4, trail)
        bv_eq(x, 5, trail)
        bv_zext(x, 4, r, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [5]

    def test_sext_positive(self):
        """Sign-extend 4-bit 5 (positive) to 8-bit → 5."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv(x, 4, trail)
        bv_eq(x, 5, trail)
        bv_sext(x, 4, r, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [5]

    def test_sext_negative(self):
        """Sign-extend 4-bit 0xF (= -1) to 8-bit → 0xFF (= 255 unsigned)."""
        # nv
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv(x, 4, trail)
        bv_eq(x, 0xF, trail)
        bv_sext(x, 4, r, trail)
        sols = []
        for _ in label_z3_bv([r], trail):
            sols.append(deref(r))
        assert sols == [0xFF]


class TestBvBacktracking:
    def test_bv_constraint_retracted_on_undo(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_bv(x, 4, trail)
        mark = trail.mark()
        bv_eq(x, 5, trail)
        # Only 5 is reachable now
        assert list(label_z3_bv([x], trail)) == [None]
        assert deref(x) == 5 or is_var(deref(x))  # may be unbound after label
        trail.undo(mark)
        # Constraint retracted — all 16 values reachable
        count = sum(1 for _ in label_z3_bv([x], trail))
        assert count == 16

    def test_z3_try_works_for_bv_comparison(self):
        """Direct BV probes work via solver.push/pop (Phase 3 Issue 6 resolution)."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_bv(x, 8, trail)
        bv_eq(x, 5, trail)
        state = get_z3_state(trail)
        z3_x = state.var_map[id(x)]
        # Probe: is x < 10? Yes (x=5 < 10)
        state.solver.push()
        state.solver.add(z3.ULT(z3_x, z3.BitVecVal(10, 8)))
        assert state.solver.check() == z3.sat
        state.solver.pop()
        # Probe: is x > 10? No (x=5 <= 10)
        state.solver.push()
        state.solver.add(z3.UGT(z3_x, z3.BitVecVal(10, 8)))
        assert state.solver.check() == z3.unsat
        state.solver.pop()
