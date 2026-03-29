# Batch A Benchmark Report - Jimmy llama3.1-8B

- Generated at (UTC): 2026-03-29T07:32:22.970817+00:00
- Source execution: docs/benchmark/results/jimmy_prompt_matrix_20260329T072854Z
- Matrix: docs/benchmark/prompt_matrix.json
- Total runs: 8

## Top 3 combinations

1. **batch_a_03** (batch_a_prose_json_strict_k8_t03) - score 0.9325; JSON 0.8500; coverage 1.0000; driving non-empty 1.0000; latency avg 3901.94 ms (p95 4104.24 ms).
2. **batch_a_06** (batch_a_structured_json_loose_k8_t0) - score 0.9033; JSON 0.8500; coverage 0.9167; driving non-empty 1.0000; latency avg 3692.11 ms (p95 3947.42 ms).
3. **batch_a_05** (batch_a_structured_json_loose_k8_t03) - score 0.8644; JSON 0.8500; coverage 0.8056; driving non-empty 1.0000; latency avg 3827.13 ms (p95 4043.56 ms).

## Common failure modes

- Specialist JSON parse/shape failures: 37 total across all runs.
- Chief None/invalid JSON (`full_setup.sections` missing): 11 total.
- Empty driving analyses (fallback/too short): 2 total.

## Latency tradeoffs

- Fastest avg latency: **batch_a_06** at 3692.11 ms (p95 3947.42 ms, score 0.9033).
- Slowest avg latency: **batch_a_07** at 3902.28 ms (p95 4092.42 ms, score 0.7519).
- In this batch, score differences are dominated by JSON validity and section coverage; latency spreads are comparatively small.

## Full ranking

1. batch_a_03 | score=0.9325 | json=0.8500 | cov=1.0000 | drive=1.0000 | avg=3901.94ms | p95=4104.24ms
2. batch_a_06 | score=0.9033 | json=0.8500 | cov=0.9167 | drive=1.0000 | avg=3692.11ms | p95=3947.42ms
3. batch_a_05 | score=0.8644 | json=0.8500 | cov=0.8056 | drive=1.0000 | avg=3827.13ms | p95=4043.56ms
4. batch_a_04 | score=0.8583 | json=0.7500 | cov=0.9167 | drive=1.0000 | avg=3826.86ms | p95=3912.60ms
5. batch_a_07 | score=0.7519 | json=0.6000 | cov=0.8056 | drive=1.0000 | avg=3902.28ms | p95=4092.42ms
6. batch_a_01 | score=0.7467 | json=0.6500 | cov=0.9167 | drive=0.6667 | avg=3813.91ms | p95=4034.55ms
7. batch_a_08 | score=0.6614 | json=0.5500 | cov=0.6111 | drive=1.0000 | avg=3891.45ms | p95=4151.69ms
8. batch_a_02 | score=0.5722 | json=0.5000 | cov=0.6111 | drive=0.6667 | avg=3708.17ms | p95=3993.45ms
