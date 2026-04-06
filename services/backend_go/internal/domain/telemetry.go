package domain

// TelemetryData holds parsed telemetry channels keyed by name.
type TelemetryData struct {
	Channels map[string][]float64
	LapCol   string
	TimeCol  string
}

// GPSPoint represents a single GPS coordinate.
type GPSPoint struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

// LapStats holds per-lap statistics.
type LapStats struct {
	Lap         int     `json:"lap"`
	Duration    float64 `json:"duration"`
	AvgSpeed    float64 `json:"avg_speed"`
	MaxSpeed    float64 `json:"max_speed"`
	AvgThrottle float64 `json:"avg_throttle"`
	AvgBrake    float64 `json:"avg_brake"`
	AvgRPM      float64 `json:"avg_rpm"`
}

// SessionStats holds aggregated session information.
type SessionStats struct {
	CircuitName string     `json:"circuit_name"`
	TotalLaps   int        `json:"total_laps"`
	BestLapTime float64    `json:"best_lap_time"`
	AvgLapTime  float64    `json:"avg_lap_time"`
	Laps        []LapStats `json:"laps"`
}

// SessionStats computes aggregated stats from the telemetry data.
func (td *TelemetryData) SessionStats() SessionStats {
	lapData, ok := td.Channels[td.LapCol]
	timeData, tok := td.Channels[td.TimeCol]
	if !ok || !tok || len(lapData) == 0 {
		return SessionStats{}
	}

	lapTimes := make(map[int][]float64)
	for i, lv := range lapData {
		lap := int(lv)
		if lap <= 0 {
			continue
		}
		if i < len(timeData) {
			lapTimes[lap] = append(lapTimes[lap], timeData[i])
		}
	}

	var laps []LapStats
	best := 1e18
	totalDur := 0.0

	for lapNum, times := range lapTimes {
		if len(times) < 2 {
			continue
		}
		duration := times[len(times)-1] - times[0]
		if duration <= 0 {
			continue
		}

		ls := LapStats{Lap: lapNum, Duration: duration}

		// Compute per-channel stats for this lap range
		startIdx := -1
		endIdx := -1
		for i, lv := range lapData {
			if int(lv) == lapNum {
				if startIdx == -1 {
					startIdx = i
				}
				endIdx = i
			}
		}
		if startIdx >= 0 && endIdx > startIdx {
			ls.AvgSpeed = avgSlice(td.Channels["Speed"], startIdx, endIdx)
			ls.MaxSpeed = maxSlice(td.Channels["Speed"], startIdx, endIdx)
			ls.AvgThrottle = avgSlice(td.Channels["Throttle"], startIdx, endIdx)
			ls.AvgBrake = avgSlice(td.Channels["Brake"], startIdx, endIdx)
			ls.AvgRPM = avgSlice(td.Channels["RPM"], startIdx, endIdx)
		}

		laps = append(laps, ls)
		totalDur += duration
		if duration < best {
			best = duration
		}
	}

	avgLap := 0.0
	if len(laps) > 0 {
		avgLap = totalDur / float64(len(laps))
	}

	return SessionStats{
		TotalLaps:   len(laps),
		BestLapTime: best,
		AvgLapTime:  avgLap,
		Laps:        laps,
	}
}

// ExtractGPS returns GPS points from telemetry lat/lon channels.
func (td *TelemetryData) ExtractGPS() []GPSPoint {
	latKeys := []string{"GPS_Latitude", "Latitude", "gLat", "CG_PosY"}
	lonKeys := []string{"GPS_Longitude", "Longitude", "gLon", "CG_PosX"}

	var latData, lonData []float64
	for _, k := range latKeys {
		if d, ok := td.Channels[k]; ok {
			latData = d
			break
		}
	}
	for _, k := range lonKeys {
		if d, ok := td.Channels[k]; ok {
			lonData = d
			break
		}
	}
	if latData == nil || lonData == nil {
		return nil
	}

	n := len(latData)
	if len(lonData) < n {
		n = len(lonData)
	}

	// Subsample to max 2000 points
	step := 1
	if n > 2000 {
		step = n / 2000
	}

	var points []GPSPoint
	for i := 0; i < n; i += step {
		if latData[i] != 0 || lonData[i] != 0 {
			points = append(points, GPSPoint{Lat: latData[i], Lon: lonData[i]})
		}
	}
	return points
}

func avgSlice(data []float64, start, end int) float64 {
	if data == nil || start >= len(data) {
		return 0
	}
	if end >= len(data) {
		end = len(data) - 1
	}
	sum := 0.0
	count := 0
	for i := start; i <= end; i++ {
		sum += data[i]
		count++
	}
	if count == 0 {
		return 0
	}
	return sum / float64(count)
}

func maxSlice(data []float64, start, end int) float64 {
	if data == nil || start >= len(data) {
		return 0
	}
	if end >= len(data) {
		end = len(data) - 1
	}
	m := data[start]
	for i := start + 1; i <= end; i++ {
		if data[i] > m {
			m = data[i]
		}
	}
	return m
}
