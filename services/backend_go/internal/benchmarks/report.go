package benchmarks

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// GenerateReport aggregates benchmark runs into per-model-role reports.
func GenerateReport(runs []BenchmarkRun) []BenchmarkReport {
	// Group by model+role
	type key struct{ Model, Role string }
	groups := make(map[key][]BenchmarkRun)
	for _, r := range runs {
		k := key{r.Model, r.Role}
		groups[k] = append(groups[k], r)
	}

	var reports []BenchmarkReport
	for k, groupRuns := range groups {
		var total, minS, maxS float64
		minS = 11 // sentinel
		for _, r := range groupRuns {
			w := r.Score.WeightedAverage()
			total += w
			if w < minS {
				minS = w
			}
			if w > maxS {
				maxS = w
			}
		}
		avg := total / float64(len(groupRuns))
		reports = append(reports, BenchmarkReport{
			Model:    k.Model,
			Role:     k.Role,
			Runs:     len(groupRuns),
			AvgScore: avg,
			MinScore: minS,
			MaxScore: maxS,
			Pass:     avg >= PassThreshold,
			Details:  groupRuns,
		})
	}
	return reports
}

// WriteJSONReport writes the benchmark report as JSON to the given path.
func WriteJSONReport(reports []BenchmarkReport, path string) error {
	data, err := json.MarshalIndent(reports, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

// WriteMarkdownReport writes a human-readable markdown summary.
func WriteMarkdownReport(reports []BenchmarkReport, path string) error {
	var sb strings.Builder
	sb.WriteString("# rF2-Bench Results\n\n")
	sb.WriteString("| Model | Role | Runs | Avg Score | Min | Max | Pass |\n")
	sb.WriteString("|-------|------|------|-----------|-----|-----|------|\n")

	for _, r := range reports {
		pass := "FAIL"
		if r.Pass {
			pass = "PASS"
		}
		sb.WriteString(fmt.Sprintf("| %s | %s | %d | %.2f | %.2f | %.2f | %s |\n",
			r.Model, r.Role, r.Runs, r.AvgScore, r.MinScore, r.MaxScore, pass))
	}

	sb.WriteString(fmt.Sprintf("\nPass threshold: %.1f\n", PassThreshold))
	return os.WriteFile(path, []byte(sb.String()), 0o644)
}
