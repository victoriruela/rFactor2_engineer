// cmd/benchmark — standalone benchmark runner.
// Tests all available cloud models against the 6 agent roles and writes the
// best assignment to model_routing.json.
//
// The API key is resolved in order:
//  1. OLLAMA_API_KEY env var
//  2. ollama_api_key of the admin user in RF2_DATA_DIR/rf2_users.db
//
// Usage (from services/backend_go/):
//
//	OLLAMA_BASE_URL=https://www.ollama.com \
//	RF2_DATA_DIR=./data \
//	BENCHMARK_MAX_CANDIDATES=200 \
//	./benchmark
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	"github.com/viciruela/rfactor2-engineer/internal/auth"
	"github.com/viciruela/rfactor2-engineer/internal/benchmarks"
	"github.com/viciruela/rfactor2-engineer/internal/config"
)

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// readAPIKeyFromDB opens the users SQLite DB and returns the admin user's API key.
func readAPIKeyFromDB(dataDir string) string {
	db, err := auth.OpenDB(dataDir)
	if err != nil {
		return ""
	}
	defer db.Close()
	user, err := db.GetUserByUsername("Mulder_admin")
	if err != nil || user == nil {
		return ""
	}
	return user.OllamaAPIKey
}

func main() {
	baseURL := getEnv("OLLAMA_BASE_URL", "https://www.ollama.com")
	apiKey := getEnv("OLLAMA_API_KEY", "")
	dataDir := getEnv("RF2_DATA_DIR", "./data")
	maxStr := getEnv("BENCHMARK_MAX_CANDIDATES", "200")

	maxCandidates, err := strconv.Atoi(maxStr)
	if err != nil || maxCandidates <= 0 {
		maxCandidates = 200
	}

	// Auto-read API key from local DB if not provided via env
	if apiKey == "" {
		apiKey = readAPIKeyFromDB(dataDir)
		if apiKey != "" {
			fmt.Println("API key loaded from local database.")
		}
	}

	if apiKey == "" {
		fmt.Fprintln(os.Stderr, "OLLAMA_API_KEY is required (or save it via the web UI into the admin profile)")
		os.Exit(1)
	}

	fmt.Printf("=== rFactor2 Engineer — Model Benchmark ===\n")
	fmt.Printf("Ollama URL    : %s\n", baseURL)
	fmt.Printf("Data dir      : %s\n", dataDir)
	fmt.Printf("Max candidates: %d\n\n", maxCandidates)

	progress := func(ev benchmarks.AutoSelectProgress) {
		data, _ := json.Marshal(ev.Data)
		fmt.Printf("[%-20s] %s\n", ev.Event, data)
	}

	result, err := benchmarks.AutoSelectModels(context.Background(), baseURL, apiKey, maxCandidates, progress)
	if err != nil {
		fmt.Fprintf(os.Stderr, "\nBenchmark failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("\n=== Results (%.0fs) ===\n", result.Elapsed)
	for _, role := range []string{"driving", "suspension", "chassis", "aero", "powertrain", "chief"} {
		a := result.Assignments[role]
		fmt.Printf("  %-15s → %-30s T=%.1f\n", role, a.Model, a.Temperature)
	}

	routingPath := filepath.Join(dataDir, "model_routing.json")
	routing := &config.ModelRouting{Version: 1, Assignments: result.Assignments}
	if err := config.SaveModelRouting(routingPath, routing); err != nil {
		fmt.Fprintf(os.Stderr, "\nFailed to save routing: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("\nRouting saved to: %s\n", routingPath)
}
