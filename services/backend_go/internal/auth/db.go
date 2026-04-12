package auth

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"path/filepath"

	_ "modernc.org/sqlite"

	"github.com/rs/zerolog/log"
	"golang.org/x/crypto/bcrypt"
)

// DB wraps the SQLite connection used for user management.
type DB struct {
	conn *sql.DB
}

// OpenDB opens (or creates) the user database inside dataDir.
func OpenDB(dataDir string) (*DB, error) {
	dbPath := filepath.Join(dataDir, "rf2_users.db")
	conn, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}
	// WAL mode for better concurrency.
	if _, err := conn.Exec("PRAGMA journal_mode=WAL"); err != nil {
		conn.Close()
		return nil, fmt.Errorf("pragma wal: %w", err)
	}
	db := &DB{conn: conn}
	if err := db.migrate(); err != nil {
		conn.Close()
		return nil, err
	}
	return db, nil
}

func (d *DB) Close() error { return d.conn.Close() }

func (d *DB) migrate() error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS users (
			id               INTEGER PRIMARY KEY AUTOINCREMENT,
			username         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
			email            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
			password_hash    TEXT    NOT NULL,
			is_verified      INTEGER NOT NULL DEFAULT 0,
			is_admin         INTEGER NOT NULL DEFAULT 0,
			ollama_api_key   TEXT    NOT NULL DEFAULT '',
			ollama_model     TEXT    NOT NULL DEFAULT '',
			created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS verification_codes (
			email      TEXT     NOT NULL,
			code       TEXT     NOT NULL,
			expires_at DATETIME NOT NULL
		)`,
	}
	for _, s := range stmts {
		if _, err := d.conn.Exec(s); err != nil {
			return fmt.Errorf("migrate: %w", err)
		}
	}
	// Idempotent column additions for existing databases.
	_, _ = d.conn.Exec("ALTER TABLE users ADD COLUMN locked_parameters TEXT NOT NULL DEFAULT '[]'")
	return nil
}

// SeedAdmin ensures the admin user exists.
func (d *DB) SeedAdmin(username, password string) error {
	var exists int
	if err := d.conn.QueryRow("SELECT COUNT(*) FROM users WHERE username = ?", username).Scan(&exists); err != nil {
		return err
	}
	if exists > 0 {
		return nil
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return err
	}
	_, err = d.conn.Exec(
		"INSERT INTO users (username, email, password_hash, is_verified, is_admin) VALUES (?, ?, ?, 1, 1)",
		username, username+"@admin.local", string(hash),
	)
	if err != nil {
		return err
	}
	log.Info().Str("username", username).Msg("admin user seeded")
	return nil
}

// User represents a row from the users table.
type User struct {
	ID               int64
	Username         string
	Email            string
	PasswordHash     string
	IsVerified       bool
	IsAdmin          bool
	OllamaAPIKey     string
	OllamaModel      string
	LockedParameters []string
}

func (d *DB) CreateUser(username, email, passwordHash string) error {
	_, err := d.conn.Exec(
		"INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
		username, email, passwordHash,
	)
	return err
}

func (d *DB) GetUserByUsername(username string) (*User, error) {
	u := &User{}
	var verified, admin int
	var lockedJSON string
	err := d.conn.QueryRow(
		"SELECT id, username, email, password_hash, is_verified, is_admin, ollama_api_key, ollama_model, locked_parameters FROM users WHERE username = ?",
		username,
	).Scan(&u.ID, &u.Username, &u.Email, &u.PasswordHash, &verified, &admin, &u.OllamaAPIKey, &u.OllamaModel, &lockedJSON)
	if err != nil {
		return nil, err
	}
	u.IsVerified = verified == 1
	u.IsAdmin = admin == 1
	_ = json.Unmarshal([]byte(lockedJSON), &u.LockedParameters)
	if u.LockedParameters == nil {
		u.LockedParameters = []string{}
	}
	return u, nil
}

func (d *DB) GetUserByEmail(email string) (*User, error) {
	u := &User{}
	var verified, admin int
	var lockedJSON string
	err := d.conn.QueryRow(
		"SELECT id, username, email, password_hash, is_verified, is_admin, ollama_api_key, ollama_model, locked_parameters FROM users WHERE email = ?",
		email,
	).Scan(&u.ID, &u.Username, &u.Email, &u.PasswordHash, &verified, &admin, &u.OllamaAPIKey, &u.OllamaModel, &lockedJSON)
	if err != nil {
		return nil, err
	}
	u.IsVerified = verified == 1
	u.IsAdmin = admin == 1
	_ = json.Unmarshal([]byte(lockedJSON), &u.LockedParameters)
	if u.LockedParameters == nil {
		u.LockedParameters = []string{}
	}
	return u, nil
}

func (d *DB) VerifyUser(email string) error {
	_, err := d.conn.Exec("UPDATE users SET is_verified = 1 WHERE email = ?", email)
	return err
}

func (d *DB) UpdateConfig(userID int64, apiKey, model string, lockedParameters []string) error {
	if lockedParameters == nil {
		lockedParameters = []string{}
	}
	lockedJSON, err := json.Marshal(lockedParameters)
	if err != nil {
		return fmt.Errorf("marshal locked_parameters: %w", err)
	}
	_, err = d.conn.Exec(
		"UPDATE users SET ollama_api_key = ?, ollama_model = ?, locked_parameters = ? WHERE id = ?",
		apiKey, model, string(lockedJSON), userID,
	)
	return err
}

func (d *DB) SaveVerificationCode(email, code string, expiresAt string) error {
	// Remove old codes for this email first.
	d.conn.Exec("DELETE FROM verification_codes WHERE email = ?", email)
	_, err := d.conn.Exec("INSERT INTO verification_codes (email, code, expires_at) VALUES (?, ?, ?)", email, code, expiresAt)
	return err
}

func (d *DB) CheckVerificationCode(email, code string) (bool, error) {
	var count int
	err := d.conn.QueryRow(
		"SELECT COUNT(*) FROM verification_codes WHERE email = ? AND code = ? AND expires_at > datetime('now')",
		email, code,
	).Scan(&count)
	if err != nil {
		return false, err
	}
	if count > 0 {
		d.conn.Exec("DELETE FROM verification_codes WHERE email = ?", email)
	}
	return count > 0, nil
}
