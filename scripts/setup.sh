#!/usr/bin/env bash
# One-time setup after cloning: unpack the challenge pack, create the Python environment,
# write .env with a fresh pseudonym key, and build our HEALTH-S1 release.
#
#   ./scripts/setup.sh                                  # finds the pack zip in the usual places
#   ./scripts/setup.sh ~/Downloads/TRUSTED_PETS_PROVING_GROUND_2026.zip
#
# Safe to run again: every step skips work that is already done.
set -euo pipefail
cd "$(dirname "$0")/.."

PACK_DIR="challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026"
say() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
die() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# 1. Challenge pack (team-only, never committed)
say "1/4 Challenge pack"
if [ -d "$PACK_DIR/data" ]; then
  echo "Already unpacked at $PACK_DIR"
else
  ZIP="${1:-${PETS_PACK_ZIP:-}}"
  if [ -z "$ZIP" ]; then
    for candidate in challenge/brief/TRUSTED_PETS_PROVING_GROUND_2026*.zip \
                     ~/Downloads/TRUSTED_PETS_PROVING_GROUND_2026*.zip \
                     ~/Downloads/TRUSTED_SinceAI2026_FINAL/TRUSTED_PETS_PROVING_GROUND_2026*.zip; do
      [ -f "$candidate" ] && ZIP="$candidate" && break
    done
  fi
  [ -n "$ZIP" ] && [ -f "$ZIP" ] || die "Challenge pack zip not found.
  Get TRUSTED_PETS_PROVING_GROUND_2026.zip from the team drive, then run:
    ./scripts/setup.sh /path/to/TRUSTED_PETS_PROVING_GROUND_2026.zip"
  echo "Unpacking $ZIP"
  mkdir -p challenge/proving_ground
  unzip -q "$ZIP" -d challenge/proving_ground && rm -rf challenge/proving_ground/__MACOSX
  [ -d "$PACK_DIR/data" ] || die "Unpacked, but $PACK_DIR/data is missing. Is this the right zip?"
fi

# 2. Python environment (3.12; the Mac's default 3.14 breaks some scientific packages)
say "2/4 Python environment"
if command -v uv >/dev/null 2>&1; then
  [ -x .venv/bin/python ] || uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -q -r requirements.txt -e "$PACK_DIR/toolkit"
else
  echo "uv not found, using python3 -m venv (install uv for faster setup: https://docs.astral.sh/uv/)"
  PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
  [ -x .venv/bin/python ] || "$PY" -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt -e "$PACK_DIR/toolkit"
fi
.venv/bin/python -c "import pets_eval, streamlit, pandas; print('Python', __import__('sys').version.split()[0], '· packages OK')"

# 3. Secrets
say "3/4 .env"
if [ -f .env ]; then
  echo ".env already exists, leaving it alone"
else
  key=$(.venv/bin/python -c "import secrets; print(secrets.token_hex(32))")
  sed "s/^PETS_HMAC_KEY=.*/PETS_HMAC_KEY=$key/" .env.example > .env
  echo "Created .env with a new PETS_HMAC_KEY. Add your ANTHROPIC_API_KEY when the LLM steps need it."
fi

# 4. Releases the app compares: the toolkit's quickstart example and our HEALTH-S1 release
say "4/4 Releases for the app"
if [ -f "$PACK_DIR/results/quickstart/health/ed_visits.csv" ]; then
  echo "Toolkit quickstart release already built"
else
  (cd "$PACK_DIR" && ../../../.venv/bin/python examples/quickstart.py > /dev/null) && echo "Built toolkit quickstart release"
fi
if [ -f outputs/health/scorecard.json ]; then
  echo "Already built (delete outputs/health to rebuild)"
else
  .venv/bin/python scripts/build_health_s1.py | tail -n 12
fi

say "Done. Start the app with:"
echo "  .venv/bin/streamlit run app/streamlit_app.py"
