package benchmarks

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/config"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

// ────────────────── Role-specific quick-test prompts ──────────────────

type roleTest struct {
	System       string
	Prompt       string
	ExpectedKeys []string            // top-level JSON keys expected
	ExpectedDir  map[string]string   // param → "increase"|"decrease"
}

var roleTests = map[string]roleTest{
	"driving": {
		System: "Eres un ingeniero de conducción de rFactor 2. Responde SOLO en español y en JSON.",
		Prompt: `Analiza esta telemetría de 3 vueltas en Spa:
- Frenadas tardías constantes en La Source (5-8 m después del punto óptimo)
- Subviraje a mitad de curva en Pouhon (pérdida de 0.3s por vuelta)
- Sobreaceleración en salida de Bus Stop (TCS activo 12% del tiempo)

Responde en JSON:
{"driving_analysis": [{"zone": "...", "issue": "...", "recommendation": "...", "priority": "high|medium|low"}], "summary": "..."}`,
		ExpectedKeys: []string{"driving_analysis", "summary"},
	},
	"suspension": {
		System: "Eres un ingeniero de suspensión de rFactor 2. Responde SOLO en español y en JSON.",
		Prompt: `Setup actual de suspensión:
- Muelles delanteros: 120 N/mm, traseros: 95 N/mm
- Amortiguadores bump delantero: 4500 N·s/m, trasero: 3800 N·s/m
- Amortiguadores rebound delantero: 8500 N·s/m, trasero: 7200 N·s/m
- Barra anti-roll delantera: 35 kN/m, trasera: 25 kN/m

Problema: sobreviraje bajo frenada fuerte y subviraje en curvas lentas.

Propón cambios en JSON:
{"sections": [{"section": "SUSPENSION", "items": [{"parameter": "...", "new_value": "...", "reason": "..."}]}], "findings_summary": "...", "confidence": 0.8}`,
		ExpectedKeys: []string{"sections", "findings_summary"},
		ExpectedDir: map[string]string{
			"Front Spring Rate": "decrease",
			"Rear Spring Rate":  "increase",
		},
	},
	"chassis": {
		System: "Eres un ingeniero de chasis de rFactor 2. Responde SOLO en español y en JSON.",
		Prompt: `Setup actual de chasis:
- Distribución de frenada: 56% delantero
- Presión neumáticos: FL 172 kPa, FR 172 kPa, RL 165 kPa, RR 165 kPa
- Camber delantero: -3.2°, trasero: -2.8°
- Toe delantero: -0.10°, trasero: 0.05°

Problema: inestabilidad en frenada y desgaste irregular de neumáticos delanteros exteriores.

Propón cambios en JSON:
{"sections": [{"section": "CHASSIS", "items": [{"parameter": "...", "new_value": "...", "reason": "..."}]}], "findings_summary": "...", "confidence": 0.8}`,
		ExpectedKeys: []string{"sections", "findings_summary"},
		ExpectedDir: map[string]string{
			"Brake Pressure Distribution": "decrease",
			"Front Camber":                "increase",
		},
	},
	"aero": {
		System: "Eres un ingeniero aerodinámico de rFactor 2. Responde SOLO en español y en JSON.",
		Prompt: `Setup aerodinámico actual:
- Ala delantera: 22 clicks
- Ala trasera: 28 clicks
- Ride height delantero: 25 mm, trasero: 55 mm

Problema: subviraje a alta velocidad en Blanchimont y Eau Rouge, el coche se siente inestable aerodimámicamente por encima de 250 km/h.

Propón cambios en JSON:
{"sections": [{"section": "AERO", "items": [{"parameter": "...", "new_value": "...", "reason": "..."}]}], "findings_summary": "...", "confidence": 0.8}`,
		ExpectedKeys: []string{"sections", "findings_summary"},
		ExpectedDir: map[string]string{
			"Front Wing": "increase",
			"Rear Wing":  "increase",
		},
	},
	"powertrain": {
		System: "Eres un ingeniero de tren motriz de rFactor 2. Responde SOLO en español y en JSON.",
		Prompt: `Setup de tren motriz actual:
- Potencia diferencial: 45%
- Freno motor: 30%
- Relaciones de marcha: 1ª 3.15, 2ª 2.38, 3ª 1.87, 4ª 1.50, 5ª 1.23, 6ª 1.05
- Final drive: 3.70

Problema: pérdida de tracción al salir de curvas lentas, sobreviraje por exceso de par en salida.

Propón cambios en JSON:
{"sections": [{"section": "POWERTRAIN", "items": [{"parameter": "...", "new_value": "...", "reason": "..."}]}], "findings_summary": "...", "confidence": 0.8}`,
		ExpectedKeys: []string{"sections", "findings_summary"},
		ExpectedDir: map[string]string{
			"Differential Power":  "decrease",
			"Engine Braking":      "increase",
		},
	},
	"chief": {
		System: "Eres el ingeniero jefe de rFactor 2. Integras informes de especialistas. Responde SOLO en español y en JSON.",
		Prompt: `Informes de ingenieros de dominio:

SUSPENSIÓN: Reducir muelles delanteros de 120 a 110 N/mm para mejorar agarre mecánico. Aumentar rebound trasero de 7200 a 7800 N·s/m.
CHASIS: Reducir brake bias de 56% a 54%. Ajustar camber delantero de -3.2° a -3.0°.
AERO: Aumentar ala delantera de 22 a 24 clicks. Mantener ala trasera.
TREN MOTRIZ: Reducir power differential de 45% a 40%.

CONTRADICCIONES: El ingeniero de suspensión propone muelles más blandos (menos carga aerodinámica efectiva) mientras el aerodinámico quiere más downforce.

Integra las propuestas, resuelve contradicciones, y genera la recomendación final en JSON:
{"setup_changes": [{"parameter": "...", "new_value": "...", "reason": "..."}], "chief_summary": "...", "conflict_resolutions": ["..."]}`,
		ExpectedKeys: []string{"setup_changes", "chief_summary"},
	},
}

