// Command rf2bench runs the rF2-Bench golden-dataset evaluation suite.
//
// Usage (from services/backend_go/):
//
//	go run ./cmd/rf2bench [flags]
//
// Flags:
//
//	-dataset     path to JSONL file or directory of JSONL scenario files
//	             (default: benchmarks/golden_dataset/scenarios)
//	-role        filter by agent role: suspension|chassis|aero|powertrain|driving
//	-difficulty  filter by difficulty: easy|medium|hard
//	-output      output report file (default: benchmark_report.md)
//	-judge-key   OpenAI-compatible API key (or BENCH_JUDGE_KEY env var)
//	-judge-url   judge API base URL (default: https://api.openai.com/v1)
//	-judge-model judge model (default: gpt-4o)
//	-no-judge    skip LLM judge — dump raw agent outputs only
//	-datadir     backend data dir with physics_rules.json + knowledge/
//	-ollama-url  Ollama base URL (overrides OLLAMA_BASE_URL)
//	-model       Ollama model override
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/agents"
	"github.com/viciruela/rfactor2-engineer/internal/benchmark"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

func main() {
	dataset := flag.String("dataset", "benchmarks/golden_dataset/scenarios", "Path to JSONL file or directory")
	role := flag.String("role", "", "Filter by agent role")
	difficulty := flag.String("difficulty", "", "Filter by difficulty")
	output := flag.String("output", "benchmark_report.md", "Output report file path")
	judgeKey := flag.String("judge-key", "", "Judge LLM API key (or BENCH_JUDGE_KEY env var)")
	judgeURL := flag.String("judge-url", "https://api.openai.com/v1", "Judge API base URL")
	judgeModel := flag.String("judge-model", "gpt-4o", "Judge LLM model")
	noJudge := flag.Bool("no-judge", false, "Skip judge — run agents only")
	dataDir := flag.String("datadir", "data", "Backend data directory")
	ollamaURL := flag.String("ollama-url", "", "Ollama base URL")
	model := flag.String("model", "", "Ollama model override")
	flag.Parse()

	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})

	apiKey := *judgeKey
	if apiKey == "" {
		apiKey = os.Getenv("BENCH_JUDGE_KEY")
	}

	baseURL := *ollamaURL
	if baseURL == "" {
		baseURL = os.Getenv("OLLAMA_BASE_URL")
	}
	if baseURL == "" {
		baseURL = "http://localhost:11434"
	}
	ollamaAPIKey := os.Getenv("OLLAMA_API_KEY")
	modelName := *model
	if modelName == "" {
		modelName = os.Getenv("OLLAMA_MODEL")
	}
	if modelName == "" {
		modelName = "llama3.2:latest"
	}

	pipeline := agents.NewPipeline(ollama.NewClient(baseURL, modelName, ollamaAPIKey), *dataDir)

	info, err := os.Stat(*dataset)
	if err != nil {
		log.Fatal().Err(err).Str("path", *dataset).Msg("cannot stat dataset path")
	}
	var cases []benchmark.BenchCase
	if info.IsDir() {
		cases, err = benchmark.LoadAllCases(*dataset)
	} else {
		cases, err = benchmark.LoadCases(*dataset)
	}
	if err != nil {
		log.Fatal().Err(err).Msg("failed to load dataset")
	}
	log.Info().Int("cases", len(cases)).Msg("dataset loaded")

	var judge *benchmark.Judge
	if !*noJudge {
		if apiKey == "" {
			log.Warn().Msg("no judge API key — running without judge (use -judge-key or BENCH_JUDGE_KEY)")
		} else {
			rubric := loadRubric(*dataset)
			judge = benchmark.NewJudge(apiKey, *judgeURL, *judgeModel, rubric)
			log.Info().Str("model", *judgeModel).Msg("judge configured")
		}
	}

	runner := &benchmark.Runner{
		Pipeline:         pipeline,
		Judge:            judge,
		FilterRole:       *role,
		FilterDifficulty: *difficulty,
	}

	ctx := context.Background()
	runAt := time.Now()
	log.Info().Msg("running rF2-Bench…")
	results := runner.Run(ctx, cases)

	pass, fail, errCnt := countSummary(results)
	log.Info().Int("pass", pass).Int("fail", fail).Int("error", errCnt).Msg("done")

	outFile, err := os.Create(*output) // #nosec G304
	if err != nil {
		log.Fatal().Err(err).Str("file", *output).Msg("cannot create report")
	}
	defer outFile.Close()

	if err := benchmark.GenerateReport(outFile, results, runAt); err != nil {
		log.Fatal().Err(err).Msg("failed to write report")
	}
	log.Info().Str("report", *output).Msg("report written")

	fmt.Fprintf(os.Stderr, "\nrF2-Bench: %d PASS / %d FAIL / %d ERROR\n", pass, fail, errCnt)
	if fail > 0 || errCnt > 0 {
		os.Exit(1)
	}
}

func countSummary(results []benchmark.BenchResult) (pass, fail, errCnt int) {
	for _, r := range results {
		switch {
		case r.Error != "":
			errCnt++
		case r.JudgeScore == nil:
			pass++ // no-judge mode: agent ran successfully
		case r.JudgeScore.Pass:
			pass++
		default:
			fail++
		}
	}
	return
}

func loadRubric(datasetPath string) string {
	dir := datasetPath
	if info, err := os.Stat(datasetPath); err == nil && !info.IsDir() {
		dir = ".."
	}
	for _, c := range []string{
		dir + "/judge_rubric.md",
		dir + "/../judge_rubric.md",
		"benchmarks/golden_dataset/judge_rubric.md",
	} {
		if b, err := os.ReadFile(c); err == nil { // #nosec G304
			return string(b)
		}
	}
	return ""
}
