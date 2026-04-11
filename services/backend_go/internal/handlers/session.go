package handlers

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog/log"

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

// CleanupOldSessions removes sessions older than maxAge.
// Callable by background workers or explicitly for maintenance.
func (h *SessionHandler) CleanupOldSessions(maxAge time.Duration) {
	clientDirs, err := os.ReadDir(h.DataDir)
	if err != nil {
		log.Warn().Err(err).Msg("cleanup: cannot read data directory")
		return
	}

	now := time.Now()
	cleanedCount := 0
	totalSize := int64(0)

	for _, clientDir := range clientDirs {
		if !clientDir.IsDir() || strings.HasPrefix(clientDir.Name(), ".") {
			continue
		}

		clientPath := filepath.Join(h.DataDir, clientDir.Name())
		sessionDirs, err := os.ReadDir(clientPath)
		if err != nil {
			continue
		}

		for _, sessionDir := range sessionDirs {
			if !sessionDir.IsDir() || strings.HasPrefix(sessionDir.Name(), "_chunks_") {
				continue
			}

			sessionPath := filepath.Join(clientPath, sessionDir.Name())
			info, err := os.Stat(sessionPath)
			if err != nil {
				continue
			}

			// Check if session is older than maxAge
			if now.Sub(info.ModTime()) > maxAge {
				// Calculate size before deletion
				size := dirSize(sessionPath)
				totalSize += size

				// Try to delete
				if err := os.RemoveAll(sessionPath); err != nil {
					log.Warn().
						Str("session_id", sessionDir.Name()).
						Err(err).
						Msg("cleanup: failed to delete old session")
				} else {
					cleanedCount++
					log.Debug().
						Str("session_id", sessionDir.Name()).
						Int64("size_bytes", size).
						Msg("cleanup: deleted old session")
				}
			}
		}
	}

	if cleanedCount > 0 {
		log.Info().
			Int("sessions", cleanedCount).
			Int64("total_mb", totalSize / (1024 * 1024)).
			Msg("cleanup: old sessions removed")
	}
}

// dirSize returns the total size of a directory in bytes.
func dirSize(path string) int64 {
	var size int64
	filepath.Walk(path, func(_ string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() {
			size += info.Size()
		}
		return nil
	})
	return size
}
