package parsers_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/viciruela/rfactor2-engineer/internal/parsers"
)

func TestParseSVMFile_ValidFile(t *testing.T) {
	// Create a temp SVM file
	content := "[BASIC]\nVehicle=Test Car\nTrack=Test Track\n\n[SUSPENSION]\nFrontAntiRollBar=10000\nRearAntiRollBar=8000\n\n[FRONTLEFT]\nSpringRate=150000\nSlowBump=5000\n"

	dir := t.TempDir()
	path := filepath.Join(dir, "test.svm")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	setup, err := parsers.ParseSVMFile(path)
	if err != nil {
		t.Fatalf("ParseSVMFile: %v", err)
	}

	if len(setup.Sections) == 0 {
		t.Fatal("expected non-empty sections")
	}

	// Check SUSPENSION section
	found := false
	for _, s := range setup.Sections {
		if s.Name == "SUSPENSION" {
			found = true
			if v, ok := s.Params["FrontAntiRollBar"]; !ok || v != "10000" {
				t.Errorf("expected FrontAntiRollBar=10000, got %q", v)
			}
		}
	}
	if !found {
		t.Error("SUSPENSION section not found")
	}
}

func TestParseSVMFile_EmptyFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "empty.svm")
	if err := os.WriteFile(path, []byte(""), 0o644); err != nil {
		t.Fatal(err)
	}

	_, err := parsers.ParseSVMFile(path)
	if err == nil {
		t.Error("expected error for empty SVM file")
	}
}

func TestCleanValue(t *testing.T) {
	tests := []struct {
		input, want string
	}{
		{"10000", "10000"},
		{"10000 // Front anti-roll bar", "Front anti-roll bar"},
		{" 5000 ", "5000"},
		{"150000//spring rate", "spring rate"},
	}

	for _, tt := range tests {
		got := parsers.CleanValue(tt.input)
		if got != tt.want {
			t.Errorf("CleanValue(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestRawNumericValue(t *testing.T) {
	tests := []struct {
		input, want string
	}{
		{"10000", "10000"},
		{"10000 // Front anti-roll bar", "10000"},
		{"150000//spring rate", "150000"},
	}

	for _, tt := range tests {
		got := parsers.RawNumericValue(tt.input)
		if got != tt.want {
			t.Errorf("RawNumericValue(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestParseSVMFile_NonExistent(t *testing.T) {
	_, err := parsers.ParseSVMFile("/nonexistent/file.svm")
	if err == nil {
		t.Error("expected error for non-existent file")
	}
}

func TestParseCSVFromReader(t *testing.T) {
	// Build a minimal MoTeC CSV-like content (14 header lines + data)
	var sb strings.Builder
	for i := 0; i < 14; i++ {
		sb.WriteString("header line\n")
	}
	sb.WriteString("Time,Speed,Lap\n")
	sb.WriteString("0.001,120.5,1\n")
	sb.WriteString("0.002,121.0,1\n")
	sb.WriteString("0.003,119.8,2\n")

	reader := strings.NewReader(sb.String())
	td, err := parsers.ParseCSVFromReader(reader)
	if err != nil {
		t.Fatalf("ParseCSVFromReader: %v", err)
	}

	if len(td.Channels) == 0 {
		t.Fatal("expected channels")
	}

	speed, ok := td.Channels["Speed"]
	if !ok {
		t.Fatal("Speed channel not found")
	}
	if len(speed) < 2 {
		t.Errorf("expected at least 2 Speed samples, got %d", len(speed))
	}
}

func TestParseCSVFile_NonExistent(t *testing.T) {
	_, err := parsers.ParseCSVFile("/nonexistent/file.csv")
	if err == nil {
		t.Error("expected error for non-existent file")
	}
}
