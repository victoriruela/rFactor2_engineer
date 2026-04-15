package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/auth"
	"github.com/viciruela/rfactor2-engineer/internal/benchmarks"
	"github.com/viciruela/rfactor2-engineer/internal/config"
)

type benchmarkRequest struct {
	MaxCandidates int `json:"max_candidates"`
}

// RunBenchmark handles POST /api/models/benchmark — runs the auto-selection
// benchmark as an SSE stream.
// The Ollama base URL comes from the server configuration (OLLAMA_BASE_URL).
// The API key is read from the authenticated user's stored profile in the DB.
func (h *ModelsHandler) RunBenchmark(c *gin.Context) {
	var req benchmarkRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid JSON payload"})
		return
	}

	// Use the server-configured Ollama URL — never accept it from the request body.
	baseURL := h.Client.BaseURL
	if isLocalOllamaBaseURL(baseURL) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "el servidor está configurado con un endpoint local de Ollama; configura OLLAMA_BASE_URL con una URL cloud"})
		return
	}

	// Read the API key from the authenticated user's DB profile.
	claims, exists := c.Get("auth_claims")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}
	cl := claims.(*auth.Claims)
	user, err := h.AuthDB.GetUserByUsername(cl.Username)
	if err != nil || user == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error obteniendo perfil de usuario"})
		return
	}
	apiKey := user.OllamaAPIKey
	if apiKey == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no hay API key guardada en tu perfil; guarda tu API key primero"})
		return
	}

	maxCandidates := req.MaxCandidates
	if maxCandidates <= 0 {
		maxCandidates = 100
	}
	if maxCandidates > 200 {
		maxCandidates = 200
	}

	// Set up SSE
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)

	flusher, canFlush := c.Writer.(http.Flusher)
	var mu sync.Mutex

	sendSSE := func(eventType string, payload any) {
		mu.Lock()
		defer mu.Unlock()
		data, _ := json.Marshal(payload)
		fmt.Fprintf(c.Writer, "event: %s\ndata: %s\n\n", eventType, data)
		if canFlush {
			flusher.Flush()
		}
	}

	progress := func(ev benchmarks.AutoSelectProgress) {
		sendSSE(ev.Event, ev.Data)
	}

	result, err := benchmarks.AutoSelectModels(
		c.Request.Context(),
		baseURL, apiKey,
		maxCandidates,
		progress,
	)
	if err != nil {
		log.Error().Err(err).Msg("benchmark failed")
		sendSSE("error", gin.H{"error": err.Error()})
		return
	}

	// Save routing to model_routing.json
	routingPath := h.DataDir + "/model_routing.json"
	routing := &config.ModelRouting{
		Version:     1,
		Assignments: result.Assignments,
	}
	if err := config.SaveModelRouting(routingPath, routing); err != nil {
		log.Error().Err(err).Msg("failed to save model routing after benchmark")
		sendSSE("error", gin.H{"error": "benchmark completado pero fallo al guardar: " + err.Error()})
		return
	}

	log.Info().
		Int("candidates", maxCandidates).
		Float64("elapsed", result.Elapsed).
		Msg("benchmark complete, routing saved")

	sendSSE("result", result)
	fmt.Fprintf(c.Writer, "event: done\ndata: {}\n\n")
	if canFlush {
		flusher.Flush()
	}
}

// SaveModelRouting handles PUT /api/models/routing — saves manual routing overrides.
// Only admin users may modify the global model assignments.
func (h *ModelsHandler) SaveModelRouting(c *gin.Context) {
	claims, exists := c.Get("auth_claims")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}
	cl := claims.(*auth.Claims)
	if !cl.IsAdmin {
		c.JSON(http.StatusForbidden, gin.H{"error": "solo administradores pueden modificar la asignación de modelos"})
		return
	}

	var req struct {
		Assignments map[string]config.ModelAssignment `json:"assignments"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid JSON payload"})
		return
	}

	routingPath := h.DataDir + "/model_routing.json"
	routing := &config.ModelRouting{
		Version:     1,
		Assignments: req.Assignments,
	}
	if err := config.SaveModelRouting(routingPath, routing); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "fallo al guardar enrutamiento: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Enrutamiento de modelos guardado.", "assignments": req.Assignments})
}
