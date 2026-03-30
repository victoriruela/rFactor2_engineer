# --- shared base ---
FROM python:3.11-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- backend ---
FROM base AS backend
COPY app/ app/
COPY .env* ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- frontend ---
FROM base AS frontend
COPY frontend/ frontend/
COPY app/ app/
COPY .streamlit/ .streamlit/
EXPOSE 8501
CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.address", "0.0.0.0"]

# --- test (unit + lint) ---
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
# Source is bind-mounted at runtime; no COPY here so edits are reflected immediately.
CMD ["pytest", "tests/", "--ignore=tests/integration", "-v"]
