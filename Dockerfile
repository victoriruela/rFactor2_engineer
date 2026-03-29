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
COPY app/core/fixed_params.json app/core/fixed_params.json
COPY app/core/param_mapping.json app/core/param_mapping.json
COPY .streamlit/ .streamlit/
EXPOSE 8501
CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.address", "0.0.0.0"]
