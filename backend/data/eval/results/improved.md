# Prompt eval: improved

- Model: `qwen2.5:7b`
- Date: 2026-11-19 21:10 UTC
- System prompt sha256: `d78ed840597eeecf`

| Metric | Value |
|---|---|
| First-try parseable JSON | 28/28 (100%) |
| First-try valid (schema + sources) | 26/28 (93%) |
| Final status accuracy | 22/28 (79%) |
|   expected answered | 20/20 (100%) |
|   expected needs_clarification | 0/3 (0%) |
|   expected no_source | 2/5 (40%) |
| Gold article cited (positives) | 20/20 (100%) |
| Citation precision (gold / all cited) | 20/28 (71%) |
| Citation precision, positives only | 20/20 (100%) |
| Unsupported claims | 0 |
| Fallbacks (no answer) | 0 |
| Repairs (>1 attempt) | 2 |
| Outputs with colloquial terms | 1/28 (4%) |
| Latency p50 | 32.3 s |
| Latency p95 | 60.2 s |

## Status misses

| Case | Expected | Got |
|---|---|---|
| neg-01 | no_source | needs_clarification |
| neg-02 | no_source | answered |
| neg-05 | no_source | needs_clarification |
| clar-01 | needs_clarification | answered |
| clar-02 | needs_clarification | answered |
| clar-03 | needs_clarification | answered |
