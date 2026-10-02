"""py.* wrappers: a right-typed value the library rejects RAISES.

RULED 2026-10-02 (follow-up to the type_error / instantiation_error ruling):
a value of the right type that is out of range or invalid -- month 13, an
unknown hash algorithm, malformed JSON, iterations <= 0 -- raises the ISO
``error(domain_error(Domain, Culprit), Context)`` with the predicate as
context, instead of failing the goal with a diagnostic note.  The domain is
ISO's name where ISO has one (``not_less_than_zero``) and the wrapper's own
otherwise.  Each case below failed silently before.

The per-module test files hold the flipped ``*_fails`` tests; this file
holds the cases that had no test of their own.
"""

from __future__ import annotations

import datetime as dt
import math
import textwrap

import pytest

from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var
from clausal.modules.py.datetime import _dt_to_term as _T


def raised(fn, *args):
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


def _err(formal, name, arity):
    return ("error", formal, ("/", name, arity))


# ── datetime ─────────────────────────────────────────────────────────────


def test_timedelta_out_of_range_raises_domain_error():
    from clausal.modules.py.datetime import _timedelta_3
    s = Var()
    term = raised(_timedelta_3, 10 ** 10, s, Var())
    assert term[1][:2] == ("domain_error", "timedelta")
    assert term[1][2][:2] == ("timedelta", 10 ** 10)
    assert term[2] == ("/", "timedelta", 3)


@pytest.mark.parametrize("fn_name", ["_date_add_3", "_date_sub_3"])
def test_date_arithmetic_past_the_calendar_raises_representation_error(fn_name):
    # Each argument is in its domain; the RESULT is past year 9999 / before
    # year 1 -- an implementation-defined limit (ISO 7.12.2 g).
    import clausal.modules.py.datetime as m
    fn = getattr(m, fn_name)
    d = _T(dt.date(9999, 12, 31) if fn_name == "_date_add_3" else dt.date(1, 1, 1))
    td = _T(dt.timedelta(days=1))
    name = fn_name[1:-2]
    assert raised(fn, d, td, Var()) == _err(
        ("representation_error", "date"), name, 3)


@pytest.mark.parametrize("fn_name", ["_date_diff_3", "_days_between_3"])
def test_date_and_datetime_mix_raises_type_error(fn_name):
    import clausal.modules.py.datetime as m
    fn = getattr(m, fn_name)
    d, t = _T(dt.date(2026, 3, 16)), _T(dt.datetime(2026, 3, 16, 9))
    name = fn_name[1:-2]
    assert raised(fn, d, t, Var()) == _err(("type_error", "date", t), name, 3)
    assert raised(fn, t, d, Var()) == _err(("type_error", "datetime", d), name, 3)


def test_naive_and_aware_mix_raises_domain_error():
    from clausal.modules.py.datetime import _date_diff_3
    naive = _T(dt.datetime(2026, 3, 16, 9))
    aware = _T(dt.datetime(2026, 3, 16, 9, tzinfo=dt.timezone.utc))
    assert raised(_date_diff_3, naive, aware, Var()) == _err(
        ("domain_error", "naive_datetime", aware), "date_diff", 3)


def test_date_between_datetime_then_date_raises_type_error():
    from clausal.modules.py.datetime import _date_between_3
    d, t = _T(dt.date(2026, 3, 16)), _T(dt.datetime(2026, 3, 16, 9))
    with pytest.raises(LogicException) as info:
        list(_date_between_3(None, "P", "F", None, t, d, Var(), Trail()))
    assert info.value.term == _err(("type_error", "datetime", d),
                                   "date_between", 3)


@pytest.mark.parametrize("stamp", [float("nan"), 1e20])
def test_timestamp_out_of_range_raises_domain_error(stamp):
    from clausal.modules.py.datetime import _timestamp_2
    term = raised(_timestamp_2, Var(), stamp)
    assert term[1][:2] == ("domain_error", "timestamp")
    culprit = term[1][2]
    assert culprit == stamp or (math.isnan(culprit) and math.isnan(stamp))
    assert term[2] == ("/", "timestamp", 2)


# ── json ─────────────────────────────────────────────────────────────────


def test_json_parse3_malformed_raises_domain_error():
    from clausal.modules.py.json import _parse_3
    s = chars("[1,")
    assert raised(_parse_3, s, Var(), []) == _err(
        ("domain_error", "json_text", s), "parse", 3)


