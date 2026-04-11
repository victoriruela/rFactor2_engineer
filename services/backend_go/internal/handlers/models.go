package handlers

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

// ModelsHandler proxies model listing from Ollama.
type ModelsHandler struct {
	Client *ollama.Client
}

// NewModelsHandler creates a models handler.
func NewModelsHandler(client *ollama.Client) *ModelsHandler {
	return &ModelsHandler{Client: client}
}

// ListModels handles GET /api/models
func (h *ModelsHandler) ListModels(c *gin.Context) {
	provider := normalizeProvider(c.Query("provider"))
	if provider != "ollama_cloud" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unsupported provider"})
		return
	}

	baseURL := strings.TrimSpace(c.Query("ollama_base_url"))
	apiKey := strings.TrimSpace(c.Query("ollama_api_key"))
	model := strings.TrimSpace(c.Query("model"))
	if baseURL == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "ollama_base_url is required for provider ollama_cloud"})
		return
	}
	if isLocalOllamaBaseURL(baseURL) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "local ollama endpoints are disabled; configure a cloud ollama_base_url"})
		return
	}

	client := h.Client
	if baseURL != "" || apiKey != "" || model != "" {
		if baseURL == "" && h.Client != nil {
			baseURL = h.Client.BaseURL
		}
		if apiKey == "" && h.Client != nil {
			apiKey = h.Client.APIKey
		}
		if model == "" && h.Client != nil {
			model = h.Client.Model
		}
		client = ollama.NewClient(baseURL, model, apiKey)
	}

	models, err := client.ListModels(c.Request.Context())
	if err != nil {
		log.Warn().Err(err).Msg("failed to list Ollama models")
		c.JSON(http.StatusOK, gin.H{"models": []any{}})
		return
	}

	c.JSON(http.StatusOK, gin.H{"models": models})
}

// HealthCheck handles GET /api/health
func (h *ModelsHandler) HealthCheck(c *gin.Context) {
	err := h.Client.HealthCheck(c.Request.Context())
	status := "ok"
	ollamaOK := true
	if err != nil {
		status = "degraded"
		ollamaOK = false
	}

	c.JSON(http.StatusOK, gin.H{
		"status": status,
		"ollama": ollamaOK,
	})
}
