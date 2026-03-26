from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import shutil
import os
import uuid
import json
import numpy as np
from app.core.telemetry_parser import parse_ld_file, parse_svm_file

app = FastAPI(title="rFactor2 Engineer API")

# Modelo de datos para la respuesta
class AnalysisResponse(BaseModel):
    circuit_data: Dict[str, List[float]] # x, y para el trazado
    issues_on_map: List[Dict[str, Any]] # Puntos específicos con color
    driving_analysis: str
    setup_analysis: str
    full_setup: Dict[str, Any]
    session_stats: Dict[str, Any] # Nuevas estadísticas de la sesión

from app.core.ai_agents import AIAngineer

ai_engineer = AIAngineer()

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_telemetry(
    ld_file: UploadFile = File(...),
    svm_file: UploadFile = File(...)
):
    session_id = str(uuid.uuid4())
    upload_dir = f"data/{session_id}"
    os.makedirs(upload_dir, exist_ok=True)

    ld_path = os.path.join(upload_dir, ld_file.filename)
    svm_path = os.path.join(upload_dir, svm_file.filename)

    with open(ld_path, "wb") as buffer:
        shutil.copyfileobj(ld_file.file, buffer)
    with open(svm_path, "wb") as buffer:
        shutil.copyfileobj(svm_file.file, buffer)

    try:
        # 1. Parsear archivos
        try:
            telemetry_df = parse_ld_file(ld_path)
            setup_dict = parse_svm_file(svm_path)
            circuit_name = ld_file.filename.split('-')[-2].strip() if '-' in ld_file.filename else "Circuito Desconocido"
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        # 2. Preparar datos para el mapa
        lat_col = next((c for c in telemetry_df.columns if 'latitude' in c.lower()), None)
        lon_col = next((c for c in telemetry_df.columns if 'longitude' in c.lower()), None)

        if lat_col and lon_col:
            # Eliminar NaNs
            telemetry_df = telemetry_df.dropna(subset=[lat_col, lon_col])
            x = telemetry_df[lon_col].tolist()
            y = telemetry_df[lat_col].tolist()
            
            if len(x) > 3000:
                step = len(x) // 3000
                x = x[::step]
                y = y[::step]
        else:
            x = [0.0]
            y = [0.0]

        # 3. Análisis por Agentes de IA - RESUMEN DE LA SESIÓN COMPLETA
        relevant_cols = [c for c in telemetry_df.columns if any(word in c.lower() for word in ['speed', 'throttle', 'brake', 'rpm', 'steer', 'temp', 'g-force', 'pos', 'press', 'wear', 'lap', 'level'])]
        if not relevant_cols:
            relevant_cols = telemetry_df.columns[:30]
        
        clean_df = telemetry_df[relevant_cols].copy()
        
        # Escalar canales comunes si parecen estar multiplicados por 10 o 100
        for col in clean_df.columns:
            if 'speed' in col.lower():
                # En rF2, la velocidad suele venir en m/s o km/h * 10
                if clean_df[col].abs().max() > 1000:
                    clean_df[col] = clean_df[col] / 100.0 # Intentar escala 100
                elif clean_df[col].abs().max() > 500:
                    clean_df[col] = clean_df[col] / 10.0
            if 'throttle' in col.lower() or 'brake' in col.lower() or 'clutch' in col.lower():
                if clean_df[col].abs().max() > 1000:
                    clean_df[col] = (clean_df[col] / 32767.0) * 100.0
        
        # Extraer estadísticas reales de la sesión
        fuel_col = next((c for c in clean_df.columns if 'level' in c.lower()), None)
        wear_cols = [c for c in clean_df.columns if 'wear' in c.lower()]
        lap_col = next((c for c in clean_df.columns if 'laptime' in c.lower()), None)
        
        # Calcular estadísticas básicas
        # Intentar detectar vueltas mediante cambios bruscos en Distance o Laptime
        total_laps = 1
        if 'Distance' in telemetry_df.columns:
            dist = telemetry_df['Distance']
            # Una vuelta suele terminar cuando la distancia vuelve a cero o tiene un salto grande hacia abajo
            laps_detected = (dist.diff() < -100).sum()
            total_laps = max(1, int(laps_detected))
        elif 'Sector' in telemetry_df.columns:
             total_laps = int(telemetry_df['Sector'].nunique()) // 3 # Estimación bruta
             total_laps = max(1, total_laps)
        
        fuel_used_total = 0.0
        fuel_avg_lap = 0.0
        if fuel_col:
            fuel_series = clean_df[fuel_col].dropna()
            if not fuel_series.empty:
                # Si el valor es muy pequeño (m3) o negativo, tomamos el rango
                fuel_used_total = float(fuel_series.max() - fuel_series.min())
                # Si el consumo total es ridículo (p.ej < 0.1), probablemente no hay datos reales de fuel
                if fuel_used_total < 0.1: fuel_used_total = 0.0
                if total_laps > 0: fuel_avg_lap = fuel_used_total / total_laps

        avg_wear = 0.0
        total_wear = 0.0
        if wear_cols:
            wear_data = clean_df[wear_cols].dropna()
            if not wear_data.empty:
                # En rF2 el desgaste suele ser de 1.0 a 0.0 o similar. 
                # Si los valores son enormes, es que están en formato binario crudo
                wear_diffs = []
                for c in wear_cols:
                    col_data = wear_data[c]
                    if col_data.abs().max() > 100: # Probablemente crudo
                        diff = float(col_data.max() - col_data.min())
                        # Normalizar si es necesario, pero rF2 Wear es caprichoso
                        # Si la diferencia es enorme, la ignoramos para evitar porcentajes locos
                        if diff > 1000000: diff = 0.0
                        wear_diffs.append(diff)
                    else:
                        wear_diffs.append(float(col_data.max() - col_data.min()))
                
                total_wear = sum(wear_diffs) / len(wear_cols)
                # Capamos el desgaste al 100% para evitar errores visuales
                total_wear = min(100.0, max(0.0, total_wear))
                if total_laps > 0: avg_wear = total_wear / total_laps

        fastest_lap_time = "N/A"
        fastest_lap_num = 0
        if lap_col:
            lap_series = clean_df[lap_col].dropna()
            # Limpiar ruidos
            lap_series = lap_series[lap_series > 10] 
            if not lap_series.empty:
                fastest_lap_time = f"{float(lap_series.min()):.3f}s"
        
        session_stats = {
            "total_laps": total_laps,
            "fuel_total": round(max(0, fuel_used_total), 2),
            "fuel_avg": round(max(0, fuel_avg_lap), 2),
            "wear_total": round(max(0, total_wear), 2),
            "wear_avg": round(max(0, avg_wear), 2),
            "fastest_lap": fastest_lap_time,
            "fastest_lap_num": fastest_lap_num or "-"
        }

        # Preparar resumen para la IA (Patrones por sectores para la sesión completa)
        n = len(clean_df)
        n_sectors = 20
        sector_summaries = []
        for i in range(n_sectors):
            start_idx = (i*n)//n_sectors
            end_idx = ((i+1)*n)//n_sectors
            sector_df = clean_df.iloc[start_idx : end_idx]
            
            stats = {
                "Speed_Max": float(sector_df.filter(like='Speed').max().iloc[0]) if not sector_df.filter(like='Speed').empty else 0.0,
                "Speed_Min": float(sector_df.filter(like='Speed').min().iloc[0]) if not sector_df.filter(like='Speed').empty else 0.0,
                "Throttle_Avg": float(sector_df.filter(like='Throttle').mean().iloc[0]) if not sector_df.filter(like='Throttle').empty else 0.0,
                "Brake_Max": float(sector_df.filter(like='Brake').max().iloc[0]) if not sector_df.filter(like='Brake').empty else 0.0,
                "RPM_Avg": float(sector_df.filter(like='RPM').mean().iloc[0]) if not sector_df.filter(like='RPM').empty else 0.0,
                "Wear_Avg_Sector": float(sector_df.filter(like='Wear').mean().iloc[0]) if not sector_df.filter(like='Wear').empty else 0.0
            }
            sector_summaries.append(f"ZONA {i+1}: {json.dumps(stats)}")
        
        summary = f"CIRCUITO: {circuit_name}\n"
        summary += f"ESTADÍSTICAS SESIÓN: {json.dumps(session_stats)}\n"
        summary += "PATRONES DETECTADOS POR ZONAS (20 DIVISIONES):\n" + "\n".join(sector_summaries)
        
        # Llamada asíncrona al análisis multi-agente
        ai_result = await ai_engineer.analyze(summary, setup_dict, circuit_name=circuit_name, session_stats=session_stats)
        
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
            circuit_data={"x": [float(i) for i in x], "y": [float(i) for i in y]},
            issues_on_map=issues_on_map,
            driving_analysis=ai_result["driving_analysis"],
            setup_analysis=ai_result["setup_analysis"],
            full_setup=convert_to_native(ai_result["full_setup"]),
            session_stats=session_stats
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Opcional: limpiar archivos después del análisis
        # shutil.rmtree(upload_dir)
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
