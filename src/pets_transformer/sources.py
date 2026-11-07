"""Where tables come from. CSV folders today; a database or data-space connector is one more class later.

Address format: "<scheme>:<location>", e.g. "csv:TRUSTED_PETS_PROVING_GROUND_2026/data/health".
"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pandas as pd

from pets_transformer.io import list_tables, read_table
from pets_transformer.registry import Registry


class TableSource(Protocol):
    @property
    def name(self) -> str: ...

    def table_names(self) -> list[str]: ...

    def read(self, table: str) -> pd.DataFrame: ...


class CsvFolderSource:
    """Every *.csv in one folder is a table; values are read as text."""

    def __init__(self, folder: str | Path, headerless: frozenset[str] = frozenset()) -> None:
        self._folder = Path(folder)
        self._headerless = headerless  # tables whose files have no header row
        if not self._folder.is_dir():
            raise FileNotFoundError(f"no such folder: {self._folder}")
        self.name = self._folder.name

    def table_names(self) -> list[str]:
        return list(list_tables(self._folder))

    def read(self, table: str) -> pd.DataFrame:
        paths = list_tables(self._folder)
        if table not in paths:
            raise KeyError(f"table {table!r} not in {self._folder}")
        return read_table(paths[table], header=table not in self._headerless)


SOURCES: Registry[str, Callable[[str], TableSource]] = Registry("table source")
SOURCES.register("csv", CsvFolderSource)


def open_source(address: str) -> TableSource:
    scheme, sep, location = address.partition(":")
    if not sep or not location:
        raise ValueError(f"source address must look like 'csv:path/to/folder', got {address!r}")
    return SOURCES.get(scheme)(location)
