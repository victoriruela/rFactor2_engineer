package ollama

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os/exec"
	"runtime"
	"time"

	"github.com/rs/zerolog/log"
)

const (
	DefaultBaseURL   = "http://localhost:11434"
	DefaultModel     = "llama3.2:latest"
	DefaultNumPredict = 4096
	DefaultTemp      = 0.3
	StartupRetries   = 15
	StartupDelay     = 1 * time.Second
)

// Client communicates with the Ollama REST API.
type Client struct {
	BaseURL    string
	APIKey     string
	Model      string
	NumPredict int
	Temp       float64
	HTTPClient *http.Client
}

// NewClient creates an Ollama client with the given options.
func NewClient(baseURL, model, apiKey string) *Client {
	if baseURL == "" {
		baseURL = DefaultBaseURL
	}
	if model == "" {
		model = DefaultModel
	}
	return &Client{
		BaseURL:    baseURL,
		APIKey:     apiKey,
		Model:      model,
		NumPredict: DefaultNumPredict,
		Temp:       DefaultTemp,
		HTTPClient: &http.Client{Timeout: 10 * time.Minute},
	}
}

// GenerateRequest is the body for POST /api/generate.
type GenerateRequest struct {
	Model   string            `json:"model"`
	Prompt  string            `json:"prompt"`
	System  string            `json:"system,omitempty"`
	Stream  bool              `json:"stream"`
	Options map[string]any    `json:"options,omitempty"`
}

// GenerateResponse is the Ollama generate response.
type GenerateResponse struct {
	Model    string `json:"model"`
	Response string `json:"response"`
	Done     bool   `json:"done"`
}

// ModelInfo represents an Ollama model entry.
type ModelInfo struct {
	Name       string `json:"name"`
	ModifiedAt string `json:"modified_at"`
	Size       int64  `json:"size"`
}

// TagsResponse is the response from GET /api/tags.
type TagsResponse struct {
	Models []ModelInfo `json:"models"`
}

// Generate calls the Ollama /api/generate endpoint (non-streaming).
func (c *Client) Generate(ctx context.Context, prompt, system string) (string, error) {
	req := GenerateRequest{
		Model:  c.Model,
		Prompt: prompt,
		System: system,
		Stream: false,
		Options: map[string]any{
			"num_predict": c.NumPredict,
			"temperature": c.Temp,
		},
	}

	body, err := json.Marshal(req)
	if err != nil {
		return "", fmt.Errorf("marshaling request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", c.BaseURL+"/api/generate", bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("creating request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("calling ollama: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("ollama returned %d: %s", resp.StatusCode, string(respBody))
	}

	var result GenerateResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("decoding response: %w", err)
	}

	return result.Response, nil
}

// ListModels calls GET /api/tags to list available models.
func (c *Client) ListModels(ctx context.Context) ([]ModelInfo, error) {
	httpReq, err := http.NewRequestWithContext(ctx, "GET", c.BaseURL+"/api/tags", nil)
	if err != nil {
		return nil, err
	}
	if c.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("listing models: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("ollama returned %d", resp.StatusCode)
	}

	var tags TagsResponse
	if err := json.NewDecoder(resp.Body).Decode(&tags); err != nil {
		return nil, err
	}

	return tags.Models, nil
}

// HealthCheck pings Ollama to verify it's running.
func (c *Client) HealthCheck(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(ctx, "GET", c.BaseURL+"/api/tags", nil)
	if err != nil {
		return err
	}
	if c.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return err
	}
	resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("ollama returned status %d", resp.StatusCode)
	}
	return nil
}

// EnsureRunning checks if Ollama is running and starts it if needed.
// Skipped for remote/cloud URLs (non-localhost).
func (c *Client) EnsureRunning(ctx context.Context) error {
	if c.BaseURL != DefaultBaseURL && c.BaseURL != "http://127.0.0.1:11434" {
		return nil // Remote Ollama, don't try to start
	}

	if err := c.HealthCheck(ctx); err == nil {
		return nil // Already running
	}

	log.Info().Msg("Ollama not running, attempting to start...")

	cmd := "ollama"
	if runtime.GOOS == "windows" {
		cmd = "ollama.exe"
	}

	process := exec.Command(cmd, "serve")
	if err := process.Start(); err != nil {
		return fmt.Errorf("starting ollama: %w", err)
	}

	// Wait for it to become healthy
	for i := 0; i < StartupRetries; i++ {
		time.Sleep(StartupDelay)
		if err := c.HealthCheck(ctx); err == nil {
			log.Info().Msg("Ollama started successfully")
			return nil
		}
	}

	return fmt.Errorf("ollama did not start within %d seconds", StartupRetries)
}
