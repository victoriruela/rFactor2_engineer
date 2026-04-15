# rF2-Bench: Benchmarking Infrastructure

Evaluates LLM model quality for each pipeline role using golden test cases and LLM-as-a-Judge scoring.

## Structure

```
benchmarks/
  golden_dataset/       # JSON test cases (50+ planned)
  run_benchmark.go      # Orchestrator: runs models against golden cases
  evaluate.go           # Judge evaluator: scores responses on 5-dimension rubric
  report.go             # Generates markdown & JSON reports
  types.go              # Shared types
```

## Quick Start

```bash
go test ./internal/benchmarks/... -run TestBenchmark -v -count=1
```

## Golden Dataset Format

Each test case is a JSON file in `golden_dataset/`:

```json
{
  "id": "TC-001",
  "role": "suspension",
  "description": "Oversteer under braking into slow corner",
  "telemetry_summary": "...",
  "session_stats": { ... },
  "setup_sections": { ... },
  "expected_direction": {
    "REARLEFT.RearSpring": "increase",
    "REARRIGHT.RearSpring": "increase"
  },
  "expected_keywords": ["sobreviraje", "frenada", "muelle trasero"]
}
```

## Scoring Rubric (5 Dimensions)

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Physics correctness | 30% | Are recommendations physically sound? |
| Parameter direction | 25% | Do changes go in the right direction? |
| Consistency | 15% | No contradictions within the response |
| Spanish quality | 15% | Proper Spanish, no English leakage |
| Completeness | 15% | Addresses all relevant setup areas |

Pass threshold: ≥ 6.0 weighted average (out of 10).

## Usage

Populate `model_routing.json` with empirical winners after running benchmarks.
