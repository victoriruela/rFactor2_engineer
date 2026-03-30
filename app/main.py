from __future__ import annotations

import json
import os
import uuid  # noqa: F401

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Optional

from app.api.schemas import AnalysisResponse, UploadInitRequest
from app.config import settings
from app.core.ai_agents import AIAngineer, list_available_models
from app.core.telemetry_parser import parse_csv_file, parse_mat_file, parse_svm_file
from app.services import session_service, upload_service
from app.services.analysis_service import AnalysisService

app = FastAPI(title="rFactor2 Engineer API")

ALLOWED_BROWSER_ORIGINS = [
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "https://car-setup.com",
    "https://telemetria.bot.nu",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_BROWSER_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_engineer = AIAngineer()

# Backward-compatible constants kept for tests and runtime overrides.
DATA_DIR = settings.DATA_DIR
UPLOAD_CHUNK_SIZE = settings.UPLOAD_CHUNK_SIZE
MAX_AI_TELEMETRY_CHARS = settings.MAX_AI_TELEMETRY_CHARS


# Backward-compatible wrappers kept for test patch points.
def _normalize_session_id(raw_session_id: Optional[str]) -> str:
    return session_service.normalize_session_id(raw_session_id)


def _resolve_client_session_id(
    x_client_session_id: Optional[str] = Header(None),
    rf2_session_id: Optional[str] = Cookie(None),
) -> str:
    return session_service.resolve_client_session_id(x_client_session_id, rf2_session_id)


def _client_root(client_session_id: str) -> str:
    return os.path.join(DATA_DIR, client_session_id)


def _list_client_sessions(client_session_id: str):
    return session_service.list_client_sessions(client_session_id, root_resolver=_client_root)


def _find_session_pair(client_session_id: str, session_id: str):
    return session_service.find_session_pair(client_session_id, session_id, root_resolver=_client_root)


@app.post("/uploads/init")
def init_upload(
    payload: UploadInitRequest,
    client_session_id: str = Depends(_resolve_client_session_id),
):
    return upload_service.init_upload(payload.filename, client_session_id)


@app.put("/uploads/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    request: Request,
    chunk_index: int,
    client_session_id: str = Depends(_resolve_client_session_id),
):
    return await upload_service.append_chunk(upload_id, request, chunk_index, client_session_id)


@app.post("/uploads/{upload_id}/complete")
def complete_upload(
    upload_id: str,
    client_session_id: str = Depends(_resolve_client_session_id),
):
    return upload_service.complete_upload(upload_id, client_session_id, root_resolver=_client_root)


@app.get("/sessions")
def list_sessions(client_session_id: str = Depends(_resolve_client_session_id)):
    return {"sessions": _list_client_sessions(client_session_id)}


@app.get("/sessions/{session_id}/file/{filename}")
def get_session_file(
    session_id: str,
    filename: str,
    client_session_id: str = Depends(_resolve_client_session_id),
):
    pair = _find_session_pair(client_session_id, session_id)
    expected_files = {pair["telemetry"], pair["svm"]}
    if filename not in expected_files:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = os.path.join(_client_root(client_session_id), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.get("/models")
def get_models(
    ollama_base_url: Optional[str] = None,
    ollama_api_key: Optional[str] = None,
):
    models = list_available_models(base_url=ollama_base_url, api_key=ollama_api_key)
    return {"models": models}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_telemetry(
    telemetry_file: UploadFile = File(...),
    svm_file: UploadFile = File(...),
    model: Optional[str] = Form(None),
    provider: Optional[str] = Form("ollama"),
    fixed_params: Optional[str] = Form(None),
    ollama_base_url: Optional[str] = Form(None),
    ollama_api_key: Optional[str] = Form(None),
):
    fixed_params_list = []
    if fixed_params:
        try:
            fixed_params_list = json.loads(fixed_params)
        except Exception:
            fixed_params_list = []

    try:
        payload = await AnalysisService.analyze_uploads(
            telemetry_file=telemetry_file,
            svm_file=svm_file,
            ai_engineer=ai_engineer,
            parse_mat_fn=parse_mat_file,
            parse_csv_fn=parse_csv_file,
            parse_svm_fn=parse_svm_file,
            model=model,
            provider=provider or "ollama",
            fixed_params_list=fixed_params_list,
            ollama_base_url=ollama_base_url,
            ollama_api_key=ollama_api_key,
            data_dir=DATA_DIR,
        )
        return AnalysisResponse(**payload)
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "connection attempts failed" in error_msg.lower() or "connection error" in error_msg.lower():
            if (provider or "ollama").lower() == "jimmy":
                detail = "Error de conexión con Jimmy API. Verifica tu conexión a Internet e inténtalo de nuevo."
            else:
                detail = (
                    "Error de conexión con el modelo local (Ollama). Asegúrate de que Ollama esté instalado, "
                    "ejecutándose y con el modelo 'llama3' descargado."
                )
        else:
            detail = error_msg
        raise HTTPException(status_code=500, detail=detail)


@app.post("/analyze_session", response_model=AnalysisResponse)
async def analyze_stored_session(
    session_id: str = Form(...),
    model: Optional[str] = Form(None),
    provider: Optional[str] = Form("ollama"),
    fixed_params: Optional[str] = Form(None),
    ollama_base_url: Optional[str] = Form(None),
    ollama_api_key: Optional[str] = Form(None),
    client_session_id: str = Depends(_resolve_client_session_id),
):
    pair = _find_session_pair(client_session_id, session_id)
    client_root = _client_root(client_session_id)
    tele_path = os.path.join(client_root, pair["telemetry"])
    svm_path = os.path.join(client_root, pair["svm"])

    if not os.path.exists(tele_path) or not os.path.exists(svm_path):
        raise HTTPException(status_code=404, detail="Session files are missing")

    telemetry_handle = open(tele_path, "rb")
    svm_handle = open(svm_path, "rb")
    telemetry_upload = UploadFile(filename=pair["telemetry"], file=telemetry_handle)
    svm_upload = UploadFile(filename=pair["svm"], file=svm_handle)
    analysis_succeeded = False

    try:
        result = await analyze_telemetry(
            telemetry_file=telemetry_upload,
            svm_file=svm_upload,
            model=model,
            provider=provider,
            fixed_params=fixed_params,
            ollama_base_url=ollama_base_url,
            ollama_api_key=ollama_api_key,
        )
        analysis_succeeded = True
        return result
    finally:
        if analysis_succeeded:
            for path in (tele_path, svm_path):
                if os.path.exists(path):
                    os.remove(path)


@app.post("/cleanup")
async def cleanup_data(client_session_id: str = Depends(_resolve_client_session_id)):
    return session_service.cleanup_client_data(client_session_id, root_resolver=_client_root)


@app.post("/cleanup_all")
async def cleanup_all_data():
    return session_service.cleanup_all_data(data_dir=DATA_DIR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
