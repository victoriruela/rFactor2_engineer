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

const defaultChunkSize = 16 * 1024 * 1024 // 16 MiB

type uploadState struct {
	Filename  string
	ChunkSize int
	NextChunk int
	Dir       string
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
		Filename string `json:"filename" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "filename required"})
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

	dir := filepath.Join(h.DataDir, sessionID, "_chunks_"+uploadID)
	if err := os.MkdirAll(dir, 0750); err != nil {
		log.Error().Err(err).Msg("Failed to create chunk directory")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "storage error"})
		return
	}

	h.mu.Lock()
	h.uploads[uploadID] = &uploadState{
		Filename:  filename,
		ChunkSize: defaultChunkSize,
		NextChunk: 0,
		Dir:       dir,
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

	if chunkIndex != state.NextChunk {
		c.JSON(http.StatusConflict, gin.H{"error": fmt.Sprintf("expected chunk %d, got %d", state.NextChunk, chunkIndex)})
		return
	}

	chunkPath := filepath.Join(state.Dir, fmt.Sprintf("chunk_%06d", chunkIndex))
	f, err := os.Create(chunkPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "storage error"})
		return
	}
	defer f.Close()

	n, err := io.Copy(f, c.Request.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "write error"})
		return
	}

	h.mu.Lock()
	state.NextChunk++
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
	if ok {
		delete(h.uploads, uploadID)
	}
	h.mu.Unlock()

	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "upload not found"})
		return
	}

	sessionID := middleware.GetSessionID(c)
	sessionName := strings.TrimSuffix(state.Filename, filepath.Ext(state.Filename))
	if sessionName == "" {
		sessionName = "session"
	}

	destDir := filepath.Join(h.DataDir, sessionID, sessionName)
	if err := os.MkdirAll(destDir, 0750); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "storage error"})
		return
	}

	destPath := filepath.Join(destDir, state.Filename)
	dest, err := os.Create(destPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "assembly error"})
		return
	}
	defer dest.Close()

	var totalBytes int64
	for i := 0; i < state.NextChunk; i++ {
		chunkPath := filepath.Join(state.Dir, fmt.Sprintf("chunk_%06d", i))
		chunk, err := os.Open(chunkPath)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "assembly error"})
			return
		}
		n, _ := io.Copy(dest, chunk)
		totalBytes += n
		chunk.Close()
	}

	// Cleanup chunk directory
	os.RemoveAll(state.Dir)

	c.JSON(http.StatusOK, domain.CompleteResponse{
		Filename:      state.Filename,
		SessionID:     sessionName,
		BytesReceived: totalBytes,
	})
}
