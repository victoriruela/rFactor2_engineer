// Package benchmark implements the rF2-Bench benchmarking infrastructure.
// It loads golden dataset test cases, invokes domain engineers via the
// production pipeline, scores responses through an external LLM judge,
// and produces a Markdown report.
package benchmark

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

// --- Golden Dataset Types ---

// BenchCase is a single test case loaded from a JSONL golden dataset file.
type BenchCase struct {
	ID              string             `json:"id"`
	Scenario        string             `json:"scenario"`
	AgentRole       string             `json:"agent_role"`
	Difficulty      string             `json:"difficulty"`
	TelemetrySummary string            `json:"telemetry_summary"`
	SessionStats    CaseSessionStats   `json:"session_stats"`
	SetupContext    CaseSetupContext   `json:"setup_context"`
	Expected        CaseExpected       `json:"expected"`
}

// CaseSessionStats is the benchmark-JSONL representation of session stats.
type CaseSessionStats struct {
	Laps        int     `json:"laps"`
	BestLap     string  `json:"best_lap"`
	AvgLap      string  `json:"avg_lap"`
	MaxSpeedKmh float64 `json:"max_speed_kmh"`
}

// CaseSetupContext holds the setup sections as delivered to the agent.
type CaseSetupContext struct {
	Sections []CaseSetupSection `json:"sections"`
}

// CaseSetupSection is one section in the benchmark setup context.
type CaseSetupSection struct {
	Name   string            `json:"name"`
	Params map[string]string `json:"params"`
}

// CaseExpected holds the ground-truth expectations for a benchmark case.
type CaseExpected struct {
	KeyFindings               []string                         `json:"key_findings"`
	AcceptableParameterChanges map[string]ParameterChangeSpec   `json:"acceptable_parameter_changes"`
	PhysicsRulesThatApply     []string                         `json:"physics_rules_that_apply"`
	MustNotContain            []string                         `json:"must_not_contain"`
	MustMention               []string                         `json:"must_mention"`
}

// ParameterChangeSpec describes the expected direction and numeric range for a parameter change.
type ParameterChangeSpec struct {
	Direction string    `json:"direction"` // "increase" | "decrease"
	Range     []float64 `json:"range"`     // [min, max]
}

// --- Result Types ---

// BenchResult holds the evaluation result for a single test case.
type BenchResult struct {
	CaseID       string
	Scenario     string
	AgentRole    string
	Difficulty   string
	AgentOutput  string // raw agent response (JSON)
	JudgeScore   *JudgeScore
	Error        string // non-empty if run or judge failed
}

// JudgeScore is the structured score returned by the external LLM judge.
type JudgeScore struct {
	Scores struct {
		PhysicsAccuracy float64 `json:"physics_accuracy"`
		JSONSchema      float64 `json:"json_schema"`
		SpanishQuality  float64 `json:"spanish_quality"`
		CoherenceLogic  float64 `json:"coherence_logic"`
		Actionability   float64 `json:"actionability"`
	} `json:"scores"`
	Penalties     []JudgePenalty `json:"penalties"`
	WeightedScore float64        `json:"weighted_score"`
	Pass          bool           `json:"pass"`
	Summary       string         `json:"summary"`
}

// JudgePenalty is a single deduction applied by the judge.
type JudgePenalty struct {
	Type      string  `json:"type"`
	Detail    string  `json:"detail"`
	Deduction float64 `json:"deduction"`
}

// --- Domain Conversion Helpers ---

// ToDomainSessionStats converts a CaseSessionStats to domain.SessionStats.
func (s CaseSessionStats) ToDomainSessionStats() *domain.SessionStats {
	return &domain.SessionStats{
		TotalLaps:   s.Laps,
		BestLapTime: parseLapTime(s.BestLap),
		AvgLapTime:  parseLapTime(s.AvgLap),
	}
}

// ToDomainSetup converts a CaseSetupContext to domain.Setup.
func (c CaseSetupContext) ToDomainSetup() *domain.Setup {
	setup := domain.NewSetup()
	for _, sec := range c.Sections {
		params := make(map[string]string, len(sec.Params))
		for k, v := range sec.Params {
			params[k] = v
		}
		setup.Sections[sec.Name] = &domain.SetupSection{
			Name:   sec.Name,
			Params: params,
		}
	}
	return setup
}

// parseLapTime converts "m:ss.mmm" strings to seconds (float64).
// Returns 0 on parse failure.
func parseLapTime(s string) float64 {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	parts := strings.SplitN(s, ":", 2)
	if len(parts) != 2 {
		f, _ := strconv.ParseFloat(s, 64)
		return f
	}
	minutes, _ := strconv.ParseFloat(parts[0], 64)
	seconds, _ := strconv.ParseFloat(parts[1], 64)
	return minutes*60 + seconds
}

// --- Dataset Loading ---

// LoadCases loads all BenchCase entries from a JSONL file.
func LoadCases(path string) ([]BenchCase, error) {
	f, err := os.Open(path) // #nosec G304 — path is controlled by benchmark CLI flags
	if err != nil {
		return nil, fmt.Errorf("opening dataset %s: %w", path, err)
	}
	defer f.Close()

	var cases []BenchCase
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 1<<20), 1<<20) // 1 MiB line buffer
	lineNum := 0
	for scanner.Scan() {
		lineNum++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "//") {
			continue
		}
		var bc BenchCase
		if err := json.Unmarshal([]byte(line), &bc); err != nil {
			return nil, fmt.Errorf("line %d in %s: %w", lineNum, path, err)
		}
		cases = append(cases, bc)
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("reading %s: %w", path, err)
	}
	return cases, nil
}

// LoadAllCases walks a directory and loads all *.jsonl files found.
func LoadAllCases(dir string) ([]BenchCase, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("reading directory %s: %w", dir, err)
	}

	var all []BenchCase
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".jsonl") {
			continue
		}
		cases, err := LoadCases(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		all = append(all, cases...)
	}
	return all, nil
}
