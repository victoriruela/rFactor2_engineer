package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/agents"
	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/middleware"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
	"github.com/viciruela/rfactor2-engineer/internal/parsers"
)

type analyzer interface {
	Analyze(ctx context.Context, telemetrySummary string, sessionStats *domain.SessionStats, setup *domain.Setup, fixedParams []string) (*domain.AnalysisResponse, error)
}

// AnalysisHandler orchestrates file parsing and agent pipeline.
type AnalysisHandler struct {
	DataDir  string
	Client   *ollama.Client
	Pipeline analyzer
}

type ollamaRequestOptions struct {
	BaseURL string
	APIKey  string
}

// NewAnalysisHandler creates an analysis handler.
func NewAnalysisHandler(dataDir string, ollamaClient *ollama.Client) *AnalysisHandler {
	defaultPipeline := agents.NewPipeline(ollamaClient, "")
	return &AnalysisHandler{
		DataDir:  dataDir,
		Client:   ollamaClient,
		Pipeline: defaultPipeline,
	}
}

// NewAnalysisHandlerWithPipeline creates an analysis handler with an injected analyzer implementation.
func NewAnalysisHandlerWithPipeline(dataDir string, ollamaClient *ollama.Client, pipeline analyzer) *AnalysisHandler {
	if pipeline == nil {
		pipeline = agents.NewPipeline(ollamaClient, "")
	}

	return &AnalysisHandler{
		DataDir:  dataDir,
		Client:   ollamaClient,
		Pipeline: pipeline,
	}
}

func (h *AnalysisHandler) resolveAnalyzer(model, provider string, opts ollamaRequestOptions) (analyzer, error) {
	provider = normalizeProvider(provider)
	if provider != "ollama_cloud" {
		return nil, fmt.Errorf("unsupported provider: %s", provider)
	}

	if model == "" && opts.BaseURL == "" && opts.APIKey == "" {
		if h.Client != nil && isLocalOllamaBaseURL(h.Client.BaseURL) {
			return nil, fmt.Errorf("local ollama endpoints are disabled; configure a cloud ollama_base_url")
		}
		return h.Pipeline, nil
	}

	baseURL := opts.BaseURL
	apiKey := opts.APIKey
	resolvedModel := model

	if h.Client != nil {
		if baseURL == "" {
			baseURL = h.Client.BaseURL
		}
		if apiKey == "" {
			apiKey = h.Client.APIKey
		}
		if resolvedModel == "" {
			resolvedModel = h.Client.Model
		}
	}

	if baseURL == "" {
		return nil, fmt.Errorf("ollama_base_url is required")
	}
	if isLocalOllamaBaseURL(baseURL) {
		return nil, fmt.Errorf("local ollama endpoints are disabled; configure a cloud ollama_base_url")
	}
	if resolvedModel == "" {
		return nil, fmt.Errorf("model is required")
	}

	overrideClient := ollama.NewClient(baseURL, resolvedModel, apiKey)
	if h.Client != nil {
		overrideClient.NumPredict = h.Client.NumPredict
		overrideClient.Temp = h.Client.Temp
		overrideClient.HTTPClient = h.Client.HTTPClient
	}

	return agents.NewPipeline(overrideClient, ""), nil
}

// Analyze handles POST /api/analyze (multipart upload + analysis)
func (h *AnalysisHandler) Analyze(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)

	// Receive files
	form, err := c.MultipartForm()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid multipart form"})
		return
	}

	telemetryFiles := form.File["telemetry"]
	svmFiles := form.File["svm"]
	model := strings.TrimSpace(c.PostForm("model"))
	provider := strings.TrimSpace(c.PostForm("provider"))
	ollamaBaseURL := strings.TrimSpace(c.PostForm("ollama_base_url"))
	ollamaAPIKey := strings.TrimSpace(c.PostForm("ollama_api_key"))
	fixedParams := extractFixedParams(c)

	if len(telemetryFiles) == 0 || len(svmFiles) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "both telemetry and svm files are required"})
		return
	}

	// Save to session directory
	sessDir := filepath.Join(h.DataDir, sessionID, "analyze")
	if err := os.MkdirAll(sessDir, 0o755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cannot create session dir"})
		return
	}

	telFile := telemetryFiles[0]
	svmFile := svmFiles[0]

	telPath := filepath.Join(sessDir, telFile.Filename)
	svmPath := filepath.Join(sessDir, svmFile.Filename)

	if err := c.SaveUploadedFile(telFile, telPath); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to save telemetry file"})
		return
	}
	if err := c.SaveUploadedFile(svmFile, svmPath); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to save svm file"})
		return
	}

	// Parse
	runner, err := h.resolveAnalyzer(model, provider, ollamaRequestOptions{BaseURL: ollamaBaseURL, APIKey: ollamaAPIKey})
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := h.analyzeFiles(c, telPath, svmPath, runner, fixedParams)
	if err != nil {
		log.Error().Err(err).Msg("analysis failed")
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}

