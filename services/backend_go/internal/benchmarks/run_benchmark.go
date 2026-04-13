package benchmarks

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

// LoadGoldenDataset reads all test case JSON files from the given directory.
func LoadGoldenDataset(dir string) ([]BenchmarkCase, error) {
	pattern := filepath.Join(dir, "*.json")
	files, err := filepath.Glob(pattern)
	if err != nil {
		return nil, fmt.Errorf("globbing golden dataset: %w", err)
	}
	if len(files) == 0 {
		return nil, fmt.Errorf("no golden test cases found in %s", dir)
	}

	var cases []BenchmarkCase
	for _, f := range files {
		data, err := os.ReadFile(f)
		if err != nil {
			log.Warn().Str("file", f).Err(err).Msg("skipping unreadable test case")
			continue
		}
		var tc BenchmarkCase
		if err := json.Unmarshal(data, &tc); err != nil {
			log.Warn().Str("file", f).Err(err).Msg("skipping invalid test case JSON")
			continue
		}
		cases = append(cases, tc)
	}
	return cases, nil
}

// RunBenchmark executes a benchmark run: sends the test case to the model and records the response.
func RunBenchmark(ctx context.Context, client *ollama.Client, model string, tc BenchmarkCase, runIndex int) BenchmarkRun {
	start := time.Now()

	// Build a prompt that mimics what the domain engineer would receive
	prompt := fmt.Sprintf(`Eres un ingeniero de setup de rFactor 2 especializado en %s.

Telemetría:
%s

Setup actual (secciones asignadas):
%s

Responde en JSON con tus propuestas de cambio siguiendo el formato:
{"sections": [{"section": "...", "items": [{"parameter": "...", "new_value": "...", "reason": "..."}]}], "findings_summary": "...", "confidence": 0.8}`,
		tc.Role, tc.TelemetrySummary, formatSetupForPrompt(tc.SetupSections))

	response, err := client.GenerateWithModel(ctx, prompt, "", model, 0.2)
	elapsed := time.Since(start).Seconds()

	if err != nil {
		return BenchmarkRun{
			CaseID:   tc.ID,
			Model:    model,
			Role:     tc.Role,
			RunIndex: runIndex,
			Response: "ERROR: " + err.Error(),
			Score:    JudgeScore{},
			Elapsed:  elapsed,
		}
	}

	return BenchmarkRun{
		CaseID:   tc.ID,
		Model:    model,
		Role:     tc.Role,
		RunIndex: runIndex,
		Response: response,
		Elapsed:  elapsed,
	}
}

func formatSetupForPrompt(sections map[string]map[string]string) string {
	data, _ := json.MarshalIndent(sections, "", "  ")
	return string(data)
}
