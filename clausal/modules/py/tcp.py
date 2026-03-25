"""clausal.modules.py.tcp — TCP socket predicates for Clausal.

Provides relational predicates for TCP client/server connections.
Import via::

    -import_from(py.tcp, [Connect, Listen, Accept, Send, Receive, Close, SetTimeout])

Wraps Python's ``socket`` module. Socket handles are opaque Python objects.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_socket = _import_stdlib("socket")

from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter ──────────────────────────────────────────────────────


class _TcpPredicate:
    """Adapter with ``_get_dispatch()`` for a TCP predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"tcp.{self._name}/{arities}"


def _simple_to_trampoline(simple_fn):
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Predicate implementations ────────────────────────────────────────────


def _connect_3(host, port, sock_out, trail, k):
    """Connect/3: Connect(Host, Port, Socket) — connect to TCP server."""
    host_d = deref(host)
    port_d = deref(port)
    if is_var(host_d) or not isinstance(host_d, str):
        return
    if is_var(port_d) or not isinstance(port_d, int):
        return
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.connect((host_d, port_d))
    except (OSError, _socket.error):
        return
    if unify(sock_out, s, trail):
        yield None


def _listen_3(host, port, server_out, trail, k):
    """Listen/3: Listen(Host, Port, ServerSocket) — create listening socket."""
    host_d = deref(host)
    port_d = deref(port)
    if is_var(host_d) or not isinstance(host_d, str):
        return
    if is_var(port_d) or not isinstance(port_d, int):
        return
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        s.bind((host_d, port_d))
        s.listen(5)
    except (OSError, _socket.error):
        return
    if unify(server_out, s, trail):
        yield None


def _accept_2(server_sock, client_out, trail, k):
    """Accept/2: Accept(ServerSocket, ClientSocket) — accept incoming connection."""
    server_d = deref(server_sock)
    if is_var(server_d) or not isinstance(server_d, _socket.socket):
        return
    try:
        client, addr = server_d.accept()
    except (OSError, _socket.error):
        return
    if unify(client_out, client, trail):
        yield None


def _send_2(sock, data, trail, k):
    """Send/2: Send(Socket, Data) — send string (UTF-8) or bytes via sendall."""
    sock_d = deref(sock)
    data_d = deref(data)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(data_d):
        return
    if isinstance(data_d, str):
        data_bytes = data_d.encode("utf-8")
    elif isinstance(data_d, bytes):
        data_bytes = data_d
    else:
        return
    try:
        sock_d.sendall(data_bytes)
    except (OSError, _socket.error):
        return
    yield None


def _receive_3(sock, bufsize, data_out, trail, k):
    """Receive/3: Receive(Socket, BufferSize, Data) — receive with custom buffer."""
    sock_d = deref(sock)
    bufsize_d = deref(bufsize)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(bufsize_d) or not isinstance(bufsize_d, int):
        return
    try:
        raw = sock_d.recv(bufsize_d)
    except (OSError, _socket.error):
        return
    if not raw:
        return  # connection closed
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        if unify(data_out, raw, trail):
            yield None
        return
    if unify(data_out, text, trail):
        yield None


def _receive_2(sock, data_out, trail, k):
    """Receive/2: Receive(Socket, Data) — receive up to 4096 bytes."""
    yield from _receive_3(sock, 4096, data_out, trail, k)


def _close_1(sock, trail, k):
    """Close/1: Close(Socket) — close socket. Always succeeds."""
    sock_d = deref(sock)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    try:
        sock_d.close()
    except (OSError, _socket.error):
        pass
    yield None


def _set_timeout_2(sock, seconds, trail, k):
    """SetTimeout/2: SetTimeout(Socket, Seconds) — set socket timeout."""
    sock_d = deref(sock)
    sec_d = deref(seconds)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(sec_d):
        return
    timeout = None if sec_d is None else float(sec_d)
    sock_d.settimeout(timeout)
    yield None


# ── Build and export predicate objects ───────────────────────────────────

Connect = _TcpPredicate("Connect")
Connect._register(3, _simple_to_trampoline(_connect_3))

Listen = _TcpPredicate("Listen")
Listen._register(3, _simple_to_trampoline(_listen_3))

Accept = _TcpPredicate("Accept")
Accept._register(2, _simple_to_trampoline(_accept_2))

Send = _TcpPredicate("Send")
Send._register(2, _simple_to_trampoline(_send_2))

Receive = _TcpPredicate("Receive")
Receive._register(2, _simple_to_trampoline(_receive_2))
Receive._register(3, _simple_to_trampoline(_receive_3))

Close = _TcpPredicate("Close")
Close._register(1, _simple_to_trampoline(_close_1))

SetTimeout = _TcpPredicate("SetTimeout")
SetTimeout._register(2, _simple_to_trampoline(_set_timeout_2))
