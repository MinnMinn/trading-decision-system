"""One process per task, so a crash costs that task and nothing else.

`concurrent.futures.ProcessPoolExecutor` shares worker processes between tasks, and when ONE worker dies
(segfault, abort, OOM kill -- on this machine's flaky RAM that happened 21 times in 49 minutes of a 27-scan
stability run, D:/tmp-tests/speed-full/run3*.log) the executor marks EVERY pending future broken: six
in-flight 15m scans, each minutes of work, are thrown away for one hardware fault, and in practice no scan
finished before the next fault arrived.

`IsolatedExecutor` has the same `submit()` / context-manager surface run_scans() already uses, but runs each
task in its OWN freshly spawned process (at most `max_workers` at a time). A process that dies without
sending its result fails only its own future, with `WorkerCrashed`; every other task keeps running. The
result travels back through a pipe and is exactly what the function returned in the child -- the same
pickled object ProcessPoolExecutor would have delivered -- so nothing about the computed values changes.

"spawn" rather than the platform default, deliberately: tasks are launched from helper threads, and forking a
multi-threaded process is unsafe (CPython 3.12 warns about it). Spawn is what Windows always used anyway, so
Windows and the Linux Docker image now take the same path.
"""
import concurrent.futures
import multiprocessing
import threading


class WorkerCrashed(Exception):
    """The task's process ended without returning a result (crash, kill, or os._exit)."""


def _child(conn, fn, args):
    try:
        conn.send(("ok", fn(*args)))
    except BaseException as exc:  # noqa: BLE001 -- report ANY failure to the parent, never die silently
        try:
            conn.send(("err", exc))
        except Exception:        # the exception itself may not pickle; its text always does
            conn.send(("err", RuntimeError(f"{type(exc).__name__}: {exc}")))
    finally:
        conn.close()


class IsolatedExecutor:
    def __init__(self, max_workers):
        self._slots = threading.Semaphore(max(1, max_workers))
        self._threads = []
        self._ctx = multiprocessing.get_context("spawn")

    def submit(self, fn, *args):
        fut = concurrent.futures.Future()
        t = threading.Thread(target=self._run, args=(fut, fn, args), daemon=True)
        t.start()
        self._threads.append(t)
        return fut

    def _run(self, fut, fn, args):
        with self._slots:
            parent, child = self._ctx.Pipe(duplex=False)
            p = self._ctx.Process(target=_child, args=(child, fn, args))
            try:
                p.start()
            except Exception as exc:
                fut.set_exception(exc)
                return
            child.close()          # the parent's copy: recv() then sees EOF the moment the child dies
            try:
                kind, value = parent.recv()
            except (EOFError, OSError):
                kind, value = None, None
            finally:
                parent.close()
            p.join()
            if kind == "ok":
                fut.set_result(value)
            elif kind == "err":
                fut.set_exception(value)
            else:
                fut.set_exception(WorkerCrashed(f"worker process ended with exit code {p.exitcode} before "
                                                f"returning a result"))

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        for t in self._threads:
            t.join()
        return False
