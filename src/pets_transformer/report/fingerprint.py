"""SHA-256 fingerprints for the manifest: prove which inputs produced which release."""

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd

_CHUNK = 1 << 20


def tables_fingerprint(tables: Mapping[str, pd.DataFrame]) -> str:
    """Fingerprint of table contents, independent of where they came from (CSV, database, ...)."""
    h = hashlib.sha256()
    for name in sorted(tables):
        frame = tables[name]
        h.update(name.encode("utf-8"))
        h.update(",".join(map(str, frame.columns)).encode("utf-8"))
        h.update(pd.util.hash_pandas_object(frame, index=False).to_numpy().tobytes())
    return h.hexdigest()


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def files_fingerprint(paths: Iterable[str | Path]) -> str:
    """One fingerprint for a set of files: order-independent, includes file names."""
    h = hashlib.sha256()
    for p in sorted(Path(x) for x in paths):
        h.update(p.name.encode("utf-8"))
        h.update(bytes.fromhex(file_sha256(p)))
    return h.hexdigest()
