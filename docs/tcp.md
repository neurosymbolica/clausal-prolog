# Clausal — TCP Module (`tcp`)

## Overview

The `tcp` module provides predicates for TCP client/server socket operations,
wrapping Python's `socket` module. Socket handles are opaque Python objects —
use them with `send`, `receive`, and `close`.

```seam
-import_from(py.tcp, [connect, send, receive, close])

echo_client(HOST, PORT, MESSAGE, RESPONSE) <- (
    connect(HOST, PORT, SOCKET),
    send(SOCKET, MESSAGE),
    receive(SOCKET, RESPONSE),
    close(SOCKET)
)
```

Or via [module import](import.md):

```seam
-import_module(py.tcp)

main <- (
    py.tcp.connect("localhost", 8080, S),
    py.tcp.send(S, "hello"),
    py.tcp.receive(S, REPLY),
    ++print(REPLY),
    py.tcp.close(S)
)
```

---

## Import

```seam
-import_from(py.tcp, [
    connect, listen, accept,
    send, receive, close, set_timeout
])
```

---

## Client predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `connect(Host, Port, Socket)` | `+Host, +Port, -Socket` | connect to TCP server, bind opaque socket handle |

```seam
--8<-- "tests/fixtures/docs/tcp_sigs.txt:connect_example"
```

A network failure raises (ruled 2026-10-02; it used to fail): a host that
does not resolve is `existence_error(source_sink, Host)` (Scryer's
`socket_client_open/3` term), a refused connection
`system_error(connection_refused)`, an unreachable host
`system_error(host_unreachable)`, a timeout `resource_error(timeout)`, a
permission refusal `permission_error(open, source_sink, Host)`. `listen/3`
on a port in use is `system_error(address_in_use)`; `send/2` on a broken
connection `system_error(broken_pipe)` or `system_error(connection_reset)`.

---

## Server predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `listen(Host, Port, ServerSocket)` | `+Host, +Port, -ServerSocket` | Create listening socket with `SO_REUSEADDR`. Port `0` → ephemeral. |
| `accept(ServerSocket, ClientSocket)` | `+Server, -Client` | accept incoming connection. Blocks until a client connects. |

```seam
--8<-- "tests/fixtures/docs/tcp_sigs.txt:server_example"
```

---

## Data transfer

| Predicate | Mode | Description |
|-----------|------|-------------|
| `send(Socket, Data)` | `+Socket, +Data` | send string (UTF-8) or bytes via `sendall()` |
| `receive(Socket, Data)` | `+Socket, -Data` | receive up to 4096 bytes, decode UTF-8 |
| `receive(Socket, BufferSize, Data)` | `+Socket, +BufSize, -Data` | receive with custom buffer size |

`receive` returns a string if the data is valid UTF-8, or raw `bytes` if
decoding fails. Fails if the connection is closed (no data received).

```seam
--8<-- "tests/fixtures/docs/tcp_sigs.txt:data_transfer_examples"
```

---

## Socket management

| Predicate | Mode | Description |
|-----------|------|-------------|
| `close(Socket)` | `+Socket` | close socket. Always succeeds (even on already-closed sockets). |
| `set_timeout(Socket, Seconds)` | `+Socket, +Seconds` | Set socket timeout (float). A later operation that times out raises `resource_error(timeout)`. |

```seam
--8<-- "tests/fixtures/docs/tcp_sigs.txt:socket_management_example"
```

---

??? example "Examples"

    ### Simple TCP client

    ```seam
    --8<-- "tests/fixtures/docs/tcp_sigs.txt:tcp_client_example"
    ```

    ### Echo server (single client)

    ```seam
    --8<-- "tests/fixtures/docs/tcp_sigs.txt:echo_server_example"
    ```

---

## Gotchas

- **Sockets are impure** — socket operations have side effects and do not
  [backtrack](control.md) cleanly. If a `send` succeeds but a later goal fails, the data
  has already been sent.
- **`accept` blocks** — it waits for a connection. Use `set_timeout` on the
  server socket to limit the wait time.
- **No automatic cleanup** — always `close` sockets explicitly. Python's
  garbage collector will eventually close them, but relying on GC is bad
  practice for network resources.
- **Port 0** in `listen` lets the OS pick an ephemeral port — useful for tests.

---

*See also: [HTTP](http.md) — higher-level HTTP requests (no sockets needed) ·
[Process](process.md) — shell commands and subprocess execution ·
[Python Interop](python_integration.md) — `++()` for advanced socket operations.*
