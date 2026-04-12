package auth

import (
	"crypto/rand"
	"database/sql"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"golang.org/x/crypto/bcrypt"
)

// Handlers groups all auth-related HTTP handlers.
type Handlers struct {
	DB        *DB
	JWTSecret string
	SMTP      *SMTPConfig
}

// NewHandlers creates a Handlers instance.
func NewHandlers(db *DB, jwtSecret string, smtp SMTPConfig) *Handlers {
	return &Handlers{DB: db, JWTSecret: jwtSecret, SMTP: &smtp}
}

type registerRequest struct {
	Username string `json:"username" binding:"required"`
	Email    string `json:"email" binding:"required"`
	Password string `json:"password" binding:"required"`
}

type verifyRequest struct {
	Email string `json:"email" binding:"required"`
	Code  string `json:"code" binding:"required"`
}

type loginRequest struct {
	Username string `json:"username" binding:"required"`
	Password string `json:"password" binding:"required"`
}

type configRequest struct {
	OllamaAPIKey     string   `json:"ollama_api_key"`
	OllamaModel      string   `json:"ollama_model"`
	LockedParameters []string `json:"locked_parameters,omitempty"`
}

func randomCode() string {
	b := make([]byte, 3)
	rand.Read(b)
	return fmt.Sprintf("%06d", (int(b[0])<<16|int(b[1])<<8|int(b[2]))%1000000)
}

// Register handles POST /api/auth/register
func (h *Handlers) Register(c *gin.Context) {
	var req registerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Faltan campos obligatorios (username, email, password)"})
		return
	}

	req.Username = strings.TrimSpace(req.Username)
	req.Email = strings.TrimSpace(strings.ToLower(req.Email))

	if len(req.Username) < 3 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "El nombre de usuario debe tener al menos 3 caracteres"})
		return
	}
	if len(req.Password) < 8 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "La contraseña debe tener al menos 8 caracteres"})
		return
	}
	if !strings.Contains(req.Email, "@") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Email inválido"})
		return
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Error interno"})
		return
	}

	if err := h.DB.CreateUser(req.Username, req.Email, string(hash)); err != nil {
		if strings.Contains(err.Error(), "UNIQUE") {
			c.JSON(http.StatusConflict, gin.H{"error": "El usuario o email ya están registrados"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Error creando usuario"})
		return
	}

	code := randomCode()
	expiresAt := time.Now().Add(15 * time.Minute).UTC().Format("2006-01-02 15:04:05")
	h.DB.SaveVerificationCode(req.Email, code, expiresAt)

	_ = SendVerificationEmail(h.SMTP, req.Email, code)

	resp := gin.H{"message": "Registro exitoso. Revisa tu email para el código de verificación."}
	if !h.SMTP.IsConfigured() {
		resp["code"] = code // dev fallback — matches AuthRegisterResponse.code on frontend
	}
	c.JSON(http.StatusCreated, resp)
}

// Verify handles POST /api/auth/verify
func (h *Handlers) Verify(c *gin.Context) {
	var req verifyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Faltan campos obligatorios (email, code)"})
		return
	}
	req.Email = strings.TrimSpace(strings.ToLower(req.Email))

	valid, err := h.DB.CheckVerificationCode(req.Email, strings.TrimSpace(req.Code))
	if err != nil || !valid {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Código inválido o expirado"})
		return
	}

	if err := h.DB.VerifyUser(req.Email); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Error verificando usuario"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Email verificado correctamente. Ya puedes iniciar sesión."})
}

// Login handles POST /api/auth/login
func (h *Handlers) Login(c *gin.Context) {
	var req loginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Faltan campos obligatorios (username, password)"})
		return
	}

	user, err := h.DB.GetUserByUsername(strings.TrimSpace(req.Username))
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Usuario o contraseña incorrectos"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Error interno"})
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Usuario o contraseña incorrectos"})
		return
	}

	if !user.IsVerified {
		c.JSON(http.StatusForbidden, gin.H{"error": "Cuenta no verificada. Revisa tu email."})
		return
	}

	token, err := GenerateToken(h.JWTSecret, user.ID, user.Username, user.IsAdmin)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Error generando token"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"token":              token,
		"username":           user.Username,
		"is_admin":           user.IsAdmin,
		"ollama_api_key":     user.OllamaAPIKey,
		"ollama_model":       user.OllamaModel,
		"locked_parameters": user.LockedParameters,
	})
}

// UpdateConfig handles PUT /api/auth/config (protected)
func (h *Handlers) UpdateConfig(c *gin.Context) {
	claims, exists := c.Get("auth_claims")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "No autorizado"})
		return
	}
	cl := claims.(*Claims)

	var req configRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Payload inválido"})
		return
	}

	if err := h.DB.UpdateConfig(cl.UserID, strings.TrimSpace(req.OllamaAPIKey), strings.TrimSpace(req.OllamaModel), req.LockedParameters); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Error guardando configuración"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Configuración guardada"})
}
