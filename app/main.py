from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, Header, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import shutil
import os
import uuid
import json
import io
import re
import numpy as np
import pandas as pd
from app.core.telemetry_parser import parse_csv_file, parse_mat_file, parse_svm_file
from app.core.track_storage import router as track_storage_router
from app.core.track_parser import parse_aiw as parse_aiw_text

app = FastAPI(title="rFactor2 Engineer API")
app.include_router(track_storage_router)

ALLOWED_BROWSER_ORIGINS = [
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "https://car-setup.com",
    "https://telemetria.bot.nu",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_BROWSER_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo de datos para la respuesta
class AnalysisResponse(BaseModel):
    circuit_data: Dict[str, Any] # x, y para el trazado, aspect_ratio
    issues_on_map: List[Dict[str, Any]] # Puntos específicos con color
    driving_analysis: str
    setup_analysis: str
    full_setup: Dict[str, Any]
    session_stats: Dict[str, Any] # Nuevas estadísticas de la sesión
    laps_data: List[Dict[str, Any]] # Datos por vuelta: número, tiempo, stats
    agent_reports: List[Dict[str, Any]] = [] # Informes individuales de agentes
    setup_agent_reports: List[Dict[str, Any]] = [] # Informes consolidados alineados con setup final
    telemetry_summary_sent: str = "" # Resumen enviado a la IA
    chief_reasoning: str = "" # Razonamiento del ingeniero jefe
    llm_provider: str = "" # Provider real usado por el backend
    llm_model: str = "" # Modelo real usado por el backend

from app.core.ai_agents import AIAngineer, list_available_models
from app.core.track_parser import router as track_parser_router
app.include_router(track_parser_router)

ai_engineer = AIAngineer()

DATA_DIR = "data"
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024
SESSION_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

# Max size (chars) for the telemetry CSV sent to AI agents.
# Jimmy (llama3.1-8B) effective context is ~8-16K tokens; a full-session CSV can
# reach 120KB+ and overwhelms the model, causing non-JSON responses.
MAX_AI_TELEMETRY_CHARS = 15_000


class UploadInitRequest(BaseModel):
    filename: str


async def _write_upload_to_disk(upload_file: UploadFile, destination_path: str, chunk_size: int = UPLOAD_CHUNK_SIZE):
    with open(destination_path, "wb") as output_file:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            output_file.write(chunk)


def _normalize_session_id(raw_session_id: Optional[str]) -> str:
    if not raw_session_id:
        raise HTTPException(status_code=400, detail="Missing session identifier")

    normalized = raw_session_id.strip()
    if not SESSION_ID_REGEX.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="Invalid session identifier")

    return normalized


def _resolve_client_session_id(
    x_client_session_id: Optional[str] = Header(None),
    rf2_session_id: Optional[str] = Cookie(None)
) -> str:
    return _normalize_session_id(x_client_session_id or rf2_session_id)


def _client_root(client_session_id: str) -> str:
    return os.path.join(DATA_DIR, client_session_id)


def _chunk_root(client_session_id: str) -> str:
    return os.path.join(_client_root(client_session_id), "_chunks")


def _chunk_meta_path(client_session_id: str, upload_id: str) -> str:
    return os.path.join(_chunk_root(client_session_id), f"{upload_id}.json")


def _chunk_part_path(client_session_id: str, upload_id: str) -> str:
    return os.path.join(_chunk_root(client_session_id), f"{upload_id}.part")


def _safe_filename(filename: str) -> str:
    safe = os.path.basename((filename or "").strip())
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe


def _list_client_sessions(client_session_id: str) -> List[Dict[str, str]]:
    root = _client_root(client_session_id)
    if not os.path.exists(root):
        return []

    grouped: Dict[str, Dict[str, str]] = {}
    for name in os.listdir(root):
        full_path = os.path.join(root, name)
        if not os.path.isfile(full_path):
            continue

        lower = name.lower()
        if not lower.endswith((".mat", ".csv", ".svm")):
            continue

        base = name.rsplit('.', 1)[0]
        grouped.setdefault(base, {})
        if lower.endswith(".svm"):
            grouped[base]["svm"] = name
        else:
            grouped[base]["telemetry"] = name

    sessions: List[Dict[str, str]] = []
    for base, files in grouped.items():
        if "telemetry" in files and "svm" in files:
            sessions.append({
                "id": base,
                "display_name": base,
                "telemetry": files["telemetry"],
                "svm": files["svm"],
            })

    return sorted(sessions, key=lambda x: x["display_name"], reverse=True)


