package auth

import (
	"fmt"
	"net/smtp"
	"strings"

	"github.com/rs/zerolog/log"
)

// SMTPConfig holds email sending configuration.
type SMTPConfig struct {
	Host string
	Port string
	User string
	Pass string
	From string
}

// IsConfigured returns true when all SMTP fields are set.
func (c *SMTPConfig) IsConfigured() bool {
	return c.Host != "" && c.Port != "" && c.User != "" && c.Pass != "" && c.From != ""
}

// SendVerificationEmail sends the 6-digit code to the user's email.
// Returns the code so that callers without SMTP config can fall back to returning it directly.
func SendVerificationEmail(cfg *SMTPConfig, toEmail, code string) error {
	if !cfg.IsConfigured() {
		log.Warn().Str("email", toEmail).Str("code", code).Msg("SMTP not configured — code logged instead of emailed")
		return nil // non-fatal: dev mode
	}

	subject := "rFactor2 Engineer — Código de verificación"
	body := fmt.Sprintf("Tu código de verificación es: %s\n\nExpira en 15 minutos.", code)

	msg := strings.Join([]string{
		"From: " + cfg.From,
		"To: " + toEmail,
		"Subject: " + subject,
		"MIME-Version: 1.0",
		"Content-Type: text/plain; charset=UTF-8",
		"",
		body,
	}, "\r\n")

	auth := smtp.PlainAuth("", cfg.User, cfg.Pass, cfg.Host)
	addr := cfg.Host + ":" + cfg.Port
	if err := smtp.SendMail(addr, auth, cfg.From, []string{toEmail}, []byte(msg)); err != nil {
		return fmt.Errorf("smtp send: %w", err)
	}
	return nil
}
