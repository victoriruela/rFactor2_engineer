package domain_test

import (
	"testing"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

func TestTelemetryData_SessionStats(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap",
		TimeCol: "Time",
		Channels: map[string][]float64{
			"Lap":   {1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3},
			"Time":  {0, 30, 60, 90, 91, 121, 151, 181, 182, 212, 242, 278},
			"Speed": {100, 150, 120, 130, 110, 160, 125, 135, 105, 155, 118, 128},
		},
	}

	stats := td.SessionStats()

	if stats.TotalLaps == 0 {
		t.Error("expected non-zero total laps")
	}
	if stats.BestLapTime <= 0 {
		t.Error("expected positive best lap time")
	}
	if stats.AvgLapTime <= 0 {
		t.Error("expected positive avg lap time")
	}
}

func TestTelemetryData_SessionStats_NoValidLapsReturnsZeroValues(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap",
		TimeCol: "Time",
		Channels: map[string][]float64{
			"Lap":  {1},
			"Time": {0},
		},
	}

	stats := td.SessionStats()

	if stats.TotalLaps != 0 {
		t.Fatalf("expected zero laps, got %d", stats.TotalLaps)
	}
	if stats.BestLapTime != 0 {
		t.Fatalf("expected best lap 0, got %f", stats.BestLapTime)
	}
	if stats.AvgLapTime != 0 {
		t.Fatalf("expected avg lap 0, got %f", stats.AvgLapTime)
	}
}

func TestTelemetryData_ExtractTimeSeries_UsesChannelAliases(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap_Number",
		TimeCol: "Session_Elapsed_Time",
		Channels: map[string][]float64{
			"Lap_Number":           {1, 1},
			"Session_Elapsed_Time": {10, 10.5},
			"Ground_Speed":         {100, 110},
			"Throttle_Pos":         {0.4, 0.6},
			"Brake_Pos":            {0.1, 0.0},
			"Engine_RPM":           {7000, 7200},
			"Gear":                 {3, 4},
			"GPS Latitude":         {41.0, 41.1},
			"GPS Longitude":        {2.0, 2.1},
		},
	}

	series := td.ExtractTimeSeries()
	if len(series) != 2 {
		t.Fatalf("expected 2 samples, got %d", len(series))
	}
	if series[1].Spd != 110 || series[1].Thr != 0.6 || series[1].RPM != 7200 {
		t.Fatalf("unexpected aliased telemetry sample: %+v", series[1])
	}
	if series[1].Lat != 41.1 || series[1].Lon != 2.1 {
		t.Fatalf("unexpected aliased GPS sample: %+v", series[1])
	}
}

func TestTelemetryData_ExtractGPS(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap",
		TimeCol: "Time",
		Channels: map[string][]float64{
			"Lap":           {1, 1, 1},
			"Time":          {0, 1, 2},
			"GPS_Latitude":  {41.57, 41.571, 41.572},
			"GPS_Longitude": {2.26, 2.261, 2.262},
		},
	}

	points := td.ExtractGPS()
	if len(points) != 3 {
		t.Errorf("expected 3 GPS points, got %d", len(points))
	}
}

func TestTelemetryData_ExtractGPS_NoGPSChannels(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap",
		TimeCol: "Time",
		Channels: map[string][]float64{
			"Lap":   {1, 1},
			"Time":  {0, 1},
			"Speed": {100, 110},
		},
	}

	points := td.ExtractGPS()
	if points != nil {
		t.Errorf("expected nil GPS points, got %d", len(points))
	}
}

func TestTelemetryData_ExtractTimeSeries_PreservesValidGPSJumps(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap_Number",
		TimeCol: "Session_Elapsed_Time",
		Channels: map[string][]float64{
			"Lap_Number":           {1, 1, 1, 1, 1},
			"Session_Elapsed_Time": {0, 1, 2, 3, 4},
			"Speed":                {100, 101, 102, 103, 104},
			"GPS Latitude":         {41.0000, 41.0001, 60.0, 41.0002, 41.0003},
			"GPS Longitude":        {2.0000, 2.0001, 80.0, 2.0002, 2.0003},
		},
	}

	series := td.ExtractTimeSeries()
	if len(series) != 5 {
		t.Fatalf("expected 5 samples, got %d", len(series))
	}
	if series[2].Lat != 60.0 || series[2].Lon != 80.0 {
		t.Fatalf("expected valid in-range GPS sample to be preserved, got lat=%f lon=%f", series[2].Lat, series[2].Lon)
	}
}

func TestTelemetryData_ExtractTimeSeries_ReplacesInvalidGPSValues(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap_Number",
		TimeCol: "Session_Elapsed_Time",
		Channels: map[string][]float64{
			"Lap_Number":           {1, 1, 1, 1},
			"Session_Elapsed_Time": {0, 1, 2, 3},
			"Speed":                {100, 101, 102, 103},
			"GPS Latitude":         {41.0000, 41.0001, 999.0, 41.0002},
			"GPS Longitude":        {2.0000, 2.0001, 500.0, 2.0002},
		},
	}

	series := td.ExtractTimeSeries()
	if len(series) != 4 {
		t.Fatalf("expected 4 samples, got %d", len(series))
	}
	if series[2].Lat != series[1].Lat || series[2].Lon != series[1].Lon {
		t.Fatalf("expected invalid GPS sample to be replaced with previous valid value, got lat=%f lon=%f", series[2].Lat, series[2].Lon)
	}
}

func TestTelemetryData_SessionStats_UsesLapTimeChannelPrecision(t *testing.T) {
	td := &domain.TelemetryData{
		LapCol:  "Lap",
		TimeCol: "Session_Elapsed_Time",
		Channels: map[string][]float64{
			"Lap":                  {1, 1, 1, 2, 2, 2},
			"Session_Elapsed_Time": {0, 10, 20, 20, 30, 40},
			"Lap_Time":             {0.1, 10.2, 87.518, 0.2, 10.0, 88.777},
		},
	}

	stats := td.SessionStats()
	if stats.TotalLaps != 2 {
		t.Fatalf("expected 2 laps, got %d", stats.TotalLaps)
	}

	gotLap1 := 0.0
	gotLap2 := 0.0
	for _, l := range stats.Laps {
		if l.Lap == 1 {
			gotLap1 = l.Duration
		}
		if l.Lap == 2 {
			gotLap2 = l.Duration
		}
	}

	if gotLap1 != 87.518 {
		t.Fatalf("expected lap 1 duration 87.518, got %.3f", gotLap1)
	}
	if gotLap2 != 88.777 {
		t.Fatalf("expected lap 2 duration 88.777, got %.3f", gotLap2)
	}
}

func TestSetup_NewSetup(t *testing.T) {
	s := domain.NewSetup()
	if s == nil {
		t.Fatal("NewSetup returned nil")
	}
	if s.Sections == nil {
		t.Error("Sections should be initialized")
	}
}