def test_json_read_file_not_json_raises_domain_error(tmp_path):
    from clausal.modules.py.json import _read_file_2
    p = tmp_path / "x.json"
    p.write_text("{not json")
    path = chars(str(p))
    assert raised(_read_file_2, path, Var()) == _err(
        ("domain_error", "json_file", path), "read_file", 2)


def test_json_write_file_unserialisable_raises_and_writes_nothing(tmp_path):
    from clausal.modules.py.json import _write_file_2
    p = tmp_path / "out.json"
    assert raised(_write_file_2, chars(str(p)), [b"x"]) == _err(
        ("type_error", "json_term", b"x"), "py.json.write_file", 2)
    assert not p.exists()


def test_json_generate_non_integral_rational_raises_type_error():
    # 1/3 has no exact JSON number (RULED 2026-10-02).
    from fractions import Fraction
    from clausal.modules.py.json import _generate_2
    assert raised(_generate_2, [Fraction(1, 3)], Var()) == _err(
        ("type_error", "json_term", Fraction(1, 3)), "py.json.generate", 2)


def test_json_generate_writes_exact_numbers():
    # RULED 2026-10-02: a decimal is its exact digits, an integral rational
    # its integer; a float stays a float.
    from decimal import Decimal
    from fractions import Fraction
    from clausal.logic.cells import chars_text
    from clausal.logic.variables import deref
    from clausal.modules.py.json import _generate_2, _pretty_generate_2
    from clausal.terms import DictTerm
    out = Var()
    term = [Decimal("0.10"), Decimal("1E+2"), Fraction(4, 2), 1.5,
            DictTerm({"k": Decimal("2.50")})]
    assert len(list(_generate_2(term, out, Trail(), None))) == 1
    assert chars_text(deref(out)) == '[0.10, 1E+2, 2, 1.5, {"k": 2.50}]'
    out = Var()
    assert len(list(_pretty_generate_2([Decimal("3.14")], out, Trail(), None))) == 1
    assert chars_text(deref(out)) == "[\n  3.14\n]"


def test_json_generate_decimal_round_trips_through_parse():
    from decimal import Decimal
    import json
    from clausal.logic.cells import chars_text
    from clausal.logic.variables import deref
    from clausal.modules.py.json import _generate_2
    out = Var()
    list(_generate_2([Decimal("0.1")], out, Trail(), None))
    assert json.loads(chars_text(deref(out)), parse_float=Decimal) == [Decimal("0.1")]


def test_json_generate_nan_decimal_raises_type_error():
    from decimal import Decimal
    from clausal.modules.py.json import _generate_2
    term = raised(_generate_2, [Decimal("NaN")], Var())
    assert term[1][:2] == ("type_error", "json_term")


def test_json_write_file_writes_exact_decimal(tmp_path):
    from decimal import Decimal
    from clausal.modules.py.json import _write_file_2
    p = tmp_path / "d.json"
    assert len(list(_write_file_2(chars(str(p)), [Decimal("1.50")], Trail(), None))) == 1
    assert "1.50" in p.read_text()


# ── http ─────────────────────────────────────────────────────────────────


def test_http_request_without_url_key_raises_domain_error():
    from clausal.modules.py.http import _request_3
    from clausal.terms import DictTerm
    opts = DictTerm({"method": chars("GET")})
    assert raised(_request_3, opts, Var(), Var()) == _err(
        ("domain_error", "http_request_options", opts), "request", 3)


def test_http_request_negative_timeout_raises_domain_error(monkeypatch):
    import clausal.modules.py.http as http
    from clausal.terms import DictTerm
    monkeypatch.setattr(http, "_urlopen", lambda *a, **k: pytest.fail("sent"))
    opts = DictTerm({"url": chars("http://x.test/"), "timeout": -1})
    assert raised(http._request_3, opts, Var(), Var()) == _err(
        ("domain_error", "not_less_than_zero", -1), "request", 3)


def test_http_request_non_number_timeout_raises_type_error():
    import clausal.modules.py.http as http
    from clausal.terms import DictTerm
    opts = DictTerm({"url": chars("http://x.test/"), "timeout": "soon"})
    assert raised(http._request_3, opts, Var(), Var()) == _err(
        ("type_error", "number", "soon"), "request", 3)