def _find_session_pair(client_session_id: str, session_id: str) -> Dict[str, str]:
    target = session_id.strip()
    for item in _list_client_sessions(client_session_id):
        if item["id"] == target:
            return item
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/uploads/init")
def init_upload(
    payload: UploadInitRequest,
    client_session_id: str = Depends(_resolve_client_session_id)
):
    upload_id = str(uuid.uuid4())
    chunk_dir = _chunk_root(client_session_id)
    os.makedirs(chunk_dir, exist_ok=True)

    safe_name = _safe_filename(payload.filename)
    meta = {
        "filename": safe_name,
        "next_chunk": 0,
        "bytes_received": 0,
    }

    part_path = _chunk_part_path(client_session_id, upload_id)
    with open(part_path, "wb") as _:
        pass
    with open(_chunk_meta_path(client_session_id, upload_id), "w", encoding="utf-8") as handle:
        json.dump(meta, handle)

    return {
        "upload_id": upload_id,
        "chunk_size": UPLOAD_CHUNK_SIZE,
        "filename": safe_name,
    }


@app.put("/uploads/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    request: Request,
    chunk_index: int,
    client_session_id: str = Depends(_resolve_client_session_id)
):
    meta_path = _chunk_meta_path(client_session_id, upload_id)
    part_path = _chunk_part_path(client_session_id, upload_id)
    if not os.path.exists(meta_path) or not os.path.exists(part_path):
        raise HTTPException(status_code=404, detail="Upload not initialized")

    with open(meta_path, "r", encoding="utf-8") as handle:
        meta = json.load(handle)

    expected_index = int(meta.get("next_chunk", 0))
    if chunk_index != expected_index:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid chunk index. Expected {expected_index}, received {chunk_index}",
        )

    body = await request.body()
    if body is None:
        raise HTTPException(status_code=400, detail="Missing chunk body")

    with open(part_path, "ab") as part_file:
        part_file.write(body)

    meta["next_chunk"] = expected_index + 1
    meta["bytes_received"] = int(meta.get("bytes_received", 0)) + len(body)
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle)

    return {
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "bytes_received": meta["bytes_received"],
    }


@app.post("/uploads/{upload_id}/complete")
def complete_upload(
    upload_id: str,
    client_session_id: str = Depends(_resolve_client_session_id)
):
    meta_path = _chunk_meta_path(client_session_id, upload_id)
    part_path = _chunk_part_path(client_session_id, upload_id)
    if not os.path.exists(meta_path) or not os.path.exists(part_path):
        raise HTTPException(status_code=404, detail="Upload not initialized")

    with open(meta_path, "r", encoding="utf-8") as handle:
        meta = json.load(handle)

    client_root = _client_root(client_session_id)
    os.makedirs(client_root, exist_ok=True)
    final_name = _safe_filename(meta.get("filename", ""))
    final_path = os.path.join(client_root, final_name)

    if os.path.exists(final_path):
        os.remove(final_path)
    shutil.move(part_path, final_path)
    os.remove(meta_path)

    return {
        "filename": final_name,
        "bytes_received": int(meta.get("bytes_received", 0)),
    }

@app.get("/sessions")
def list_sessions(client_session_id: str = Depends(_resolve_client_session_id)):
    return {"sessions": _list_client_sessions(client_session_id)}

