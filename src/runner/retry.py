from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_retry(
    func: Callable[[], T],
    max_attempts: int,
    backoff_sec: int,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> tuple[T, int]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(), attempt
        except Exception as e:  # noqa: BLE001
            last_error = e
            if attempt >= max_attempts:
                break
            if on_retry is not None:
                on_retry(attempt, e)
            if backoff_sec > 0:
                time.sleep(backoff_sec)
    assert last_error is not None
    raise last_error

