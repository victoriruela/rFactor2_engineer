# Benchmark Cases for Jimmy Prompt Tuning

This directory contains fixed benchmark inputs for Jimmy prompt evaluation.

## Scope

- Inputs only (no runner logic).
- Cases are deterministic fixtures for integration benchmark harness work in later tasks.
- Every case follows the schema defined in `tests/integration/benchmark_schema.py`.

## Case Design Rules

- Use realistic but compact telemetry summaries.
- Include enough setup sections so section-specialist coverage can be measured.
- Keep expected targets explicit through `expected_focus_sections`.
- Keep text in Spanish to match production prompts.

## Files

- `case_template.json`: canonical structure for new benchmark cases.
- `case_01_suzuka_baseline.json`: stable baseline behavior.
- `case_02_suzuka_mid_understeer.json`: understeer-heavy scenario.
- `case_03_suzuka_exit_oversteer.json`: traction-limited exits.
