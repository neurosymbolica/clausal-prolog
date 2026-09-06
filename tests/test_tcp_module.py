"""Tests for Phase 7e TCP module: py.tcp."""

from __future__ import annotations

import socket
import threading

import pytest

from clausal.logic.atoms import mint
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE

from clausal.modules.py.tcp import (
    connect, listen, accept, send, receive, close, set_timeout,
    _connect_3, _listen_3, _accept_2,
    _send_2, _receive_2, _receive_3,
    _close_1, _set_timeout_2,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── Echo server fixture ──────────────────────────────────────────────────


@pytest.fixture
def echo_server():
    """Start an echo server on localhost, yield (host, port), clean up."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(5)
    port = server.getsockname()[1]
    ready = threading.Event()

    def _serve():
        ready.set()
        try:
            client, _ = server.accept()
            data = client.recv(4096)
            if data:
                client.sendall(data)  # echo back
            client.close()
        except socket.timeout:
            pass
        finally:
            server.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    ready.wait(timeout=2)
    yield ("127.0.0.1", port)
    t.join(timeout=2)


@pytest.fixture
def multi_echo_server():
    """Echo server that handles multiple connections sequentially."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    server.settimeout(5)
    port = server.getsockname()[1]
    ready = threading.Event()
    stop = threading.Event()

    def _serve():
        ready.set()
        while not stop.is_set():
            try:
                client, _ = server.accept()
                data = client.recv(4096)
                if data:
                    client.sendall(data)
                client.close()
            except socket.timeout:
                break
            except OSError:
                break
        server.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    ready.wait(timeout=2)
    yield ("127.0.0.1", port)
    stop.set()
    t.join(timeout=2)


# ── connect/3 ────────────────────────────────────────────────────────────


class TestConnect:

    def test_connect_to_echo_server(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        sols, trail = simple_solutions(_connect_3, host, port, sock)
        assert len(sols) == 1
        s = deref(sock)
        assert isinstance(s, socket.socket)
        s.close()

    def test_connection_refused_fails(self):
        """connect to a port that's definitely not listening."""
        # nv
        sock = Var()
        sols, _ = simple_solutions(_connect_3, "127.0.0.1", 1, sock)
        assert len(sols) == 0

    def test_unbound_host_fails(self):
        # nv
        sock = Var()
        sols, _ = simple_solutions(_connect_3, Var(), 80, sock)
        assert len(sols) == 0

    def test_unbound_port_fails(self):
        # nv
        sock = Var()
        sols, _ = simple_solutions(_connect_3, "localhost", Var(), sock)
        assert len(sols) == 0


# ── listen/3 + accept/2 ─────────────────────────────────────────────────


class TestListenAccept:

    def test_listen_and_accept(self):
        """listen on ephemeral port, connect from client, accept."""
        # nv
        server_sock = Var()
        sols, trail = simple_solutions(_listen_3, "127.0.0.1", 0, server_sock)
        assert len(sols) == 1
        server = deref(server_sock)
        port = server.getsockname()[1]

        # connect from a client
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", port))

        # accept on server
        accepted = Var()
        sols2, trail2 = simple_solutions(_accept_2, server, accepted)
        assert len(sols2) == 1
        assert isinstance(deref(accepted), socket.socket)

        deref(accepted).close()
        client.close()
        server.close()

    def test_ephemeral_port(self):
        """listen with port 0 picks an available port."""
        # nv
        server_sock = Var()
        sols, trail = simple_solutions(_listen_3, "127.0.0.1", 0, server_sock)
        assert len(sols) == 1
        server = deref(server_sock)
        assert server.getsockname()[1] > 0
        server.close()


# ── send/2 + receive/2,3 ────────────────────────────────────────────────


class TestSendReceive:

    def test_echo_round_trip(self, echo_server):
        """connect, send, receive echoed data, close."""
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)

        # send
        sols, _ = simple_solutions(_send_2, s, "hello")
        assert len(sols) == 1

        # receive
        data = Var()
        sols, trail = simple_solutions(_receive_2, s, data)
        assert len(sols) == 1
        assert deref(data) == "hello"

        s.close()

    def test_receive_custom_buffer_size(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)

        simple_solutions(_send_2, s, "world")
        data = Var()
        sols, trail = simple_solutions(_receive_3, s, 1024, data)
        assert len(sols) == 1
        assert deref(data) == "world"
        s.close()

    def test_send_unbound_data_fails(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)
        sols, _ = simple_solutions(_send_2, s, Var())
        assert len(sols) == 0
        s.close()

    def test_send_bytes(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)
        sols, _ = simple_solutions(_send_2, s, b"bytes data")
        assert len(sols) == 1
        data = Var()
        simple_solutions(_receive_2, s, data)
        assert deref(data) == "bytes data"
        s.close()


# ── close/1 ──────────────────────────────────────────────────────────────


class TestClose:

    def test_close_succeeds(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)
        sols, _ = simple_solutions(_close_1, s)
        assert len(sols) == 1

    def test_double_close_harmless(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)
        simple_solutions(_close_1, s)
        # Second close should still succeed (close() on closed socket is OK)
        sols, _ = simple_solutions(_close_1, s)
        assert len(sols) == 1

    def test_close_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_close_1, Var())
        assert len(sols) == 0


