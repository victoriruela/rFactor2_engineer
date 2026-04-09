package handlers

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/middleware"
)

// SessionHandler manages session listing, downloads, and cleanup.
type SessionHandler struct {
	DataDir string
}

// NewSessionHandler creates a session handler.
func NewSessionHandler(dataDir string) *SessionHandler {
	return &SessionHandler{DataDir: dataDir}
}

// ListSessions handles GET /api/sessions
func (h *SessionHandler) ListSessions(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)
	sessDir := filepath.Join(h.DataDir, sessionID)

	entries, err := os.ReadDir(sessDir)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"sessions": []any{}})
		return
	}

	var sessions []domain.SessionInfo
	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), "_chunks_") {
			continue
		}

		subDir := filepath.Join(sessDir, entry.Name())
		subEntries, err := os.ReadDir(subDir)
		if err != nil {
			continue
		}

		var telemetry, svm string
		for _, f := range subEntries {
			name := f.Name()
			ext := strings.ToLower(filepath.Ext(name))
			switch ext {
			case ".mat", ".csv":
				telemetry = name
			case ".svm":
				svm = name
			}
		}

		if telemetry != "" && svm != "" {
			sessions = append(sessions, domain.SessionInfo{
				ID:        entry.Name(),
				Telemetry: telemetry,
				SVM:       svm,
			})
		}
	}

	if sessions == nil {
		sessions = []domain.SessionInfo{}
	}

	c.JSON(http.StatusOK, gin.H{"sessions": sessions})
}

// DownloadFile handles GET /api/sessions/:session_id/file/:filename
func (h *SessionHandler) DownloadFile(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)
	reqSessionID := c.Param("session_id")
	filename := c.Param("filename")

	// Path traversal guard
	if strings.Contains(filename, "..") || strings.Contains(filename, "/") || strings.Contains(filename, "\\") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid filename"})
		return
	}

	filePath := filepath.Join(h.DataDir, sessionID, reqSessionID, filename)

	// Verify the file is within the expected directory
	absPath, err := filepath.Abs(filePath)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid path"})
		return
	}
	absDataDir, _ := filepath.Abs(filepath.Join(h.DataDir, sessionID))
	if !strings.HasPrefix(absPath, absDataDir) {
		c.JSON(http.StatusForbidden, gin.H{"error": "access denied"})
		return
	}

	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		c.JSON(http.StatusNotFound, gin.H{"error": "file not found"})
		return
	}

	c.File(filePath)
}

// Cleanup handles POST /api/cleanup
func (h *SessionHandler) Cleanup(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)
	sessDir := filepath.Join(h.DataDir, sessionID)

	if err := os.RemoveAll(sessDir); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cleanup failed"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "cleaned"})
}

// CleanupAll handles POST /api/cleanup_all
func (h *SessionHandler) CleanupAll(c *gin.Context) {
	sessionID := middleware.GetSessionID(c)
	sessDir := filepath.Join(h.DataDir, sessionID)

	if err := os.RemoveAll(sessDir); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cleanup failed"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "cleaned"})
}

// DeleteSession handles DELETE /api/sessions/:session_id
func (h *SessionHandler) DeleteSession(c *gin.Context) {
	clientSessionID := middleware.GetSessionID(c)
	targetID := c.Param("session_id")

	// Path traversal guard
	if strings.Contains(targetID, "..") || strings.Contains(targetID, "/") || strings.Contains(targetID, "\\") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid session id"})
		return
	}

	sessDir := filepath.Join(h.DataDir, clientSessionID, targetID)

	// Verify path is within expected directory
	absPath, err := filepath.Abs(sessDir)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid path"})
		return
	}
	absDataDir, _ := filepath.Abs(filepath.Join(h.DataDir, clientSessionID))
	if !strings.HasPrefix(absPath, absDataDir) {
		c.JSON(http.StatusForbidden, gin.H{"error": "access denied"})
		return
	}

	if _, err := os.Stat(sessDir); os.IsNotExist(err) {
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}

	if err := os.RemoveAll(sessDir); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "delete failed"})
		return
	}

	c.Status(http.StatusNoContent)
}
