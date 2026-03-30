# AGENTS.md - app/config/

Configuración central del backend.

## Reglas
- Toda constante operacional nueva debe declararse aquí (`settings.py`).
- Evitar números mágicos dentro de `app/main.py` y `app/services/*`.
- Si se cambia un valor por defecto, documentarlo también en AGENTS raíz y README si impacta despliegue.

## Variables actuales
- `RF2_DATA_DIR`
- `RF2_UPLOAD_CHUNK_SIZE`
- `RF2_MAX_AI_TELEMETRY_CHARS`
- `RF2_MAX_TELEMETRY_COLUMNS`
- `RF2_AI_SAMPLES_PER_LAP`
- `RF2_MAP_MAX_POINTS`
- `RF2_CHUNK_STALE_HOURS`
- `RF2_ANALYSIS_TMP_STALE_HOURS`
