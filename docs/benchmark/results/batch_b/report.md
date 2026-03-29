# Batch B Benchmark Report - Jimmy llama3.1-8B

- Generated at (UTC): 2026-03-29T07:44:07.549561+00:00
- Source execution: docs/benchmark/results/jimmy_prompt_matrix_20260329T074051Z
- Matrix: docs/benchmark/prompt_matrix_batch_b.json
- Total runs: 8

## Top 3 combinations

1. **batch_b_07** (batch_b_hybrid_strict_compact_k8_t0) - score 0.9325; JSON 0.8500; coverage 1.0000; driving non-empty 1.0000; latency avg 3813.77 ms (p95 4153.84 ms).
2. **batch_b_05** (batch_b_structured_loose_guarded_k8_t01) - score 0.8292; JSON 0.7500; coverage 0.8333; driving non-empty 1.0000; latency avg 3803.94 ms (p95 4010.00 ms).
3. **batch_b_08** (batch_b_hybrid_strict_compact_k8_t02) - score 0.8292; JSON 0.7500; coverage 0.8333; driving non-empty 1.0000; latency avg 3837.83 ms (p95 4052.40 ms).

## Comparison vs Batch A winner

- Batch A top run: **batch_a_03** (batch_a_prose_json_strict_k8_t03) with score 0.9325.
- Batch B recommended winner: **batch_b_07** (batch_b_hybrid_strict_compact_k8_t0) with score 0.9325.
- Composite score delta (B - A): -0.0000.
- JSON validity delta (B - A): +0.0000.
- Coverage delta (B - A): +0.0000.
- Driving non-empty delta (B - A): +0.0000.
- Avg latency delta ms (B - A): -88.17.

## Common failure modes

- Specialist JSON parse/shape failures: 39 total across all runs.
- Chief None/invalid JSON (`full_setup.sections` missing): 11 total.
- Empty driving analyses (fallback/too short): 0 total.

## Recommendation

Use **batch_b_07** as the current winner for next-phase integration because it maximizes composite score under the Batch A scoring function while preserving full driving-analysis availability.

## Full ranking

1. batch_b_07 | score=0.9325 | json=0.8500 | cov=1.0000 | drive=1.0000 | avg=3813.77ms | p95=4153.84ms
2. batch_b_05 | score=0.8292 | json=0.7500 | cov=0.8333 | drive=1.0000 | avg=3803.94ms | p95=4010.00ms
3. batch_b_08 | score=0.8292 | json=0.7500 | cov=0.8333 | drive=1.0000 | avg=3837.83ms | p95=4052.40ms
4. batch_b_01 | score=0.8128 | json=0.8000 | cov=0.7222 | drive=1.0000 | avg=3933.32ms | p95=4165.04ms
5. batch_b_06 | score=0.7842 | json=0.6500 | cov=0.8333 | drive=1.0000 | avg=3885.81ms | p95=4047.66ms
6. batch_b_02 | score=0.7064 | json=0.6500 | cov=0.6111 | drive=1.0000 | avg=3902.65ms | p95=4311.46ms
7. batch_b_04 | score=0.6711 | json=0.5500 | cov=0.6389 | drive=1.0000 | avg=3845.23ms | p95=4099.36ms
8. batch_b_03 | score=0.5611 | json=0.5000 | cov=0.3889 | drive=1.0000 | avg=3751.78ms | p95=3874.81ms
