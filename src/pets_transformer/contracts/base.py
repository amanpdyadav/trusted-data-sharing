"""Common base for every shared file, so all four behave the same way (DRY)."""

from pathlib import Path
from typing import Final, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION: Final[Literal["1"]] = "1"


class Contract(BaseModel):
    """Strict, immutable model: unknown fields are errors, so format drift between owners fails loudly."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    @classmethod
    def load(cls, path: str | Path) -> Self:
        """Read a .json, .yaml or .yml file and validate it."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix in {".yaml", ".yml"}:
            return cls.model_validate(yaml.safe_load(text))
        return cls.model_validate_json(text)

    def save(self, path: str | Path) -> Path:
        """Write as YAML or JSON depending on the file extension."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix in {".yaml", ".yml"}:
            data = self.model_dump(mode="json", exclude_none=True)
            p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        else:
            p.write_text(self.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")
        return p
