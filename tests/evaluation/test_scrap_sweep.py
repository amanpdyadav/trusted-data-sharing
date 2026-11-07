"""Post and news sweep: clue reading and the diagnosis-group clue (no data package needed)."""

import pandas as pd

from evaluation.attacks import StayedBetween
from evaluation.scrap_sweep import InGroup, _news_clues, _post_clues, symptom_group


def test_symptoms_map_to_diagnosis_groups_in_three_languages() -> None:
    assert symptom_group("Slipped on ice, wrist pain.") == "injury"
    assert symptom_group("Jo 7 tuntia päivystyksessä 🙄 kova päänsärky") == "neurological"
    assert symptom_group("Aurajoen päivystyksessä taas. Kirvelyä virtsatessa ja kuume.") == "urological"
    assert symptom_group("Hello") is None


def test_post_clues_read_time_town_sex_stay_and_symptoms() -> None:
    post = {"posted_ts": "2025-01-23 07:28:00", "profile_city": "Turku", "display_name": "Riitta Lipponen",
            "text": "Spent 3 hours in the ER tonight. Slipped on ice, wrist pain."}  # fmt: skip
    clues = _post_clues(post, {"Riitta": "F"})
    labels = [c.label for c in clues]
    assert labels[1:3] == ["lives in Turku", "'Riitta' is usually a woman's name"]
    stay = next(c for c in clues if isinstance(c, StayedBetween))
    assert (stay.low_min, stay.high_min) == (120, 210)


def test_news_clues_read_hour_age_and_sex() -> None:
    clip = {"event_date": "2025-07-07", "place": "Turku", "sex_mentioned": "F", "age_mentioned": "90",
            "text": "Pelastus sai kello 8 ilmoituksen. Noin 90-vuotias nainen kaatui kotonaan."}  # fmt: skip
    labels = [c.label for c in _news_clues(clip, pd.Timestamp("2025-07-07"))]
    assert "rescue called at 8:00" in labels
    assert "aged about 90" in labels


def test_in_group_keeps_unknown_rows_and_reads_codes_or_groups() -> None:
    codes = pd.DataFrame({"icd10_primary": ["S52", "J18", ""]})
    assert InGroup("injury", "x").matches(codes).tolist() == [True, False, True]
    groups = pd.DataFrame({"diagnosis_group": ["injury", "ILI"]})
    assert InGroup("injury", "x").matches(groups).tolist() == [True, False]
