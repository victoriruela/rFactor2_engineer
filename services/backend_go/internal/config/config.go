package config

import (
	"os"
	"strconv"
)

type Config struct {
	Port         int
	DataDir      string
	OllamaURL    string
	OllamaModel  string
	OllamaAPIKey string
	LogLevel     string
}

func Load() *Config {
	return &Config{
		Port:         getEnvInt("RF2_PORT", 8080),
		DataDir:      getEnv("RF2_DATA_DIR", "./data"),
		OllamaURL:    getEnv("OLLAMA_BASE_URL", "http://localhost:11434"),
		OllamaModel:  getEnv("OLLAMA_MODEL", "llama3.2:latest"),
		OllamaAPIKey: getEnv("OLLAMA_API_KEY", ""),
		LogLevel:     getEnv("RF2_LOG_LEVEL", "info"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}
