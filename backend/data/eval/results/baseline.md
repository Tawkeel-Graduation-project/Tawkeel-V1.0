# Prompt eval: baseline

- Model: `qwen2.5:7b`
- Date: 2026-11-19 20:51 UTC
- System prompt sha256: `83a71b5cf7c96e68`

| Metric | Value |
|---|---|
| First-try parseable JSON | 28/28 (100%) |
| First-try valid (schema + sources) | 26/28 (93%) |
| Final status accuracy | 22/28 (79%) |
|   expected answered | 20/20 (100%) |
|   expected needs_clarification | 0/3 (0%) |
|   expected no_source | 2/5 (40%) |
| Gold article cited (positives) | 20/20 (100%) |
| Citation precision (gold / all cited) | 20/29 (69%) |
| Unsupported claims | 0 |
| Fallbacks (no answer) | 0 |
| Repairs (>1 attempt) | 2 |
| Outputs with colloquial terms | 0/28 (0%) |
| Latency p50 | 31.6 s |
| Latency p95 | 58.8 s |

## Status misses

| Case | Expected | Got |
|---|---|---|
| neg-01 | no_source | needs_clarification |
| neg-02 | no_source | answered |
| neg-05 | no_source | needs_clarification |
| clar-01 | needs_clarification | answered |
| clar-02 | needs_clarification | answered |
| clar-03 | needs_clarification | answered |
