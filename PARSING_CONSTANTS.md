# Parsing Constants

## File Paths

| Constant | Value | Source |
|----------|-------|--------|
| Data upload directory | `data/` | `app/main.py:32` |
| Parameter mapping | `app/core/param_mapping.json` | `app/core/ai_agents.py:250` |
| Fixed params | `app/core/fixed_params.json` | `frontend/streamlit_app.py:11` |
| Streamlit config | `.streamlit/config.toml` | Streamlit convention |
| Max upload size | `20000` MB | `.streamlit/config.toml` |

## CSV Format (MoTeC Export)

| Constant | Value |
|----------|-------|
| Metadata lines to skip | 14 |
| Headers line | 15 (0-indexed: 14) |
| Units line | 16 (0-indexed: 15) |
| Data starts at line | 17 (0-indexed: 16) |

## GPS Smoothing

| Constant | Value |
|----------|-------|
| Outlier threshold | 1.5 * std from median |
| Rolling window | 11 samples, centered |

## Lap Filtering

| Constant | Value |
|----------|-------|
| Out-lap exclusion | Lap number 0 |
| Duration outlier threshold | 110% of median lap duration |

## AI Subsampling

| Constant | Value |
|----------|-------|
| Points per lap for AI | ~50 |
| Max telemetry columns | 100 |
| Map subsampling cap | 5000 points |

## Telemetry API Payload

| Constant | Value |
|----------|-------|
| `telemetry_series` max samples (web payload cap) | 12000 |
