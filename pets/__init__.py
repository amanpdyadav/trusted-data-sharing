"""PETs Transformer: detect, plan, transform, measure and report on a privacy-protected data release."""
from pathlib import Path

try:  # load ANTHROPIC_API_KEY and PETS_HMAC_KEY from .env when present
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
PG_ROOT = ROOT / "challenge" / "proving_ground" / "TRUSTED_PETS_PROVING_GROUND_2026"
DATA = PG_ROOT / "data"
OUTPUTS = ROOT / "outputs"
