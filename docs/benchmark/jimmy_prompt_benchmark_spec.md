# Jimmy Prompt Benchmark Spec (T1)

## Purpose

Define a reproducible benchmark contract for Jimmy prompt tuning before implementing an execution harness.

This spec locks:

- input dataset location,
- objective metrics,
- pass/fail thresholds,
- scoring expectations for qualitative reasoning.

## Dataset

Benchmark fixture cases are stored in:

`tests/integration/fixtures/benchmark_cases/`

Current baseline set:

- `case_01_suzuka_baseline.json`
- `case_02_suzuka_mid_understeer.json`
- `case_03_suzuka_exit_oversteer.json`

Case schema is defined in:

`tests/integration/benchmark_schema.py`

## Evaluation Unit

One benchmark run executes `AIAngineer.analyze()` once per case and records:

- full response payload,
- per-case wall-clock latency,
- extracted specialist/chief JSON blocks,
- rubric scores.

## Metrics and Thresholds

All thresholds are release gates for Jimmy prompt updates.

### 1) JSON Validity Rate (specialists and chief)

Definition:

- `specialists_json_validity_rate = valid_specialist_json_outputs / total_specialist_outputs`
- `chief_json_validity_rate = valid_chief_json_outputs / total_cases`

A specialist output is valid when it parses as JSON and includes `items` (list). A chief output is valid when it parses as JSON and includes `full_setup.sections`.

Thresholds:

- `specialists_json_validity_rate >= 0.95`
- `chief_json_validity_rate >= 0.98`

### 2) Non-Empty Driving Analysis Rate

Definition:

- `non_empty_driving_analysis_rate = cases_with_non_empty_driving_analysis / total_cases`

A driving analysis is non-empty when:

- text length `>= 80` characters,
- it is not fallback/error text (for example contains no `No se pudo obtener`).

Threshold:

- `non_empty_driving_analysis_rate >= 0.99`

### 3) Recommendation Coverage by Section

Definition:

For each case, coverage is computed only on `expected_focus_sections` from the fixture.

- `case_section_coverage = covered_expected_sections / total_expected_sections`

A section is covered when at least one recommendation item in output maps to that section.

Aggregate metric:

- `avg_section_coverage = mean(case_section_coverage across all cases)`

Threshold:

- `avg_section_coverage >= 0.70`

### 4) Latency (avg and p95)

Definition:

- Measure end-to-end wall-clock seconds for each `analyze()` call.
- Compute `latency_avg_seconds` and `latency_p95_seconds` over all cases.

Thresholds:

- `latency_avg_seconds <= 12.0`
- `latency_p95_seconds <= 20.0`

### 5) Qualitative Reasoning Rubric Score

Definition:

Per case, reviewers score 1-5 in four dimensions:

- telemetry_specificity,
- causal_quality,
- actionability,
- consistency_with_fixed_params.

Per-case rubric score:

- `case_rubric_score = mean(4 dimension scores)`

Aggregate metric:

- `rubric_score_avg = mean(case_rubric_score across all cases)`

Thresholds:

- `rubric_score_avg >= 3.8`
- no individual case below `3.0`

## Rubric Anchors

Use the following anchors to reduce reviewer variance:

- Score 5: cites concrete telemetry values and lap/distance references, gives a clear mechanism, actionable value changes, and fully respects fixed params.
- Score 4: mostly specific and actionable, minor gaps in mechanism depth.
- Score 3: generally useful but partially generic or weakly linked to telemetry.
- Score 2: vague recommendations with weak telemetry grounding or inconsistent constraints.
- Score 1: mostly generic, contradictory, or ignores constraints.

## Out of Scope (T1)

- No benchmark execution CLI or runner.
- No automatic report generation.
- No CI gate wiring.

Those are intentionally deferred to follow-up tasks.
