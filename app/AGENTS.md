# AGENTS.md - app/

Guía para agentes que trabajen en el backend Python.

## Objetivo
- Mantener `app/main.py` como capa API ligera.
- Colocar lógica de negocio en `app/services/`.
- Colocar parsing/modelos/agentes LLM en `app/core/`.

## Reglas
- Evita añadir lógica pesada dentro de endpoints FastAPI.
- Si cambias contratos de respuesta, actualiza `app/api/schemas.py`.
- Si introduces constantes nuevas, centralízalas en `app/config/settings.py`.
- Toda función de I/O de archivos grandes debe considerar memoria y cleanup.

## Estructura
- `app/main.py`: arranque y rutas API.
- `app/api/`: esquemas de request/response.
- `app/services/`: orquestación de upload/sesiones/análisis.
- `app/core/`: parsers, AI agents, mappings, prompts.
- `app/config/`: configuración runtime.
