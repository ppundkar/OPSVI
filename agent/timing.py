"""Rolling response-time samples exposed on /v1/metrics."""

from __future__ import annotations

from collections import defaultdict, deque


class TimingBoard:
    def __init__(self, size: int = 400) -> None:
        self.samples: deque[tuple[str, float]] = deque(maxlen=size)
        self.by_path: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=100))

    def add(self, path: str, elapsed_ms: float) -> None:
        self.samples.append((path, elapsed_ms))
        self.by_path[path].append(elapsed_ms)

    def summary(self) -> dict:
        values = [item[1] for item in self.samples]
        return {
            "requests": len(values),
            "p50_ms": _percentile(values, 50),
            "p95_ms": _percentile(values, 95),
            "max_ms": round(max(values), 2) if values else 0,
            "by_path": {
                path: {
                    "requests": len(items),
                    "p50_ms": _percentile(list(items), 50),
                    "p95_ms": _percentile(list(items), 95),
                }
                for path, items in self.by_path.items()
            },
        }


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 2)
