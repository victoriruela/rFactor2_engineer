# AGENTS.md - frontend/

Guía para agentes en la capa Streamlit.

## Objetivo
- Frontend solo presenta datos y consume API.
- Evitar duplicar parsing de telemetría ya existente en backend.

## Reglas
- No añadir lógica de negocio pesada en UI.
- Reusar contratos desde API (`/analyze`, `/sessions`, `/uploads/*`).
- Mantener separación entre estado de sesión UI y datos persistidos backend.

## Estado actual de modularización
- Separado en módulos: `api_client.py`, `session_manager.py`, `setup_parser.py`, `telemetry_processing.py`, `components/browser_hooks.py`, `components/telemetry_embed.py`.
- `streamlit_app.py` debe permanecer como orquestador de UI (estado, acciones y render de secciones), delegando lógica pesada de telemetría y JavaScript.

## Próxima dirección de refactor
- Continuar separando `streamlit_app.py` en módulos de UI (`pages_ui`, `telemetry_views`, `analysis_views`).
- Mantener el modo de sesión efímera: sin persistencia de sesión en cookie/query-param.
