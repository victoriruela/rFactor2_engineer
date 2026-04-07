package handlers

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/parsers"
)

// GetSetup handles GET /api/setup/:sessionId — retrieves the full setup from the SVM file.
// This allows the frontend to display the setup immediately after uploading files,
// without running the full analysis.
func (h *AnalysisHandler) GetSetup(c *gin.Context) {
	sessionID := c.Param("sessionId")
	if sessionID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "sessionId required"})
		return
	}

	sessDir := filepath.Join(h.DataDir, sessionID)
	entries, err := os.ReadDir(sessDir)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}

	// Find the SVM file in the first session subdirectory
	var svmPath string
	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}
		subDir := filepath.Join(sessDir, entry.Name())
		subEntries, err := os.ReadDir(subDir)
		if err != nil {
			continue
		}
		for _, f := range subEntries {
			if strings.HasSuffix(f.Name(), ".svm") {
				svmPath = filepath.Join(subDir, f.Name())
				break
			}
		}
		if svmPath != "" {
			break
		}
	}

	if svmPath == "" {
		c.JSON(http.StatusNotFound, gin.H{"error": "SVM file not found in session"})
		return
	}

	// Parse SVM and extract full setup
	setup, err := parsers.ParseSVMFile(svmPath)
	if err != nil {
		log.Error().Err(err).Str("path", svmPath).Msg("Failed to parse SVM")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to parse setup file"})
		return
	}

	// Convert setup to the response format (sections with full parameters)
	fullSetup := make(map[string][]domain.SetupChange)
	for section, setupSection := range setup.Sections {
		if setupSection == nil {
			continue
		}
		for paramName, paramValue := range setupSection.Params {
			fullSetup[section] = append(fullSetup[section], domain.SetupChange{
				Parameter: paramName,
				OldValue:  paramValue,
				NewValue:  "",
				Reason:    "",
				ChangePct: "",
			})
		}
	}

	c.JSON(http.StatusOK, gin.H{"full_setup": fullSetup})
}
