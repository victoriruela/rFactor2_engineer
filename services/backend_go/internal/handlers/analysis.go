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
	DataDir   string
	Client    *ollama.Client
	Pipeline  analyzer
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

func (h *AnalysisHandler) resolveAnalyzer(model, provider string) (analyzer, error) {
	if provider != "" && provider != "ollama" {
		return nil, fmt.Errorf("unsupported provider: %s", provider)
	}

	if model == "" || h.Client == nil {
		return h.Pipeline, nil
	}

	overrideClient := ollama.NewClient(h.Client.BaseURL, model, h.Client.APIKey)
	overrideClient.NumPredict = h.Client.NumPredict
	overrideClient.Temp = h.Client.Temp
	overrideClient.HTTPClient = h.Client.HTTPClient

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
	runner, err := h.resolveAnalyzer(model, provider)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := h.analyzeFiles(c, telPath, svmPath, runner)
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

	sessDir := filepath.Join(h.DataDir, sessionID, uploadSessionID)

	entries, err := os.ReadDir(sessDir)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}

	var telPath, svmPath string
	for _, entry := range entries {
		name := entry.Name()
		ext := strings.ToLower(filepath.Ext(name))
		switch ext {
		case ".mat", ".csv":
			telPath = filepath.Join(sessDir, name)
		case ".svm":
			svmPath = filepath.Join(sessDir, name)
		}
	}

	if telPath == "" || svmPath == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "telemetry and svm files not found in session"})
		return
	}

	runner, err := h.resolveAnalyzer(model, provider)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := h.analyzeFiles(c, telPath, svmPath, runner)
	if err != nil {
		log.Error().Err(err).Msg("analysis failed")
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}

func (h *AnalysisHandler) analyzeFiles(c *gin.Context, telPath, svmPath string, runner analyzer) (*domain.AnalysisResponse, error) {
	return h.analyzeFilesWithProgress(c, telPath, svmPath, runner, nil)
}

func (h *AnalysisHandler) analyzeFilesWithProgress(c *gin.Context, telPath, svmPath string, runner analyzer, progress agents.ProgressFn) (*domain.AnalysisResponse, error) {
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
	summary := buildTelemetrySummary(telData)
	sts := telData.SessionStats()
	timeSeries := telData.ExtractTimeSeries()

	// Run pipeline (with optional progress callback)
	var resp *domain.AnalysisResponse
	if p, ok := runner.(*agents.Pipeline); ok && progress != nil {
		resp, err = p.AnalyzeWithProgress(c.Request.Context(), summary, &sts, setup, nil, progress)
	} else {
		resp, err = runner.Analyze(c.Request.Context(), summary, &sts, setup, nil)
	}
	if err != nil {
		return nil, err
	}

	resp.TelemetryTimeSeries = timeSeries
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

	sessDir := filepath.Join(h.DataDir, sessionID, uploadSessionID)

	entries, err := os.ReadDir(sessDir)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}

	var telPath, svmPath string
	for _, entry := range entries {
		name := entry.Name()
		ext := strings.ToLower(filepath.Ext(name))
		switch ext {
		case ".mat", ".csv":
			telPath = filepath.Join(sessDir, name)
		case ".svm":
			svmPath = filepath.Join(sessDir, name)
		}
	}

	if telPath == "" || svmPath == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "telemetry and svm files not found in session"})
		return
	}

	runner, err := h.resolveAnalyzer(model, provider)
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

	resp, err := h.analyzeFilesWithProgress(c, telPath, svmPath, runner, progress)
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

func buildTelemetrySummary(td *domain.TelemetryData) string {
	var sb strings.Builder
	sb.WriteString("=== TELEMETRY SUMMARY ===\n")
	sb.WriteString(fmt.Sprintf("Channels: %d\n", len(td.Channels)))
	sb.WriteString(fmt.Sprintf("Time column: %s\n", td.TimeCol))
	sb.WriteString(fmt.Sprintf("Lap column: %s\n\n", td.LapCol))

	stats := td.SessionStats()
	sb.WriteString(fmt.Sprintf("Total laps: %d\n", stats.TotalLaps))
	sb.WriteString(fmt.Sprintf("Best lap time: %.3f s\n", stats.BestLapTime))
	sb.WriteString(fmt.Sprintf("Average lap time: %.3f s\n\n", stats.AvgLapTime))

	// Channel summary (min/max/avg for key channels)
	keyChannels := []string{
		"Speed", "Throttle", "Brake", "Steering",
		"RPM", "Gear", "LateralAcceleration", "LongitudinalAcceleration",
	}
	for _, ch := range keyChannels {
		data, ok := td.Channels[ch]
		if !ok {
			continue
		}
		min, max, avg := channelStats(data)
		sb.WriteString(fmt.Sprintf("%s: min=%.2f max=%.2f avg=%.2f\n", ch, min, max, avg))
	}

	return sb.String()
}

func channelStats(data []float64) (min, max, avg float64) {
	if len(data) == 0 {
		return 0, 0, 0
	}
	min = data[0]
	max = data[0]
	sum := 0.0
	for _, v := range data {
		if v < min {
			min = v
		}
		if v > max {
			max = v
		}
		sum += v
	}
	avg = sum / float64(len(data))
	return
}
