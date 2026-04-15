package benchmarks

// BenchmarkCase represents a single golden test case for evaluating model quality.
type BenchmarkCase struct {
	ID                string                       `json:"id"`
	Role              string                       `json:"role"`
	Description       string                       `json:"description"`
	TelemetrySummary  string                       `json:"telemetry_summary"`
	SessionStats      map[string]interface{}        `json:"session_stats"`
	SetupSections     map[string]map[string]string `json:"setup_sections"`
	ExpectedDirection map[string]string            `json:"expected_direction"` // param → "increase"|"decrease"
	ExpectedKeywords  []string                     `json:"expected_keywords"`
}

// JudgeScore holds the 5-dimension rubric scores from the LLM-as-a-Judge evaluator.
type JudgeScore struct {
	PhysicsCorrectness float64 `json:"physics_correctness"` // 0-10
	ParameterDirection float64 `json:"parameter_direction"` // 0-10
	Consistency        float64 `json:"consistency"`         // 0-10
	SpanishQuality     float64 `json:"spanish_quality"`     // 0-10
	Completeness       float64 `json:"completeness"`        // 0-10
}

// WeightedAverage computes the weighted score across dimensions.
func (s JudgeScore) WeightedAverage() float64 {
	return s.PhysicsCorrectness*0.30 +
		s.ParameterDirection*0.25 +
		s.Consistency*0.15 +
		s.SpanishQuality*0.15 +
		s.Completeness*0.15
}

// PassThreshold is the minimum weighted average to consider a model acceptable.
const PassThreshold = 6.0

// BenchmarkRun captures the result of a single model evaluation against one test case.
type BenchmarkRun struct {
	CaseID   string     `json:"case_id"`
	Model    string     `json:"model"`
	Role     string     `json:"role"`
	RunIndex int        `json:"run_index"` // 1-3 (3 runs per model-role pair)
	Response string     `json:"response"`
	Score    JudgeScore `json:"score"`
	Elapsed  float64    `json:"elapsed_seconds"`
}

// BenchmarkReport summarizes results for a model-role combination.
type BenchmarkReport struct {
	Model      string        `json:"model"`
	Role       string        `json:"role"`
	Runs       int           `json:"runs"`
	AvgScore   float64       `json:"avg_weighted_score"`
	MinScore   float64       `json:"min_weighted_score"`
	MaxScore   float64       `json:"max_weighted_score"`
	Pass       bool          `json:"pass"`
	Details    []BenchmarkRun `json:"details"`
}
