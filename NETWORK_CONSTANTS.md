# Network Constants

| Constant | Value | Source |
|----------|-------|--------|
| FastAPI host | `0.0.0.0` | `app/main.py:494` |
| FastAPI port | `8000` | `app/main.py:494` |
| Streamlit port | `8501` | Streamlit default |
| Ollama API base URL | `http://localhost:11434` | `app/core/ai_agents.py:13` (env `OLLAMA_BASE_URL`) |
| Streamlit → FastAPI base | `http://localhost:8000` | `frontend/streamlit_app.py` (hardcoded) |
