# Acceptance Criteria (Definition of Done)

## Fixed evaluation set
- Path: TBD
- Description: A stable held-out set that is never used for training.

## Baseline
- Baseline model/run-id: TBD
- Baseline WER: TBD

## Target
- Target WER: TBD
- Minimum improvement vs baseline: TBD (absolute or relative)

## Pass/Fail Rules
PASS if:
- WER <= Target WER
- Evaluation is reproducible (same eval set, same decoding settings)

FAIL if:
- WER missing OR evaluation not reproducible
- Regression vs baseline beyond tolerance

## Notes
- Keep decoding settings fixed (beam size, temperature, etc.)
- Record: run-id, dataset hash, commit hash (if applicable)

<!-- ACCEPT_AUTOPILOT_START -->
## Baseline (current)

- Baseline run-id: ALT2_20260102_195009
- Baseline WER   : 1.32668329177057
- Baseline loss  : 0.0945207849144936
- Eval source    : logs\LATEST\EVAL.log

## Initial target (adjustable)

- Target WER: 1.061347  (20% relative improvement vs baseline)

## Pass/Fail (draft)

PASS if:
- Offline fixed-eval WER <= Target WER
- Decoding settings fixed and recorded
- Evaluation reproducible

FAIL if:
- WER missing / irreproducible
- Regression vs baseline

<!-- ACCEPT_AUTOPILOT_END -->
