"""Guards for our production rules and module boundaries. These fail the build if someone crosses a line."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pets_transformer"


def _modules() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


ANSWER_FILES = ("truth/", "field_catalog", "attack_specs", "pii_spans", "adversary/")


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_rule1_no_answer_files_or_organiser_scorer_at_runtime(path: Path) -> None:
    """Rule 1: runtime code must work on company data, which has no answer key."""
    assert not any(m == "pets_eval" or m.startswith("pets_eval.") for m in _imports(path)), (
        f"{path.name} imports the organisers' scorer"
    )
    for literal in _string_literals(path):
        hit = next((f for f in ANSWER_FILES if f in literal), None)
        assert hit is None, f"{path.name} refers to answer file {hit!r}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_rule2_only_the_ai_helper_talks_to_the_network(path: Path) -> None:
    """Rule 2: data stays on the machine. Only llm.py may open a connection, and it is localhost-only."""
    if path.name == "llm.py":
        return
    network = {"urllib.request", "http.client", "socket", "requests", "httpx", "aiohttp"}
    assert not (_imports(path) & network), f"{path.name} imports a network library"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_runtime_never_imports_the_evaluation_harness(path: Path) -> None:
    """Layering: evaluation may use the runtime package, never the other way round."""
    assert not any(m == "evaluation" or m.startswith("evaluation.") for m in _imports(path))


@pytest.mark.parametrize("package", ["transform", "assess", "plan", "keys.py", "contracts"])
def test_protection_and_checks_never_depend_on_the_ai(package: str) -> None:
    """The AI may advise; it may not protect or measure. Keeps releases reproducible with AI off."""
    target = SRC / package
    paths = [target] if target.is_file() else sorted(target.rglob("*.py"))
    for path in paths:
        assert "pets_transformer.llm" not in _imports(path), f"{path.name} imports the AI helper"
