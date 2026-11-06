"""Linkage attack demo: play the attacker against a release and show who can be re-identified.

Uses the attacker knowledge shipped in the challenge pack (news clips, social posts, public directory)
and the toolkit's own linkage attack, so the numbers match the official scorecard. Everything is synthetic.
"""
from pathlib import Path

import pandas as pd
from pets_eval import attacks, io

from . import DATA, PG_ROOT

ADVERSARIES = {
    "news_clips_health": "Local news story about an accident",
    "social_posts_health": "Social media post from the emergency department",
    "public_directory": "Public phone and address directory",
}


def _spec(dataset: str, table: str, adversary: str) -> dict:
    for sp in io.load_attack_specs(PG_ROOT):
        if sp["dataset"] == dataset and sp["table"] == table and sp["adversary"] == adversary:
            return sp
    raise KeyError(f"no attack spec for {adversary} on {dataset}/{table}")


def names_removed(dataset: str, table: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The naive release most organisations make: drop the direct identifiers, keep everything else."""
    orig = io.read_table(DATA / dataset / f"{table}.csv")
    cat = io.load_catalog(PG_ROOT)
    direct = cat[(cat.dataset == dataset) & (cat.table == table) & (cat.privacy_role == "direct_identifier")].column
    rk = io.record_key(cat, dataset, table, orig)
    rowmap = pd.DataFrame({"protected_row": range(len(orig)), "original_record_id": orig[rk].astype(str)})
    return orig.drop(columns=[c for c in direct if c in orig.columns]), rowmap


def run_attack(protected: pd.DataFrame, rowmap: pd.DataFrame, adversary: str,
               dataset: str = "health", table: str = "ed_visits") -> dict:
    """Re-identification and diagnosis-inference rates for one attacker against one release."""
    sp = _spec(dataset, table, adversary)
    adv, truth = io.load_adversary(PG_ROOT, adversary)
    identity = io.load_identity_truth(PG_ROOT, dataset, table)
    orig = io.read_table(DATA / dataset / f"{table}.csv")
    cat = io.load_catalog(PG_ROOT)
    qis = attacks.qis_from_spec(sp["qis"], protected.columns)
    if not qis:
        return {"adversary": adversary, "reidentification_rate": 0.0,
                "note": "every attacker column this attack needs was removed"}
    temporal = list(cat[(cat.dataset == dataset) & (cat.table == table) & (cat.data_kind == "temporal")].column)
    res = attacks.linkage_attack(adv, truth, protected.reset_index(drop=True), rowmap, identity, qis=qis,
                                 original=orig, record_key=io.record_key(cat, dataset, table, orig),
                                 sensitive=sp.get("sensitive"), temporal_cols=temporal)
    res["adversary"] = adversary
    return res


def example_matches(protected: pd.DataFrame, adversary: str = "news_clips_health", n: int = 3,
                    dataset: str = "health", table: str = "ed_visits", show: str = "icd10_primary") -> list[dict]:
    """Walk-through examples: what the attacker read, how many records match, and what a unique match reveals."""
    sp = _spec(dataset, table, adversary)
    adv, _ = io.load_adversary(PG_ROOT, adversary)
    qis = attacks.qis_from_spec(sp["qis"], protected.columns)
    prot = protected.reset_index(drop=True)
    prep = attacks._Prepared(prot, qis)  # toolkit internal: candidate records for one attacker row
    text_col = next((c for c in ("text", "headline", "name") if c in adv.columns), adv.columns[1])
    out = []
    for r in adv.to_dict("records"):
        cand, used = prep.candidates(r)
        if used == 0 or len(cand) == 0:
            continue
        out.append({"attacker_knows": r[text_col], "matching_records": int(len(cand)),
                    "revealed": prot.loc[cand[0], show] if len(cand) == 1 and show in prot.columns else None})
        if len(out) >= n:
            break
    return out


def mosaic_link(a: tuple[str, str], b: tuple[str, str], key_a: list[str], key_b: list[str]) -> dict:
    """Cross-dataset linkage (the mosaic effect): join two names-removed releases on shared quasi-identifiers
    and check against the ground truth how many people are linked, and how many of those links are right."""
    def side(ds, tb, key):
        df, _ = names_removed(ds, tb)
        cat = io.load_catalog(PG_ROOT)
        rk = io.record_key(cat, ds, tb, df)
        truth = io.load_identity_truth(PG_ROOT, ds, tb)
        df = df.merge(truth.rename(columns={truth.columns[0]: rk, truth.columns[1]: "person_id"}), on=rk)
        df = df.drop_duplicates("person_id").rename(columns=dict(zip(key, [f"k{i}" for i in range(len(key))])))
        keys = [f"k{i}" for i in range(len(key))]
        return df[df.groupby(keys)[keys[0]].transform("size") == 1], keys
    left, keys = side(*a, key_a)
    right, _ = side(*b, key_b)
    m = left.merge(right, on=keys, suffixes=("_a", "_b"))
    correct = int((m.person_id_a == m.person_id_b).sum())
    return {"linked": int(len(m)), "correct": correct, "precision": round(correct / len(m), 4) if len(m) else 0.0,
            "people_a": int(left.shape[0]), "joined_on": dict(zip(key_a, key_b)), "matches": m}


def load_release(folder: Path, table: str = "ed_visits") -> tuple[pd.DataFrame, pd.DataFrame]:
    """A protected release folder written by our transform (or the quickstart): table plus its scoring row map."""
    return io.read_table(Path(folder) / f"{table}.csv"), io.load_rowmap(Path(folder) / f"rowmap_{table}.csv")
