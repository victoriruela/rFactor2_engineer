package middleware

import (
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

const SessionHeader = "X-Client-Session-Id"
const SessionCookie = "rf2_session_id"
const SessionCtxKey = "client_session_id"

// SessionResolver extracts or creates a client session ID from the request.
func SessionResolver() gin.HandlerFunc {
	return func(c *gin.Context) {
		sid := c.GetHeader(SessionHeader)
		if sid == "" {
			sid, _ = c.Cookie(SessionCookie)
		}
		if sid == "" {
			sid = uuid.New().String()
		}
		c.Set(SessionCtxKey, sid)
		c.Header(SessionHeader, sid)
		c.Next()
	}
}

// GetSessionID retrieves the session ID from the Gin context.
func GetSessionID(c *gin.Context) string {
	if v, ok := c.Get(SessionCtxKey); ok {
		return v.(string)
	}
	return ""
}
