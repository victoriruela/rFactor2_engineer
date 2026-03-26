# rFactor2 Engineer - Especificación Técnica

## Descripción General
rFactor2 Engineer es una aplicación diseñada para ayudar a pilotos de rFactor 2 a mejorar su tiempo de vuelta mediante el análisis de telemetría de MoTeC (.ld) y setups del coche (.svm). Utiliza agentes de IA para interpretar los datos y proporcionar recomendaciones tanto de conducción como de reglajes.

## Arquitectura
- **Frontend**: Streamlit. Elegido por su rapidez de desarrollo y capacidad para mostrar gráficos de datos de forma interactiva.
- **Backend API**: FastAPI. Para gestionar el procesamiento de archivos y la lógica de los agentes de IA.
- **Procesamiento de Telemetría**: Librerías especializadas (como `motec-decoder` o implementación propia) para leer archivos binarios `.ld`.
- **Agentes de IA**: LangChain utilizando Free API (vía g4f/GPT-4o) para máxima velocidad y calidad sin costes. También soporta descarga directa de modelos locales (GPT4All), Ollama local externo o modelos en la nube (Groq).

## Funcionalidades
1. **Carga de Archivos**: Soporte para archivos `.ld` y `.svm`.
2. **Decodificación**: Extracción de canales de telemetría (velocidad, aceleración, posición, temperaturas, etc.) y parámetros del setup.
3. **Análisis por IA**:
   - **Agente de Conducción**: Analiza trazadas, puntos de frenada y aplicación de acelerador.
   - **Agente de Setup**: Analiza el comportamiento del coche (sobreviraje, subviraje, temperaturas de neumáticos) basándose en la telemetría y el setup actual.
   - **Agente Coordinador**: Combina la información para generar el reporte final.
4. **Visualización**:
   - Mapa del circuito con código de colores (Rojo: Conducción, Amarillo: Setup, Naranja: Ambos).
   - Listas detalladas de puntos de mejora.
   - Tabla completa de cambios en el setup (incluyendo lo que NO se cambia).

## Estructura de Archivos Propuesta
```text
rFactor2_engineer/
├── app/
│   ├── main.py (FastAPI entry point)
│   ├── api/
│   │   ├── endpoints.py
│   │   └── models.py
│   ├── core/
│   │   ├── telemetry_parser.py
│   │   ├── setup_parser.py
│   │   └── ai_agents.py
│   └── utils/
├── frontend/
│   └── streamlit_app.py
├── data/ (Carpeta temporal para archivos subidos)
├── requirements.txt
└── README.md
```
