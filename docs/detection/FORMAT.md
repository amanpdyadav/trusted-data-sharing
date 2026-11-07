# detection.json format (v1, main branch)

> Kept for reference. On this branch the shared file is `contracts/detection.py` (`DetectionReport`), which took
> over two fields from this format: `basis` (law and standard IDs) and `needed_by` (scenarios that request the
> column). The paths below are the main branch's.

The shared file from step 1 (Detect) to step 2 (Plan). One file per dataset, written to
`outputs/detection/<dataset>.detection.json` by `scripts/detect_eval.py --write` or `pets.detection_file.write()`.
Owners: Hari and Chinedu. Readers: Aman (plan), Anjali (screens), Silenat (scores).

```jsonc
{
  "schema": "pets-transformer/detection/v1",
  "dataset": "health",
  "created_utc": "2026-11-07T10:12:00+00:00",
  "detector": { "version": "v4", "column_names_used": true, "rows_sampled_per_table": 20000,
                "values_checked_per_column": 400, "review_below": 0.6 },
  "summary": {
    "tables": 4, "columns": 53,
    "by_role": { "direct_identifier": 6, "quasi_identifier": 13, "...": 0 },
    "art9_columns": ["ed_visits.icd10_primary", "..."],   // special-category data (GDPR Art. 9)
    "needs_review": ["ed_visits.ambulance_unit", "..."],  // sure < review_below: a person (or the local model) checks these
    "needed_by_any_task": 24
  },
  "tables": {
    "ed_visits": {
      "rows": 46398, "sampled_rows": 20000,
      "about_people": true,                 // false = the table describes places or equipment, not people
      "columns": [
        {
          "column": "los_minutes",
          "role": "sensitive_attribute",    // one of the 7 roles in metadata/taxonomy.md (pets-eval calls it privacy_role)
          "subtype": "HEALTH_DATA",         // taxonomy subtype
          "sure": 0.65,                     // 0–1: how strongly the evidence agrees
          "method": "name",                 // rule | name | context | llm
          "evidence": "column name 'los_minutes' indicates health data",
          "basis": ["L-GDPR-9"],            // IDs in "sources" below and in docs/detection/SOURCES.md
          "art9": true,                     // special-category data under GDPR Art. 9
          "review": false,
          "needed_by": [                    // analyses that use this column (from the organisers' task definitions)
            { "task": "H-U2", "scenarios": ["HEALTH-S1", "HEALTH-S3"],
              "alternative": true,          // true = the task can use another column instead (see "need")
              "need": "los_minutes|arrival_ts+discharge_ts" }
          ]
        }
      ]
    }
  },
  "tasks":   { "H-U2": { "description": "Median length of stay by triage level", "table": "ed_visits",
                         "kind": "aggregate", "scenarios": ["HEALTH-S1", "HEALTH-S3"], "needs": ["triage", "..."] } },
  "sources": { "L-GDPR-9": "GDPR Art. 9(1)", "F-HETU": "Digital and Population Data Services Agency (DVV), personal identity code" }
}
```

## How the plan step should read it

- **`role` + `subtype`** say what the column is. They do not say what to do with it.
- **`needed_by`** says what breaks if the column is dropped. Filter by the release's scenario: a column needed by a
  task in that scenario must be kept in some form (generalised, pseudonymised, noised), unless `alternative` is true
  and another option of the same need is kept.
- **`art9`** marks special-category data: these need the strongest justification to release at row level.
- **`review`** marks columns the rules are unsure about. Show them to the person approving the plan.
- **`evidence` + `basis`** are the explanation to show on screen and in the release note.

## Relation to the scorer

`pets-eval detect` scores a CSV `dataset,table,column,privacy_role,subtype`. It is the same labels: `role` here is
`privacy_role` there.
