"""Reading tables. Everything is read as text: phone numbers, postcodes and IDs break when parsed as numbers."""

from pathlib import Path

import pandas as pd


def read_table(path: str | Path) -> pd.DataFrame:
    """Read one CSV with every value as a string and empty cells as ''."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def list_tables(folder: str | Path) -> dict[str, Path]:
    """Table name -> CSV path for every CSV in a folder (not recursive), sorted by name."""
    return {p.stem: p for p in sorted(Path(folder).glob("*.csv"))}
