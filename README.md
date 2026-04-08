# rFactor2 Engineer

rFactor2 Engineer es una aplicación de análisis de telemetría y setup para rFactor 2. El runtime actual es un backend Go que sirve la API REST y la web embebida sin necesidad de Docker.

## ✨ Características Principales

- **Análisis de telemetría de sesión** y lectura de setups `*.svm`.
- **Recomendaciones de setup** generadas por agentes de IA que usan Ollama.
- **Web embebida** servida directamente desde el binario Go.
- **Ejecución local sin Docker**.
- **Artefacto Windows listo para ejecutar** en `dist/`.

## 🏗️ Estructura del Proyecto

```text
rFactor2_engineer/
├── apps/expo_app/              # Fuente de la web Expo
├── services/backend_go/        # Backend Go y assets estáticos embebidos
│   ├── cmd/server/             # Servidor Go principal
│   └── internal/               # Lógica del backend, handlers y parsers
├── data/                       # Sesiones y uploads temporales
├── docs/                       # Documentación del proyecto
├── scripts/                    # Scripts de utilidad para Windows y deploy
└── dist/                       # Artefactos de build generados localmente
```

## 🚀 Requisitos

- Go 1.23+ instalado.
- Ollama instalado y corriendo en `http://localhost:11434`.
- Modelo `llama3.2:latest` descargado en Ollama:

```powershell
ollama pull llama3.2:latest
```

## 🧰 Construir el artefacto de Windows

Desde la raíz del repositorio:

```powershell
cd services/backend_go
go build -ldflags "-s -w" -o ..\..\dist\rfactor2-engineer-windows-amd64.exe ./cmd/server
```

El ejecutable resultante estará en `dist/rfactor2-engineer-windows-amd64.exe`.

## ▶️ Ejecutar la aplicación

En Windows, abre PowerShell y ejecuta:

```powershell
cd dist
.\rfactor2-engineer-windows-amd64.exe
```

La API se servirá en `http://localhost:8080`.

### Variables opcionales

- `PORT` — puerto HTTP (por defecto `8080`)
- `DATA_DIR` — directorio de sesiones (por defecto `data`)
- `OLLAMA_BASE_URL` — URL de Ollama (por defecto `http://localhost:11434`)
- `OLLAMA_MODEL` — modelo Ollama (por defecto `llama3.2:latest`)

## 🔧 Desarrollo

Para ejecutar el backend desde el código fuente:

```powershell
cd services/backend_go
go run ./cmd/server
```

El servidor escuchará en `http://localhost:8080`.

## 📄 Notas

- No se utiliza Docker para la ejecución local actual.
- El frontend está preconstruido y embebido en `services/backend_go/cmd/server/static`.
- Si modificas la web Expo, genera los assets nuevamente en `apps/expo_app` y actualiza el contenido de `services/backend_go/cmd/server/static`.
