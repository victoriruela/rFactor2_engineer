package main

import (
	"context"
	"embed"
	"fmt"
	"io/fs"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/config"
	"github.com/viciruela/rfactor2-engineer/internal/handlers"
	"github.com/viciruela/rfactor2-engineer/internal/middleware"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

//go:embed all:static
var staticFS embed.FS

func main() {
	// ── Logging ──
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr, TimeFormat: time.RFC3339})

	cfg := config.Load()

	lvl, err := zerolog.ParseLevel(cfg.LogLevel)
	if err == nil {
		zerolog.SetGlobalLevel(lvl)
	}

	if cfg.LogLevel == "debug" {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	// ── Data dir ──
	if err := os.MkdirAll(cfg.DataDir, 0o755); err != nil {
		log.Fatal().Err(err).Msg("cannot create data directory")
	}

	// ── Ollama client ──
	ollamaClient := ollama.NewClient(cfg.OllamaURL, cfg.OllamaModel, cfg.OllamaAPIKey)

	// ── Handlers ──
	uploadH := handlers.NewUploadHandler(cfg.DataDir)
	sessionH := handlers.NewSessionHandler(cfg.DataDir)
	analysisH := handlers.NewAnalysisHandler(cfg.DataDir, ollamaClient)
	modelsH := handlers.NewModelsHandler(ollamaClient)
	tracksH := handlers.NewTracksHandler()

	// ── Start background cleanup worker ──
	go startCleanupWorker(sessionH)

	// ── Router ──
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.CORSMiddleware())
	r.Use(ginZerolog())

	api := r.Group("/api")
	api.Use(middleware.SessionResolver())
	{
		// Health
		api.GET("/health", modelsH.HealthCheck)

		// Upload (chunked)
		api.POST("/uploads/init", uploadH.InitUpload)
		api.PUT("/uploads/:upload_id/chunk", uploadH.UploadChunk)
		api.POST("/uploads/:upload_id/complete", uploadH.CompleteUpload)

		// Sessions
		api.GET("/sessions", sessionH.ListSessions)
		api.GET("/sessions/:session_id/file/:filename", sessionH.DownloadFile)
		api.DELETE("/sessions/:session_id", sessionH.DeleteSession)
		api.POST("/cleanup", sessionH.Cleanup)
		api.POST("/cleanup_all", sessionH.CleanupAll)

		// Analysis
		api.POST("/analyze", analysisH.Analyze)
		api.POST("/analyze_session", analysisH.AnalyzeSession)
		api.POST("/analyze_stream", analysisH.AnalyzeStream)
		api.POST("/session_telemetry", analysisH.LoadSessionTelemetry)
		api.GET("/setup/:sessionId", analysisH.GetSetup)

		// Models
		api.GET("/models", modelsH.ListModels)

		// Tracks
		api.GET("/tracks", tracksH.ListTracks)
	}

	// ── Serve Expo static build via go:embed ──
	staticSub, err := fs.Sub(staticFS, "static")
	if err != nil {
		log.Warn().Msg("no embedded static files, API-only mode")
	} else {
		r.NoRoute(gin.WrapH(spaHandler(http.FS(staticSub))))
	}

	// ── Server ──
	addr := fmt.Sprintf(":%d", cfg.Port)
	srv := &http.Server{
		Addr:         addr,
		Handler:      r,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 300 * time.Second, // long for analysis
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		log.Info().Int("port", cfg.Port).Msg("server starting")
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal().Err(err).Msg("server error")
		}
	}()

	// ── Graceful shutdown ──
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Info().Msg("shutting down…")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Error().Err(err).Msg("forced shutdown")
	}
	log.Info().Msg("server stopped")
}

// spaHandler serves the SPA — falls back to index.html for unknown routes.
func spaHandler(fsys http.FileSystem) http.Handler {
	fileServer := http.FileServer(fsys)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			http.NotFound(w, r)
			return
		}

		path := r.URL.Path
		// Try to open — if not found, serve index.html
		f, err := fsys.Open(path)
		if err != nil {
			r.URL.Path = "/"
			fileServer.ServeHTTP(w, r)
			return
		}
		f.Close()
		fileServer.ServeHTTP(w, r)
	})
}

func ginZerolog() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		c.Next()
		log.Info().
			Str("method", c.Request.Method).
			Str("path", c.Request.URL.Path).
			Int("status", c.Writer.Status()).
			Dur("latency", time.Since(start)).
			Msg("")
	}
}

// startCleanupWorker runs a periodic cleanup task to remove old sessions.
// Sessions older than 24 hours are cleaned up every hour.
func startCleanupWorker(sessionH *handlers.SessionHandler) {
	ticker := time.NewTicker(1 * time.Hour)
	defer ticker.Stop()

	// Run cleanup immediately on startup
	sessionH.CleanupOldSessions(24 * time.Hour)

	// Then run periodically
	for range ticker.C {
		sessionH.CleanupOldSessions(24 * time.Hour)
	}
}
