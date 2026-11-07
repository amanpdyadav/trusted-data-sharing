# Detection

Step 1 of the pipeline: work out what every column holds, how sure we are, and why it matters.
Owner: Hari (with Chinedu for free text). Code: `src/pets_transformer/detect/`.

## How it works

Two detectors label every column independently, and `combined.py` picks one label per column:

| Detector | File | Strength |
|---|---|---|
| Rule-based (Aman) | `detect/rules.py` | Validators with check digits, name hints in three languages, identifier columns, reference tables |
| Layered (Hari, from the main branch) | `detect/layered.py`, `detect/checks.py` | Works from values when names say nothing: trade-union vocabulary, health context from diagnosis codes, people tables, first-name lists and surname endings |
| **Combined** (default) | `detect/combined.py` | Agreeing labels stand; on a disagreement the stronger evidence (higher confidence) wins; ties keep the rule-based label |

`detect_source()` uses the combined detector, so the CLI (`pets-transformer detect`), the web app and
`python -m evaluation detect-all` all get it. Every label carries `evidence` (what fired) and, where the
layered detector contributed, `basis`: IDs of the laws and standards in `SOURCES.md`.

## Results (organisers' scorer, all 9 labelled datasets)

| Detector | Macro-F1 | Sensitive attributes found | Names hidden (like the HR file) |
|---|---|---|---|
| Baseline B1 (organisers) | 0.646 | 10 % | – |
| Rule-based | 0.875 | 62 % | 0.669 |
| Layered | 0.907 | 85 % | 0.779 |
| **Combined** | **0.930** | **88 %** | **0.790** |

Both detectors were tuned on overlapping data, so no held-out number is fully clean: see `SCORES.md` and
`DECISIONS.md` (D6, D7). The unseen HR file is the clean test; organisers hold its labels.

## Files

- `SOURCES.md`: every rule, law and standard we rely on, and what we took from it
- `DECISIONS.md`: each design decision with options, reason and source
- `SCORES.md`: every measured iteration, from the organisers' baseline onwards
- `FORMAT.md`: the main branch's original `detection.json` format (kept for reference; the shared contract is now
  `contracts/detection.py`, which gained `basis` and `needed_by`)

## Commands

```bash
python -m evaluation detect-all                               # score every dataset (education held out)
pets-transformer detect --dataset unseen --source csv:<package>/data/unseen --out out/unseen/detection.json \
  --labels-csv pets_submission/unseen_field_labels.csv        # the HR file labels for the organisers
```
