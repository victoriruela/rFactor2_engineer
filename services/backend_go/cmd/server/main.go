package main

import (
	"context"
	"embed"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"os/signal"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/auth"
	"github.com/viciruela/rfactor2-engineer/internal/config"
	"github.com/viciruela/rfactor2-engineer/internal/handlers"
	"github.com/viciruela/rfactor2-engineer/internal/middleware"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

//go:embed all:static
var staticFS embed.FS

var expoEntryScriptRE = regexp.MustCompile(`<script\s+src="(/_expo/static/js/web/entry-[a-f0-9]+\.js)"\s+defer></script>`)

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
	cleanDataDir(cfg.DataDir)

	// ── Auth DB ──
	authDB, err := auth.OpenDB(cfg.DataDir)
	if err != nil {
		log.Fatal().Err(err).Msg("cannot open auth database")
	}
	if err := authDB.SeedAdmin("Mulder_admin", "100fuchupabien31416"); err != nil {
		log.Fatal().Err(err).Msg("cannot seed admin user")
	}

	jwtSecret := cfg.JWTSecret
	if jwtSecret == "" {
		jwtSecret = uuid.NewString()
		log.Warn().Msg("RF2_JWT_SECRET not set — using random secret (tokens will not survive restarts)")
	}

	smtpCfg := auth.SMTPConfig{
		Host: cfg.SMTPHost,
		Port: cfg.SMTPPort,
		User: cfg.SMTPUser,
		Pass: cfg.SMTPPass,
		From: cfg.SMTPFrom,
	}
	authH := auth.NewHandlers(authDB, jwtSecret, smtpCfg)

	// ── Ollama client ──
	ollamaClient := ollama.NewClient(cfg.OllamaURL, cfg.OllamaModel, cfg.OllamaAPIKey)

	// ── Handlers ──
	analysisH := handlers.NewAnalysisHandler(cfg.DataDir, ollamaClient)
	modelsH := handlers.NewModelsHandler(ollamaClient)
	tracksH := handlers.NewTracksHandler()

	// ── Router ──
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.CORSMiddleware())
	r.Use(ginZerolog())

	api := r.Group("/api")
	api.Use(middleware.SessionResolver())
	{
		// Health (public)
		api.GET("/health", modelsH.HealthCheck)

		// Auth (public)
		authGroup := api.Group("/auth")
		{
			authGroup.POST("/register", authH.Register)
			authGroup.POST("/verify", authH.Verify)
			authGroup.POST("/login", authH.Login)
		}

		// Protected routes
		protected := api.Group("")
		protected.Use(middleware.JWTRequired(jwtSecret))
		{
			// Analysis (preparsed client payload — no file writes)
			protected.POST("/analyze_preparsed", analysisH.AnalyzePreparsed)
			protected.POST("/analyze_preparsed_stream", analysisH.AnalyzePreparsedStream)

			// Models
			protected.GET("/models", modelsH.ListModels)

			// Tracks
			protected.GET("/tracks", tracksH.ListTracks)

			// Auth config
			protected.PUT("/auth/config", authH.UpdateConfig)
		}
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

		routePath := r.URL.Path
		if routePath == "/favicon.ico" {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		isHTMLRoute := routePath == "/" || strings.HasSuffix(routePath, ".html")
		if isHTMLRoute {
			// Keep HTML uncacheable so clients pick up new hashed bundles after deploys.
			w.Header().Set("Cache-Control", "no-store, no-cache, must-revalidate")
			w.Header().Set("Pragma", "no-cache")
			w.Header().Set("Expires", "0")
			if routePath == "/" || routePath == "/index.html" {
				serveNormalizedIndexHTML(w, fsys)
				return
			}
		}
		// Try to open — if not found, serve index.html
		f, err := fsys.Open(routePath)
		if err != nil {
			// Missing static assets (e.g. old entry-*.js) must return 404, not index.html.
			if ext := path.Ext(routePath); ext != "" {
				http.NotFound(w, r)
				return
			}
			w.Header().Set("Cache-Control", "no-store, no-cache, must-revalidate")
			w.Header().Set("Pragma", "no-cache")
			w.Header().Set("Expires", "0")
			serveNormalizedIndexHTML(w, fsys)
			return
		}
		f.Close()
		fileServer.ServeHTTP(w, r)
	})
}

func serveNormalizedIndexHTML(w http.ResponseWriter, fsys http.FileSystem) {
	f, err := fsys.Open("/index.html")
	if err != nil {
		http.Error(w, "index.html not found", http.StatusInternalServerError)
		return
	}
	defer f.Close()

	content, err := io.ReadAll(f)
	if err != nil {
		http.Error(w, "cannot read index.html", http.StatusInternalServerError)
		return
	}

	html := string(content)
	normalized := expoEntryScriptRE.ReplaceAllString(html, `<script type="module" src="$1" defer></script>`)

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(normalized))
}

// cleanDataDir removes all entries inside dir (but keeps the directory itself
// and the auth database files).
func cleanDataDir(dir string) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasPrefix(name, "rf2_users.db") {
			continue // preserve auth database and its WAL/SHM files
		}
		p := filepath.Join(dir, name)
		if err := os.RemoveAll(p); err != nil {
			log.Warn().Err(err).Str("path", p).Msg("failed to remove data entry on startup")
		}
	}
	log.Info().Str("dir", dir).Msg("data directory cleaned on startup")
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