// AnalyzeSession handles POST /api/analyze_session (use pre-uploaded files)
func (h *AnalysisHandler) AnalyzeSession(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)

	uploadSessionID := c.PostForm("session_id")
	if uploadSessionID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "session_id is required"})
		return
	}
	model := strings.TrimSpace(c.PostForm("model"))
	provider := strings.TrimSpace(c.PostForm("provider"))
	ollamaBaseURL := strings.TrimSpace(c.PostForm("ollama_base_url"))
	ollamaAPIKey := strings.TrimSpace(c.PostForm("ollama_api_key"))
	fixedParams := extractFixedParams(c)

	telPath, svmPath, err := h.resolveSessionFilePaths(sessionID, uploadSessionID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	runner, err := h.resolveAnalyzer(model, provider, ollamaRequestOptions{BaseURL: ollamaBaseURL, APIKey: ollamaAPIKey})
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := h.analyzeFiles(c, telPath, svmPath, runner, fixedParams)
	if err != nil {
		log.Error().Err(err).Msg("analysis failed")
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}

// LoadSessionTelemetry handles POST /api/session_telemetry (telemetry only, no AI pipeline).
func (h *AnalysisHandler) LoadSessionTelemetry(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)

	uploadSessionID := c.PostForm("session_id")
	if uploadSessionID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "session_id is required"})
		return
	}

	telPath, err := h.resolveTelemetryFilePath(sessionID, uploadSessionID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	ext := strings.ToLower(filepath.Ext(telPath))
	var telData *domain.TelemetryData
	switch ext {
	case ".mat":
		telData, err = parsers.ParseMATFile(telPath)
	case ".csv":
		telData, err = parsers.ParseCSVFile(telPath)
	default:
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("unsupported telemetry format: %s", ext)})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("telemetry parse error: %v", err)})
		return
	}

	stats := telData.SessionStats()
	resp := &domain.AnalysisResponse{
		CircuitData:         parsers.ExtractGPS(telData, 2000),
		IssuesOnMap:         []domain.IssueMarker{},
		DrivingAnalysis:     "",
		SetupAnalysis:       map[string][]domain.SetupChange{},
		FullSetup:           map[string][]domain.SetupChange{},
		SessionStats:        &stats,
		LapsData:            stats.Laps,
		AgentReports:        []domain.SectionReport{},
		TelemetrySummary:    agents.BuildEnhancedTelemetrySummary(telData),
		ChiefReasoning:      "",
		TelemetryTimeSeries: telData.ExtractTimeSeries(),
	}

	c.JSON(http.StatusOK, resp)
}

func (h *AnalysisHandler) resolveTelemetryFilePath(clientSessionID, uploadSessionID string) (string, error) {
	sessDir := filepath.Join(h.DataDir, clientSessionID, uploadSessionID)

	entries, err := os.ReadDir(sessDir)
	if err != nil {
		return "", fmt.Errorf("session not found")
	}

	for _, entry := range entries {
		if entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}

		ext := strings.ToLower(filepath.Ext(entry.Name()))
		switch ext {
		case ".mat", ".csv":
			return filepath.Join(sessDir, entry.Name()), nil
		}
	}

	return "", fmt.Errorf("telemetry file not found in session")
}

func (h *AnalysisHandler) analyzeFiles(c *gin.Context, telPath, svmPath string, runner analyzer, fixedParams []string) (*domain.AnalysisResponse, error) {
	return h.analyzeFilesWithProgress(c, telPath, svmPath, runner, fixedParams, nil)
}

