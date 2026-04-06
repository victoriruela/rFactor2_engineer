# Network Constants

| Constant | Value | Source |
|----------|-------|--------|
| Gin server host | `0.0.0.0` | `services/backend_go/cmd/server/main.go` |
| Gin server port | `8080` | `services/backend_go/cmd/server/main.go` (env `RF2_PORT`) |
| Ollama API base URL | `http://localhost:11434` | `services/backend_go/internal/ollama/client.go` (env `OLLAMA_BASE_URL`) |
| Expo dev server port | `8081` | Expo default (`npx expo start --web`) |

## Production Networking

In production, the single Go binary serves both the API and the embedded Expo web build:

| Connection | URL |
|------------|-----|
| Browser → Expo web | `https://car-setup.com/` (served by Go via go:embed) |
| Browser → API | `https://car-setup.com/api/*` (Gin routes) |
| Go → Ollama | `http://localhost:11434` (local Ollama on same host) |
| Nginx → Go binary | `http://127.0.0.1:8080` |
