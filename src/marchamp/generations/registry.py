"""In-memory generation registry (FR-021b).

Generations live only as long as the process. Nothing in this feature requires durable
output, and a user who wants to keep a PDF has already downloaded it.
"""

from __future__ import annotations

from threading import Lock

from marchamp.generations.service import Generation


class GenerationRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Generation] = {}
        self._lock = Lock()

    def put(self, generation: Generation) -> Generation:
        with self._lock:
            self._items[generation.id] = generation
        return generation

    def get(self, generation_id: str) -> Generation | None:
        with self._lock:
            return self._items.get(generation_id)
