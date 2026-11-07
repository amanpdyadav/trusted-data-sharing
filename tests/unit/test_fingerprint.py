import hashlib
from pathlib import Path

from pets_transformer.report.fingerprint import file_sha256, files_fingerprint


def test_file_hash_matches_sha256(tmp_path: Path) -> None:
    p = tmp_path / "a.csv"
    p.write_bytes(b"id,value\n1,x\n")
    assert file_sha256(p) == hashlib.sha256(b"id,value\n1,x\n").hexdigest()


def test_set_fingerprint_ignores_order_but_not_content_or_names(tmp_path: Path) -> None:
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("1")
    b.write_text("2")
    first = files_fingerprint([a, b])
    assert first == files_fingerprint([b, a])
    b.write_text("3")
    assert files_fingerprint([a, b]) != first
    renamed = tmp_path / "c.csv"
    b.rename(renamed)
    renamed.write_text("2")
    assert files_fingerprint([a, renamed]) != first
