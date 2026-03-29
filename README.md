# rFactor2 Engineer

rFactor2 Engineer es una aplicación inteligente diseñada para pilotos de rFactor 2 que buscan optimizar su rendimiento en pista mediante el análisis de telemetría y el ajuste preciso del setup del vehículo. La aplicación utiliza agentes de IA (basados en LangChain con Ollama y el modelo Llama 3.2 3B local) para procesar archivos de MoTeC (.ld) y archivos de configuración (.svm), proporcionando recomendaciones visuales y detalladas.

## ✨ Características Principales

- **Análisis de Telemetría MoTeC**: Soporte para archivos `.ld`.
- **Interpretación de Setup**: Lectura de archivos `.svm` de rFactor 2.
- **Mapa de Circuito Inteligente**: Visualización del trazado con zonas coloreadas según el tipo de pérdida de tiempo:
  - 🔴 **Rojo**: Pérdida por mala conducción.
  - 🟡 **Amarillo**: Pérdida por deficiencia en el setup.
  - 🟠 **Naranja**: Pérdida combinada (conducción y setup).
- **Agentes de IA con Ollama + Llama 3.2 3B**:
  - Modelo local `llama3.2:latest` ejecutado mediante Ollama del host.
  - Requisito: Ollama instalado en el host y accesible en `http://localhost:11434`.
  - Si falta el modelo: `ollama pull llama3.2:latest`.
  - Ingeniero de Pista (Conducción).
  - Mecánico de Competición (Setup).
- **Reporte de Setup Completo**: Recomendaciones detalladas para cada parámetro del setup, justificando tanto los cambios como la decisión de mantener ciertos valores.

## 🏗️ Estructura del Proyecto

```text
rFactor2_engineer/
├── app/
│   ├── main.py                # Servidor API FastAPI
│   ├── core/
│   │   ├── ai_agents.py       # Lógica de agentes de IA (LangChain + Ollama)
│   │   └── telemetry_parser.py # Decodificadores de archivos .ld, .svm
├── frontend/
│   └── streamlit_app.py       # Interfaz de usuario interactiva
├── models/
│   └── Llama-3.2-3B-Instruct-Q4_0.gguf  # Modelo local
├── data/                      # Almacenamiento temporal de archivos
├── requirements.txt           # Dependencias del proyecto
└── .env                       # Variables de entorno
```

## 🚀 Guía de Instalación y Ejecución

### 1. Requisitos Previos

- Python 3.9 o superior.
- [Ollama](https://ollama.com/) instalado en el host (Windows/Linux/macOS).
- Modelo `llama3.2:latest` descargado en Ollama (**requisito obligatorio** para la app y los tests de integración):
  ```
  ollama pull llama3.2:latest
  ```

### 2. Instalación de Dependencias

Clona el repositorio y ejecuta:

```powershell
pip install -r requirements.txt
```

### 3. Configuración

El archivo `.env` en la raíz del proyecto contiene la configuración de Ollama:

```text
OLLAMA_MODEL="llama3.2-3b-instruct"
OLLAMA_BASE_URL="http://localhost:11434"
```

En Docker Compose, el backend usa el Ollama del host mediante:

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### 4. Lanzar la Aplicación

Debes iniciar tanto el backend (API) como el frontend (Streamlit).

**Paso A: Iniciar el Backend (FastAPI)**
Abre una terminal y ejecuta:

```powershell
python -m uvicorn app.main:app --reload
```
La API estará disponible en `http://localhost:8000`.

**Paso B: Iniciar el Frontend (Streamlit)**
Abre otra terminal y ejecuta:

```powershell
streamlit run frontend/streamlit_app.py
```
La aplicación se abrirá automáticamente en tu navegador (por defecto en `http://localhost:8501`).

**Notas importantes:**
- El backend inicia rápidamente (el LLM se carga de forma lazy en el primer análisis).
- Inicia Ollama en el host antes de analizar (`ollama serve` si no está ya corriendo).
- Si falta el modelo, descárgalo una vez con `ollama pull llama3.2:latest`.
- Ver docs API en `http://localhost:8000/docs`.

### Ejecución con Docker (recomendada)

```powershell
docker compose up --build
```

Servicios:
- Frontend: `http://localhost:8501`
- Backend: `http://localhost:8000`
- Ollama (host): `http://localhost:11434`

## 🛠️ Uso

1. Abre la interfaz de Streamlit.
2. Sube los archivos de tu sesión arrastrándolos al cargador:
   - Archivo de telemetría de datos (`.ld`).
   - Archivo de setup del coche (`.svm`).
   - *Nota: Ambos archivos deben tener el mismo nombre base.*
3. Si has subido varias sesiones, selecciona la que deseas analizar en el menú desplegable.
4. Haz clic en **"Analizar Datos"**.
5. Revisa el mapa del circuito y las listas de recomendaciones para mejorar tu tiempo de vuelta.

## 🔗 Asana MCP Integration

Este proyecto incluye un plugin de Claude Code para gestionar la autenticación OAuth2 y configuración MCP de Asana en múltiples IDEs (Claude Desktop, Claude CLI, VS Code Copilot, JetBrains Copilot).

- **Plugin zip:** [`asana-mcp-plugin.zip`](asana-mcp-plugin.zip) — descomprimir en `~/.claude/asana-mcp/`
- **Documentación completa:** [`ASANA.md`](ASANA.md)

## 📝 Notas Técnicas
- El parseo de archivos `.ld` se realiza mediante una implementación interna que lee la estructura binaria de MoTeC, extrayendo canales de telemetría sin depender de librerías externas de terceros.
- La visualización del mapa utiliza `Plotly` para gráficos interactivos.
- Los agentes de IA están configurados para procesar la telemetría y el setup de forma integral, cumpliendo con el requisito de no dejar ningún punto del setup sin analizar.
