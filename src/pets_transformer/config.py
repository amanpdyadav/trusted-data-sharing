"""Settings come from the environment (12-factor), so the same code runs on practice data and company data."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LlmSettings:
    """The local AI is optional. Off by default: every step must work on rules alone."""

    enabled: bool = False
    url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    timeout_s: float = 60.0
    cache_dir: Path | None = None


@dataclass(frozen=True)
class Settings:
    package_root: Path = Path("TRUSTED_PETS_PROVING_GROUND_2026")
    out_dir: Path = Path("out")
    scenario_dirs: tuple[Path, ...] = (Path("scenarios"),)
    codelist_dir: Path = Path("codelists")
    results_dir: Path = Path("results")  # what the evaluation commands write: benchmark, baselines, screens
    llm: LlmSettings = field(default_factory=LlmSettings)

    @property
    def epsilon_ledger(self) -> Path:
        """Differential-privacy spending per receiver; private, kept with the controller's outputs."""
        return self.out_dir / "epsilon_ledger.jsonl"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        e = os.environ if env is None else env
        out_dir = Path(e.get("PETS_OUT_DIR", str(cls.out_dir)))
        scenario_dirs = tuple(Path(p) for p in e.get("PETS_SCENARIO_DIRS", "scenarios").split(os.pathsep) if p)
        return cls(
            package_root=Path(e.get("PETS_PACKAGE_ROOT", str(cls.package_root))),
            out_dir=out_dir,
            scenario_dirs=scenario_dirs,
            codelist_dir=Path(e.get("PETS_CODELIST_DIR", str(cls.codelist_dir))),
            results_dir=Path(e.get("PETS_RESULTS_DIR", str(cls.results_dir))),
            llm=LlmSettings(
                enabled=e.get("PETS_LLM_ENABLED", "false").strip().lower() in _TRUE,
                url=e.get("PETS_LLM_URL", LlmSettings.url),
                model=e.get("PETS_LLM_MODEL", LlmSettings.model),
                timeout_s=float(e.get("PETS_LLM_TIMEOUT_S", LlmSettings.timeout_s)),
                cache_dir=out_dir / ".cache" / "llm",
            ),
        )
