"""Reading tables. Everything is read as text: phone numbers, postcodes and IDs break when parsed as numbers."""

from pathlib import Path

import pandas as pd


def positional_names(count: int) -> list[str]:
    """Names for the columns of a file without a header row: col_01, col_02 ..."""
    width = max(2, len(str(count)))
    return [f"col_{i:0{width}d}" for i in range(1, count + 1)]


def read_table(path: str | Path, header: bool = True) -> pd.DataFrame:
    """Read one CSV with every value as a string and empty cells as ''.

    header=False: the file has no header row; its columns are called col_01, col_02 ...
    """
    if header:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, header=None)
    frame.columns = positional_names(frame.shape[1])
    return frame


def read_header(path: str | Path) -> list[str]:
    """The first row of a CSV as written (blank cells come back as 'Unnamed: n'), without reading the rest."""
    return [str(c) for c in pd.read_csv(path, dtype=str, nrows=0).columns]


def list_tables(folder: str | Path) -> dict[str, Path]:
    """Table name -> CSV path for every CSV in a folder (not recursive), sorted by name."""
    return {p.stem: p for p in sorted(Path(folder).glob("*.csv"))}
