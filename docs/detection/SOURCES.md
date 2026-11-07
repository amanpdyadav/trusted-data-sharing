# Sources register

What each detection rule relies on. Verify section numbers before quoting them in the video or the submission.
"Pack" means the challenge pack in `challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026/`.

## Challenge rules (define how we are scored)

| ID | Source | What we take from it |
|---|---|---|
| S-TAX | Pack `metadata/taxonomy.md` | The 7 privacy roles, data kinds, subtypes, and the CSV format `pets-eval detect` scores |
| S-CAT | Pack `metadata/field_catalog.csv` | Ground-truth labels for 475 columns in 9 datasets. Used **only for scoring**, never read by the detector |
| S-DICT | Pack `docs/DATA_DICTIONARY.md` | What each column means; the "traps" notes (hidden identifiers) |
| S-EVAL | Pack `docs/EVALUATION.md` | Scoring: per-role precision/recall/F1, macro-F1, subtype accuracy |
| S-BENCH | Pack `docs/BENCHMARK.md` | Baseline B1: macro-F1 0.65, sensitive-attribute recall 0.10 |
| S-PLAY | Pack `docs/PET_PLAYBOOK.md` | Which protections apply to which kind of column; cites Article 29 WP Opinion 05/2014 and ENISA |
| S-UNSEEN | Pack `data/unseen/README.md` | Unseen HR file: uninformative names, values only, organisers hold the labels |
| S-PLAN | Team build plan (Aman, 6 Nov) | Detection scope, `detection.json`, targets F1 ≥ 0.85 and sensitive found ≥ 70 %, local AI rules |

## Law: why a column is personal, sensitive or safe

| ID | Source | What we take from it |
|---|---|---|
| L-GDPR-4.1 | GDPR Art. 4(1) | Personal data: any information relating to an identified or identifiable person, "directly or indirectly". Basis for direct vs quasi-identifiers |
| L-GDPR-R26 | GDPR Recital 26 | Identifiability judged by "means reasonably likely to be used", e.g. singling out. Basis for quasi-identifiers and combinations |
| L-GDPR-9 | GDPR Art. 9(1) | Special categories: health, racial or ethnic origin, political opinions, religious or philosophical beliefs, trade union membership, genetic, biometric, sex life or sexual orientation. Basis for `sensitive_attribute` |
| L-GDPR-5 | GDPR Art. 5(1)(c), Art. 25 | Data minimisation, data protection by design. Why every column is labelled before any protection is chosen |
| L-GDPR-4.5 | GDPR Art. 4(5) | Pseudonymisation. What later steps do with detected identifiers |
| L-FI-DPA | Finnish Data Protection Act 1050/2018, section 29 | Specific rules for processing the personal identity code (HETU) |
| L-FI-SUA | Act on the Secondary Use of Health and Social Data 552/2019 (Findata) | Legal frame for health research releases (HEALTH-S1) |
| L-FI-ECSA | Act on Electronic Communications Services 917/2014 (supervised in part by Traficom) | Traffic and location data are confidential. Basis for treating IPs, sign-in and call records as identifying |
| L-CJEU-IP | CJEU C-582/14 *Breyer* (2016) | A dynamic IP address can be personal data when the holder can be identified with additional data |

## Format standards: how a value is recognised

| ID | Source | Check used |
|---|---|---|
| F-HETU | Digital and Population Data Services Agency (DVV), personal identity code | `DDMMYY` + century sign + 3-digit individual number + check character; check = (9 digits) mod 31 into `0123456789ABCDEFHJKLMNPRSTUVWXY`. Century signs: `+` 1800s; `-` `Y` `X` `W` `V` `U` 1900s; `A` `B` `C` `D` `E` `F` 2000s (extra signs since 2023). Odd individual number = male |
| F-YTUNNUS | Finnish Business ID (Y-tunnus), Finnish Patent and Registration Office / Tax Administration | 7 digits + `-` + check digit, weights 7,9,10,5,8,4,2, mod 11 |
| F-IBAN | ISO 13616 | Country code + 2 check digits + BBAN; mod-97 = 1. Finnish IBANs are 18 characters |
| F-CARD | ISO/IEC 7812 | 13–19 digits passing the Luhn check |
| F-PHONE | Traficom numbering regulation (Finnish numbering plan); ITU-T E.164 | `+358` or a leading `0`; mobile prefixes 040–050 range; foreign numbers in E.164 (`+46…`) |
| F-PLATE | Traficom vehicle register (Finnish registration plates) | Letters + `-` + digits, e.g. `ABC-123` |
| F-POST | Posti (Finnish postal codes) | 5 digits |
| F-EMAIL | RFC 5322 (simplified) | `local@domain.tld` |
| F-IP | RFC 791 (IPv4), RFC 4291 (IPv6) | Dotted quad / hex groups |
| F-MAC | IEEE 802 | Six hex octets; the locally administered bit (2nd hex digit 2/6/A/E) marks randomised MACs |
| F-ICD10 | WHO ICD-10 | Letter + 2 digits, optional `.` + digit: diagnosis code, so health data (L-GDPR-9) |
| F-GSRN | GS1 Global Service Relation Number | 18 digits with GS1 mod-10 check: electricity metering point IDs |

## Further reading (for questions from judges)

- EDPB Guidelines 01/2025 on pseudonymisation
- Article 29 Working Party, Opinion 05/2014 on anonymisation techniques
- ISO/IEC 20889:2018 (de-identification techniques), ISO/IEC 27559:2022 (de-identification framework)
- NIST SP 800-188, De-identifying Government Datasets
