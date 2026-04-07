package main

import (
	"io"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestSpaHandler_FallbackForUnknownGet(t *testing.T) {
	t.Helper()

	staticSub, err := fs.Sub(staticFS, "static")
	if err != nil {
		t.Fatalf("cannot create static sub FS: %v", err)
	}

	sub, err := staticFS.ReadFile("static/index.html")
	if err != nil {
		t.Fatalf("cannot read embedded index.html: %v", err)
	}

	r := gin.New()
	r.NoRoute(gin.WrapH(spaHandler(http.FS(staticSub))))

	req := httptest.NewRequest(http.MethodGet, "/unknown-route", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200 for unknown GET route, got %d", w.Code)
	}

	body := w.Body.String()
	if !strings.Contains(body, "<title>rFactor2 Engineer</title>") {
		t.Fatalf("expected embedded index HTML, got: %s", body)
	}

	if len(sub) == 0 {
		t.Fatal("embedded index file is empty")
	}
}

func TestSpaHandler_DoesNotHandleUnknownPost(t *testing.T) {
	staticSub, err := fs.Sub(staticFS, "static")
	if err != nil {
		t.Fatalf("cannot create static sub FS: %v", err)
	}

	r := gin.New()
	r.NoRoute(gin.WrapH(spaHandler(http.FS(staticSub))))

	req := httptest.NewRequest(http.MethodPost, "/unknown-route", strings.NewReader("payload"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for unknown POST route, got %d", w.Code)
	}

	body, _ := io.ReadAll(w.Result().Body)
	if strings.Contains(string(body), "rFactor2 Engineer") {
		t.Fatalf("unexpected SPA HTML in POST response: %s", string(body))
	}
}
