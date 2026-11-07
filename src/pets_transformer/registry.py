"""A tiny named registry shared by validators, transforms, text detectors and sources (open/closed)."""

from collections.abc import Hashable, Iterator
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class Registry(Generic[K, V]):
    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[K, V] = {}

    def register(self, key: K, item: V) -> V:
        if key in self._items:
            raise ValueError(f"{self._kind} {key!r} is already registered")
        self._items[key] = item
        return item

    def get(self, key: K) -> V:
        try:
            return self._items[key]
        except KeyError:
            raise KeyError(f"no {self._kind} registered for {key!r}") from None

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __iter__(self) -> Iterator[V]:
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)
