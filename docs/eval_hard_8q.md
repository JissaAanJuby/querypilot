# QueryPilot Evaluation Results

- Date: 2026-09-29 07:39
- Model: gemini-3.5-flash-lite
- Questions: 8

## Ablation

| Configuration | Execution Accuracy | Avg Latency | Failed Queries |
|---|---|---|---|
| Baseline | 100.0% (8/8) | 1.61 s | 0 |
| Self-Correction | 100.0% (8/8) | 1.47 s | 0 |

## Accuracy by difficulty

| Configuration | hard |
|---|---|
| Baseline | 8/8 |
| Self-Correction | 8/8 |

## Failure analysis (self-correction run)

- Total queries: 8
- Initial failures (attempt 1 error or empty): 0
- Successfully corrected: 0
- Remaining failures: 0
- Correction success rate: n/a
- Average attempts per query: 1.00
- Attempt-1 accuracy within this same run: 100.0%

### Queries that needed correction

### Executed successfully but WRONG (semantic errors)

None in this run.