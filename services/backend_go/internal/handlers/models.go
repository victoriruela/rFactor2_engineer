package handlers

import (
	"net/http"

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
	models, err := h.Client.ListModels(c.Request.Context())
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
