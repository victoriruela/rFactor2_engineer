package parsers

import (
	"bufio"
	"encoding/csv"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

const (
	csvMetadataLines = 14 // First 14 lines are metadata
	csvHeaderLine    = 14 // 0-indexed line 14 = headers (line 15 in 1-indexed)
	csvUnitsLine     = 15 // 0-indexed line 15 = units
	csvDataStart     = 16 // Data starts at 0-indexed line 16 (line 17 in 1-indexed)
)

// ParseCSVFile parses a MoTeC CSV export file.
// First 14 lines are metadata, line 15 is headers, line 16 is units, data starts at line 17.
func ParseCSVFile(path string) (*domain.TelemetryData, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)

	// Skip metadata lines
	for i := 0; i < csvMetadataLines; i++ {
		if !scanner.Scan() {
			return nil, ErrNoHeaders
		}
	}

	// Read headers (line 15)
	if !scanner.Scan() {
		return nil, ErrNoHeaders
	}
	headerLine := scanner.Text()
	reader := csv.NewReader(strings.NewReader(headerLine))
	headerFields, err := reader.Read()
	if err != nil {
		return nil, ErrNoHeaders
	}

	headers := make([]string, len(headerFields))
	for i, h := range headerFields {
		headers[i] = strings.TrimSpace(h)
	}

	// Skip units line
	if !scanner.Scan() {
		return nil, ErrNoData
	}

	// Read data
	channels := make(map[string][]float64)
	for _, h := range headers {
		if h != "" {
			channels[h] = nil
		}
	}

	rowCount := 0
	for scanner.Scan() {
		line := scanner.Text()
		if strings.TrimSpace(line) == "" {
			continue
		}
		r := csv.NewReader(strings.NewReader(line))
		fields, err := r.Read()
		if err != nil {
			continue
		}

		allEmpty := true
		for i, field := range fields {
			if i >= len(headers) || headers[i] == "" {
				continue
			}
			val, err := strconv.ParseFloat(strings.TrimSpace(field), 64)
			if err != nil {
				continue
			}
			allEmpty = false
			channels[headers[i]] = append(channels[headers[i]], val)
		}

		if !allEmpty {
			rowCount++
			// Pad any channels that didn't get a value this row
			for _, h := range headers {
				if h == "" {
					continue
				}
				if len(channels[h]) < rowCount {
					channels[h] = append(channels[h], 0)
				}
			}
		}
	}

	if rowCount == 0 {
		return nil, ErrNoData
	}

	// Remove empty channels
	for k, v := range channels {
		if len(v) == 0 {
			delete(channels, k)
		}
	}

	td := &domain.TelemetryData{Channels: channels}
	detectSpecialColumns(td)

	return td, nil
}

// ParseCSVFromReader parses MoTeC CSV from an io.Reader.
func ParseCSVFromReader(r io.Reader) (*domain.TelemetryData, error) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)

	for i := 0; i < csvMetadataLines; i++ {
		if !scanner.Scan() {
			return nil, ErrNoHeaders
		}
	}

	if !scanner.Scan() {
		return nil, ErrNoHeaders
	}
	headerLine := scanner.Text()
	csvR := csv.NewReader(strings.NewReader(headerLine))
	headerFields, err := csvR.Read()
	if err != nil {
		return nil, ErrNoHeaders
	}

	headers := make([]string, len(headerFields))
	for i, h := range headerFields {
		headers[i] = strings.TrimSpace(h)
	}

	if !scanner.Scan() {
		return nil, ErrNoData
	}

	channels := make(map[string][]float64)
	for _, h := range headers {
		if h != "" {
			channels[h] = nil
		}
	}

	rowCount := 0
	for scanner.Scan() {
		line := scanner.Text()
		if strings.TrimSpace(line) == "" {
			continue
		}
		csvR := csv.NewReader(strings.NewReader(line))
		fields, err := csvR.Read()
		if err != nil {
			continue
		}
		allEmpty := true
		for i, field := range fields {
			if i >= len(headers) || headers[i] == "" {
				continue
			}
			val, err := strconv.ParseFloat(strings.TrimSpace(field), 64)
			if err != nil {
				continue
			}
			allEmpty = false
			channels[headers[i]] = append(channels[headers[i]], val)
		}
		if !allEmpty {
			rowCount++
			for _, h := range headers {
				if h == "" {
					continue
				}
				if len(channels[h]) < rowCount {
					channels[h] = append(channels[h], 0)
				}
			}
		}
	}

	if rowCount == 0 {
		return nil, ErrNoData
	}

	for k, v := range channels {
		if len(v) == 0 {
			delete(channels, k)
		}
	}

	td := &domain.TelemetryData{Channels: channels}
	detectSpecialColumns(td)
	return td, nil
}

func detectSpecialColumns(td *domain.TelemetryData) {
	for name := range td.Channels {
		lower := strings.ToLower(name)
		if strings.Contains(lower, "lap") && strings.Contains(lower, "number") {
			td.LapCol = name
		}
		if name == "Lap_Number" && td.LapCol == "" {
			td.LapCol = name
		}
		if name == "Session_Elapsed_Time" {
			td.TimeCol = name
		}
	}
}