@pytest.mark.parametrize("url", ["ftpx://a/b", "http:///path", "http://[::1"])
def test_http_unusable_url_raises_domain_error(url):
    # urllib refuses these itself, before any network traffic.
    from clausal.modules.py.http import _get_2
    u = chars(url)
    assert raised(_get_2, u, Var()) == _err(("domain_error", "url", u), "get", 2)


def test_http_network_failure_still_fails(monkeypatch):
    # A refused connection is the network's answer, not the caller's value.
    import urllib.error
    import clausal.modules.py.http as http

    def refuse(*a, **k):
        raise urllib.error.URLError(ConnectionRefusedError(111, "refused"))
    monkeypatch.setattr(http, "_urlopen", refuse)
    assert list(http._get_2(chars("http://x.test/"), Var(), Trail(), None)) == []


# ── csv ──────────────────────────────────────────────────────────────────


def test_csv_generate_unbound_cell_raises_instantiation_error():
    from clausal.modules.py.csv import _generate_2
    assert raised(_generate_2, [["a", Var()]], Var()) == (
        "error", "instantiation_error", ("/", "generate", 2))


def test_csv_generate_records_unbound_value_raises_instantiation_error():
    from clausal.modules.py.csv import _generate_records_3
    from clausal.terms import DictTerm
    rec = DictTerm({"a": Var()})
    assert raised(_generate_records_3, ["a"], [rec], Var()) == (
        "error", "instantiation_error", ("/", "generate_records", 3))


def test_http_bad_header_value_is_not_blamed_on_the_url(monkeypatch):
    import clausal.modules.py.http as http

    def bad_header(*a, **k):
        raise ValueError("Invalid header value b'x\\r\\ny'")
    monkeypatch.setattr(http, "_urlopen", bad_header)
    # Not domain_error(url, _): the ValueError is the header's, and the
    # dispatch boundary turns it into its python_error term.
    with pytest.raises(ValueError, match="header"):
        list(http._get_2(chars("http://x.test/"), Var(), Trail(), None))


def test_set_seed_accepts_bytes():
    from clausal.modules.py.random import _random_seed_1
    assert len(list(_random_seed_1(b"seed", Trail(), None))) == 1


def test_csv_write_file_unbound_cell_raises_and_writes_nothing(tmp_path):
    from clausal.modules.py.csv import _write_file_2
    p = tmp_path / "out.csv"
    assert raised(_write_file_2, chars(str(p)), [["a", Var()]]) == (
        "error", "instantiation_error", ("/", "write_file", 2))
    assert not p.exists()


def test_csv_record_with_unknown_column_raises_domain_error():
    from clausal.modules.py.csv import _generate_records_3
    from clausal.terms import DictTerm
    rec = DictTerm({"a": chars("1"), "b": chars("2")})
    assert raised(_generate_records_3, ["a"], [rec], Var()) == _err(
        ("domain_error", "csv_record", rec), "generate_records", 3)


# ── random ───────────────────────────────────────────────────────────────


def test_sample_negative_size_raises_domain_error():
    from clausal.modules.py.random import _random_sample_3
    assert raised(_random_sample_3, [1, 2], -1, Var()) == _err(
        ("domain_error", "not_less_than_zero", -1), "sample", 3)


def test_sample_larger_than_list_still_fails():
    # No sample of that size exists: a legitimate "no".
    from clausal.modules.py.random import _random_sample_3
    assert list(_random_sample_3([1, 2], 3, Var(), Trail(), None)) == []


@pytest.mark.parametrize("p", [1.5, -1])
def test_maybe_probability_out_of_range_raises_domain_error(p):
    from clausal.modules.py.random import _maybe_1
    assert raised(_maybe_1, p) == _err(("domain_error", "probability", p),
                                       "maybe", 1)


# ── end to end: catch/3 in a program sees the ISO term ───────────────────


def test_domain_error_is_catchable_in_a_program(tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import deref
    from tests._suffix import SEAM

    p = tmp_path / f"hashdom{SEAM}"
    p.write_text(textwrap.dedent("""
        -import_from(py.hash, [hash])

        caught(A, D, C) <- (
            catch(hash(A, "abc", _), error(domain_error(D, C), _), true)
        ),
    """).lstrip())
    mod = _load_module("hashdom", str(p)).__dict__["$module"]
    D, C = Var(), Var()
    sols = [(deref(D), deref(C)) for _ in call("caught", "nope", D, C,
                                               module=mod)]
    assert sols == [("hash_algorithm", "nope")]
