"""Run a 500-run Jimmy prompt grid search in parallel batches of 10.

This script evaluates Jimmy (llama3.1-8B) over benchmark fixtures and selects a
best runtime profile using a composite score focused on:
- JSON validity
- expected-section recommendation coverage
- non-empty driving analysis
- anti-refusal behavior
- anti-hallucination lap-reference behavior

Outputs are written to docs/benchmark/results/grid_search_500_<timestamp>/.
"""

from __future__ import annotations

import csv
import importlib.util
import itertools
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from scripts.benchmark_prompt_matrix import (
    _resolve_prompts,
    _run_case,
    compute_run_metrics,
)

DEFAULT_TOTAL_RUNS = 500
DEFAULT_BATCH_SIZE = 10
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_OUTPUT_ROOT = Path("docs/benchmark/results")
DEFAULT_FIXTURES_DIR = Path("tests/integration/fixtures/benchmark_cases")
SCHEMA_FILE_PATH = Path("tests/integration/benchmark_schema.py")

JIMMY_RUNTIME_CONFIG_PATH = Path("app/core/jimmy_runtime_config.v1.json")

REFUSAL_PATTERNS = [
    r"lo siento, pero no puedo",
    r"no puedo ayudarte con eso",
    r"no puedo ayudar con eso",
    r"necesito mas contexto",
]


@dataclass
class RunResult:
    run_config: Dict[str, Any]
    metrics: Dict[str, Any]
    case_summaries: List[Dict[str, Any]]
    score: float


