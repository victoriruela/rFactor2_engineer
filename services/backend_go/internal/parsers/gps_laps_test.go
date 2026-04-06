package parsers_test

import (
	"testing"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/parsers"
)

func TestSmoothGPS(t *testing.T) {
	// Build simple data with an outlier
	data := make([]float64, 50)
	for i := range data {
		data[i] = 41.57 + float64(i)*0.0001
	}
	// Inject outlier
	data[25] = 99.0

	smoothed := parsers.SmoothGPS(data)

	if len(smoothed) != len(data) {
		t.Fatalf("expected %d points, got %d", len(data), len(smoothed))
	}

	// The outlier should be smoothed away
	if smoothed[25] > 50 {
		t.Errorf("outlier not smoothed: val=%f", smoothed[25])
	}
}

func TestFilterIncompleteLaps(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap",
		TimeCol: "Time",
		Channels: map[string][]float64{
			"Lap":  {0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3},
			"Time": {0, 1, 2, 3, 92, 93, 94, 185, 186, 187, 280},
		},
	}

	parsers.FilterIncompleteLaps(td)

	// Lap 0 should be excluded
	laps := td.Channels[td.LapCol]
	for _, l := range laps {
		if l == 0 {
			t.Error("lap 0 should be filtered out")
		}
	}
}
