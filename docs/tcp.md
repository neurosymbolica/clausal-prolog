# Clausal — TCP Module (`tcp`)

## Overview

The `tcp` module provides predicates for TCP client/server socket operations,
wrapping Python's `socket` module. Socket handles are opaque Python objects —
use them with `Send`, `Receive`, and `Close`.

```clausal
-import_from(py.tcp, [Connect, Send, Receive, Close])

EchoClient(HOST, PORT, MESSAGE, RESPONSE) <- (
    Connect(HOST, PORT, SOCKET),
    Send(SOCKET, MESSAGE),
    Receive(SOCKET, RESPONSE),
    Close(SOCKET)
)
```

Or via [module import](import.md):

```clausal
-import_module(py.tcp)

Main <- (
    py.tcp.Connect("localhost", 8080, S),
    py.tcp.Send(S, "hello"),
    py.tcp.Receive(S, REPLY),
    ++print(REPLY),
    py.tcp.Close(S)
)
```

---

## Import

```clausal
-import_from(py.tcp, [
    Connect, Listen, Accept,
    Send, Receive, Close, SetTimeout
])
```

---

## Client predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Connect(Host, Port, Socket)` | `+Host, +Port, -Socket` | Connect to TCP server, bind opaque socket handle |

```clausal
--8<-- "tests/fixtures/docs/tcp_sigs.txt:connect_example"
```

Fails if the connection is refused or the host is unreachable.

---

## Server predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Listen(Host, Port, ServerSocket)` | `+Host, +Port, -ServerSocket` | Create listening socket with `SO_REUSEADDR`. Port `0` → ephemeral. |
| `Accept(ServerSocket, ClientSocket)` | `+Server, -Client` | Accept incoming connection. Blocks until a client connects. |

```clausal
--8<-- "tests/fixtures/docs/tcp_sigs.txt:server_example"
```

---

## Data transfer

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Send(Socket, Data)` | `+Socket, +Data` | Send string (UTF-8) or bytes via `sendall()` |
| `Receive(Socket, Data)` | `+Socket, -Data` | Receive up to 4096 bytes, decode UTF-8 |
| `Receive(Socket, BufferSize, Data)` | `+Socket, +BufSize, -Data` | Receive with custom buffer size |

`Receive` returns a string if the data is valid UTF-8, or raw `bytes` if
decoding fails. Fails if the connection is closed (no data received).

```clausal
--8<-- "tests/fixtures/docs/tcp_sigs.txt:data_transfer_examples"
```

---

## Socket management

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Close(Socket)` | `+Socket` | Close socket. Always succeeds (even on already-closed sockets). |
| `SetTimeout(Socket, Seconds)` | `+Socket, +Seconds` | Set socket timeout (float). Subsequent operations fail on timeout. |

```clausal
--8<-- "tests/fixtures/docs/tcp_sigs.txt:socket_management_example"
```

---

??? example "Examples"

    ### Simple TCP client

    ```clausal
    --8<-- "tests/fixtures/docs/tcp_sigs.txt:tcp_client_example"
    ```

    ### Echo server (single client)

    ```clausal
    --8<-- "tests/fixtures/docs/tcp_sigs.txt:echo_server_example"
    ```

---

## Gotchas

- **Sockets are impure** — socket operations have side effects and do not
  [backtrack](control.md) cleanly. If a `Send` succeeds but a later goal fails, the data
  has already been sent.
- **`Accept` blocks** — it waits for a connection. Use `SetTimeout` on the
  server socket to limit the wait time.
- **No automatic cleanup** — always `Close` sockets explicitly. Python's
  garbage collector will eventually close them, but relying on GC is bad
  practice for network resources.
- **Port 0** in `Listen` lets the OS pick an ephemeral port — useful for tests.

---

*See also: [HTTP](http.md) — higher-level HTTP requests (no sockets needed) ·
[Process](process.md) — shell commands and subprocess execution ·
[Python Interop](python_integration.md) — `++()` for advanced socket operations.*
