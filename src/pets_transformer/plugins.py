"""Plug-ins from other packages, without touching this repository.

A company package declares in its pyproject.toml:

    [project.entry-points."pets_transformer.plugins"]
    acme = "acme_pets.plugin:register"

and `register(hub: PluginHub) -> None` adds its validators, transforms, text detectors or data sources,
e.g. Spanish DNI or Portuguese NIF validators for TrustED's hospital partners.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from pets_transformer.contracts import Technique
from pets_transformer.detect.base import Validator
from pets_transformer.detect.validators import VALIDATORS
from pets_transformer.registry import Registry
from pets_transformer.sources import SOURCES, TableSource
from pets_transformer.text.base import SPAN_DETECTORS, SpanDetector
from pets_transformer.transform.base import TRANSFORMS, ColumnTransform

ENTRY_POINT_GROUP = "pets_transformer.plugins"


@dataclass(frozen=True)
class PluginHub:
    """Everything a plug-in may extend. Registries refuse duplicates, so plug-ins add but never replace."""

    validators: Registry[str, Validator] = field(default_factory=lambda: VALIDATORS)
    transforms: Registry[Technique, ColumnTransform] = field(default_factory=lambda: TRANSFORMS)
    span_detectors: Registry[str, SpanDetector] = field(default_factory=lambda: SPAN_DETECTORS)
    sources: Registry[str, Callable[[str], TableSource]] = field(default_factory=lambda: SOURCES)


Registrar = Callable[[PluginHub], None]


def installed_registrars() -> list[tuple[str, Registrar]]:
    from importlib.metadata import entry_points  # noqa: PLC0415  (only needed when plug-ins are loaded)

    return [(ep.name, ep.load()) for ep in entry_points(group=ENTRY_POINT_GROUP)]


def load_plugins(registrars: Iterable[tuple[str, Registrar]] | None = None, hub: PluginHub | None = None) -> list[str]:
    """Call each plug-in's register function once; returns their names. Inputs injectable for tests."""
    target = hub or PluginHub()
    names: list[str] = []
    for name, register in installed_registrars() if registrars is None else registrars:
        register(target)
        names.append(name)
    return names
