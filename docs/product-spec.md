# Especificación de Producto — rFactor2 Engineer

Referencia completa del producto. Consultada por agentes que implementan funcionalidad de
parsing de telemetría, pipeline LLM, o UI de análisis.

---

## Objetivo Funcional

El usuario sube archivos de telemetría (MoTeC `.mat` o `.csv`) y setup del vehículo (`.svm`)
de rFactor 2. El sistema analiza la telemetría curva a curva y genera:

- **Análisis de conducción**: 5 puntos de mejora por curva con valores numéricos reales.
- **Recomendaciones de setup**: cambios propuestos por ~14 agentes especialistas (uno por sección),
  consolidados por un Ingeniero Jefe que enforce simetría axial y coherencia global.
- **Circuit map interactivo**: mapa GPS del circuito con puntos coloreados por tipo de issue
  (rojo=pilotaje, amarillo=setup, naranja=ambos).

Todo el output está en **español castellano**.

---

## Arquitectura del Sistema

```
Browser (Expo Web embebida en binario Go)
       │  HTTP REST
       ▼
  Backend Go (:8080)   [Gin, zerolog, SQLite, go:embed]
       │
       ├── /api/uploads/*        ← Upload chunked de telemetría
       ├── /api/sessions         ← CRUD de sesiones
       ├── /api/analyze          ← Pipeline LLM completo
       ├── /api/models           ← Lista modelos Ollama disponibles
       ├── /api/tracks/*         ← Biblioteca de tracks
       ├── /api/health           ← Health check
       └── /                     ← Serve Expo web (go:embed dist/)
       │
       ▼
  Ollama (:11434)
       ├── llama3.2:latest (3B, default)
       └── (o chatjimmy.ai API para llama3.1-8B)
```

### Artefacto de Deploy

**Binario Go único** para Linux (amd64). Contiene:
- API REST completa
- Web app Expo embebida via `go:embed`
- Parsers de .mat/.csv/.svm
- Pipeline LLM de 4 agentes
- SQLite para sesiones

Deploy: scp binario → servidor Linux → ejecutar detrás de Nginx con TLS.

---

## Pipeline de IA — 4 Agentes

```
Telemetry CSV (≤15K chars) + Setup dict
        │
        ▼
[Translation Agent]      → extiende param_mapping.json con nombres en español
        │
        ▼
[Driving Agent]          → 5 puntos curva-por-curva (sin propuestas de setup)
        │
        ▼
[~14 Section Specialists] → paralelo con goroutines, JSON {parameter, new_value, reason}
        │
        ▼
[Chief Engineer]         → consolidación, simetría axial, coherencia global, full_setup JSON
        │
        ▼
Post-processing           → merge especialista+jefe, enforce simetría, sanitizado de razones
        │
        ▼
        AnalysisResponse
```

---

## Parsers de Telemetría

| Formato | Parser | Notas |
|---------|--------|-------|
| `.mat` | MATLAB Level 5 binary | Canales con `Value`/`Time`, alineación por longitud |
| `.csv` | MoTeC CSV (1000Hz) | Skip 14 header lines, headers línea 15, datos desde 17 |
| `.svm` | rFactor 2 setup INI | Secciones `[SECTION]`, pares `key=value`, UTF-16/UTF-8 |

### GPS Smoothing
- Outlier threshold: 1.5× std
- Rolling window: 11 muestras centradas

### Lap Filtering
- Excluir lap 0 (out-lap)
- Excluir laps con duración > 110% de mediana

---

## Secciones de Setup Analizadas

`GENERAL`, `FRONTWING`, `REARWING`, `BODYAERO`, `SUSPENSION`, `CONTROLS`, `ENGINE`,
`DRIVELINE`, `FRONTLEFT`, `FRONTRIGHT`, `REARLEFT`, `REARRIGHT`, `AERODYNAMICS`, `TIRES`

Excluidas: `BASIC`, `LEFTFENDER`, `RIGHTFENDER`

---

## Providers LLM

| Provider | Modelo | Uso |
|----------|--------|-----|
| Ollama (local) | `llama3.2:latest` (3B) | Análisis completo, ~14 especialistas |
| Ollama Cloud | Cualquier modelo disponible | Con API key |
| Jimmy (chatjimmy.ai) | `llama3.1-8B` | Alternativa remota, contexto reducido |

---

## Etapas de Desarrollo

| Etiqueta | Significado |
|----------|-------------|
| `[STAGE-1-ENV]` | Bootstrap Go + Expo |
| `[STAGE-2-CORE]` | Parsers, upload, sesiones, tracks |
| `[STAGE-3-LLM]` | Pipeline LLM completo en Go |
| `[STAGE-4-WEB]` | Embed Expo web en Go binary |
| `[STAGE-5-QA]` | Tests integration + E2E |
| `[STAGE-6-RELEASE]` | Build Linux + deploy |
