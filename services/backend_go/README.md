# README — Backend Go

Backend del rFactor2 Engineer. Binario Go único que sirve la API REST y la web app Expo embebida.

## Requisitos

- Go 1.23+
- Ollama corriendo en `localhost:11434` con modelo `llama3.2:latest`
- (Opcional) Node.js 20+ para rebuild de la web app Expo

## Desarrollo

```bash
cd services/backend_go
go run ./cmd/server
# Servidor en http://localhost:8080
```

## Variables de Entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `PORT` | `8080` | Puerto del servidor |
| `DATA_DIR` | `data` | Directorio de datos de sesiones |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL de Ollama |
| `OLLAMA_MODEL` | `llama3.2:latest` | Modelo LLM por defecto |

## Build Linux

```powershell
$env:GOOS = "linux"; $env:GOARCH = "amd64"
go build -ldflags "-s -w" -o rf2engineer ./cmd/server
```

## Tests

```bash
go test ./...           # Unit + integration
go test ./e2e/...       # E2E (requiere servidor corriendo)
```
