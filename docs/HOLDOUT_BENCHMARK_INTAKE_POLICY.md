# HOLDOUT BENCHMARK INTAKE POLICY

Purpose:
- prepare real benchmark-populated holdout safely
- prevent leakage into train/eval
- require provenance before benchmark claims

Rules:
- every candidate must have a unique candidate_id
- every candidate must declare provenance, license, and language
- every candidate must declare whether manual transcript exists
- no candidate may be added to training
- no benchmark claims until candidate set is reviewed and promoted into locked_holdout_manifest.v1.json
- canonical truth remains:
  - .\nsb-speak.ps1
  - logs\LATEST\SPEAK_LAST_STATUS.json
  - logs\LATEST\FBL_STATUS_BUNDLE.txt

Status language:
- intake_only != benchmark_ready
- benchmark_ready is false until explicit promotion
