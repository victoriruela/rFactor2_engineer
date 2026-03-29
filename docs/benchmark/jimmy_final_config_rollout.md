# Jimmy Final Config Rollout (T6)

This document codifies the final Jimmy configuration selected from benchmark outputs in:

- `docs/benchmark/results/batch_a/report.md`
- `docs/benchmark/results/batch_b/report.md`

Versioned runtime-facing artifact:

- `app/core/jimmy_runtime_config.v1.json`

## Final Selected Settings

- `selectedModel`: `llama3.1-8B`
- `prompt variant`: `batch_b_hybrid_strict_compact_k8_t0` (`run_id`: `batch_b_07`)
- `prompt source`: `docs/benchmark/prompt_matrix_batch_b.json`
- `topK`: `8`
- `temperature`: `0.0`
- `parse/cleanup`: strip Jimmy stats tags, strip outer quotes, trim whitespace, extract first JSON object, clean trailing commas before JSON parse

## Why This Winner

- Batch A winner was `batch_a_03` with score `0.9325`.
- Batch B winner `batch_b_07` matches the same score `0.9325` and improves avg latency by `88.17 ms`.
- Batch B report recommendation explicitly selects `batch_b_07` for next-phase integration.

## Fallback Policy (Code-Facing)

See `fallbackPolicy` in `app/core/jimmy_runtime_config.v1.json`.

Policy summary:

- Retry budget: `1` retry per stage.
- Retry on: empty output, specialist invalid JSON/missing `items`, `chief_none`, chief invalid JSON/missing `full_setup.sections`, empty/too-short driving analysis.
- Do not retry on: non-retryable client errors (`HTTP 4xx` except `408` and `429`) and repeated prompt-contract violations after retry.
- On exhausted retries: mark degraded mode (`degraded=true`) and set `fallback_reason`.

## Production Rollout Acceptance Criteria

- Runtime integration reads settings from `app/core/jimmy_runtime_config.v1.json` without parameter drift.
- Regression benchmark score remains `>= 0.93` on the same fixture dataset.
- Failure handling emits degraded signal (`degraded=true`, `fallback_reason`) for all exhausted retries.
- Chief invalid/None outcomes are governed by the configured retry policy before fallback.
- Scope guard: this task only delivers config/spec artifacts and does not wire runtime behavior.