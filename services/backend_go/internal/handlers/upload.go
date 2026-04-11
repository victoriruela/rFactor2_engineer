package handlers

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/middleware"
)

const defaultChunkSize = 32 * 1024 * 1024 // 32 MiB

type uploadState struct {
	Filename      string
	ChunkSize     int
	TotalSize     int64
	TotalChunks   int
	SessionName   string
	DestDir       string
	TempPath      string
	FinalPath     string
	Received      map[int]int64
	BytesReceived int64
}

// UploadHandler manages chunked file uploads.
type UploadHandler struct {
	DataDir string
	mu      sync.Mutex
	uploads map[string]*uploadState
}

// NewUploadHandler creates an upload handler.
func NewUploadHandler(dataDir string) *UploadHandler {
	return &UploadHandler{
		DataDir: dataDir,
		uploads: make(map[string]*uploadState),
	}
}

// InitUpload handles POST /api/uploads/init
func (h *UploadHandler) InitUpload(c *gin.Context) {
	var req struct {
		Filename  string `json:"filename" binding:"required"`
		TotalSize int64  `json:"total_size" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "filename and total_size required"})
		return
	}
	if req.TotalSize <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid total_size"})
		return
	}

	// Sanitize filename
	filename := filepath.Base(req.Filename)
	if filename == "." || filename == "/" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid filename"})
		return
	}

	sessionID := middleware.GetSessionID(c)
	uploadID := uuid.New().String()
	sessionName := strings.TrimSuffix(filename, filepath.Ext(filename))
	if sessionName == "" {
		sessionName = "session"
	}

	destDir := filepath.Join(h.DataDir, sessionID, sessionName)
	if err := os.MkdirAll(destDir, 0750); err != nil {
		log.Error().Err(err).Msg("Failed to create upload destination")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "storage error"})
		return
	}

	tempPath := filepath.Join(destDir, fmt.Sprintf(".%s.%s.part", filename, uploadID[:8]))
	finalPath := filepath.Join(destDir, filename)

	tempFile, err := os.OpenFile(tempPath, os.O_CREATE|os.O_RDWR|os.O_TRUNC, 0640)
	if err != nil {
		log.Error().Err(err).Msg("Failed to create temp upload file")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "storage error"})
		return
	}
	if err := tempFile.Truncate(req.TotalSize); err != nil {
		tempFile.Close()
		_ = os.Remove(tempPath)
		log.Error().Err(err).Msg("Failed to preallocate temp upload file")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "storage error"})
		return
	}
	_ = tempFile.Close()

	totalChunks := int((req.TotalSize + int64(defaultChunkSize) - 1) / int64(defaultChunkSize))

	h.mu.Lock()
	h.uploads[uploadID] = &uploadState{
		Filename:    filename,
		ChunkSize:   defaultChunkSize,
		TotalSize:   req.TotalSize,
		TotalChunks: totalChunks,
		SessionName: sessionName,
		DestDir:     destDir,
		TempPath:    tempPath,
		FinalPath:   finalPath,
		Received:    make(map[int]int64, totalChunks),
	}
	h.mu.Unlock()

	c.JSON(http.StatusOK, domain.UploadInit{
		UploadID:  uploadID,
		ChunkSize: defaultChunkSize,
		Filename:  filename,
	})
}

// UploadChunk handles PUT /api/uploads/:upload_id/chunk
func (h *UploadHandler) UploadChunk(c *gin.Context) {
	uploadID := c.Param("upload_id")
	chunkIndexStr := c.Query("chunk_index")
	chunkIndex, err := strconv.Atoi(chunkIndexStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid chunk_index"})
		return
	}

	h.mu.Lock()
	state, ok := h.uploads[uploadID]
	h.mu.Unlock()

	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "upload not found"})
		return
	}

	if chunkIndex < 0 || chunkIndex >= state.TotalChunks {
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("chunk_index out of range: %d", chunkIndex)})
		return
	}

	h.mu.Lock()
	if existingBytes, exists := state.Received[chunkIndex]; exists {
		h.mu.Unlock()
		c.JSON(http.StatusOK, domain.ChunkResponse{
			UploadID:      uploadID,
			ChunkIndex:    chunkIndex,
			BytesReceived: existingBytes,
		})
		return
	}
	h.mu.Unlock()

	f, err := os.OpenFile(state.TempPath, os.O_WRONLY, 0640)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "storage error"})
		return
	}
	defer f.Close()

	offset := int64(chunkIndex) * int64(state.ChunkSize)
	if _, err := f.Seek(offset, io.SeekStart); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "write error"})
		return
	}

	n, err := io.Copy(f, c.Request.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "write error"})
		return
	}

	expectedBytes := int64(state.ChunkSize)
	remaining := state.TotalSize - offset
	if remaining < expectedBytes {
		expectedBytes = remaining
	}
	if n != expectedBytes {
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("invalid chunk size for index %d: got %d expected %d", chunkIndex, n, expectedBytes)})
		return
	}

	h.mu.Lock()
	if _, exists := state.Received[chunkIndex]; !exists {
		state.Received[chunkIndex] = n
		state.BytesReceived += n
	}
	h.mu.Unlock()

	c.JSON(http.StatusOK, domain.ChunkResponse{
		UploadID:      uploadID,
		ChunkIndex:    chunkIndex,
		BytesReceived: n,
	})
}

// CompleteUpload handles POST /api/uploads/:upload_id/complete
func (h *UploadHandler) CompleteUpload(c *gin.Context) {
	uploadID := c.Param("upload_id")

	h.mu.Lock()
	state, ok := h.uploads[uploadID]
	h.mu.Unlock()

	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "upload not found"})
		return
	}

	if len(state.Received) != state.TotalChunks {
		c.JSON(http.StatusConflict, gin.H{
			"error": fmt.Sprintf("upload incomplete: received %d/%d chunks", len(state.Received), state.TotalChunks),
		})
		return
	}

	if err := os.Remove(state.FinalPath); err != nil && !os.IsNotExist(err) {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "finalize error"})
		return
	}

	if err := os.Rename(state.TempPath, state.FinalPath); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "finalize error"})
		return
	}

	h.mu.Lock()
	delete(h.uploads, uploadID)
	h.mu.Unlock()

	c.JSON(http.StatusOK, domain.CompleteResponse{
		Filename:      state.Filename,
		SessionID:     state.SessionName,
		BytesReceived: state.BytesReceived,
	})
}