# ── set_timeout/2 ─────────────────────────────────────────────────────────


class TestSetTimeout:

    def test_set_timeout(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)
        sols, _ = simple_solutions(_set_timeout_2, s, 1.0)
        assert len(sols) == 1
        assert s.gettimeout() == 1.0
        s.close()

    def test_unbound_seconds_fails(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        simple_solutions(_connect_3, host, port, sock)
        s = deref(sock)
        sols, _ = simple_solutions(_set_timeout_2, s, Var())
        assert len(sols) == 0
        s.close()


# ── Trampoline integration ───────────────────────────────────────────────


class TestTcpTrampoline:

    def test_full_echo_trampoline(self, echo_server):
        """Full test via trampoline protocol."""
        # nv
        host, port = echo_server
        sock = Var()
        sols, trail = trampoline_solutions(connect, host, port, sock)
        assert len(sols) == 1
        s = deref(sock)

        sols, _ = trampoline_solutions(send, s, "trampoline test")
        assert len(sols) == 1

        data = Var()
        sols, trail = trampoline_solutions(receive, s, data)
        assert len(sols) == 1
        assert deref(data) == "trampoline test"

        trampoline_solutions(close, s)


# ── Task 12b: atoms in the text positions (spec §9.4) ────────────────────


class TestAtomArguments:
    """A wrapper that takes text accepts a string OR an ATOM (spec §9.4).

    ``py.tcp`` was never migrated onto ``to_text``: the host of
    ``connect/3``/``listen/3`` and the payload of ``send/2`` gated on
    ``isinstance(x, str)``, so a source-written ``connect('127.0.0.1', P, S)``
    — an atom in the default ``-double_quotes(atom)`` mode — failed silently.
    """

    def test_connect_and_send_accept_atoms(self, echo_server):
        # nv
        host, port = echo_server
        sock = Var()
        sols, _ = simple_solutions(_connect_3, mint(host), port, sock)
        assert len(sols) == 1
        s = deref(sock)

        sols, _ = simple_solutions(_send_2, s, mint("t12b atom payload"))
        assert len(sols) == 1

        data = Var()
        sols, _ = simple_solutions(_receive_2, s, data)
        assert len(sols) == 1
        # The atom crossed as its spelling, never as a tuple repr.
        assert deref(data) == "t12b atom payload"
        simple_solutions(_close_1, s)

    def test_listen_accepts_an_atom_host(self):
        # nv
        server = Var()
        sols, _ = simple_solutions(_listen_3, mint("127.0.0.1"), 0, server)
        assert len(sols) == 1
        try:
            assert deref(server).getsockname()[0] == "127.0.0.1"
        finally:
            simple_solutions(_close_1, deref(server))
