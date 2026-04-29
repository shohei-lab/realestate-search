"""簡易レート制御。前回呼び出しから一定時間経過するまで sleep する。

スレッドセーフではない。CLI 単発実行の前提。
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class RateLimiter:
    rps: float          # requests per second
    _last_call: float = 0.0

    @property
    def min_interval(self) -> float:
        if self.rps <= 0:
            return 0.0
        return 1.0 / self.rps

    def wait(self, *, _now: float | None = None, _sleep=time.sleep) -> None:
        """次のリクエストまでに必要な時間 sleep する。"""
        now = _now if _now is not None else time.monotonic()
        elapsed = now - self._last_call
        remaining = self.min_interval - elapsed
        if remaining > 0:
            _sleep(remaining)
            now = (now + remaining) if _now is not None else time.monotonic()
        self._last_call = now
