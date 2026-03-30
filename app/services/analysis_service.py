"""Telemetry analysis orchestration service consumed by API routes."""

from __future__ import annotations

import io
import json
import math
import os
import shutil
import uuid
import datetime as dt
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, UploadFile

from app.config import settings
from app.services.upload_service import write_upload_to_disk


def convert_to_native(obj: Any) -> Any:
    if isinstance(obj, (np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: convert_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_to_native(i) for i in obj]
    return obj


class AnalysisService:
    """Executes telemetry+setup processing and delegates to AI engine."""

    @staticmethod
    def _cleanup_stale_analysis_tmp(data_dir: str) -> None:
        root = os.path.join(data_dir, "_analysis_tmp")
        if not os.path.isdir(root):
            return

        now = dt.datetime.now(dt.timezone.utc).timestamp()
        max_age_seconds = max(1, settings.ANALYSIS_TMP_STALE_HOURS) * 3600
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if not os.path.isdir(path):
                continue
            try:
                age = now - os.path.getmtime(path)
                if age >= max_age_seconds:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                continue

    @staticmethod
    def _first_col(df: pd.DataFrame, *keywords: str) -> Optional[str]:
        for kw in keywords:
            matches = [c for c in df.columns if kw.lower() in c.lower()]
            if matches:
                return matches[0]
        return None

    @staticmethod
    def _safe_stat(series: pd.Series, func: Callable[[pd.Series], Any]) -> float:
        try:
            v = func(series.dropna())
            if not np.isnan(v) and not np.isinf(v):
                return round(float(v), 2)
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _build_circuit_map(telemetry_df: pd.DataFrame) -> Dict[str, Any]:
        lat_col = next((c for c in telemetry_df.columns if "latitude" in c.lower()), None)
        lon_col = next((c for c in telemetry_df.columns if "longitude" in c.lower()), None)
        lap_col = next((c for c in telemetry_df.columns if "lap number" in c.lower()), None)

        if not lat_col or not lon_col:
            return {"x": [0.0], "y": [0.0], "aspect_ratio": 1.0}

        map_source_df = telemetry_df.dropna(subset=[lat_col, lon_col])
        if map_source_df.empty:
            return {"x": [0.0], "y": [0.0], "aspect_ratio": 1.0}

        map_df = map_source_df
        if lap_col:
            valid_laps = map_source_df[lap_col].dropna().unique()
            if len(valid_laps) > 1:
                laps_to_check = [l for l in valid_laps if l > 1] or list(valid_laps)
                best_lap = max(laps_to_check, key=lambda l: len(map_source_df[map_source_df[lap_col] == l]))
                map_df = map_source_df[map_source_df[lap_col] == best_lap].copy()

        avg_lat = map_df[lat_col].mean()
        aspect_ratio = 1.0 / math.cos(math.radians(avg_lat)) if not np.isnan(avg_lat) else 1.0

        x = map_df[lon_col].tolist()
        y = map_df[lat_col].tolist()

        if len(x) > settings.MAP_MAX_POINTS:
            step = max(1, len(x) // settings.MAP_MAX_POINTS)
            x = x[::step]
            y = y[::step]
            if x and y and (x[0] != x[-1] or y[0] != y[-1]):
                x.append(x[0])
                y.append(y[0])

        return {"x": [float(i) for i in x], "y": [float(i) for i in y], "aspect_ratio": aspect_ratio}

    @classmethod
    def _build_laps_and_stats(cls, telemetry_df: pd.DataFrame) -> tuple[list[dict], list[str], dict]:
        lap_col = "Lap Number"
        lap_numbers = [1] if lap_col not in telemetry_df.columns else sorted(telemetry_df[lap_col].dropna().unique())

        spd_col = cls._first_col(telemetry_df, "Ground Speed", "Speed")
        thr_col = cls._first_col(telemetry_df, "Throttle Pos", "Throttle")
        brk_col = cls._first_col(telemetry_df, "Brake Pos", "Brake")
        rpm_col = cls._first_col(telemetry_df, "Engine RPM", "RPM")
        fuel_col = cls._first_col(telemetry_df, "Fuel Level", "Fuel")

        wear_cols = [c for c in telemetry_df.columns if "wear" in c.lower()]
        temp_cols = [c for c in telemetry_df.columns if "tyre" in c.lower() and "temp" in c.lower()]

        laps_data: List[Dict[str, Any]] = []
        lap_summaries: List[str] = []
        fastest_lap_time_val = None
        fastest_lap_num = "-"

        for lap_num in lap_numbers:
            lap_df = telemetry_df if lap_col not in telemetry_df.columns else telemetry_df[telemetry_df[lap_col] == lap_num]
            if lap_df.empty:
                continue

            lap_time_val = None
            lap_time_str = "N/A"
            if "Last Laptime" in lap_df.columns:
                lt_s = lap_df["Last Laptime"].dropna()
                lt_valid = lt_s[(lt_s > 10) & (lt_s < 600)]
                if not lt_valid.empty:
                    lap_time_val = float(lt_valid.iloc[-1])
                    mins = int(lap_time_val // 60)
                    secs = lap_time_val % 60
                    lap_time_str = f"{mins}:{secs:06.3f}"

            if lap_time_val and (fastest_lap_time_val is None or lap_time_val < fastest_lap_time_val):
                fastest_lap_time_val = lap_time_val
                fastest_lap_num = str(int(lap_num))

            avg_wear = float(np.nanmean([lap_df[c].dropna().mean() for c in wear_cols])) if wear_cols else 0.0
            avg_temp = float(np.nanmean([lap_df[c].dropna().mean() for c in temp_cols])) if temp_cols else 0.0
            if np.isnan(avg_wear):
                avg_wear = 0.0
            if np.isnan(avg_temp):
                avg_temp = 0.0

            lap_info = {
                "lap": int(lap_num),
                "lap_time": lap_time_str,
                "lap_time_seconds": lap_time_val,
                "speed_max": cls._safe_stat(lap_df[spd_col], np.max) if spd_col in lap_df else 0.0,
                "speed_avg": cls._safe_stat(lap_df[spd_col], np.mean) if spd_col in lap_df else 0.0,
                "speed_min": cls._safe_stat(lap_df[spd_col], np.min) if spd_col in lap_df else 0.0,
                "throttle_avg": cls._safe_stat(lap_df[thr_col], np.mean) if thr_col in lap_df else 0.0,
                "brake_max": cls._safe_stat(lap_df[brk_col], np.max) if brk_col in lap_df else 0.0,
                "brake_avg": cls._safe_stat(lap_df[brk_col], np.mean) if brk_col in lap_df else 0.0,
                "rpm_avg": int(cls._safe_stat(lap_df[rpm_col], np.mean)) if rpm_col in lap_df else 0,
                "rpm_max": int(cls._safe_stat(lap_df[rpm_col], np.max)) if rpm_col in lap_df else 0,
                "fuel_start": cls._safe_stat(lap_df[fuel_col], lambda s: s.iloc[0] if len(s) > 0 else 0) if fuel_col in lap_df else 0.0,
                "fuel_end": cls._safe_stat(lap_df[fuel_col], lambda s: s.iloc[-1] if len(s) > 0 else 0) if fuel_col in lap_df else 0.0,
                "wear_avg": round(avg_wear, 2),
                "tyre_temp_avg": round(avg_temp, 1),
            }
            laps_data.append(lap_info)

            lap_summaries.append(
                f"VUELTA {int(lap_num)}: Tiempo={lap_time_str}, "
                f"Vel(max={lap_info['speed_max']}, avg={lap_info['speed_avg']}, min={lap_info['speed_min']}), "
                f"Throttle_avg={lap_info['throttle_avg']}%, Brake(max={lap_info['brake_max']}%, avg={lap_info['brake_avg']}%), "
                f"RPM(avg={lap_info['rpm_avg']}, max={lap_info['rpm_max']}), "
                f"Fuel({lap_info['fuel_start']}→{lap_info['fuel_end']}L), "
                f"Desgaste_avg={lap_info['wear_avg']}%, Temp_neumaticos={lap_info['tyre_temp_avg']}°C"
            )

        total_laps = len(laps_data)
        fastest_lap_time = "N/A"
        if fastest_lap_time_val:
            mins = int(fastest_lap_time_val // 60)
            secs = fastest_lap_time_val % 60
            fastest_lap_time = f"{mins}:{secs:06.3f}"

        fuel_used_total = 0.0
        fuel_avg_lap = 0.0
        if laps_data and laps_data[0]["fuel_start"] > 0:
            fuel_used_total = laps_data[0]["fuel_start"] - laps_data[-1]["fuel_end"]
            fuel_avg_lap = fuel_used_total / max(total_laps, 1)

        total_wear = 0.0
        if wear_cols:
            wear_diffs = []
            for wc in wear_cols:
                ws = telemetry_df[wc].dropna()
                if not ws.empty:
                    diff = float(ws.max() - ws.min())
                    if 0 < diff < 100:
                        wear_diffs.append(diff)
            if wear_diffs:
                total_wear = min(100.0, max(0.0, sum(wear_diffs) / len(wear_diffs)))

        session_stats = {
            "total_laps": total_laps,
            "fuel_total": round(max(0.0, fuel_used_total), 2),
            "fuel_avg": round(max(0.0, fuel_avg_lap), 2),
            "wear_total": round(max(0.0, total_wear), 2),
            "wear_avg": round(max(0.0, total_wear / max(total_laps, 1)), 2),
            "fastest_lap": fastest_lap_time,
            "fastest_lap_num": fastest_lap_num,
        }

        return laps_data, lap_summaries, session_stats

    @staticmethod
    def _build_ai_csv(telemetry_df: pd.DataFrame, lap_numbers: list, lap_col: str, driving_only: bool) -> tuple[str, int]:
        def is_relevant(c: str) -> bool:
            c_l = c.lower()
            if driving_only:
                return (
                    ("lap" in c_l and ("number" in c_l or "dist" in c_l))
                    or "throttle" in c_l
                    or ("brake" in c_l and "pos" in c_l)
                    or "steer" in c_l
                    or "rpm" in c_l
                    or c_l == "gear"
                    or (c_l.startswith("gear") and "setting" not in c_l)
                )
            return any(
                w in c_l
                for w in [
                    "speed",
                    "throttle",
                    "brake",
                    "rpm",
                    "steer",
                    "temp",
                    "g force",
                    "press",
                    "wear",
                    "lap",
                    "fuel",
                    "gear",
                    "tyre",
                    "tire",
                    "ride height",
                    "downforce",
                    "drag",
                    "camber",
                    "toe",
                    "susp pos",
                    "susp force",
                    "grip",
                    "load",
                    "pitch",
                    "roll",
                    "distance",
                ]
            )

        key_columns = [c for c in telemetry_df.columns if is_relevant(c)]
        if not driving_only:
            key_columns = key_columns[: settings.MAX_TELEMETRY_COLUMNS]

        parts = []
        for lap_num in lap_numbers:
            lap_df = telemetry_df if lap_col not in telemetry_df.columns else telemetry_df[telemetry_df[lap_col] == lap_num]
            if lap_df.empty or not key_columns:
                continue
            step = max(1, len(lap_df) // settings.AI_SAMPLES_PER_LAP)
            sampled = lap_df[key_columns].iloc[::step].copy()
            sampled.insert(0, "Vuelta", int(lap_num))
            parts.append(sampled)

        if not parts:
            return (
                "No hay datos de telemetría disponibles."
                if not driving_only
                else "No hay datos de telemetría de conducción disponibles.",
                len(key_columns),
            )

        merged = pd.concat(parts, ignore_index=True)
        csv_buffer = io.StringIO()
        merged.to_csv(csv_buffer, index=False, float_format="%.2f")
        csv_text = csv_buffer.getvalue()

        if len(csv_text) > settings.MAX_AI_TELEMETRY_CHARS:
            suffix = (
                "\n... [datos de conducción truncados]"
                if driving_only
                else "\n... [datos de telemetría truncados — se muestran los primeros registros]"
            )
            csv_text = csv_text[: settings.MAX_AI_TELEMETRY_CHARS] + suffix

        del merged
        return csv_text, len(key_columns)

    @classmethod
    async def analyze_uploads(
        cls,
        telemetry_file: UploadFile,
        svm_file: UploadFile,
        ai_engineer,
        parse_mat_fn: Callable[[str], pd.DataFrame],
        parse_csv_fn: Callable[[str], pd.DataFrame],
        parse_svm_fn: Callable[[str], Dict[str, Any]],
        model: Optional[str],
        provider: str,
        fixed_params_list: list,
        ollama_base_url: Optional[str],
        ollama_api_key: Optional[str],
        data_dir: str,
    ) -> Dict[str, Any]:
        cls._cleanup_stale_analysis_tmp(data_dir)
        session_id = str(uuid.uuid4())
        upload_dir = os.path.join(data_dir, "_analysis_tmp", session_id)
        os.makedirs(upload_dir, exist_ok=True)

        tele_path = os.path.join(upload_dir, telemetry_file.filename)
        svm_path = os.path.join(upload_dir, svm_file.filename)

        await write_upload_to_disk(telemetry_file, tele_path)
        await write_upload_to_disk(svm_file, svm_path)

        telemetry_df = None
        try:
            try:
                telemetry_df = parse_mat_fn(tele_path) if tele_path.lower().endswith(".mat") else parse_csv_fn(tele_path)
                setup_dict = parse_svm_fn(svm_path)
                circuit_name = (
                    telemetry_file.filename.split("-")[-2].strip()
                    if "-" in telemetry_file.filename
                    else "Circuito Desconocido"
                )
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))

            circuit_data = cls._build_circuit_map(telemetry_df)
            laps_data, lap_summaries, session_stats = cls._build_laps_and_stats(telemetry_df)

            lap_col = "Lap Number"
            lap_numbers = [1] if lap_col not in telemetry_df.columns else sorted(telemetry_df[lap_col].dropna().unique())

            telemetry_csv_for_ai, key_count = cls._build_ai_csv(telemetry_df, lap_numbers, lap_col, driving_only=False)
            driving_csv_for_ai, driving_key_count = cls._build_ai_csv(telemetry_df, lap_numbers, lap_col, driving_only=True)
            lap_summaries_text = "\n".join(lap_summaries)

            summary = (
                f"CIRCUITO: {circuit_name}\n"
                f"ESTADÍSTICAS SESIÓN: {json.dumps(session_stats)}\n"
                f"DATOS POR VUELTA (resumen): {lap_summaries_text}\n\n"
                f"DATOS DETALLADOS DE TELEMETRÍA (submuestreados, ~{settings.AI_SAMPLES_PER_LAP} puntos por vuelta, {key_count} canales):\n"
                f"{telemetry_csv_for_ai}"
            )

            driving_summary = (
                f"CIRCUITO: {circuit_name}\n"
                f"ESTADÍSTICAS SESIÓN: {json.dumps(session_stats)}\n"
                f"DATOS POR VUELTA (resumen): {lap_summaries_text}\n\n"
                f"TELEMETRÍA DE CONDUCCIÓN (throttle, freno, dirección, RPM, marcha — ~{settings.AI_SAMPLES_PER_LAP} puntos por vuelta, {driving_key_count} canales):\n"
                f"{driving_csv_for_ai}"
            )

            ai_result = await ai_engineer.analyze(
                summary,
                setup_dict,
                circuit_name=circuit_name,
                session_stats=session_stats,
                model_tag=model or None,
                provider=provider or "ollama",
                fixed_params=fixed_params_list,
                driving_telemetry_summary=driving_summary,
                ollama_base_url=ollama_base_url or None,
                ollama_api_key=ollama_api_key or None,
            )

            # Release big prompt payloads as soon as we get the AI response.
            del telemetry_csv_for_ai
            del driving_csv_for_ai
            del driving_summary

            x = circuit_data["x"]
            y = circuit_data["y"]
            issues_on_map = [
                {
                    "x": x[len(x) // 4],
                    "y": y[len(y) // 4],
                    "status": "driving_issue",
                    "color": "red",
                    "label": "Pérdida por conducción",
                },
                {
                    "x": x[len(x) // 2],
                    "y": y[len(y) // 2],
                    "status": "setup_issue",
                    "color": "yellow",
                    "label": "Pérdida por setup",
                },
                {
                    "x": x[3 * len(x) // 4],
                    "y": y[3 * len(y) // 4],
                    "status": "both",
                    "color": "orange",
                    "label": "Pérdida mixta",
                },
            ]

            return {
                "circuit_data": circuit_data,
                "issues_on_map": issues_on_map,
                "driving_analysis": ai_result["driving_analysis"],
                "setup_analysis": ai_result["setup_analysis"],
                "full_setup": convert_to_native(ai_result["full_setup"]),
                "session_stats": session_stats,
                "laps_data": convert_to_native(laps_data),
                "agent_reports": convert_to_native(ai_result.get("agent_reports", [])),
                "setup_agent_reports": convert_to_native(ai_result.get("setup_agent_reports", [])),
                "telemetry_summary_sent": summary,
                "chief_reasoning": ai_result.get("chief_reasoning", ""),
                "llm_provider": ai_result.get("llm_provider", provider or "ollama"),
                "llm_model": ai_result.get("llm_model", model or ""),
            }
        finally:
            await telemetry_file.close()
            await svm_file.close()
            shutil.rmtree(upload_dir, ignore_errors=True)
            if telemetry_df is not None:
                del telemetry_df
