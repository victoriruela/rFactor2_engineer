"""Local benchmark harness for Jimmy prompt matrix experiments.

This script runs the benchmark fixtures from tests/integration/fixtures/benchmark_cases
against Jimmy's llama3.1-8B endpoint using configurable prompt matrix runs.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from langchain_core.prompts import PromptTemplate

from app.core.ai_agents import CHIEF_ENGINEER_PROMPT, DRIVING_PROMPT, SECTION_AGENT_PROMPT

JIMMY_API_URL = os.getenv("JIMMY_API_URL", "https://chatjimmy.ai/api/chat")
JIMMY_MODEL_TAG = "llama3.1-8B"
JIMMY_STATS_RE = re.compile(r"<\|stats\|>.*?<\|/stats\|>", re.DOTALL)
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_FIXTURES_DIR = Path("tests/integration/fixtures/benchmark_cases")
DEFAULT_OUTPUT_ROOT = Path("docs/benchmark/results")
DEFAULT_MATRIX_PATH = Path("docs/benchmark/prompt_matrix.json")
SCHEMA_FILE_PATH = Path("tests/integration/benchmark_schema.py")


def _load_schema_module(repo_root: Path):
    schema_path = repo_root / SCHEMA_FILE_PATH
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    spec = importlib.util.spec_from_file_location("benchmark_schema", schema_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load schema module from {schema_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_prompt_matrix(matrix_path: Path) -> List[Dict[str, Any]]:
    with matrix_path.open("r", encoding="utf-8") as matrix_file:
        payload = json.load(matrix_file)

    runs = payload.get("runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list) or not runs:
        raise ValueError("Prompt matrix file must be a JSON object with non-empty 'runs' list")

    normalized_runs: List[Dict[str, Any]] = []
    for idx, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ValueError(f"Run at index {idx} must be an object")

        run_id = str(run.get("run_id") or f"run_{idx + 1}")
        prompt_variant = str(run.get("prompt_variant") or "default")
        system_prompt = str(run.get("systemPrompt") or "")
        top_k = run.get("topK", 8)
        temperature = run.get("temperature", 0.3)
        metadata = run.get("metadata") or {}
        prompt_overrides = run.get("prompt_overrides") or {}

        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError(f"Run '{run_id}' has invalid topK: {top_k}")
        if not isinstance(temperature, (int, float)):
            raise ValueError(f"Run '{run_id}' has invalid temperature: {temperature}")
        if not isinstance(metadata, dict):
            raise ValueError(f"Run '{run_id}' has invalid metadata (must be object)")
        if not isinstance(prompt_overrides, dict):
            raise ValueError(f"Run '{run_id}' has invalid prompt_overrides (must be object)")

        normalized_runs.append(
            {
                "run_id": run_id,
                "prompt_variant": prompt_variant,
                "systemPrompt": system_prompt,
                "topK": top_k,
                "temperature": float(temperature),
                "metadata": metadata,
                "prompt_overrides": prompt_overrides,
            }
        )

    return normalized_runs


def _build_prompt_text(prompt_template: str, inputs: Dict[str, Any]) -> str:
    return PromptTemplate.from_template(prompt_template).format(**inputs)


def strip_jimmy_artifacts(raw_text: str) -> str:
    cleaned = JIMMY_STATS_RE.sub("", raw_text or "").strip()
    if len(cleaned) >= 2 and cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def extract_first_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None

    start = raw_text.find("{")
    if start == -1:
        return None

    depth = 0
    for idx, char in enumerate(raw_text[start:], start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = raw_text[start : idx + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    cleaned = re.sub(r",\s*}\s*$", "}", candidate)
                    cleaned = re.sub(r",\s*]\s*$", "]", cleaned)
                    try:
                        return json.loads(cleaned)
                    except json.JSONDecodeError:
                        return None
    return None


def _jimmy_chat(user_prompt: str, run_cfg: Dict[str, Any], timeout_seconds: int) -> str:
    payload = {
        "messages": [{"role": "user", "content": user_prompt}],
        "chatOptions": {
            "selectedModel": JIMMY_MODEL_TAG,
            "systemPrompt": run_cfg["systemPrompt"],
            "topK": run_cfg["topK"],
            "temperature": run_cfg["temperature"],
        },
        "attachment": None,
    }

    response = requests.post(
        JIMMY_API_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Referer": "https://chatjimmy.ai/",
            "Origin": "https://chatjimmy.ai",
        },
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return strip_jimmy_artifacts(response.text)


def _clean_setup_value(raw_value: Any) -> str:
    raw_text = str(raw_value)
    if "//" in raw_text:
        return raw_text.split("//", 1)[1].strip()
    return raw_text.strip()


def _build_current_setup_summary(setup_data: Dict[str, Dict[str, str]]) -> str:
    lines: List[str] = []
    for section_name, section_data in setup_data.items():
        if section_name.upper() in {"BASIC", "LEFTFENDER", "RIGHTFENDER"}:
            continue

        filtered = {
            key: _clean_setup_value(value)
            for key, value in section_data.items()
            if not (key.startswith("Gear") and "Setting" in key)
        }
        if not filtered:
            continue

        lines.append(f"\n[{section_name}]")
        for key, value in filtered.items():
            lines.append(f"  {key} = {value}")

    return "\n".join(lines)


def _is_specialist_json_valid(payload: Optional[Dict[str, Any]]) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("items"), list)


def _is_chief_json_valid(payload: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(payload, dict):
        return False
    full_setup = payload.get("full_setup")
    if not isinstance(full_setup, dict):
        return False
    return isinstance(full_setup.get("sections"), list)


def is_non_empty_driving_analysis(driving_analysis: str) -> bool:
    if not driving_analysis:
        return False
    if "No se pudo obtener" in driving_analysis:
        return False
    return len(driving_analysis.strip()) >= 80


def _normalize_section(section_name: str) -> str:
    return str(section_name or "").strip().upper()


def _recommended_sections(
    specialist_reports: Sequence[Dict[str, Any]], chief_json: Optional[Dict[str, Any]]
) -> Dict[str, int]:
    coverage: Dict[str, int] = {}

    if _is_chief_json_valid(chief_json):
        chief_sections = chief_json["full_setup"].get("sections", [])
        for section in chief_sections:
            section_name = _normalize_section(section.get("name", ""))
            items = section.get("items", [])
            if section_name and isinstance(items, list) and items:
                coverage[section_name] = len(items)
        return coverage

    for specialist in specialist_reports:
        section_name = _normalize_section(specialist.get("name", ""))
        items = specialist.get("items")
        if section_name and isinstance(items, list) and items:
            coverage[section_name] = len(items)

    return coverage


def _compute_coverage_rate(expected_sections: Sequence[str], covered_sections: Dict[str, int]) -> float:
    normalized_expected = [_normalize_section(section) for section in expected_sections if section]
    if not normalized_expected:
        return 1.0

    covered = sum(1 for section in normalized_expected if section in covered_sections)
    return covered / len(normalized_expected)


def _percentile_ms(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * percentile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(sorted_values[low])

    fraction = rank - low
    return float(sorted_values[low] + (sorted_values[high] - sorted_values[low]) * fraction)


def compute_run_metrics(case_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total_cases = len(case_results)
    specialist_total = 0
    specialist_valid = 0
    chief_total = total_cases
    chief_valid = 0
    driving_non_empty = 0
    latency_values: List[float] = []
    coverage_by_case: Dict[str, float] = {}

    for case_result in case_results:
        specialist_total += int(case_result.get("specialist_total", 0))
        specialist_valid += int(case_result.get("specialist_valid", 0))
        chief_valid += 1 if case_result.get("chief_valid") else 0
        driving_non_empty += 1 if case_result.get("driving_analysis_non_empty") else 0
        latency_values.append(float(case_result.get("latency_ms", 0.0)))

        case_id = str(case_result.get("case_id", "unknown"))
        coverage_by_case[case_id] = float(case_result.get("coverage_rate", 0.0))

    json_total = specialist_total + chief_total
    json_valid = specialist_valid + chief_valid

    if total_cases:
        coverage_avg = statistics.mean(coverage_by_case.values())
        driving_rate = driving_non_empty / total_cases
    else:
        coverage_avg = 0.0
        driving_rate = 0.0

    return {
        "json_validity_rate": (json_valid / json_total) if json_total else 0.0,
        "json_validity_breakdown": {
            "specialists": {
                "valid": specialist_valid,
                "total": specialist_total,
                "rate": (specialist_valid / specialist_total) if specialist_total else 0.0,
            },
            "chief": {
                "valid": chief_valid,
                "total": chief_total,
                "rate": (chief_valid / chief_total) if chief_total else 0.0,
            },
        },
        "driving_analysis_non_empty_rate": driving_rate,
        "recommendation_coverage_by_section": {
            "by_case": coverage_by_case,
            "average": coverage_avg,
        },
        "latency_ms": {
            "average": statistics.mean(latency_values) if latency_values else 0.0,
            "p95": _percentile_ms(latency_values, 0.95),
        },
        "qualitative_rubric": {
            "status": "pending_manual_scoring",
            "scale": "1-5",
            "dimensions": [
                "telemetry_specificity",
                "causal_quality",
                "actionability",
                "consistency_with_fixed_params",
            ],
            "per_case": {
                str(case_result.get("case_id", "unknown")): {
                    "telemetry_specificity": None,
                    "causal_quality": None,
                    "actionability": None,
                    "consistency_with_fixed_params": None,
                    "notes": "",
                }
                for case_result in case_results
            },
        },
    }


def _resolve_prompts(run_cfg: Dict[str, Any]) -> Dict[str, str]:
    variant_name = run_cfg["prompt_variant"]
    prompts = {
        "driving_prompt": DRIVING_PROMPT,
        "section_prompt": SECTION_AGENT_PROMPT,
        "chief_prompt": CHIEF_ENGINEER_PROMPT,
    }

    overrides = run_cfg.get("prompt_overrides") or {}
    for key in ("driving_prompt", "section_prompt", "chief_prompt"):
        if key in overrides:
            prompts[key] = str(overrides[key])

    prompts["variant_name"] = variant_name
    return prompts


def _run_case(
    case_data: Dict[str, Any],
    run_cfg: Dict[str, Any],
    prompts: Dict[str, str],
    timeout_seconds: int,
) -> Dict[str, Any]:
    start = time.perf_counter()

    telemetry_summary = str(case_data.get("telemetry_summary", ""))
    setup_data = case_data.get("setup_data", {})
    circuit_name = str(case_data.get("circuit_name", ""))
    session_stats = case_data.get("session_stats", {})
    fixed_params = case_data.get("fixed_params", [])

    if fixed_params:
        fixed_prompt = ", ".join(str(param) for param in fixed_params)
    else:
        fixed_prompt = "Ninguno."

    driving_prompt = _build_prompt_text(
        prompts["driving_prompt"],
        {
            "telemetry_summary": telemetry_summary,
            "session_stats": json.dumps(session_stats, ensure_ascii=False, indent=2),
        },
    )
    driving_analysis = _jimmy_chat(driving_prompt, run_cfg, timeout_seconds)

    specialist_results: List[Dict[str, Any]] = []
    for section_name, section_data in setup_data.items():
        if str(section_name).upper() in {"BASIC", "LEFTFENDER", "RIGHTFENDER"}:
            continue

        filtered_section = {
            key: value
            for key, value in section_data.items()
            if not (str(key).startswith("Gear") and "Setting" in str(key))
        }
        if not filtered_section:
            continue

        cleaned_section = {
            str(key): _clean_setup_value(value)
            for key, value in filtered_section.items()
        }

        specialist_prompt = _build_prompt_text(
            prompts["section_prompt"],
            {
                "section_name": str(section_name),
                "telemetry_summary": telemetry_summary,
                "section_data": json.dumps(cleaned_section, ensure_ascii=False, indent=2),
                "context_data": "N/A",
                "circuit_name": circuit_name,
                "fixed_params_prompt": fixed_prompt,
            },
        )
        specialist_raw = _jimmy_chat(specialist_prompt, run_cfg, timeout_seconds)
        specialist_json = extract_first_json_object(specialist_raw)

        specialist_results.append(
            {
                "name": section_name,
                "raw": specialist_raw,
                "parsed": specialist_json,
                "json_valid": _is_specialist_json_valid(specialist_json),
                "items": specialist_json.get("items", []) if isinstance(specialist_json, dict) else [],
            }
        )

    chief_prompt = _build_prompt_text(
        prompts["chief_prompt"],
        {
            "specialist_reports": json.dumps(
                [{"name": entry["name"], "items": entry.get("items", [])} for entry in specialist_results],
                ensure_ascii=False,
                indent=2,
            ),
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name,
            "current_setup": _build_current_setup_summary(setup_data),
            "memory_context": "N/A",
            "fixed_params_prompt": fixed_prompt,
        },
    )
    chief_raw = _jimmy_chat(chief_prompt, run_cfg, timeout_seconds)
    chief_json = extract_first_json_object(chief_raw)

    latency_ms = (time.perf_counter() - start) * 1000.0
    recommended_sections = _recommended_sections(specialist_results, chief_json)
    coverage_rate = _compute_coverage_rate(case_data.get("expected_focus_sections", []), recommended_sections)

    return {
        "case_id": case_data.get("case_id", "unknown"),
        "description": case_data.get("description", ""),
        "latency_ms": latency_ms,
        "driving_analysis": driving_analysis,
        "driving_analysis_non_empty": is_non_empty_driving_analysis(driving_analysis),
        "specialist_total": len(specialist_results),
        "specialist_valid": sum(1 for entry in specialist_results if entry["json_valid"]),
        "chief_valid": _is_chief_json_valid(chief_json),
        "expected_focus_sections": case_data.get("expected_focus_sections", []),
        "recommended_sections": recommended_sections,
        "coverage_rate": coverage_rate,
        "specialist_outputs": specialist_results,
        "chief_output": {
            "raw": chief_raw,
            "parsed": chief_json,
        },
    }


def _write_summary_csv(csv_path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    fieldnames = [
        "run_id",
        "prompt_variant",
        "topK",
        "temperature",
        "json_validity_rate",
        "driving_analysis_non_empty_rate",
        "recommendation_coverage_avg",
        "latency_avg_ms",
        "latency_p95_ms",
        "metadata",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _benchmark_output_folder(root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = root / f"jimmy_prompt_matrix_{timestamp}"
    output_path.mkdir(parents=True, exist_ok=False)
    return output_path


def run_benchmark(
    matrix_path: Path,
    fixtures_dir: Path,
    output_root: Path,
    timeout_seconds: int,
) -> Tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    schema_module = _load_schema_module(repo_root)

    matrix_runs = _load_prompt_matrix(matrix_path)
    case_paths = schema_module.discover_benchmark_cases(repo_root / fixtures_dir)
    cases = [schema_module.load_benchmark_case(case_path) for case_path in case_paths]

    if not cases:
        raise ValueError(f"No benchmark cases found in {fixtures_dir}")

    output_folder = _benchmark_output_folder(output_root)
    summary_rows: List[Dict[str, Any]] = []
    run_outputs: List[Dict[str, Any]] = []

    for run_cfg in matrix_runs:
        prompts = _resolve_prompts(run_cfg)
        case_results = [
            _run_case(
                case_data=case_data,
                run_cfg=run_cfg,
                prompts=prompts,
                timeout_seconds=timeout_seconds,
            )
            for case_data in cases
        ]
        metrics = compute_run_metrics(case_results)

        run_output = {
            "run_config": run_cfg,
            "prompt_variant": prompts["variant_name"],
            "case_count": len(case_results),
            "metrics": metrics,
            "cases": case_results,
        }
        run_outputs.append(run_output)

        summary_rows.append(
            {
                "run_id": run_cfg["run_id"],
                "prompt_variant": run_cfg["prompt_variant"],
                "topK": run_cfg["topK"],
                "temperature": run_cfg["temperature"],
                "json_validity_rate": f"{metrics['json_validity_rate']:.4f}",
                "driving_analysis_non_empty_rate": f"{metrics['driving_analysis_non_empty_rate']:.4f}",
                "recommendation_coverage_avg": f"{metrics['recommendation_coverage_by_section']['average']:.4f}",
                "latency_avg_ms": f"{metrics['latency_ms']['average']:.2f}",
                "latency_p95_ms": f"{metrics['latency_ms']['p95']:.2f}",
                "metadata": json.dumps(run_cfg.get("metadata", {}), ensure_ascii=False),
            }
        )

    result_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jimmy_api_url": JIMMY_API_URL,
        "model": JIMMY_MODEL_TAG,
        "matrix_path": str(matrix_path),
        "fixtures_dir": str(fixtures_dir),
        "run_count": len(run_outputs),
        "runs": run_outputs,
    }

    json_output = output_folder / "results.json"
    csv_output = output_folder / "summary.csv"

    with json_output.open("w", encoding="utf-8") as json_file:
        json.dump(result_payload, json_file, ensure_ascii=False, indent=2)

    _write_summary_csv(csv_output, summary_rows)
    return json_output, csv_output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Jimmy prompt matrix benchmark")
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX_PATH,
        help="Path to prompt matrix JSON file",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help="Directory containing benchmark case fixtures",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root folder where benchmark result folders are created",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout for each Jimmy request",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    json_path, csv_path = run_benchmark(
        matrix_path=args.matrix,
        fixtures_dir=args.fixtures_dir,
        output_root=args.output_root,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"Benchmark complete. JSON: {json_path}")
    print(f"Benchmark complete. CSV: {csv_path}")


if __name__ == "__main__":
    main()
