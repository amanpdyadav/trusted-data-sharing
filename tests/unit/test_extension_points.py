"""Expandability: new validators, sources and scenarios plug in without editing existing code."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from pets_transformer.contracts import Subtype
from pets_transformer.plan.scenario import load_scenarios
from pets_transformer.plugins import PluginHub, load_plugins
from pets_transformer.registry import Registry
from pets_transformer.sources import CsvFolderSource, open_source


@dataclass(frozen=True)
class SpanishDni:
    """What a partner plug-in would add: 8 digits + check letter."""

    name: str = "es_dni"
    subtype: Subtype = Subtype.NATIONAL_ID

    def is_valid(self, value: str) -> bool:
        v = value.strip().upper()
        return len(v) == 9 and v[:8].isdigit() and "TRWAGMYFPDXBNJZSQVHLCKE"[int(v[:8]) % 23] == v[8]


def _fresh_hub() -> PluginHub:
    return PluginHub(
        validators=Registry("validator"),
        transforms=Registry("transform"),
        span_detectors=Registry("span detector"),
        sources=Registry("table source"),
    )


def test_plugin_adds_a_validator_without_code_changes() -> None:
    hub = _fresh_hub()

    def register(h: PluginHub) -> None:
        h.validators.register("es_dni", SpanishDni())

    assert load_plugins([("spain", register)], hub) == ["spain"]
    assert hub.validators.get("es_dni").is_valid("12345678Z")


def test_plugins_cannot_replace_builtins() -> None:
    hub = _fresh_hub()
    hub.validators.register("es_dni", SpanishDni())
    with pytest.raises(ValueError, match="already registered"):
        load_plugins([("evil", lambda h: h.validators.register("es_dni", SpanishDni()))], hub)


def test_csv_source(tmp_path: Path) -> None:
    (tmp_path / "people.csv").write_text("id,phone\n1,040 123 4567\n2,\n", encoding="utf-8")
    src = open_source(f"csv:{tmp_path}")
    assert isinstance(src, CsvFolderSource)
    assert src.table_names() == ["people"]
    df = src.read("people")
    assert df["phone"].tolist() == ["040 123 4567", ""]  # read as text, empty stays ''
    with pytest.raises(KeyError):
        src.read("missing")


@pytest.mark.parametrize("address", ["no-scheme", "csv:", "ftp:/x"])
def test_bad_source_addresses(address: str) -> None:
    with pytest.raises((ValueError, KeyError)):
        open_source(address)


def test_scenarios_load_from_several_folders(repo: Path, tmp_path: Path) -> None:
    company = tmp_path / "company"
    company.mkdir()
    text = (repo / "scenarios/HEALTH-S1.yaml").read_text(encoding="utf-8").replace("HEALTH-S1", "ACME-HR-1")
    (company / "acme.yaml").write_text(text, encoding="utf-8")
    found = load_scenarios([repo / "scenarios", company, tmp_path / "missing"])
    assert {"HEALTH-S1", "ACME-HR-1"} <= set(found)


def test_duplicate_scenario_ids_are_an_error(repo: Path, tmp_path: Path) -> None:
    (tmp_path / "copy.yaml").write_text((repo / "scenarios/HEALTH-S1.yaml").read_text(), encoding="utf-8")
    with pytest.raises(ValueError, match="twice"):
        load_scenarios([repo / "scenarios", tmp_path])
