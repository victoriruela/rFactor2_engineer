# Network Constants

| Constant | Value | Source |
|----------|-------|--------|
| FastAPI host | `0.0.0.0` | `app/main.py:494` |
| FastAPI port | `8000` | `app/main.py:494` |
| Streamlit port | `8501` | Streamlit default |
| Ollama API base URL | `http://localhost:11434` | `app/core/ai_agents.py:13` (env `OLLAMA_BASE_URL`) |
| Streamlit → FastAPI base | `http://localhost:8000` | `frontend/streamlit_app.py:12` (env `RF2_API_URL`) |

## Docker Networking

When running via `docker compose`, services communicate using container DNS names instead of `localhost`:

| Connection | URL | Env var |
|------------|-----|---------|
| Frontend → Backend | `http://backend:8000` | `RF2_API_URL` |
| Backend → Ollama | `http://ollama:11434` | `OLLAMA_BASE_URL` |
