# rFactor2 Engineer

rFactor2 Engineer es una aplicación inteligente diseñada para pilotos de rFactor 2 que buscan optimizar su rendimiento en pista mediante el análisis de telemetría y el ajuste preciso del setup del vehículo. La aplicación utiliza agentes de IA (basados en LangChain y modelos Llama 3.3) para procesar archivos de MoTeC (.ld) y archivos de configuración (.svm), proporcionando recomendaciones visuales y detalladas.

## ✨ Características Principales

- **Análisis de Telemetría MoTeC**: Soporte para archivos `.ld`.
- **Interpretación de Setup**: Lectura de archivos `.svm` de rFactor 2.
- **Mapa de Circuito Inteligente**: Visualización del trazado con zonas coloreadas según el tipo de pérdida de tiempo:
  - 🔴 **Rojo**: Pérdida por mala conducción.
  - 🟡 **Amarillo**: Pérdida por deficiencia en el setup.
  - 🟠 **Naranja**: Pérdida combinada (conducción y setup).
- **Agentes de IA Expertos**: 
  - Ingeniero de Pista (Conducción).
  - Mecánico de Competición (Setup).
- **Reporte de Setup Completo**: Recomendaciones detalladas para cada parámetro del setup, justificando tanto los cambios como la decisión de mantener ciertos valores.

## 🏗️ Estructura del Proyecto

```text
rFactor2_engineer/
├── app/
│   ├── main.py                # Servidor API FastAPI
│   ├── core/
│   │   ├── ai_agents.py       # Lógica de agentes de IA (LangChain + Groq)
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
- Una cuenta en [Groq Cloud](https://console.groq.com/) para obtener una API Key (modelo Llama 3.3 gratuito).

### 2. Instalación de Dependencias

Clona el repositorio y ejecuta:

```powershell
pip install -r requirements.txt
```

### 3. Configuración

Crea un archivo `.env` en la raíz del proyecto con tu clave de API de Groq:

```text
GROQ_API_KEY=tu_api_key_aqui
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