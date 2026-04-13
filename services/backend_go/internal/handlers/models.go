package handlers

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/auth"
	"github.com/viciruela/rfactor2-engineer/internal/config"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

// ModelsHandler proxies model listing from Ollama.
type ModelsHandler struct {
	Client  *ollama.Client
	DataDir string
	AuthDB  *auth.DB
}

// NewModelsHandler creates a models handler.
func NewModelsHandler(client *ollama.Client, dataDir string, authDB *auth.DB) *ModelsHandler {
	return &ModelsHandler{Client: client, DataDir: dataDir, AuthDB: authDB}
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
		c.JSON(http.StatusBadGateway, gin.H{"error": "No se pudieron obtener los modelos: " + err.Error()})
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

// GetModelRouting handles GET /api/models/routing — returns per-role model assignments.
func (h *ModelsHandler) GetModelRouting(c *gin.Context) {
	routingPath := h.DataDir + "/model_routing.json"
	routing, err := config.LoadModelRouting(routingPath)
	if err != nil || routing == nil {
		c.JSON(http.StatusOK, gin.H{
			"routing":  nil,
			"message":  "No model routing configured; using global defaults.",
			"fallback": h.Client.Model,
		})
		return
	}

	// Enrich each assignment with effective model (resolve empty → fallback)
	type enrichedAssignment struct {
		Role            string  `json:"role"`
		Model           string  `json:"model"`
		EffectiveModel  string  `json:"effective_model"`
		Temperature     float64 `json:"temperature"`
	}
	var assignments []enrichedAssignment
	for role, a := range routing.Assignments {
		effective := a.Model
		if effective == "" {
			effective = h.Client.Model
		}
		assignments = append(assignments, enrichedAssignment{
			Role:           role,
			Model:          a.Model,
			EffectiveModel: effective,
			Temperature:    a.Temperature,
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"routing":    assignments,
		"fallback":   h.Client.Model,
	})
}
