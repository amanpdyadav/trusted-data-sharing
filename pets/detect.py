"""Step 1, Detect: classify every column of a table by privacy role and subtype.

Owner: Detect. Output must match metadata/taxonomy.md so `pets-eval detect` can score it:
a DataFrame with columns dataset, table, column, privacy_role, subtype (plus our own `reason`).
Approach: cheap rules on names and value patterns first, then the LLM for anything uncertain.
"""
import pandas as pd

ROLES = ["direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier",
         "free_text", "record_key", "non_sensitive"]


def detect_table(df: pd.DataFrame, dataset: str, table: str) -> pd.DataFrame:
    """Return one row per column: dataset, table, column, privacy_role, subtype, reason."""
    raise NotImplementedError("Detect: rules + LLM column classifier")