def _load_schema_module(repo_root: Path):
    schema_path = repo_root / SCHEMA_FILE_PATH
    spec = importlib.util.spec_from_file_location("benchmark_schema", schema_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load schema module from {schema_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _extract_lap_numbers(text: str) -> List[int]:
    return [int(m.group(1)) for m in re.finditer(r"Vuelta\s+(\d+)", text or "", flags=re.IGNORECASE)]


def _has_refusal_text(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(pattern, lower) for pattern in REFUSAL_PATTERNS)


def _total_laps_from_case(case_data: Dict[str, Any]) -> int | None:
    stats = case_data.get("session_stats") or {}
    raw = stats.get("total_laps")
    try:
        if raw is None:
            return None
        return int(raw)
    except Exception:
        return None


def _lap_reference_violation(driving_analysis: str, case_data: Dict[str, Any]) -> bool:
    total_laps = _total_laps_from_case(case_data)
    if total_laps is None:
        return False
    laps = _extract_lap_numbers(driving_analysis)
    if not laps:
        return False
    # Strict: references beyond observed session laps are considered hallucinated.
    return max(laps) > total_laps


def _build_system_prompt(
    style: str,
    json_contract: str,
    anti_hallucination: str,
    specialist_focus: str,
    chief_focus: str,
) -> str:
    return " ".join([style, json_contract, anti_hallucination, specialist_focus, chief_focus]).strip()


def generate_grid_runs(total_runs: int) -> List[Dict[str, Any]]:
    styles = [
        "Eres Jimmy (llama3.1-8B) ingeniero de pista rFactor2. Tono tecnico, breve y accionable.",
        "Rol: Ingeniero de rendimiento rFactor2. Priorizas consistencia entre telemetria y recomendaciones.",
        "Eres analista de telemetria rFactor2. Evita narrativa innecesaria, manten precision numerica.",
        "Rol profesional: setup engineer rFactor2. Prioriza cambios concretos por seccion.",
        "Eres Jimmy para car setup. Responde con rigor de ingenieria y sin relleno.",
    ]

    json_contracts = [
        "Si se solicita estructura, responde SOLO JSON estricto, sin texto extra ni markdown.",
        "Salida estructurada: objeto JSON unico, doble comilla, sin comas finales.",
        "Cuando corresponda, produce JSON parseable y estable para pipeline automatizado.",
        "Formato estructurado obligatorio: JSON valido sin prefijos/sufijos narrativos.",
        "En respuestas de especialistas y chief, devuelve JSON limpio y minimo.",
    ]

    anti_hallucinations = [
        "No inventes vueltas, curvas ni distancias fuera de la telemetria dada.",
        "Si falta evidencia numerica, indica incertidumbre y evita suposiciones.",
        "Usa solo valores presentes en el contexto; no extrapoles datos inexistentes.",
        "No escribas recomendaciones genericas sin soporte en telemetria concreta.",
        "Si no hay base suficiente para un cambio, devuelve items vacio con justificacion tecnica.",
    ]

    specialist_focuses = [
        "Especialistas: entrega items con parameter, new_value y reason, enfocados en cambios reales.",
        "Especialistas: evita respuestas de rechazo; responde siempre dentro del contrato JSON.",
        "Especialistas: prioriza parametros con mayor impacto por seccion y explica causalidad.",
        "Especialistas: no propongas parametros fijos; redirige a alternativas no bloqueadas.",
    ]

    chief_focuses = [
        "Chief: integra propuestas validas de especialistas y conserva su razonamiento tecnico.",
        "Chief: se permisivo con especialistas salvo contradicciones claras o riesgos tecnicos.",
        "Chief: garantiza coherencia final y evita descartar cambios sin justificacion.",
        "Chief: devuelve full_setup.sections con items aplicables y trazables.",
    ]

    topk_values = [1, 2, 4, 8, 12]
    temperature_values = [0.0, 0.1, 0.2, 0.3, 0.4]

    all_combinations = itertools.product(
        styles,
        json_contracts,
        anti_hallucinations,
        specialist_focuses,
        chief_focuses,
        topk_values,
        temperature_values,
    )

    runs: List[Dict[str, Any]] = []
    for idx, (style, contract, anti_h, spc, chief, topk, temp) in enumerate(all_combinations, start=1):
        if idx > total_runs:
            break
        system_prompt = _build_system_prompt(style, contract, anti_h, spc, chief)
        runs.append(
            {
                "run_id": f"grid500_{idx:03d}",
                "prompt_variant": f"grid500_s{(idx % 5) + 1}_k{topk}_t{temp:.1f}",
                "systemPrompt": system_prompt,
                "topK": topk,
                "temperature": float(temp),
                "metadata": {
                    "search": "grid500",
                    "index": idx,
                },
                "prompt_overrides": {},
            }
        )
    return runs


def _evaluate_run(run_cfg: Dict[str, Any], cases: Sequence[Dict[str, Any]], timeout_seconds: int) -> RunResult:
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

    base_metrics = compute_run_metrics(case_results)

    refusal_count = 0
    lap_violations = 0
    case_summaries: List[Dict[str, Any]] = []

    for case_data, case_result in zip(cases, case_results):
        driving_text = str(case_result.get("driving_analysis", ""))
        has_refusal = _has_refusal_text(driving_text)
        has_lap_violation = _lap_reference_violation(driving_text, case_data)

        refusal_count += 1 if has_refusal else 0
        lap_violations += 1 if has_lap_violation else 0

        case_summaries.append(
            {
                "case_id": case_result.get("case_id"),
                "latency_ms": case_result.get("latency_ms"),
                "specialist_total": case_result.get("specialist_total"),
                "specialist_valid": case_result.get("specialist_valid"),
                "chief_valid": case_result.get("chief_valid"),
                "coverage_rate": case_result.get("coverage_rate"),
                "driving_analysis_non_empty": case_result.get("driving_analysis_non_empty"),
                "refusal_text": has_refusal,
                "lap_reference_violation": has_lap_violation,
            }
        )

    total_cases = max(1, len(cases))
    refusal_rate = refusal_count / total_cases
    lap_violation_rate = lap_violations / total_cases

    metrics = {
        **base_metrics,
        "refusal_rate": refusal_rate,
        "lap_reference_violation_rate": lap_violation_rate,
    }

    # Composite score tuned for setup recommendation reliability.
    score = (
        0.45 * float(metrics["json_validity_rate"])
        + 0.30 * float(metrics["recommendation_coverage_by_section"]["average"])
        + 0.15 * float(metrics["driving_analysis_non_empty_rate"])
        + 0.05 * (1.0 - refusal_rate)
        + 0.05 * (1.0 - lap_violation_rate)
    )

    return RunResult(
        run_config=run_cfg,
        metrics=metrics,
        case_summaries=case_summaries,
        score=score,
    )


def _output_folder(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / f"grid_search_500_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    return out


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_grid_search(
    total_runs: int = DEFAULT_TOTAL_RUNS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    fixtures_dir: Path = DEFAULT_FIXTURES_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Tuple[Path, Dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[1]
    schema_module = _load_schema_module(repo_root)
    case_paths = schema_module.discover_benchmark_cases(repo_root / fixtures_dir)
    cases = [schema_module.load_benchmark_case(case_path) for case_path in case_paths]
    if not cases:
        raise ValueError(f"No benchmark cases found in {fixtures_dir}")

    runs = generate_grid_runs(total_runs)
    out_dir = _output_folder(output_root)

    # Persist the generated matrix for reproducibility.
    matrix_payload = {"runs": runs}
    matrix_path = out_dir / "matrix.generated.json"
    matrix_path.write_text(json.dumps(matrix_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    all_results: List[RunResult] = []

    for start in range(0, len(runs), batch_size):
        batch = runs[start : start + batch_size]
        print(f"Running batch {start // batch_size + 1}: runs {start + 1}-{start + len(batch)}")

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = [executor.submit(_evaluate_run, run_cfg, cases, timeout_seconds) for run_cfg in batch]
            for future in as_completed(futures):
                all_results.append(future.result())

    # Rank by score desc; tie-break by lower latency avg.
    all_results.sort(key=lambda r: (-r.score, float(r.metrics["latency_ms"]["average"])))

    summary_rows: List[Dict[str, Any]] = []
    for rank, result in enumerate(all_results, start=1):
        summary_rows.append(
            {
                "rank": rank,
                "run_id": result.run_config["run_id"],
                "prompt_variant": result.run_config["prompt_variant"],
                "topK": result.run_config["topK"],
                "temperature": result.run_config["temperature"],
                "composite_score": f"{result.score:.4f}",
                "json_validity_rate": f"{result.metrics['json_validity_rate']:.4f}",
                "coverage_avg": f"{result.metrics['recommendation_coverage_by_section']['average']:.4f}",
                "driving_non_empty_rate": f"{result.metrics['driving_analysis_non_empty_rate']:.4f}",
                "refusal_rate": f"{result.metrics['refusal_rate']:.4f}",
                "lap_reference_violation_rate": f"{result.metrics['lap_reference_violation_rate']:.4f}",
                "latency_avg_ms": f"{result.metrics['latency_ms']['average']:.2f}",
                "latency_p95_ms": f"{result.metrics['latency_ms']['p95']:.2f}",
            }
        )

    _write_csv(out_dir / "summary.csv", summary_rows)
    _write_csv(out_dir / "ranking.csv", summary_rows)

    best = all_results[0]
    best_payload = {
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "run_id": best.run_config["run_id"],
        "prompt_variant": best.run_config["prompt_variant"],
        "systemPrompt": best.run_config["systemPrompt"],
        "topK": best.run_config["topK"],
        "temperature": best.run_config["temperature"],
        "score": best.score,
        "metrics": best.metrics,
    }
    (out_dir / "best_run.json").write_text(json.dumps(best_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_runs": total_runs,
        "batch_size": batch_size,
        "timeout_seconds": timeout_seconds,
        "fixtures_dir": str(fixtures_dir),
        "matrix_path": str(matrix_path),
        "best": best_payload,
        "runs": [
            {
                "run_config": result.run_config,
                "score": result.score,
                "metrics": result.metrics,
                "case_summaries": result.case_summaries,
            }
            for result in all_results
        ],
    }

    (out_dir / "results.json").write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Grid search complete. Output: {out_dir}")
    print(f"Best run: {best.run_config['run_id']} score={best.score:.4f}")

    return out_dir, best_payload


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def main() -> None:
    total_runs = _parse_int_env("JIMMY_GRID_TOTAL_RUNS", DEFAULT_TOTAL_RUNS)
    batch_size = _parse_int_env("JIMMY_GRID_BATCH_SIZE", DEFAULT_BATCH_SIZE)
    timeout_seconds = _parse_int_env("JIMMY_GRID_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)

    run_grid_search(
        total_runs=total_runs,
        batch_size=batch_size,
        timeout_seconds=timeout_seconds,
    )


if __name__ == "__main__":
    main()