// ────────────────── Quick evaluation (no LLM judge) ──────────────────

// ModelRoleScore captures the benchmark result for one model on one role.
type ModelRoleScore struct {
	Model          string  `json:"model"`
	Role           string  `json:"role"`
	JSONValid      bool    `json:"json_valid"`
	StructureScore float64 `json:"structure_score"` // 0-1
	SpanishScore   float64 `json:"spanish_score"`   // 0-1
	DirectionScore float64 `json:"direction_score"` // 0-1
	Elapsed        float64 `json:"elapsed_seconds"`
	WeightedScore  float64 `json:"weighted_score"`  // 0-10
	Error          string  `json:"error,omitempty"`
}

// evaluateResponse scores a model's response for a given role without using an LLM judge.
func evaluateResponse(response string, test roleTest, elapsed float64) ModelRoleScore {
	score := ModelRoleScore{Elapsed: elapsed}

	// 1. JSON validity (30%)
	jsonStr := extractJSONFromResponse(response)
	if jsonStr == "" {
		score.WeightedScore = 0
		return score
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal([]byte(jsonStr), &parsed); err != nil {
		score.WeightedScore = 0
		return score
	}
	score.JSONValid = true

	// 2. Structure: expected keys present (25%)
	if len(test.ExpectedKeys) > 0 {
		found := 0
		for _, k := range test.ExpectedKeys {
			if _, ok := parsed[k]; ok {
				found++
			}
		}
		score.StructureScore = float64(found) / float64(len(test.ExpectedKeys))
	} else {
		score.StructureScore = 1.0 // no expectation → pass
	}

	// 3. Spanish quality (15%) — check for common English leaks
	score.SpanishScore = spanishScore(response)

	// 4. Direction correctness (15%)
	if len(test.ExpectedDir) > 0 {
		score.DirectionScore = directionScore(response, test.ExpectedDir)
	} else {
		score.DirectionScore = 1.0
	}

	// 5. Speed bonus (15%) — faster responses score higher, capped at 60s
	speedScore := 1.0
	if elapsed > 60 {
		speedScore = 0.0
	} else if elapsed > 30 {
		speedScore = 1.0 - (elapsed-30)/30.0
	}

	// Weighted average → 0-10 scale
	score.WeightedScore = 10.0 * (
		0.30*boolToFloat(score.JSONValid) +
			0.25*score.StructureScore +
			0.15*score.SpanishScore +
			0.15*score.DirectionScore +
			0.15*speedScore)

	return score
}

func boolToFloat(b bool) float64 {
	if b {
		return 1.0
	}
	return 0.0
}

var englishLeakWords = regexp.MustCompile(`(?i)\b(the|and|because|should|increase|decrease|however|therefore|recommend|adjustment|spring rate|damper|wing angle)\b`)

func spanishScore(text string) float64 {
	matches := englishLeakWords.FindAllString(text, -1)
	words := len(strings.Fields(text))
	if words == 0 {
		return 0
	}
	ratio := float64(len(matches)) / float64(words)
	// 0 leaks → 1.0, ≥5% leaks → 0
	return math.Max(0, 1.0-ratio*20)
}

func directionScore(response string, expected map[string]string) float64 {
	lower := strings.ToLower(response)
	correct := 0
	total := len(expected)
	for param, dir := range expected {
		paramLower := strings.ToLower(param)
		// Look for the parameter mention and a directional word nearby
		idx := strings.Index(lower, paramLower)
		if idx == -1 {
			continue // parameter not mentioned — neutral
		}
		// Check context around the parameter mention (±200 chars)
		start := idx - 200
		if start < 0 {
			start = 0
		}
		end := idx + 200
		if end > len(lower) {
			end = len(lower)
		}
		context := lower[start:end]

		if dir == "increase" {
			if strings.Contains(context, "aumentar") || strings.Contains(context, "incrementar") ||
				strings.Contains(context, "subir") || strings.Contains(context, "más") ||
				strings.Contains(context, "increase") {
				correct++
			}
		} else if dir == "decrease" {
			if strings.Contains(context, "reducir") || strings.Contains(context, "disminuir") ||
				strings.Contains(context, "bajar") || strings.Contains(context, "menos") ||
				strings.Contains(context, "decrease") {
				correct++
			}
		}
	}
	if total == 0 {
		return 1.0
	}
	return float64(correct) / float64(total)
}

// ────────────────── Auto-select orchestrator ──────────────────

// AutoSelectProgress is sent via SSE during the benchmark.
type AutoSelectProgress struct {
	Event string      `json:"event"`
	Data  interface{} `json:"data"`
}

// AutoSelectResult is the final output of the auto-selection process.
type AutoSelectResult struct {
	Assignments map[string]config.ModelAssignment `json:"assignments"`
	Details     []ModelRoleScore                  `json:"details"`
	Elapsed     float64                           `json:"elapsed_seconds"`
}

// AutoSelectModels runs the benchmark and selects the best model for each role.
func AutoSelectModels(
	ctx context.Context,
	baseURL, apiKey string,
	maxCandidates int,
	progress func(AutoSelectProgress),
) (*AutoSelectResult, error) {
	if maxCandidates <= 0 {
		maxCandidates = 5
	}

	start := time.Now()

	// 1. List available models
	tmpClient := ollama.NewClient(baseURL, "", apiKey)
	models, err := tmpClient.ListModels(ctx)
	if err != nil {
		return nil, fmt.Errorf("listing models: %w", err)
	}
	if len(models) == 0 {
		return nil, fmt.Errorf("no models available on %s", baseURL)
	}

	// 2. Sort by size descending (larger models tend to perform better)
	sort.Slice(models, func(i, j int) bool {
		return models[i].Size > models[j].Size
	})

	// 3. Filter: skip embedding/vision-only models by name heuristics
	var candidates []ollama.ModelInfo
	for _, m := range models {
		name := strings.ToLower(m.Name)
		if strings.Contains(name, "embed") || strings.Contains(name, "nomic") ||
			strings.Contains(name, "all-minilm") || strings.Contains(name, "bge-") {
			continue
		}
		candidates = append(candidates, m)
		if len(candidates) >= maxCandidates {
			break
		}
	}
	if len(candidates) == 0 {
		return nil, fmt.Errorf("no suitable candidate models found")
	}

	roles := []string{"driving", "suspension", "chassis", "aero", "powertrain", "chief"}
	totalTests := len(candidates) * len(roles)

	progress(AutoSelectProgress{
		Event: "benchmark_start",
		Data: map[string]interface{}{
			"total_models": len(candidates),
			"total_roles":  len(roles),
			"total_tests":  totalTests,
			"candidates":   modelNames(candidates),
		},
	})

	// 4. Run tests: for each model, test all roles in parallel
	var allScores []ModelRoleScore
	testsDone := 0

	for _, model := range candidates {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}

		progress(AutoSelectProgress{
			Event: "model_start",
			Data:  map[string]string{"model": model.Name},
		})

		// Run 6 role tests concurrently for this model
		var mu sync.Mutex
		var wg sync.WaitGroup
		roleScores := make([]ModelRoleScore, len(roles))

		for i, role := range roles {
			wg.Add(1)
			go func(idx int, role string) {
				defer wg.Done()

				test := roleTests[role]
				client := ollama.NewClient(baseURL, model.Name, apiKey)
				client.NumPredict = 2048 // shorter for benchmark
				client.HTTPClient = tmpClient.HTTPClient

				testStart := time.Now()
				response, err := client.Generate(ctx, test.Prompt, test.System)
				elapsed := time.Since(testStart).Seconds()

				var s ModelRoleScore
				if err != nil {
					s = ModelRoleScore{
						Model:   model.Name,
						Role:    role,
						Elapsed: elapsed,
						Error:   err.Error(),
					}
				} else {
					s = evaluateResponse(response, test, elapsed)
					s.Model = model.Name
					s.Role = role
				}

				mu.Lock()
				roleScores[idx] = s
				testsDone++
				mu.Unlock()

				progress(AutoSelectProgress{
					Event: "test_complete",
					Data: map[string]interface{}{
						"model":    model.Name,
						"role":     role,
						"score":    s.WeightedScore,
						"elapsed":  s.Elapsed,
						"done":     testsDone,
						"total":    totalTests,
						"progress": float64(testsDone) / float64(totalTests) * 100,
					},
				})
			}(i, role)
		}

		wg.Wait()
		allScores = append(allScores, roleScores...)

		progress(AutoSelectProgress{
			Event: "model_complete",
			Data:  map[string]string{"model": model.Name},
		})
	}

	// 5. For each role, pick the model with the highest weighted score
	assignments := make(map[string]config.ModelAssignment)
	for _, role := range roles {
		var bestScore float64
		var bestModel string
		var bestTemp float64

		for _, s := range allScores {
			if s.Role == role && s.WeightedScore > bestScore {
				bestScore = s.WeightedScore
				bestModel = s.Model
			}
		}

		// Use the default temperature from existing routing for this role
		switch role {
		case "driving":
			bestTemp = 0.4
		case "chief":
			bestTemp = 0.3
		default:
			bestTemp = 0.2
		}

		assignments[role] = config.ModelAssignment{
			Model:       bestModel,
			Temperature: bestTemp,
		}

		progress(AutoSelectProgress{
			Event: "role_selected",
			Data: map[string]interface{}{
				"role":  role,
				"model": bestModel,
				"score": bestScore,
				"temp":  bestTemp,
			},
		})

		log.Info().
			Str("role", role).
			Str("model", bestModel).
			Float64("score", bestScore).
			Msg("benchmark: best model selected for role")
	}

	totalElapsed := time.Since(start).Seconds()

	result := &AutoSelectResult{
		Assignments: assignments,
		Details:     allScores,
		Elapsed:     totalElapsed,
	}

	progress(AutoSelectProgress{
		Event: "benchmark_complete",
		Data: map[string]interface{}{
			"assignments": assignments,
			"elapsed":     totalElapsed,
		},
	})

	return result, nil
}

func modelNames(models []ollama.ModelInfo) []string {
	names := make([]string, len(models))
	for i, m := range models {
		names[i] = m.Name
	}
	return names
}
