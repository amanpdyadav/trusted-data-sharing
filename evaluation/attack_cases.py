"""The two verified problem-demo attacks (see demo/mosaic_attack.py and the Mosaic Attack Walkthrough).

Clues are written as the attacker reads them from the public scrap; nothing here comes from the hospital data.
"""

import pandas as pd

from evaluation.attacks import AgedBetween, ArrivedBetween, AttackCase, Equals, Injured, StayedBetween

_POSTED = pd.Timestamp("2025-01-23 07:28")
_NEWS_DAY = pd.Timestamp("2025-12-31")

SOCIAL_POST = AttackCase(
    id="POST00635",
    scrap="adversary/social_posts_health.csv",
    description="'Spent 3 hours in the ER tonight. Slipped on ice, wrist pain.' posted by a named woman",
    target_record_id="ED25-003320",
    clues=(
        ArrivedBetween(_POSTED - pd.Timedelta(hours=12), _POSTED + pd.Timedelta(hours=1), "arrived in the 12 h before"),
        Equals("sex", "F", "female (from the name)"),
        StayedBetween(150, 210, "stayed about 3 hours"),
        Injured("injury diagnosis (slipped, wrist)"),
    ),
)

NEWS_CLIP = AttackCase(
    id="NEWS00100",
    scrap="adversary/news_clips_health.csv",
    description="'A 57-year-old man was injured in Turku on Wednesday when a firework exploded.' No name.",
    target_record_id="ED25-051327",
    clues=(
        ArrivedBetween(
            _NEWS_DAY - pd.Timedelta(days=1), _NEWS_DAY + pd.Timedelta(days=1), "arrived that day or the evening before"
        ),
        Equals("municipality", "Turku", "lives in Turku"),
        Equals("sex", "M", "male"),
        # The clip states the age exactly ("57-vuotias"); model the strongest realistic attacker, not a vaguer one.
        AgedBetween(57, 58, _NEWS_DAY, "aged 57"),
        Injured("injury diagnosis"),
    ),
)

DEMO_CASES: tuple[AttackCase, ...] = (SOCIAL_POST, NEWS_CLIP)
