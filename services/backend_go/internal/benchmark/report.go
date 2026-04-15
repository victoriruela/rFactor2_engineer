package benchmark

import (
	"fmt"
	"io"
	"sort"
	"strings"
	"time"
)

// GenerateReport writes a Markdown benchmark report to w.
func GenerateReport(w io.Writer, results []BenchResult, runAt time.Time) error {
	pass, fail, skipped := countResults(results)
	total := len(results)

	lines := []string{
		"# rF2-Bench — Benchmark Report",
		"",
		fmt.Sprintf("**Run at**: %s", runAt.UTC().Format("2006-01-02 15:04:05 UTC")),
		fmt.Sprintf("**Total cases**: %d | **Pass**: %d | **Fail**: %d | **Error/Skip**: %d", total, pass, fail, skipped),
		"",
	}

	// Overall pass rate
	if total > 0 {
		pct := float64(pass) / float64(total) * 100
		lines = append(lines, fmt.Sprintf("**Overall pass rate**: %.1f%%", pct))
		lines = append(lines, "")
	}

	// Summary table by scenario
	lines = append(lines, "## Summary by Scenario", "")
	lines = append(lines, "| Scenario | Role | Difficulty | Score | Pass | Notes |")
	lines = append(lines, "|----------|------|------------|-------|------|-------|")

	// Sort by scenario then case ID
	sorted := make([]BenchResult, len(results))
	copy(sorted, results)
	sort.Slice(sorted, func(i, j int) bool {
		if sorted[i].Scenario != sorted[j].Scenario {
			return sorted[i].Scenario < sorted[j].Scenario
		}
		return sorted[i].CaseID < sorted[j].CaseID
	})

	for _, r := range sorted {
		score := "—"
		pass := "—"
		notes := ""
		if r.Error != "" {
			score = "ERR"
			pass = "❌"
			notes = truncate(r.Error, 60)
		} else if r.JudgeScore != nil {
			score = fmt.Sprintf("%.2f", r.JudgeScore.WeightedScore)
			if r.JudgeScore.Pass {
				pass = "✅"
			} else {
				pass = "❌"
			}
			notes = truncate(r.JudgeScore.Summary, 80)
		}
		lines = append(lines, fmt.Sprintf("| %s | %s | %s | %s | %s | %s |",
			r.CaseID, r.AgentRole, r.Difficulty, score, pass, notes))
	}
	lines = append(lines, "")

	// Per-role statistics
	lines = append(lines, "## Statistics by Role", "")
	roleStats := computeRoleStats(results)
	lines = append(lines, "| Role | Cases | Avg Score | Pass Rate |")
	lines = append(lines, "|------|-------|-----------|-----------|")
	for _, role := range sortedKeys(roleStats) {
		st := roleStats[role]
		lines = append(lines, fmt.Sprintf("| %s | %d | %.2f | %.0f%% |",
			role, st.Count, st.AvgScore, st.PassRate*100))
	}
	lines = append(lines, "")

	// Detailed results
	lines = append(lines, "## Detailed Results", "")
	for _, r := range sorted {
		lines = append(lines, fmt.Sprintf("### %s — %s (%s)", r.CaseID, r.Scenario, r.Difficulty))
		lines = append(lines, fmt.Sprintf("**Role**: `%s`", r.AgentRole))
		if r.Error != "" {
			lines = append(lines, fmt.Sprintf("**Error**: %s", r.Error))
			lines = append(lines, "")
			continue
		}
		if r.JudgeScore == nil {
			lines = append(lines, "_No judge score (judge disabled)_", "")
			continue
		}
		s := r.JudgeScore
		lines = append(lines, fmt.Sprintf("**Weighted score**: %.2f | **Pass**: %v", s.WeightedScore, s.Pass))
		lines = append(lines, "")
		lines = append(lines, "| Dimension | Score |")
		lines = append(lines, "|-----------|-------|")
		lines = append(lines, fmt.Sprintf("| Physics Accuracy (25%%) | %.1f |", s.Scores.PhysicsAccuracy))
		lines = append(lines, fmt.Sprintf("| JSON Schema (20%%) | %.1f |", s.Scores.JSONSchema))
		lines = append(lines, fmt.Sprintf("| Spanish Quality (15%%) | %.1f |", s.Scores.SpanishQuality))
		lines = append(lines, fmt.Sprintf("| Coherence & Logic (25%%) | %.1f |", s.Scores.CoherenceLogic))
		lines = append(lines, fmt.Sprintf("| Actionability (15%%) | %.1f |", s.Scores.Actionability))
		if len(s.Penalties) > 0 {
			lines = append(lines, "")
			lines = append(lines, "**Penalties**:")
			for _, p := range s.Penalties {
				lines = append(lines, fmt.Sprintf("- `%s` (−%.1f): %s", p.Type, p.Deduction, p.Detail))
			}
		}
		lines = append(lines, "")
		lines = append(lines, fmt.Sprintf("**Judge summary**: %s", s.Summary))
		lines = append(lines, "")
	}

	_, err := fmt.Fprintln(w, strings.Join(lines, "\n"))
	return err
}

type roleStatEntry struct {
	Count    int
	Total    float64
	PassCnt  int
	AvgScore float64
	PassRate float64
}

func computeRoleStats(results []BenchResult) map[string]*roleStatEntry {
	m := make(map[string]*roleStatEntry)
	for _, r := range results {
		if r.Error != "" || r.JudgeScore == nil {
			continue
		}
		if _, ok := m[r.AgentRole]; !ok {
			m[r.AgentRole] = &roleStatEntry{}
		}
		st := m[r.AgentRole]
		st.Count++
		st.Total += r.JudgeScore.WeightedScore
		if r.JudgeScore.Pass {
			st.PassCnt++
		}
	}
	for _, st := range m {
		if st.Count > 0 {
			st.AvgScore = st.Total / float64(st.Count)
			st.PassRate = float64(st.PassCnt) / float64(st.Count)
		}
	}
	return m
}

func countResults(results []BenchResult) (pass, fail, skipped int) {
	for _, r := range results {
		if r.Error != "" {
			skipped++
		} else if r.JudgeScore == nil {
			skipped++
		} else if r.JudgeScore.Pass {
			pass++
		} else {
			fail++
		}
	}
	return
}

func sortedKeys(m map[string]*roleStatEntry) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func truncate(s string, n int) string {
	s = strings.ReplaceAll(s, "\n", " ")
	if len(s) <= n {
		return s
	}
	return s[:n-1] + "…"
}