func (h *AnalysisHandler) analyzeFilesWithProgress(c *gin.Context, telPath, svmPath string, runner analyzer, fixedParams []string, progress agents.ProgressFn) (*domain.AnalysisResponse, error) {
	// Parse telemetry
	ext := strings.ToLower(filepath.Ext(telPath))
	var telData *domain.TelemetryData
	var err error

	switch ext {
	case ".mat":
		telData, err = parsers.ParseMATFile(telPath)
	case ".csv":
		telData, err = parsers.ParseCSVFile(telPath)
	default:
		return nil, fmt.Errorf("unsupported telemetry format: %s", ext)
	}
	if err != nil {
		return nil, fmt.Errorf("telemetry parse error: %w", err)
	}

	// Parse setup
	setup, err := parsers.ParseSVMFile(svmPath)
	if err != nil {
		return nil, fmt.Errorf("svm parse error: %w", err)
	}

	// Build telemetry summary and session stats
	summary := agents.BuildEnhancedTelemetrySummary(telData)
	sts := telData.SessionStats()
	timeSeries := telData.ExtractTimeSeries()

	// Run pipeline (with optional progress callback)
	var resp *domain.AnalysisResponse
	if p, ok := runner.(*agents.Pipeline); ok && progress != nil {
		resp, err = p.AnalyzeWithProgress(c.Request.Context(), summary, &sts, setup, fixedParams, progress)
	} else {
		resp, err = runner.Analyze(c.Request.Context(), summary, &sts, setup, fixedParams)
	}
	if err != nil {
		return nil, err
	}

	resp.TelemetryTimeSeries = timeSeries
	resp.CircuitData = parsers.ExtractGPS(telData, 2000)
	return resp, nil
}

// AnalyzeStream handles POST /api/analyze_stream — identical to AnalyzeSession but
// streams Server-Sent Events with pipeline progress before emitting the final result.
func (h *AnalysisHandler) AnalyzeStream(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)

	uploadSessionID := c.PostForm("session_id")
	if uploadSessionID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "session_id is required"})
		return
	}
	model := strings.TrimSpace(c.PostForm("model"))
	provider := strings.TrimSpace(c.PostForm("provider"))
	ollamaBaseURL := strings.TrimSpace(c.PostForm("ollama_base_url"))
	ollamaAPIKey := strings.TrimSpace(c.PostForm("ollama_api_key"))

	telPath, svmPath, err := h.resolveSessionFilePaths(sessionID, uploadSessionID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	runner, err := h.resolveAnalyzer(model, provider, ollamaRequestOptions{BaseURL: ollamaBaseURL, APIKey: ollamaAPIKey})
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Set up SSE headers
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)

	flusher, canFlush := c.Writer.(http.Flusher)
	var streamMu sync.Mutex

	sendSSE := func(eventType string, payload any) {
		streamMu.Lock()
		defer streamMu.Unlock()

		data, _ := json.Marshal(payload)
		fmt.Fprintf(c.Writer, "event: %s\ndata: %s\n\n", eventType, data)
		if canFlush {
			flusher.Flush()
		}
	}

	progress := func(ev agents.ProgressEvent) {
		sendSSE("progress", ev)
	}

	fixedParams := extractFixedParams(c)
	resp, err := h.analyzeFilesWithProgress(c, telPath, svmPath, runner, fixedParams, progress)
	if err != nil {
		log.Error().Err(err).Msg("stream analysis failed")
		sendSSE("error", gin.H{"error": err.Error()})
		return
	}

	sendSSE("result", resp)
	fmt.Fprintf(c.Writer, "event: done\ndata: {}\n\n")
	if canFlush {
		flusher.Flush()
	}
}

func extractFixedParams(c *gin.Context) []string {
	raw := c.PostFormArray("fixed_params")
	if len(raw) == 0 {
		return nil
	}

	seen := make(map[string]struct{})
	result := make([]string, 0, len(raw))
	for _, param := range raw {
		trimmed := strings.TrimSpace(param)
		if trimmed == "" {
			continue
		}
		key := strings.ToLower(trimmed)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		result = append(result, trimmed)
	}
	return result
}

func (h *AnalysisHandler) resolveSessionFilePaths(clientSessionID, uploadSessionID string) (string, string, error) {
	sessDir := filepath.Join(h.DataDir, clientSessionID, uploadSessionID)

	entries, err := os.ReadDir(sessDir)
	if err != nil {
		return "", "", fmt.Errorf("session not found")
	}

	var telPath, svmPath string
	for _, entry := range entries {
		if entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}

		name := entry.Name()
		ext := strings.ToLower(filepath.Ext(name))
		switch ext {
		case ".mat", ".csv":
			telPath = filepath.Join(sessDir, name)
		case ".svm":
			svmPath = filepath.Join(sessDir, name)
		}
	}

	if telPath == "" {
		return "", "", fmt.Errorf("telemetry file not found in session")
	}
	if svmPath == "" {
		return "", "", fmt.Errorf("svm file not found in session")
	}

	return telPath, svmPath, nil
}
