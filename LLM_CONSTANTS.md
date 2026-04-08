# LLM Constants

| Constant | Value | Source |
|----------|-------|--------|
| Default model tag | `llama3.2:latest` (= 3b, 2.0 GB) | `services/backend_go/internal/ollama/client.go` (env `OLLAMA_MODEL`) |
| `num_predict` | `4096` | `services/backend_go/internal/agents/pipeline.go` |
| `temperature` | `0.3` | `services/backend_go/internal/agents/pipeline.go` |
| Ollama startup wait | 15 attempts, 1s apart | `services/backend_go/internal/ollama/client.go` |

## Providers

| Provider | Endpoint | Notes |
|----------|----------|-------|
| Ollama (local) | `http://localhost:11434` | Default; auto-started if not running |
| Ollama Cloud | `https://ollama.com` | Requires `OLLAMA_API_KEY`; keys from `https://ollama.com/settings/keys` |
| Jimmy | `https://chatjimmy.ai` | llama3.1-8B; alternate key normalization in specialist/chief agents |
