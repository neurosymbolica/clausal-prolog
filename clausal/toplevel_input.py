"""Input helpers of the ``?-`` top-level that are not line editing.

:class:`KeyWatcher` -- while a query searches for its next answer, a key
pressed on the terminal interrupts it (the top-level then prints
``% Execution Aborted`` and prompts again), as in Shumway (Esc) and as Markus
Triska's talk on the top-level asks ("a key press could bring us back to
stating queries").  Ctrl-C always did; this needs no signal key.
"""
from __future__ import annotations

import os
import select
import signal
import threading


class KeyWatcher:
    """Context manager: a thread that watches file descriptor *fd* while the
    body runs, and interrupts the main thread (SIGINT, so a
    ``KeyboardInterrupt`` where the search is) when a byte arrives.

    The byte is consumed.  If the body ended first, a byte read in the race
    is kept in :attr:`leftover` for the next key read instead of interrupting.
    """

    POLL = 0.05

    def __init__(self, fd: int):
        self.fd = fd
        self.leftover: bytes = b""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "KeyWatcher":
        if not hasattr(signal, "SIGINT") or \
                threading.current_thread() is not threading.main_thread():
            return self                     # nothing to interrupt from here
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch, daemon=True,
                                        name="clausal-key-watcher")
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self.fd], [], [], self.POLL)
            except (OSError, ValueError):
                return
            if not ready:
                continue
            try:
                data = os.read(self.fd, 1)
            except OSError:
                return
            if not data:
                return
            if self._stop.is_set():
                self.leftover = data        # the search had just ended
            else:
                os.kill(os.getpid(), signal.SIGINT)
            return
