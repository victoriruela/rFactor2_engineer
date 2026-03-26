# rFactor2 Engineer

rFactor2 Engineer es una aplicación inteligente diseñada para pilotos de rFactor 2 que buscan optimizar su rendimiento en pista mediante el análisis de telemetría y el ajuste preciso del setup del vehículo. La aplicación utiliza agentes de IA (basados en LangChain con soporte para modelos locales gratuitos vía Ollama o en la nube vía Groq) para procesar archivos de MoTeC (.ld) y archivos de configuración (.svm), proporcionando recomendaciones visuales y detalladas.

## ✨ Características Principales

- **Análisis de Telemetría MoTeC**: Soporte para archivos `.ld`.
- **Interpretación de Setup**: Lectura de archivos `.svm` de rFactor 2.
- **Mapa de Circuito Inteligente**: Visualización del trazado con zonas coloreadas según el tipo de pérdida de tiempo:
  - 🔴 **Rojo**: Pérdida por mala conducción.
  - 🟡 **Amarillo**: Pérdida por deficiencia en el setup.
  - 🟠 **Naranja**: Pérdida combinada (conducción y setup).
- **Agentes de IA Flexibles**: 
  - **Free API (Nuevo - Recomendado)**: Utiliza el motor `g4f` para acceder a modelos potentes como GPT-4o de forma gratuita y sin necesidad de registro o API keys. Mucho más rápido que el modo local.
  - **Local Directo**: Descarga automática de modelos ligeros mediante `GPT4All`.
  - Soporte para **Ollama** (Modelos locales externos).
  - Soporte para **Groq** (Modelos en la nube).
  - Ingeniero de Pista (Conducción).
  - Mecánico de Competición (Setup).
- **Reporte de Setup Completo**: Recomendaciones detalladas para cada parámetro del setup, justificando tanto los cambios como la decisión de mantener ciertos valores.

## 🏗️ Estructura del Proyecto

```text
rFactor2_engineer/
├── app/
│   ├── main.py                # Servidor API FastAPI
│   ├── core/
│   │   ├── ai_agents.py       # Lógica de agentes de IA (LangChain)
│   │   └── telemetry_parser.py # Decodificadores de archivos .ld, .svm
├── frontend/
│   └── streamlit_app.py       # Interfaz de usuario interactiva
├── data/                      # Almacenamiento temporal de archivos
├── requirements.txt           # Dependencias del proyecto
└── .env                       # Variables de entorno (API Keys)
```

## 🚀 Guía de Instalación y Ejecución

### 1. Requisitos Previos

- Python 3.9 o superior.
- **Opción A (Recomendada - Local Directo):** No requiere nada. El sistema descargará un modelo ligero (`orca-mini`) automáticamente al primer inicio.
- **Opción B (Local con Ollama):** [Ollama](https://ollama.com/) instalado y el modelo `llama3` descargado (`ollama run llama3`).
- **Opción C (Nube):** Una cuenta en [Groq Cloud](https://console.groq.com/) para obtener una API Key.

### 2. Instalación de Dependencias

Clona el repositorio y ejecuta:

```powershell
pip install -r requirements.txt
```

### 3. Configuración

Crea o edita el archivo `.env` en la raíz del proyecto. 

**Para usar Free API (Default - GPT-4o gratis y rápido, sin login):**
```text
LLM_PROVIDER="free-api"
```
**Para usar Local Directo (Modelo descargado auto):**
```text
LLM_PROVIDER="local"
LOCAL_MODEL_NAME="Llama-3.2-3B-Instruct-Q4_0.gguf"
LOCAL_MODEL_PATH="./models"
```

**Para usar Ollama (Local externo):**
```text
LLM_PROVIDER="ollama"
OLLAMA_MODEL="llama3"
OLLAMA_BASE_URL="http://localhost:11434"
```

**Para usar Groq (Nube):**
```text
LLM_PROVIDER="groq"
GROQ_API_KEY=tu_api_key_aqui
GROQ_MODEL="llama-3.3-70b-versatile"
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
- El backend inicia **rápidamente** (LLM carga lazy solo en primera análisis).
- Primera `/analyze` puede tardar **1-2 min** (init LLM + pruebas de proveedores gratuitos con timeout).
- Si lento/falla: Cambia en `.env` a `LLM_PROVIDER="local"` (descarga modelo 2GB auto) o instala Ollama.
- Ver docs API en `http://localhost:8000/docs`.

## 🛠️ Uso

1. Abre la interfaz de Streamlit.
2. Sube los archivos de tu sesión arrastrándolos al cargador:
   - Archivo de telemetría de datos (`.ld`).
   - Archivo de setup del coche (`.svm`).
   - *Nota: Ambos archivos deben tener el mismo nombre base.*
3. Si has subido varias sesiones, selecciona la que deseas analizar en el menú desplegable.
4. Haz clic en **"Analizar Datos"**.
5. Revisa el mapa del circuito y las listas de recomendaciones para mejorar tu tiempo de vuelta.

## 📝 Notas Técnicas
- El parseo de archivos `.ld` se realiza mediante una implementación interna que lee la estructura binaria de MoTeC, extrayendo canales de telemetría sin depender de librerías externas de terceros.
- La visualización del mapa utiliza `Plotly` para gráficos interactivos.
- Los agentes de IA están configurados para procesar la telemetría y el setup de forma integral, cumpliendo con el requisito de no dejar ningún punto del setup sin analizar.