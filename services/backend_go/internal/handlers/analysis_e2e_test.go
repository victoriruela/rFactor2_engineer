package handlers_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/handlers"
	"github.com/viciruela/rfactor2-engineer/internal/middleware"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

type fakeAnalyzer struct {
	called bool
}

func (f *fakeAnalyzer) Analyze(_ context.Context, _ string, stats *domain.SessionStats, _ *domain.Setup, _ []string) (*domain.AnalysisResponse, error) {
	f.called = true
	return &domain.AnalysisResponse{
		DrivingAnalysis: "ok",
		SetupAnalysis:   map[string][]domain.SetupChange{},
		FullSetup:       map[string][]domain.SetupChange{},
		SessionStats:    stats,
		AgentReports:    []domain.SectionReport{},
		ChiefReasoning:  "ok",
	}, nil
}

func TestE2E_ChunkedUploadThenAnalyzeSession(t *testing.T) {
	dir := t.TempDir()
	r := gin.New()
	r.Use(middleware.SessionResolver())

	client := ollama.NewClient("https://ollama.example.com", "llama3.2:latest", "")
	uploadH := handlers.NewUploadHandler(dir)
	sessionH := handlers.NewSessionHandler(dir)
	fake := &fakeAnalyzer{}
	analysisH := handlers.NewAnalysisHandlerWithPipeline(dir, client, fake)

	api := r.Group("/api")
	api.POST("/uploads/init", uploadH.InitUpload)
	api.PUT("/uploads/:upload_id/chunk", uploadH.UploadChunk)
	api.POST("/uploads/:upload_id/complete", uploadH.CompleteUpload)
	api.GET("/sessions", sessionH.ListSessions)
	api.POST("/analyze_session", analysisH.AnalyzeSession)

	headerSessionID := "e2e-session"

	uploadOneFile := func(filename string, content []byte) {
		t.Helper()

		initReq := httptest.NewRequest(http.MethodPost, "/api/uploads/init", strings.NewReader(`{"filename":"`+filename+`","total_size":`+strconv.Itoa(len(content))+`}`))
		initReq.Header.Set("Content-Type", "application/json")
		initReq.Header.Set("X-Client-Session-Id", headerSessionID)
		initW := httptest.NewRecorder()
		r.ServeHTTP(initW, initReq)
		if initW.Code != http.StatusOK {
			t.Fatalf("init %s expected 200, got %d: %s", filename, initW.Code, initW.Body.String())
		}

		var initResp struct {
			UploadID string `json:"upload_id"`
		}
		if err := json.Unmarshal(initW.Body.Bytes(), &initResp); err != nil {
			t.Fatalf("decode init %s: %v", filename, err)
		}

		chunkReq := httptest.NewRequest(http.MethodPut, "/api/uploads/"+initResp.UploadID+"/chunk?chunk_index=0", bytes.NewReader(content))
		chunkReq.Header.Set("X-Client-Session-Id", headerSessionID)
		chunkW := httptest.NewRecorder()
		r.ServeHTTP(chunkW, chunkReq)
		if chunkW.Code != http.StatusOK {
			t.Fatalf("chunk %s expected 200, got %d: %s", filename, chunkW.Code, chunkW.Body.String())
		}

		completeReq := httptest.NewRequest(http.MethodPost, "/api/uploads/"+initResp.UploadID+"/complete", nil)
		completeReq.Header.Set("X-Client-Session-Id", headerSessionID)
		completeW := httptest.NewRecorder()
		r.ServeHTTP(completeW, completeReq)
		if completeW.Code != http.StatusOK {
			t.Fatalf("complete %s expected 200, got %d: %s", filename, completeW.Code, completeW.Body.String())
		}
	}

	// Minimal parseable CSV for parser expectations: 14 metadata lines + header + data rows.
	csv := strings.Repeat("meta\n", 14) + "Time,Speed,Lap\n0.001,120.5,1\n0.002,121.0,1\n"
	svm := "[GENERAL]\nFuelSetting=10\n"

	uploadOneFile("session01.csv", []byte(csv))
	uploadOneFile("session01.svm", []byte(svm))

	listReq := httptest.NewRequest(http.MethodGet, "/api/sessions", nil)
	listReq.Header.Set("X-Client-Session-Id", headerSessionID)
	listW := httptest.NewRecorder()
	r.ServeHTTP(listW, listReq)
	if listW.Code != http.StatusOK {
		t.Fatalf("sessions expected 200, got %d: %s", listW.Code, listW.Body.String())
	}

	var listResp struct {
		Sessions []domain.SessionInfo `json:"sessions"`
	}
	if err := json.Unmarshal(listW.Body.Bytes(), &listResp); err != nil {
		t.Fatalf("decode sessions response: %v", err)
	}
	if len(listResp.Sessions) != 1 {
		t.Fatalf("expected 1 complete session, got %d", len(listResp.Sessions))
	}
	if listResp.Sessions[0].ID != "session01" {
		t.Fatalf("expected session ID session01, got %s", listResp.Sessions[0].ID)
	}

	analyzeReq := httptest.NewRequest(http.MethodPost, "/api/analyze_session", strings.NewReader("session_id=session01"))
	analyzeReq.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	analyzeReq.Header.Set("X-Client-Session-Id", headerSessionID)
	analyzeW := httptest.NewRecorder()
	r.ServeHTTP(analyzeW, analyzeReq)

	if analyzeW.Code != http.StatusOK {
		t.Fatalf("analyze_session expected 200, got %d: %s", analyzeW.Code, analyzeW.Body.String())
	}

	if !fake.called {
		t.Fatal("expected fake analyzer to be called")
	}
}
