package benchmark

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/viciruela/rfactor2-engineer/internal/agents"
)

// Runner orchestrates benchmark execution against the production pipeline.
type Runner struct {
	Pipeline *agents.Pipeline
	Judge    *Judge
	// FilterRole restricts execution to a specific agent role (empty = all).
	FilterRole string
	// FilterDifficulty restricts execution to a specific difficulty (empty = all).
	FilterDifficulty string
}

// Run executes all provided cases and returns their results.
func (r *Runner) Run(ctx context.Context, cases []BenchCase) []BenchResult {
	results := make([]BenchResult, 0, len(cases))
	for _, bc := range cases {
		if r.FilterRole != "" && bc.AgentRole != r.FilterRole {
			continue
		}
		if r.FilterDifficulty != "" && bc.Difficulty != r.FilterDifficulty {
			continue
		}
		result := r.runCase(ctx, bc)
		results = append(results, result)
	}
	return results
}

func (r *Runner) runCase(ctx context.Context, bc BenchCase) BenchResult {
	res := BenchResult{
		CaseID:     bc.ID,
		Scenario:   bc.Scenario,
		AgentRole:  bc.AgentRole,
		Difficulty: bc.Difficulty,
	}

	stats := bc.SessionStats.ToDomainSessionStats()
	setup := bc.SetupContext.ToDomainSetup()

	var rawOutput string
	var runErr error

	switch bc.AgentRole {
	case "suspension", "chassis", "aero", "powertrain":
		sections, summary, err := r.Pipeline.RunDomainEngineer(ctx, bc.AgentRole, bc.TelemetrySummary, stats, setup, nil)
		if err != nil {
			runErr = err
		} else {
			out := map[string]interface{}{
				"sections":         sections,
				"findings_summary": summary,
			}
			b, _ := json.Marshal(out)
			rawOutput = string(b)
		}

	case "driving":
		analysis, err := r.Pipeline.RunDrivingAgentBench(ctx, bc.TelemetrySummary, stats)
		if err != nil {
			runErr = err
		} else {
			rawOutput = analysis
		}

	default:
		runErr = fmt.Errorf("unsupported agent role for benchmarking: %q", bc.AgentRole)
	}

	if runErr != nil {
		res.Error = runErr.Error()
		return res
	}

	res.AgentOutput = rawOutput

	if r.Judge != nil {
		score, err := r.Judge.Evaluate(ctx, bc, rawOutput)
		if err != nil {
			res.Error = fmt.Sprintf("judge error: %v", err)
		} else {
			res.JudgeScore = score
		}
	}

	return res
}
