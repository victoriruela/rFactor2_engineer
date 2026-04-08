package middleware

import (
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

// CORSMiddleware returns a CORS middleware configured for development and production.
func CORSMiddleware() gin.HandlerFunc {
	return cors.New(cors.Config{
		AllowOrigins:     []string{"http://localhost:8081", "http://localhost:19006", "https://car-setup.com", "https://telemetria.bot.nu"},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept", SessionHeader},
		ExposeHeaders:    []string{SessionHeader},
		AllowCredentials: true,
	})
}
