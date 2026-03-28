from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import shutil
import os
import uuid
import json
import io
import numpy as np
import pandas as pd
from app.core.telemetry_parser import parse_csv_file, parse_mat_file, parse_svm_file

app = FastAPI(title="rFactor2 Engineer API")

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
    telemetry_summary_sent: str = "" # Resumen enviado a la IA
    chief_reasoning: str = "" # Razonamiento del ingeniero jefe

class ReanalyzeRequest(BaseModel):
    section_key: str
    telemetry_summary: str
    setup_data: Dict[str, Any]
    previous_full_setup: Dict[str, Any]
    circuit_name: str = "Desconocido"
    model: Optional[str] = None

class ReanalyzeResponse(BaseModel):
    updated_sections: List[Dict[str, Any]]
    chief_reasoning: str
    sections_reanalyzed: List[str]

from app.core.ai_agents import AIAngineer, list_available_models

ai_engineer = AIAngineer()

DATA_DIR = "data"

@app.get("/sessions")
def list_sessions():
    if not os.path.exists(DATA_DIR):
        return {"sessions": []}
    
    sessions = []
    for sid in os.listdir(DATA_DIR):
        path = os.path.join(DATA_DIR, sid)
        if os.path.isdir(path):
            files = os.listdir(path)
            # Buscar archivos relevantes
            tele_file = next((f for f in files if f.lower().endswith(('.mat', '.csv'))), None)
            svm_file = next((f for f in files if f.lower().endswith('.svm')), None)
            if tele_file and svm_file:
                sessions.append({
                    "id": sid,
                    "telemetry": tele_file,
                    "svm": svm_file,
                    "display_name": tele_file.rsplit('.', 1)[0]
                })
    return {"sessions": sessions}

@app.get("/sessions/{session_id}/file/{filename}")
def get_session_file(session_id: str, filename: str):
    file_path = os.path.join(DATA_DIR, session_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(file_path)

@app.get("/models")
def get_models():
    models = list_available_models()
    return {"models": models}

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_telemetry(
    telemetry_file: UploadFile = File(...),
    svm_file: UploadFile = File(...),
    model: Optional[str] = Form(None)
):
    session_id = str(uuid.uuid4())
    upload_dir = f"data/{session_id}"
    os.makedirs(upload_dir, exist_ok=True)

    tele_path = os.path.join(upload_dir, telemetry_file.filename)
    svm_path = os.path.join(upload_dir, svm_file.filename)

    with open(tele_path, "wb") as buffer:
        shutil.copyfileobj(telemetry_file.file, buffer)
    with open(svm_path, "wb") as buffer:
        shutil.copyfileobj(svm_file.file, buffer)

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
                # Aseguramos que los extremos (min/max de x e y) estén incluidos
                # Buscamos los índices de los valores extremos
                idx_min_x = x.index(min(x))
                idx_max_x = x.index(max(x))
                idx_min_y = y.index(min(y))
                idx_max_y = y.index(max(y))
                
                extreme_indices = {idx_min_x, idx_max_x, idx_min_y, idx_max_y}
                
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
        gear_col = _first_col(telemetry_df, 'Gear')
        dist_col = _first_col(telemetry_df, 'Lap Distance', 'Distance')
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
        
        summary = f"CIRCUITO: {circuit_name}\n"
        summary += f"ESTADÍSTICAS SESIÓN: {json.dumps(session_stats)}\n"
        summary += f"DATOS POR VUELTA (resumen): " + "\n".join(lap_summaries) + "\n\n"
        summary += f"DATOS DETALLADOS DE TELEMETRÍA (submuestreados, ~50 puntos por vuelta, {len(key_columns)} canales):\n"
        summary += telemetry_csv_for_ai
        
        # Llamada asíncrona al análisis multi-agente
        ai_result = await ai_engineer.analyze(summary, setup_dict, circuit_name=circuit_name, session_stats=session_stats, model_tag=model or None)
        
        # 4. Generar puntos de interés en el mapa
        issues_on_map = [
            {"x": x[len(x)//4], "y": y[len(y)//4], "status": "driving_issue", "color": "red", "label": "Pérdida por conducción"},
            {"x": x[len(x)//2], "y": y[len(y)//2], "status": "setup_issue", "color": "yellow", "label": "Pérdida por setup"},
            {"x": x[3*len(x)//4], "y": y[3*len(y)//4], "status": "both", "color": "orange", "label": "Pérdida mixta"}
        ]

        # Asegurar tipos nativos de Python para JSON
        def convert_to_native(obj):
            if isinstance(obj, (np.int64, np.int32)): return int(obj)
            if isinstance(obj, (np.float64, np.float32)): return float(obj)
            if isinstance(obj, dict): return {k: convert_to_native(v) for k, v in obj.items()}
            if isinstance(obj, list): return [convert_to_native(i) for i in obj]
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
            telemetry_summary_sent=summary,
            chief_reasoning=ai_result.get("chief_reasoning", "")
        )
    except Exception as e:
        error_msg = str(e)
        if "connection attempts failed" in error_msg.lower() or "connection error" in error_msg.lower():
            detail = "Error de conexión con el modelo local (Ollama). Asegúrate de que Ollama esté instalado, ejecutándose y con el modelo 'llama3' descargado."
        else:
            detail = error_msg
        raise HTTPException(status_code=500, detail=detail)
    finally:
        # Opcional: limpiar archivos después del análisis
        # shutil.rmtree(upload_dir)
        pass

@app.post("/reanalyze_section", response_model=ReanalyzeResponse)
async def reanalyze_section(req: ReanalyzeRequest):
    try:
        result = await ai_engineer.reanalyze_section(
            section_key=req.section_key,
            telemetry_summary=req.telemetry_summary,
            setup_data=req.setup_data,
            previous_full_setup=req.previous_full_setup,
            circuit_name=req.circuit_name,
            model_tag=req.model or None
        )
        if not result:
            raise HTTPException(status_code=500, detail="El ingeniero jefe no pudo completar el re-análisis.")
        return ReanalyzeResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
