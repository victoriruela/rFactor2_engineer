# AGENTS.md - app/services/

Capa de servicios del backend.

## Principios
- Sin dependencia de FastAPI salvo excepciones controladas (`HTTPException` cuando aplica).
- Debe ser reusable por API y por posibles jobs internos.
- Mantener funciones con responsabilidades únicas.

## Servicios actuales
- `session_service.py`: normalización de sesión, listado/búsqueda, cleanup.
- `upload_service.py`: flujo de subida chunked y escritura a disco.
- `analysis_service.py`: orquestación de parseo y análisis IA.

## Reglas de memoria/disco
- Limpiar temporales al finalizar cada análisis.
- Evitar retener DataFrames grandes más tiempo del necesario.
- Mantener límites y umbrales en `app/config/settings.py`.
