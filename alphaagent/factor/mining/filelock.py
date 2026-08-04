"""跨进程文件锁（fcntl.flock），用于多进程并行挖掘时保护共享因子库/registry 的写。

多个挖掘进程共享同一个 factorzoo 因子库与 mining_delivered_registry.json，
并发 submit 时若不加锁会互相覆盖 / 损坏。本模块提供基于 ``fcntl.flock`` 的
阻塞式文件锁，锁文件放在待保护文件旁（如 ``{factorlib_path}.lock``）。
"""

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows 仅作降级
    fcntl = None  # type: ignore[assignment]

# 进程内已持有的锁路径 -> 持有计数（同一进程可重入，避免嵌套 flock 自死锁）
_held: dict[str, int] = {}


class FileLock(AbstractContextManager["FileLock"]):
    """对 ``lock_path`` 加排他锁；进程内可重入，跨进程由 flock 互斥。"""

    def __init__(self, lock_path: Path | str) -> None:
        self.lock_path = Path(lock_path)
        self._fd: int | None = None

    def _key(self) -> str:
        return str(self.lock_path.resolve())

    def acquire(self) -> "FileLock":
        key = self._key()
        if _held.get(key, 0) > 0:
            _held[key] += 1
            return self
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        self._fd = fd
        _held[key] = 1
        return self

    def release(self) -> None:
        key = self._key()
        count = _held.get(key, 0)
        if count <= 0:
            return
        if count > 1:
            _held[key] = count - 1
            return
        _held.pop(key, None)
        if self._fd is not None:
            if fcntl is not None:
                try:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                finally:
                    os.close(self._fd)
            else:
                os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, *exc: Any) -> None:
        self.release()


def factor_report_lock(factorlib_path: Path | str) -> FileLock:
    """对因子库路径派生的锁文件加锁（``{factorlib}.lock``）。"""
    return FileLock(Path(factorlib_path).expanduser().resolve().with_suffix(".lock"))