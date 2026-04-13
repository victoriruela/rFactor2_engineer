package config

import (
	"encoding/json"
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
	JWTSecret    string
	SMTPHost     string
	SMTPPort     string
	SMTPUser     string
	SMTPPass     string
	SMTPFrom     string
}

// ModelAssignment holds the model and temperature for a specific agent role.
type ModelAssignment struct {
	Model       string  `json:"model"`
	Temperature float64 `json:"temperature"`
}

// ModelRouting holds per-role model assignments, loaded from model_routing.json or env vars.
type ModelRouting struct {
	Version     int                          `json:"version"`
	Assignments map[string]ModelAssignment   `json:"assignments"`
}

// ForRole returns the model for a given role, falling back to the global default.
func (mr *ModelRouting) ForRole(role, globalDefault string) string {
	if mr != nil {
		if a, ok := mr.Assignments[role]; ok && a.Model != "" {
			return a.Model
		}
	}
	return globalDefault
}

// TempForRole returns the temperature for a given role, falling back to defaultTemp.
func (mr *ModelRouting) TempForRole(role string, defaultTemp float64) float64 {
	if mr != nil {
		if a, ok := mr.Assignments[role]; ok && a.Temperature > 0 {
			return a.Temperature
		}
	}
	return defaultTemp
}

// LoadModelRouting loads model routing config from the given JSON file.
// Returns nil (no error) if the file does not exist.
func LoadModelRouting(path string) (*ModelRouting, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var mr ModelRouting
	if err := json.Unmarshal(data, &mr); err != nil {
		return nil, err
	}
	return &mr, nil
}

// SaveModelRouting writes the routing config to the given JSON file.
func SaveModelRouting(path string, routing *ModelRouting) error {
	data, err := json.MarshalIndent(routing, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func Load() *Config {
	return &Config{
		Port:         getEnvInt("RF2_PORT", 8080),
		DataDir:      getEnv("RF2_DATA_DIR", "./data"),
		OllamaURL:    getEnv("OLLAMA_BASE_URL", "http://localhost:11434"),
		OllamaModel:  getEnv("OLLAMA_MODEL", "llama3.2:latest"),
		OllamaAPIKey: getEnv("OLLAMA_API_KEY", ""),
		LogLevel:     getEnv("RF2_LOG_LEVEL", "info"),
		JWTSecret:    getEnv("RF2_JWT_SECRET", ""),
		SMTPHost:     getEnv("RF2_SMTP_HOST", ""),
		SMTPPort:     getEnv("RF2_SMTP_PORT", "587"),
		SMTPUser:     getEnv("RF2_SMTP_USER", ""),
		SMTPPass:     getEnv("RF2_SMTP_PASS", ""),
		SMTPFrom:     getEnv("RF2_SMTP_FROM", ""),
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
