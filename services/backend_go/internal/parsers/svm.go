package parsers

import (
	"bufio"
	"os"
	"strings"

	"golang.org/x/text/encoding/unicode"
	"golang.org/x/text/transform"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

// ParseSVMFile parses an rFactor 2 .svm setup file (INI-like format).
// Tries UTF-16 first (common for rF2), falls back to UTF-8.
func ParseSVMFile(path string) (*domain.Setup, error) {
	lines, err := readSVMLines(path)
	if err != nil {
		return nil, err
	}

	setup := domain.NewSetup()
	var currentSection string

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			currentSection = line[1 : len(line)-1]
			setup.Sections[currentSection] = &domain.SetupSection{
				Name:   currentSection,
				Params: make(map[string]string),
			}
			continue
		}

		// Check for active (non-commented) key=value
		if !strings.HasPrefix(line, "//") {
			if idx := strings.IndexByte(line, '='); idx > 0 && currentSection != "" {
				key := strings.TrimSpace(line[:idx])
				value := strings.TrimSpace(line[idx+1:])
				if sec, ok := setup.Sections[currentSection]; ok {
					sec.Params[key] = value
				}
			}
			continue
		}

		// Commented-out line: check if it is a setting (//Key=value pattern)
		remainder := strings.TrimPrefix(line, "//")
		if idx := strings.IndexByte(remainder, '='); idx > 0 && currentSection != "" {
			key := strings.TrimSpace(remainder[:idx])
			// Accept only identifier-like keys (letters + digits, typically ending in "Setting")
			if isSettingKey(key) {
				value := strings.TrimSpace(remainder[idx+1:])
				if sec, ok := setup.Sections[currentSection]; ok {
					// Only add if not already present from an active line
					if _, exists := sec.Params[key]; !exists {
						sec.Params[key] = value
						sec.ReadOnlyParams = append(sec.ReadOnlyParams, key)
					}
				}
			}
		}
	}

	if len(setup.Sections) == 0 {
		return nil, ErrEmptySetup
	}

	return setup, nil
}

// isSettingKey checks whether a raw key string looks like a valid rF2 setting identifier.
// Valid keys start with an uppercase letter and contain only alphanumeric characters.
func isSettingKey(key string) bool {
	if len(key) == 0 || key[0] < 'A' || key[0] > 'Z' {
		return false
	}
	for _, c := range key {
		if !((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) {
			return false
		}
	}
	return true
}

// CleanValue extracts the display value from an SVM parameter.
// e.g. "223//N/mm" returns "N/mm", "42" returns "42".
func CleanValue(raw string) string {
	if idx := strings.Index(raw, "//"); idx >= 0 {
		return strings.TrimSpace(raw[idx+2:])
	}
	return strings.TrimSpace(raw)
}

// RawNumericValue extracts the numeric prefix from an SVM value.
// e.g. "223//N/mm" returns "223".
func RawNumericValue(raw string) string {
	if idx := strings.Index(raw, "//"); idx >= 0 {
		return strings.TrimSpace(raw[:idx])
	}
	return strings.TrimSpace(raw)
}

func readSVMLines(path string) ([]string, error) {
	// Try UTF-16 first
	lines, err := readLinesUTF16(path)
	if err == nil && len(lines) > 0 {
		// Validate: at least one line should look like a section header or key=value
		for _, l := range lines {
			l = strings.TrimSpace(l)
			if strings.HasPrefix(l, "[") || strings.Contains(l, "=") {
				return lines, nil
			}
		}
	}

	// Fall back to UTF-8
	return readLinesUTF8(path)
}

func readLinesUTF16(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	decoder := unicode.UTF16(unicode.LittleEndian, unicode.UseBOM).NewDecoder()
	reader := transform.NewReader(f, decoder)
	scanner := bufio.NewScanner(reader)

	var lines []string
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return lines, nil
}

func readLinesUTF8(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	var lines []string
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return lines, nil
}
