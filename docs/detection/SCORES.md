# Detection scores

Scored with `pets-eval detect` against `metadata/field_catalog.csv` (475 columns, 9 datasets).
Dev = health, finance, cyber, customer_service, education. Held out = mobility, smart_city, energy, public_admin.
"Sensitive found" is the recall of the `sensitive_attribute` role (the team plan's "sensitive columns found").

| # | Date | What changed | Set | Macro-F1 | Sensitive found | Subtype acc. | Notes |
|---|---|---|---|---|---|---|---|
| 0 | 7 Nov | Organisers' baseline B1 (`results/b1_field_labels.csv`) | all 9 | 0.646 | 0.10 | 0.60 | Reproduces BENCHMARK.md. Weakest roles: sensitive attribute F1 0.16, non-sensitive 0.62, quasi-identifier 0.67 |
| 1 | 7 Nov | Detector v1: format checkers, structure, vocabularies, health context, name hints | dev | 0.832 | 0.86 | 0.75 | 65 of 331 roles wrong. Main errors: ICD false positives on school codes, health context leaking into education tables, over-broad name hints, shop names and job titles passing as personal names |
| 2 | 7 Nov | v2: ICD needs ≥ 3 distinct letters; health context only from diagnosis codes; tighter name hints; first-name list and surname endings; domains; people tables | dev | 0.927 | 0.91 | 0.84 | 26 wrong |
| 3 | 7 Nov | v3 (frozen): sparse label columns, people-table IDs, file names are not domains | dev | 0.959 | 0.89 | 0.88 | Tuned on these 331 columns |
| 3 | 7 Nov | v3, names hidden | dev | 0.787 | 0.29 | 0.67 | Values alone cannot tell a heart rate from any other number |
| 3 | 7 Nov | **v3 on held-out (clean test, run once)** | held out | **0.620** | 0.00 | 0.75 | **Baseline B1 on the same 4 datasets: 0.632.** No better than baseline on unseen data: the dev score was mostly fit. See D6 |
| 3 | 7 Nov | v3 on held-out, names hidden | held out | 0.647 | 0.00 | 0.74 | |
| – | 7 Nov | Baseline B1 split the same way | dev / held out | 0.654 / 0.632 | 0.11 / 0.00 | | For a fair comparison |
| 4 | 7 Nov | v4: card issuer prefix, plausible coordinate range, tables about places not people, late-payment and medical vocabulary | dev | 0.959 | 0.89 | 0.88 | No change on dev |
| 4 | 7 Nov | v4 on held-out, **after seeing its errors (not a clean test)** | held out | 0.768 | 0.60 | 0.78 | Baseline B1: 0.632 / 0.00 |
| 4 | 7 Nov | v4, names hidden | held out | 0.711 | 0.00 | 0.75 | |
| 4 | 7 Nov | v4, all 9 datasets | all | **0.907** | **0.85** | 0.85 | Baseline B1: 0.646 / 0.10. Beats both plan targets, with the held-out caveat above |
| 4 | 7 Nov | v4, all 9 datasets, names hidden | all | 0.779 | 0.25 | 0.69 | The gap the local model (D5) must close for the unseen HR file |
| – | 7 Nov | Aman's rule-based detector (branch bring-final-pets-transformer), same scorer | all 9 | 0.875 | 0.62 | 0.81 | Names hidden 0.669 / 0.03. His clean held-out (education) 0.676 |
| 5 | 7 Nov | **Combined** (rule-based + layered, stronger evidence wins), on the combine branch | all 9 | **0.930** | **0.88** | 0.87 | Names hidden 0.790 / 0.25. Not clean on either held-out set: each one is the other detector's tuning data |
| 5 | 7 Nov | Combined, `python -m evaluation detect-all` | dev 8 / education | 0.934 / 0.899 | 0.90 / 0.80 | 0.88 / 0.75 | Education was in the layered detector's dev set |

Team plan targets: macro-F1 ≥ 0.85, sensitive found ≥ 70 %.
