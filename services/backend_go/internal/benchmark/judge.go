package benchmark

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const defaultJudgeModel = "gpt-4o"

// Judge calls an external OpenAI-compatible LLM to score agent responses.
type Judge struct {
	APIKey   string
	BaseURL  string // default: https://api.openai.com/v1
	Model    string // default: gpt-4o
	RubricMD string // full text of judge_rubric.md, injected into system prompt

	httpClient *http.Client
}

// NewJudge creates a Judge configured for the OpenAI API.
func NewJudge(apiKey, baseURL, model, rubricMD string) *Judge {
	if baseURL == "" {
		baseURL = "https://api.openai.com/v1"
	}
	if model == "" {
		model = defaultJudgeModel
	}
	return &Judge{
		APIKey:   apiKey,
		BaseURL:  baseURL,
		Model:    model,
		RubricMD: rubricMD,
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

// Evaluate scores a BenchCase given the agent's raw output string.
func (j *Judge) Evaluate(ctx context.Context, bc BenchCase, agentOutput string) (*JudgeScore, error) {
	prompt := j.buildPrompt(bc, agentOutput)
	raw, err := j.callLLM(ctx, prompt)
	if err != nil {
		return nil, err
	}
	return parseJudgeResponse(raw)
}

func (j *Judge) buildPrompt(bc BenchCase, agentOutput string) string {
	expectedJSON, _ := json.MarshalIndent(bc.Expected, "", "  ")
	setupJSON, _ := json.MarshalIndent(bc.SetupContext, "", "  ")

	var sb strings.Builder
	sb.WriteString("Eres un experto en ingeniería de automovilismo y evaluador de sistemas LLM para análisis de telemetría de sim-racing (rFactor2).\n\n")
	sb.WriteString("Tu tarea: evaluar la respuesta de un Agente Domain Engineer según la rúbrica rF2-Bench.\n\n")
	if j.RubricMD != "" {
		sb.WriteString("--- RÚBRICA ---\n")
		sb.WriteString(j.RubricMD)
		sb.WriteString("\n\n")
	}
	sb.WriteString("--- ESCENARIO ---\n")
	sb.WriteString(fmt.Sprintf("ID: %s | Escenario: %s | Rol: %s | Dificultad: %s\n\n", bc.ID, bc.Scenario, bc.AgentRole, bc.Difficulty))
	sb.WriteString("--- TELEMETRÍA ENTREGADA AL AGENTE ---\n")
	sb.WriteString(bc.TelemetrySummary)
	sb.WriteString("\n\n--- SETUP CONTEXT ---\n")
	sb.WriteString(string(setupJSON))
	sb.WriteString("\n\n--- RESPUESTA DEL AGENTE ---\n")
	sb.WriteString(agentOutput)
	sb.WriteString("\n\n--- EXPECTED (referencia) ---\n")
	sb.WriteString(string(expectedJSON))
	sb.WriteString("\n\n--- INSTRUCCIONES ---\n")
	sb.WriteString("Evalúa la respuesta en 5 dimensiones de 0 a 10. Aplica penalizaciones automáticas donde corresponda.\n")
	sb.WriteString("Devuelve SOLO el siguiente JSON (sin markdown, sin texto extra):\n\n")
	sb.WriteString(`{
  "scores": {
    "physics_accuracy": <0-10>,
    "json_schema": <0-10>,
    "spanish_quality": <0-10>,
    "coherence_logic": <0-10>,
    "actionability": <0-10>
  },
  "penalties": [
    {"type": "physical_inversion|invented_value|self_contradiction|must_not_contain|must_mention", "detail": "...", "deduction": <float>}
  ],
  "weighted_score": <float>,
  "pass": <true|false>,
  "summary": "<1-2 frases en español>"
}`)
	return sb.String()
}

// openAIRequest is the request body for the OpenAI chat completions API.
type openAIRequest struct {
	Model    string              `json:"model"`
	Messages []openAIMessage     `json:"messages"`
	Temp     float64             `json:"temperature"`
}

type openAIMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type openAIResponse struct {
	Choices []struct {
		Message openAIMessage `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

func (j *Judge) callLLM(ctx context.Context, prompt string) (string, error) {
	reqBody := openAIRequest{
		Model: j.Model,
		Messages: []openAIMessage{
			{Role: "user", Content: prompt},
		},
		Temp: 0.1,
	}
	b, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("marshaling judge request: %w", err)
	}

	url := strings.TrimRight(j.BaseURL, "/") + "/chat/completions"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(b))
	if err != nil {
		return "", fmt.Errorf("creating judge HTTP request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+j.APIKey)

	resp, err := j.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("judge HTTP call: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("judge API returned %d: %s", resp.StatusCode, body)
	}

	var oaResp openAIResponse
	if err := json.Unmarshal(body, &oaResp); err != nil {
		return "", fmt.Errorf("parsing judge response: %w", err)
	}
	if oaResp.Error != nil {
		return "", fmt.Errorf("judge API error: %s", oaResp.Error.Message)
	}
	if len(oaResp.Choices) == 0 {
		return "", fmt.Errorf("judge returned no choices")
	}
	return oaResp.Choices[0].Message.Content, nil
}

func parseJudgeResponse(raw string) (*JudgeScore, error) {
	// Strip markdown code fences if present
	clean := strings.TrimSpace(raw)
	if strings.HasPrefix(clean, "```") {
		lines := strings.Split(clean, "\n")
		if len(lines) >= 2 {
			// drop first and last fence lines
			clean = strings.Join(lines[1:len(lines)-1], "\n")
			if strings.HasPrefix(clean, "```") {
				clean = strings.Join(strings.Split(clean, "\n")[1:], "\n")
			}
		}
	}
	// Find JSON object boundaries
	start := strings.IndexByte(clean, '{')
	end := strings.LastIndexByte(clean, '}')
	if start == -1 || end == -1 || end <= start {
		return nil, fmt.Errorf("no JSON object found in judge response: %.200s", raw)
	}
	clean = clean[start : end+1]

	var score JudgeScore
	if err := json.Unmarshal([]byte(clean), &score); err != nil {
		return nil, fmt.Errorf("parsing judge JSON: %w: %.200s", err, clean)
	}
	return &score, nil
}
