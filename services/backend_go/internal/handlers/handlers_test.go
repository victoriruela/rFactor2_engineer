package handlers_test

import (
	"bytes"
	"encoding/json"
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
	analysisH := handlers.NewAnalysisHandler(dataDir, client)
	modelsH := handlers.NewModelsHandler(client)
	tracksH := handlers.NewTracksHandler()
	uploadH := handlers.NewUploadHandler(dataDir)

	api := r.Group("/api")
	api.GET("/sessions", sessionH.ListSessions)
	api.POST("/cleanup", sessionH.Cleanup)
	api.GET("/health", modelsH.HealthCheck)
	api.GET("/models", modelsH.ListModels)
	api.GET("/tracks", tracksH.ListTracks)
	api.POST("/session_telemetry", analysisH.LoadSessionTelemetry)
	api.POST("/uploads/init", uploadH.InitUpload)
	api.PUT("/uploads/:upload_id/chunk", uploadH.UploadChunk)
	api.POST("/uploads/:upload_id/complete", uploadH.CompleteUpload)

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

func TestChunkedUpload_CreatesSessionListedInSessions(t *testing.T) {
	dir := t.TempDir()
	r := newTestRouter(dir)

	// 1) Init
	body := strings.NewReader(`{"filename":"race01.mat","total_size":4}`)
	initReq := httptest.NewRequest("POST", "/api/uploads/init", body)
	initReq.Header.Set("Content-Type", "application/json")
	initReq.Header.Set("X-Client-Session-Id", "test-session")
	initW := httptest.NewRecorder()
	r.ServeHTTP(initW, initReq)

	if initW.Code != http.StatusOK {
		t.Fatalf("init expected 200, got %d: %s", initW.Code, initW.Body.String())
	}

	var initResp struct {
		UploadID string `json:"upload_id"`
	}
	if err := json.Unmarshal(initW.Body.Bytes(), &initResp); err != nil {
		t.Fatalf("cannot decode init response: %v", err)
	}
	if initResp.UploadID == "" {
		t.Fatal("upload_id is empty")
	}

	// 2) Chunk
	chunkReq := httptest.NewRequest("PUT", "/api/uploads/"+initResp.UploadID+"/chunk?chunk_index=0", bytes.NewReader([]byte("abcd")))
	chunkReq.Header.Set("X-Client-Session-Id", "test-session")
	chunkW := httptest.NewRecorder()
	r.ServeHTTP(chunkW, chunkReq)

	if chunkW.Code != http.StatusOK {
		t.Fatalf("chunk expected 200, got %d: %s", chunkW.Code, chunkW.Body.String())
	}

	// 3) Complete
	completeReq := httptest.NewRequest("POST", "/api/uploads/"+initResp.UploadID+"/complete", nil)
	completeReq.Header.Set("X-Client-Session-Id", "test-session")
	completeW := httptest.NewRecorder()
	r.ServeHTTP(completeW, completeReq)

	if completeW.Code != http.StatusOK {
		t.Fatalf("complete expected 200, got %d: %s", completeW.Code, completeW.Body.String())
	}

	// 4) List sessions should include derived session folder race01
	listReq := httptest.NewRequest("GET", "/api/sessions", nil)
	listReq.Header.Set("X-Client-Session-Id", "test-session")
	listW := httptest.NewRecorder()
	r.ServeHTTP(listW, listReq)

	if listW.Code != http.StatusOK {
		t.Fatalf("sessions expected 200, got %d: %s", listW.Code, listW.Body.String())
	}

	var listResp struct {
		Sessions []struct {
			ID        string `json:"id"`
			Telemetry string `json:"telemetry"`
			SVM       string `json:"svm"`
		} `json:"sessions"`
	}
	if err := json.Unmarshal(listW.Body.Bytes(), &listResp); err != nil {
		t.Fatalf("cannot decode sessions response: %v", err)
	}

	if len(listResp.Sessions) != 0 {
		// With only MAT uploaded, session is not complete yet and should not appear.
		t.Fatalf("expected 0 complete sessions with only telemetry file, got %d", len(listResp.Sessions))
	}

	// Verify file actually landed in the derived session folder.
	if _, err := os.Stat(filepath.Join(dir, "test-session", "race01", "race01.mat")); err != nil {
		t.Fatalf("expected uploaded file in derived session folder: %v", err)
	}
}

func TestLoadSessionTelemetry_AllowsTelemetryOnlySession(t *testing.T) {
	dir := t.TempDir()
	sessDir := filepath.Join(dir, "test-session", "telemetry-only")
	if err := os.MkdirAll(sessDir, 0o755); err != nil {
		t.Fatal(err)
	}

	// Minimal CSV accepted by the parser: 14 metadata rows, header, units, then data.
	csv := strings.Repeat("meta\n", 14) +
		"Time,Speed,Lap,GPS Latitude,GPS Longitude\n" +
		"s,km/h,-,deg,deg\n" +
		"0.001,120.5,1,25.487,51.447\n" +
		"0.002,121.0,1,25.488,51.448\n"
	if err := os.WriteFile(filepath.Join(sessDir, "telemetry.csv"), []byte(csv), 0o644); err != nil {
		t.Fatal(err)
	}

	r := newTestRouter(dir)
	req := httptest.NewRequest(http.MethodPost, "/api/session_telemetry", strings.NewReader("session_id=telemetry-only"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("X-Client-Session-Id", "test-session")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	if !strings.Contains(w.Body.String(), "telemetry_series") {
		t.Fatalf("expected telemetry payload, got: %s", w.Body.String())
	}
}
