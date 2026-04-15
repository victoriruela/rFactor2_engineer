package benchmarks

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

// JudgePromptTemplate is the system prompt for the LLM-as-a-Judge evaluator.
const JudgePromptTemplate = `Eres un evaluador experto en ingeniería de vehículos de simulación.
Evalúa la siguiente respuesta de un ingeniero de setup de rFactor 2.

Caso de prueba: %s
Rol evaluado: %s

Respuesta del modelo:
%s

Criterios esperados:
- Direcciones de cambio esperadas: %s
- Palabras clave esperadas: %s

Puntúa de 0 a 10 en cada dimensión:
1. physics_correctness: ¿Las recomendaciones son físicamente correctas?
2. parameter_direction: ¿Los cambios van en la dirección correcta?
3. consistency: ¿No hay contradicciones internas?
4. spanish_quality: ¿El español es correcto sin fugas de inglés?
5. completeness: ¿Aborda todas las áreas relevantes del setup?

Responde SOLO en JSON:
{"physics_correctness": X, "parameter_direction": X, "consistency": X, "spanish_quality": X, "completeness": X}`

// EvaluateWithJudge uses a judge model to score a benchmark run's response.
func EvaluateWithJudge(ctx context.Context, judgeClient *ollama.Client, judgeModel string, tc BenchmarkCase, run *BenchmarkRun) error {
	dirJSON, _ := json.Marshal(tc.ExpectedDirection)
	kwJSON, _ := json.Marshal(tc.ExpectedKeywords)

	prompt := fmt.Sprintf(JudgePromptTemplate,
		tc.Description, tc.Role, run.Response,
		string(dirJSON), string(kwJSON))

	response, err := judgeClient.GenerateWithModel(ctx, prompt, "", judgeModel, 0.1)
	if err != nil {
		return fmt.Errorf("judge evaluation failed: %w", err)
	}

	// Extract JSON from judge response
	jsonStr := extractJSONFromResponse(response)
	if jsonStr == "" {
		return fmt.Errorf("judge returned no valid JSON")
	}

	var score JudgeScore
	if err := json.Unmarshal([]byte(jsonStr), &score); err != nil {
		return fmt.Errorf("parsing judge score: %w", err)
	}

	run.Score = score
	return nil
}

// extractJSONFromResponse finds the first JSON object in a response string.
func extractJSONFromResponse(s string) string {
	start := strings.Index(s, "{")
	if start == -1 {
		return ""
	}
	depth := 0
	for i := start; i < len(s); i++ {
		switch s[i] {
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				return s[start : i+1]
			}
		}
	}
	return ""
}
