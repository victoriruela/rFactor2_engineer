package handlers_test

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/viciruela/rfactor2-engineer/internal/handlers"
	"github.com/viciruela/rfactor2-engineer/internal/middleware"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func newTestRouter(dataDir string) *gin.Engine {
	r := gin.New()
	r.Use(middleware.SessionResolver())

	client := ollama.NewClient("http://localhost:11434", "test", "")
	sessionH := handlers.NewSessionHandler(dataDir)
	modelsH := handlers.NewModelsHandler(client)
	tracksH := handlers.NewTracksHandler()
	uploadH := handlers.NewUploadHandler(dataDir)

	api := r.Group("/api")
	api.GET("/sessions", sessionH.ListSessions)
	api.POST("/cleanup", sessionH.Cleanup)
	api.GET("/health", modelsH.HealthCheck)
	api.GET("/models", modelsH.ListModels)
	api.GET("/tracks", tracksH.ListTracks)
	api.POST("/uploads/init", uploadH.InitUpload)

	return r
}

func TestListSessions_Empty(t *testing.T) {
	dir := t.TempDir()
	r := newTestRouter(dir)

	req := httptest.NewRequest("GET", "/api/sessions", nil)
	req.Header.Set("X-Client-Session-Id", "test-session")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestListSessions_WithData(t *testing.T) {
	dir := t.TempDir()
	sessDir := filepath.Join(dir, "test-session", "my-session")
	if err := os.MkdirAll(sessDir, 0o755); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(sessDir, "telemetry.mat"), []byte("fake"), 0o644)
	os.WriteFile(filepath.Join(sessDir, "setup.svm"), []byte("fake"), 0o644)

	r := newTestRouter(dir)
	req := httptest.NewRequest("GET", "/api/sessions", nil)
	req.Header.Set("X-Client-Session-Id", "test-session")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestCleanup(t *testing.T) {
	dir := t.TempDir()
	sessDir := filepath.Join(dir, "test-session")
	os.MkdirAll(sessDir, 0o755)
	os.WriteFile(filepath.Join(sessDir, "dummy.txt"), []byte("x"), 0o644)

	r := newTestRouter(dir)
	req := httptest.NewRequest("POST", "/api/cleanup", nil)
	req.Header.Set("X-Client-Session-Id", "test-session")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	// Verify directory is removed
	if _, err := os.Stat(sessDir); !os.IsNotExist(err) {
		t.Error("session dir should have been removed")
	}
}

func TestHealthCheck(t *testing.T) {
	dir := t.TempDir()
	r := newTestRouter(dir)

	req := httptest.NewRequest("GET", "/api/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestListTracks(t *testing.T) {
	dir := t.TempDir()
	r := newTestRouter(dir)

	req := httptest.NewRequest("GET", "/api/tracks", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestUploadInit(t *testing.T) {
	dir := t.TempDir()
	r := newTestRouter(dir)

	body := strings.NewReader(`{"filename":"test.mat","total_size":1024}`)
	req := httptest.NewRequest("POST", "/api/uploads/init", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-Session-Id", "test-session")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
}