@app.get("/sessions/{session_id}/file/{filename}")
def get_session_file(
    session_id: str,
    filename: str,
    client_session_id: str = Depends(_resolve_client_session_id)
):
    pair = _find_session_pair(client_session_id, session_id)
    expected_files = {pair["telemetry"], pair["svm"]}
    if filename not in expected_files:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = os.path.join(_client_root(client_session_id), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    from fastapi.responses import FileResponse
    return FileResponse(file_path)

@app.get("/models")
def get_models(
    ollama_base_url: Optional[str] = None,
    ollama_api_key: Optional[str] = None,
):
    models = list_available_models(base_url=ollama_base_url, api_key=ollama_api_key)
    return {"models": models}

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_telemetry(
    telemetry_file: UploadFile = File(...),
    svm_file: UploadFile = File(...),
    model: Optional[str] = Form(None),
    provider: Optional[str] = Form("ollama"),
    fixed_params: Optional[str] = Form(None),
    ollama_base_url: Optional[str] = Form(None),
    ollama_api_key: Optional[str] = Form(None),
):
    session_id = str(uuid.uuid4())
    upload_dir = os.path.join(DATA_DIR, "_analysis_tmp", session_id)
    os.makedirs(upload_dir, exist_ok=True)

    # Parsear lista de parámetros fijados si existe
    fixed_params_list = []
    if fixed_params:
        try:
            fixed_params_list = json.loads(fixed_params)
        except Exception:
            pass

    tele_path = os.path.join(upload_dir, telemetry_file.filename)
    svm_path = os.path.join(upload_dir, svm_file.filename)

    await _write_upload_to_disk(telemetry_file, tele_path)
    await _write_upload_to_disk(svm_file, svm_path)

    try:
        # 1. Parsear archivos
        try:
            if tele_path.lower().endswith('.mat'):
                telemetry_df = parse_mat_file(tele_path)
            else:
                telemetry_df = parse_csv_file(tele_path)

            setup_dict = parse_svm_file(svm_path)
            circuit_name = telemetry_file.filename.split('-')[-2].strip() if '-' in telemetry_file.filename else "Circuito Desconocido"
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        # 2. Preparar datos para el mapa
        lat_col = next((c for c in telemetry_df.columns if 'latitude' in c.lower()), None)
        lon_col = next((c for c in telemetry_df.columns if 'longitude' in c.lower()), None)
        lap_col = next((c for c in telemetry_df.columns if 'lap number' in c.lower()), None)

        if lat_col and lon_col:
            # Eliminar NaNs
            telemetry_df = telemetry_df.dropna(subset=[lat_col, lon_col])

            # Intentar usar una única vuelta representativa para el trazado del mapa
            # Preferiblemente una vuelta completa (no la primera ni la última si están incompletas)
            if lap_col:
                valid_laps = telemetry_df[lap_col].unique()
                if len(valid_laps) > 1:
                    # Usamos la segunda vuelta completa como referencia (o la mejor si tuviéramos tiempos aquí)
                    # Para simplificar, usamos la que tiene más muestras y no sea la 0 o 1 si hay más
                    laps_to_check = [l for l in valid_laps if l > 1]
                    if not laps_to_check:
                        laps_to_check = list(valid_laps)

                    best_lap = max(laps_to_check, key=lambda l: len(telemetry_df[telemetry_df[lap_col] == l]))
                    map_df = telemetry_df[telemetry_df[lap_col] == best_lap].copy()
                else:
                    map_df = telemetry_df.copy()
            else:
                map_df = telemetry_df.copy()

            # Cálculo de aspect ratio para corregir distorsión GPS (Lon/Lat)
            avg_lat = map_df[lat_col].mean()
            # 1 grado de latitud son ~111.1km. 1 grado de longitud son 111.1km * cos(lat)
            import math
            # La distorsión es: para una misma distancia en metros, la diferencia en grados Lon es mayor que en Lat
            # Escala X (Lon) debe multiplicarse por cos(lat) para ser comparable con Lat en metros
            # O equivalentemente, en el gráfico (donde 1 unidad X = 1 unidad Y visualmente):
            # aspect_ratio = dy / dx = 1 / cos(lat) para que se vea real
            aspect_ratio = 1.0 / math.cos(math.radians(avg_lat))

            x = map_df[lon_col].tolist()
            y = map_df[lat_col].tolist()

            # Submuestreo inteligente para no perder detalle pero ser eficiente
            if len(x) > 5000:
                step = len(x) // 5000
                new_x, new_y = [], []
                for i in range(0, len(x), step):
                    new_x.append(x[i])
                    new_y.append(y[i])
                    # Si el siguiente paso se salta un extremo, lo añadimos (opcionalmente)
                    # Pero es más sencillo añadir los extremos al final y ordenar si fuera necesario,
                    # aunque el trazado debe seguir el orden temporal.

                # Para mantener el orden temporal del trazado, simplemente nos aseguramos de que los puntos
                # en los índices extremos estén en la lista final si no lo están por el step.
                # Pero en 5000 puntos es casi seguro que están cerca.
                # Una mejor forma es asegurar que el trazado sea CERRADO
                if x[0] != x[-1] or y[0] != y[-1]:
                    new_x.append(x[0])
                    new_y.append(y[0])

                x, y = new_x, new_y
        else:
            x = [0.0]
            y = [0.0]
            aspect_ratio = 1.0

        # 3. Dividir telemetría por vueltas y generar resumen por vuelta
        cols = telemetry_df.columns.tolist()
        relevant_cols = [c for c in cols if any(w in c.lower() for w in [
            'speed', 'throttle', 'brake', 'rpm', 'steer', 'temp', 'g force',
            'press', 'wear', 'lap', 'fuel', 'gear', 'tyre', 'tire', 'ride height',
            'downforce', 'drag', 'camber', 'toe', 'susp pos', 'susp force', 'grip',
            'load', 'pitch', 'roll', 'distance'
        ])]
        if not relevant_cols:
            relevant_cols = cols[:50]

        def _first_col(df, *keywords):
            for kw in keywords:
                matches = [c for c in df.columns if kw.lower() in c.lower()]
                if matches:
                    return matches[0]
            return None

        spd_col  = _first_col(telemetry_df, 'Ground Speed', 'Speed')
        thr_col  = _first_col(telemetry_df, 'Throttle Pos', 'Throttle')
        brk_col  = _first_col(telemetry_df, 'Brake Pos', 'Brake')
        rpm_col  = _first_col(telemetry_df, 'Engine RPM', 'RPM')
        fuel_col = _first_col(telemetry_df, 'Fuel Level', 'Fuel')
        _first_col(telemetry_df, 'Gear')
        _first_col(telemetry_df, 'Lap Distance', 'Distance')
        wear_cols = [c for c in telemetry_df.columns if 'wear' in c.lower()]
        temp_cols = [c for c in telemetry_df.columns if 'tyre' in c.lower() and 'temp' in c.lower()]

        # Dividir por vueltas
        lap_col = 'Lap Number'
        if lap_col not in telemetry_df.columns:
            lap_numbers = [1]
        else:
            lap_numbers = sorted(telemetry_df[lap_col].dropna().unique())

        laps_data = []
        lap_summaries = []
        fastest_lap_time_val = None
        fastest_lap_num = "-"

        for lap_num in lap_numbers:
            if lap_col in telemetry_df.columns:
                lap_df = telemetry_df[telemetry_df[lap_col] == lap_num]
            else:
                lap_df = telemetry_df

            if lap_df.empty:
                continue

            def _safe_stat(col_name, func):
                try:
                    if col_name and col_name in lap_df.columns:
                        v = func(lap_df[col_name].dropna())
                        if not np.isnan(v) and not np.isinf(v):
                            return round(float(v), 2)
                except Exception:
                    pass
                return 0.0

            # Tiempo de vuelta desde Last Laptime
            lap_time_val = None
            lap_time_str = "N/A"
            for lt_c in ['Last Laptime']:
                if lt_c in lap_df.columns:
                    lt_s = lap_df[lt_c].dropna()
                    lt_valid = lt_s[(lt_s > 10) & (lt_s < 600)]
                    if not lt_valid.empty:
                        lap_time_val = float(lt_valid.iloc[-1])
                        mins = int(lap_time_val // 60)
                        secs = lap_time_val % 60
                        lap_time_str = f"{mins}:{secs:06.3f}"
                        break

            if lap_time_val and (fastest_lap_time_val is None or lap_time_val < fastest_lap_time_val):
                fastest_lap_time_val = lap_time_val
                fastest_lap_num = str(int(lap_num))

            # Estadísticas por vuelta
            avg_wear_vals = []
            for wc in wear_cols:
                ws = lap_df[wc].dropna()
                if not ws.empty:
                    avg_wear_vals.append(round(float(ws.mean()), 2))
            avg_wear = round(sum(avg_wear_vals) / len(avg_wear_vals), 2) if avg_wear_vals else 0.0

            avg_temp_vals = []
            for tc in temp_cols:
                ts = lap_df[tc].dropna()
                if not ts.empty:
                    avg_temp_vals.append(round(float(ts.mean()), 1))
            avg_temp = round(sum(avg_temp_vals) / len(avg_temp_vals), 1) if avg_temp_vals else 0.0

            lap_info = {
                "lap": int(lap_num),
                "lap_time": lap_time_str,
                "lap_time_seconds": lap_time_val,
                "speed_max": _safe_stat(spd_col, np.max),
                "speed_avg": _safe_stat(spd_col, np.mean),
                "speed_min": _safe_stat(spd_col, np.min),
                "throttle_avg": _safe_stat(thr_col, np.mean),
                "brake_max": _safe_stat(brk_col, np.max),
                "brake_avg": _safe_stat(brk_col, np.mean),
                "rpm_avg": int(_safe_stat(rpm_col, np.mean)),
                "rpm_max": int(_safe_stat(rpm_col, np.max)),
                "fuel_start": _safe_stat(fuel_col, lambda s: s.iloc[0] if len(s) > 0 else 0),
                "fuel_end": _safe_stat(fuel_col, lambda s: s.iloc[-1] if len(s) > 0 else 0),
                "wear_avg": avg_wear,
                "tyre_temp_avg": avg_temp,
            }
            laps_data.append(lap_info)

            # Resumen textual para la IA
            lap_summary = (f"VUELTA {int(lap_num)}: Tiempo={lap_time_str}, "
                          f"Vel(max={lap_info['speed_max']}, avg={lap_info['speed_avg']}, min={lap_info['speed_min']}), "
                          f"Throttle_avg={lap_info['throttle_avg']}%, Brake(max={lap_info['brake_max']}%, avg={lap_info['brake_avg']}%), "
                          f"RPM(avg={lap_info['rpm_avg']}, max={lap_info['rpm_max']}), "
                          f"Fuel({lap_info['fuel_start']}→{lap_info['fuel_end']}L), "
                          f"Desgaste_avg={lap_info['wear_avg']}%, Temp_neumaticos={lap_info['tyre_temp_avg']}°C")
            lap_summaries.append(lap_summary)

        # Estadísticas globales de sesión
        total_laps = len(laps_data)
        fastest_lap_time = "N/A"
        if fastest_lap_time_val:
            mins = int(fastest_lap_time_val // 60)
            secs = fastest_lap_time_val % 60
            fastest_lap_time = f"{mins}:{secs:06.3f}"

        fuel_used_total = 0.0
        fuel_avg_lap = 0.0
        if laps_data and laps_data[0]['fuel_start'] > 0:
            fuel_used_total = laps_data[0]['fuel_start'] - laps_data[-1]['fuel_end']
            if total_laps > 0:
                fuel_avg_lap = fuel_used_total / total_laps

        total_wear = 0.0
        avg_wear_session = 0.0
        if wear_cols:
            wear_diffs = []
            for wc in wear_cols:
                ws = telemetry_df[wc].dropna()
                if not ws.empty:
                    diff = float(ws.max() - ws.min())
                    if 0 < diff < 100:
                        wear_diffs.append(diff)
            if wear_diffs:
                total_wear = sum(wear_diffs) / len(wear_diffs)
                total_wear = min(100.0, max(0.0, total_wear))
                if total_laps > 0:
                    avg_wear_session = total_wear / total_laps

        session_stats = {
            "total_laps": total_laps,
            "fuel_total": round(max(0.0, fuel_used_total), 2),
            "fuel_avg": round(max(0.0, fuel_avg_lap), 2),
            "wear_total": round(max(0.0, total_wear), 2),
            "wear_avg": round(max(0.0, avg_wear_session), 2),
            "fastest_lap": fastest_lap_time,
            "fastest_lap_num": fastest_lap_num
        }

        # Generar datos detallados por vuelta para la IA (submuestreados)
        # Seleccionar columnas relevantes para el análisis
        # Columnas prioritarias ordenadas por importancia para el análisis
        priority_cols = [
            'Lap Number', 'Lap Distance', 'Ground Speed', 'Throttle Pos', 'Brake Pos',
            'Steering', 'Engine RPM', 'Gear', 'G Force Lat', 'G Force Long',
            'Fuel Level', 'Tyre Wear FL', 'Tyre Wear FR', 'Tyre Wear RL', 'Tyre Wear RR',
            'Tyre Pressure FL', 'Tyre Pressure FR', 'Tyre Pressure RL', 'Tyre Pressure RR',
            'Tyre Temp FL Inner', 'Tyre Temp FL Centre', 'Tyre Temp FL Outer',
            'Tyre Temp FR Inner', 'Tyre Temp FR Centre', 'Tyre Temp FR Outer',
            'Tyre Temp RL Inner', 'Tyre Temp RL Centre', 'Tyre Temp RL Outer',
            'Tyre Temp RR Inner', 'Tyre Temp RR Centre', 'Tyre Temp RR Outer',
            'Ride Height FL', 'Ride Height FR', 'Ride Height RL', 'Ride Height RR',
            'Susp Pos FL', 'Susp Pos FR', 'Susp Pos RL', 'Susp Pos RR',
            'Grip Fract FL', 'Grip Fract FR', 'Grip Fract RL', 'Grip Fract RR',
            'Tyre Load FL', 'Tyre Load FR', 'Tyre Load RL', 'Tyre Load RR',
            'Front Downforce', 'Rear Downforce', 'Drag',
            'Brake Temp FL', 'Brake Temp FR', 'Brake Temp RL', 'Brake Temp RR',
            'Body Pitch', 'Body Roll', 'Camber FL', 'Camber FR', 'Camber RL', 'Camber RR',
            'Min Corner Speed', 'Max Straight Speed', 'Delta Best',
        ]
        # Añadir cualquier otra columna que sea relevante pero no esté en la lista de prioridad
        all_relevant = [c for c in telemetry_df.columns if any(w in c.lower() for w in [
            'speed', 'throttle', 'brake', 'rpm', 'steer', 'temp', 'g force',
            'press', 'wear', 'lap', 'fuel', 'gear', 'tyre', 'tire', 'ride height',
            'downforce', 'drag', 'camber', 'toe', 'susp pos', 'susp force', 'grip',
            'load', 'pitch', 'roll', 'distance'
        ])]

        # Combinar manteniendo el orden de prioridad y eliminando duplicados
        key_columns = []
        for c in priority_cols:
            if c in telemetry_df.columns:
                key_columns.append(c)
        for c in all_relevant:
            if c not in key_columns:
                key_columns.append(c)

        # Limitar a 100 columnas máximo para mantener tamaño razonable del contexto
        if len(key_columns) > 100:
            key_columns = key_columns[:100]

        telemetry_for_ai_parts = []
        for lap_num in lap_numbers:
            if lap_col in telemetry_df.columns:
                lap_df_ai = telemetry_df[telemetry_df[lap_col] == lap_num]
            else:
                lap_df_ai = telemetry_df
            if lap_df_ai.empty:
                continue
            # Submuestrear a ~50 puntos por vuelta
            step_ai = max(1, len(lap_df_ai) // 50)
            sampled = lap_df_ai[key_columns].iloc[::step_ai].copy()
            sampled.insert(0, 'Vuelta', int(lap_num))
            telemetry_for_ai_parts.append(sampled)

        if telemetry_for_ai_parts:
            telemetry_for_ai_df = pd.concat(telemetry_for_ai_parts, ignore_index=True)
            csv_buffer = io.StringIO()
            telemetry_for_ai_df.to_csv(csv_buffer, index=False, float_format='%.2f')
            telemetry_csv_for_ai = csv_buffer.getvalue()
        else:
            telemetry_csv_for_ai = "No hay datos de telemetría disponibles."

        # Truncate to avoid exceeding the LLM context window (especially Jimmy llama3.1-8B).
        if len(telemetry_csv_for_ai) > MAX_AI_TELEMETRY_CHARS:
            telemetry_csv_for_ai = telemetry_csv_for_ai[:MAX_AI_TELEMETRY_CHARS] + "\n... [datos de telemetría truncados — se muestran los primeros registros]"

        summary = f"CIRCUITO: {circuit_name}\n"
        summary += f"ESTADÍSTICAS SESIÓN: {json.dumps(session_stats)}\n"
        summary += "DATOS POR VUELTA (resumen): " + "\n".join(lap_summaries) + "\n\n"
        summary += f"DATOS DETALLADOS DE TELEMETRÍA (submuestreados, ~50 puntos por vuelta, {len(key_columns)} canales):\n"
        summary += telemetry_csv_for_ai

        # Resumen de telemetría exclusivo para el agente de conducción:
        # solo throttle, freno, dirección, RPM y marcha (técnica de pilotaje)
        def _is_driving_col(col_name):
            c = col_name.lower()
            return (
                ('lap' in c and ('number' in c or 'dist' in c)) or
                'throttle' in c or
                ('brake' in c and 'pos' in c) or
                'steer' in c or
                'rpm' in c or
                c == 'gear' or
                (c.startswith('gear') and 'setting' not in c)
            )

        driving_cols = [c for c in telemetry_df.columns if _is_driving_col(c)]
        driving_for_ai_parts = []
        for lap_num in lap_numbers:
            if lap_col in telemetry_df.columns:
                lap_df_drv = telemetry_df[telemetry_df[lap_col] == lap_num]
            else:
                lap_df_drv = telemetry_df
            if lap_df_drv.empty or not driving_cols:
                continue
            step_drv = max(1, len(lap_df_drv) // 50)
            sampled_drv = lap_df_drv[driving_cols].iloc[::step_drv].copy()
            sampled_drv.insert(0, 'Vuelta', int(lap_num))
            driving_for_ai_parts.append(sampled_drv)

        if driving_for_ai_parts:
            driving_for_ai_df = pd.concat(driving_for_ai_parts, ignore_index=True)
            drv_buf = io.StringIO()
            driving_for_ai_df.to_csv(drv_buf, index=False, float_format='%.2f')
            driving_csv = drv_buf.getvalue()
        else:
            driving_csv = "No hay datos de telemetría de conducción disponibles."

        if len(driving_csv) > MAX_AI_TELEMETRY_CHARS:
            driving_csv = driving_csv[:MAX_AI_TELEMETRY_CHARS] + "\n... [datos de conducción truncados]"

        driving_summary = f"CIRCUITO: {circuit_name}\n"
        driving_summary += f"ESTADÍSTICAS SESIÓN: {json.dumps(session_stats)}\n"
        driving_summary += "DATOS POR VUELTA (resumen): " + "\n".join(lap_summaries) + "\n\n"
        driving_summary += (
            f"TELEMETRÍA DE CONDUCCIÓN (throttle, freno, dirección, RPM, marcha "
            f"— ~50 puntos por vuelta, {len(driving_cols)} canales):\n"
        )
        driving_summary += driving_csv

        # Llamada asíncrona al análisis multi-agente
        ai_result = await ai_engineer.analyze(
            summary, setup_dict,
            circuit_name=circuit_name,
            session_stats=session_stats,
            model_tag=model or None,
            provider=provider or "ollama",
            fixed_params=fixed_params_list,
            driving_telemetry_summary=driving_summary,
            ollama_base_url=ollama_base_url or None,
            ollama_api_key=ollama_api_key or None,
        )

        # 4. Generar puntos de interés en el mapa
        issues_on_map = [
            {"x": x[len(x)//4], "y": y[len(y)//4], "status": "driving_issue", "color": "red", "label": "Pérdida por conducción"},
            {"x": x[len(x)//2], "y": y[len(y)//2], "status": "setup_issue", "color": "yellow", "label": "Pérdida por setup"},
            {"x": x[3*len(x)//4], "y": y[3*len(y)//4], "status": "both", "color": "orange", "label": "Pérdida mixta"}
        ]

        # Asegurar tipos nativos de Python para JSON
        def convert_to_native(obj):
            if isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, (np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, dict):
                return {k: convert_to_native(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert_to_native(i) for i in obj]
            return obj

        return AnalysisResponse(
            circuit_data={
                "x": [float(i) for i in x],
                "y": [float(i) for i in y],
                "aspect_ratio": aspect_ratio
            },
            issues_on_map=issues_on_map,
            driving_analysis=ai_result["driving_analysis"],
            setup_analysis=ai_result["setup_analysis"],
            full_setup=convert_to_native(ai_result["full_setup"]),
            session_stats=session_stats,
            laps_data=convert_to_native(laps_data),
            agent_reports=convert_to_native(ai_result.get("agent_reports", [])),
            setup_agent_reports=convert_to_native(ai_result.get("setup_agent_reports", [])),
            telemetry_summary_sent=summary,
            chief_reasoning=ai_result.get("chief_reasoning", ""),
            llm_provider=ai_result.get("llm_provider", provider or "ollama"),
            llm_model=ai_result.get("llm_model", model or "")
        )
    except HTTPException:
        # Preserve explicit HTTP status codes raised inside the pipeline.
        raise
    except Exception as e:
        error_msg = str(e)
        if "connection attempts failed" in error_msg.lower() or "connection error" in error_msg.lower():
            if (provider or "ollama").lower() == "jimmy":
                detail = "Error de conexión con Jimmy API. Verifica tu conexión a Internet e inténtalo de nuevo."
            else:
                detail = "Error de conexión con el modelo local (Ollama). Asegúrate de que Ollama esté instalado, ejecutándose y con el modelo 'llama3' descargado."
        else:
            detail = error_msg
        raise HTTPException(status_code=500, detail=detail)
    finally:
        await telemetry_file.close()
        await svm_file.close()
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.post("/analyze_session", response_model=AnalysisResponse)
async def analyze_stored_session(
    session_id: str = Form(...),
    model: Optional[str] = Form(None),
    provider: Optional[str] = Form("ollama"),
    fixed_params: Optional[str] = Form(None),
    ollama_base_url: Optional[str] = Form(None),
    ollama_api_key: Optional[str] = Form(None),
    client_session_id: str = Depends(_resolve_client_session_id),
):
    pair = _find_session_pair(client_session_id, session_id)
    client_root = _client_root(client_session_id)
    tele_path = os.path.join(client_root, pair["telemetry"])
    svm_path = os.path.join(client_root, pair["svm"])

    if not os.path.exists(tele_path) or not os.path.exists(svm_path):
        raise HTTPException(status_code=404, detail="Session files are missing")

    telemetry_handle = open(tele_path, "rb")
    svm_handle = open(svm_path, "rb")
    telemetry_upload = UploadFile(filename=pair["telemetry"], file=telemetry_handle)
    svm_upload = UploadFile(filename=pair["svm"], file=svm_handle)
    analysis_succeeded = False

    try:
        result = await analyze_telemetry(
            telemetry_file=telemetry_upload,
            svm_file=svm_upload,
            model=model,
            provider=provider,
            fixed_params=fixed_params,
            ollama_base_url=ollama_base_url,
            ollama_api_key=ollama_api_key,
        )
        analysis_succeeded = True
        return result
    finally:
        if analysis_succeeded:
            for path in (tele_path, svm_path):
                if os.path.exists(path):
                    os.remove(path)

@app.post("/cleanup")
async def cleanup_data(client_session_id: str = Depends(_resolve_client_session_id)):
    """Borra archivos de telemetría/setup del cliente actual y chunks temporales."""
    client_root = _client_root(client_session_id)
    if not os.path.exists(client_root):
        return {"status": "ok", "message": "No data directory"}

    deleted_count = 0
    for root, dirs, files in os.walk(client_root):
        for file in files:
            if file.lower().endswith((".mat", ".csv", ".svm", ".part", ".json")):
                try:
                    os.remove(os.path.join(root, file))
                    deleted_count += 1
                except Exception as e:
                    print(f"Error borrando {file}: {e}")

    # Opcionalmente borrar carpetas vacías
    for root, dirs, files in os.walk(client_root, topdown=False):
        for name in dirs:
            dir_path = os.path.join(root, name)
            if not os.listdir(dir_path):
                os.rmdir(dir_path)

    if os.path.isdir(client_root) and not os.listdir(client_root):
        os.rmdir(client_root)

    return {"status": "ok", "deleted_files": deleted_count}

class AIWTextRequest(BaseModel):
    aiw_text: str


@app.post("/tracks/parse-aiw-text")
async def parse_aiw_text_endpoint(payload: AIWTextRequest):
    """Parse raw AIW text (as JSON body) and return track centreline data."""
    result = parse_aiw_text(payload.aiw_text)
    if not result.get("points"):
        raise HTTPException(status_code=422, detail="No waypoints found in AIW data")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
