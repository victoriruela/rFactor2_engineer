package domain

import "math"

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

// TelemetrySample holds a single downsampled time-series sample for the frontend charts.
type TelemetrySample struct {
	T    float64 `json:"t"`
	Spd  float64 `json:"spd"`
	Thr  float64 `json:"thr"`
	Brk  float64 `json:"brk"`
	RPM  float64 `json:"rpm"`
	Gear float64 `json:"gear"`
	Lat  float64 `json:"lat"`
	Lon  float64 `json:"lon"`
	Lap  int     `json:"lap"`
}

// ExtractTimeSeries builds a downsampled slice of TelemetrySample from TelemetryData.
func (td *TelemetryData) ExtractTimeSeries() []TelemetrySample {
	n := 0
	for _, ch := range td.Channels {
		if len(ch) > n {
			n = len(ch)
		}
	}
	if n == 0 {
		return nil
	}

	step := 1
	timeData := td.Channels[td.TimeCol]
	lapData := td.Channels[td.LapCol]
	speed := firstChannel(td.Channels, "Speed", "Ground_Speed")
	throttle := firstChannel(td.Channels, "Throttle", "Throttle_Pos")
	brake := firstChannel(td.Channels, "Brake", "Brake_Pos")
	rpm := firstChannel(td.Channels, "RPM", "Engine_RPM")
	gear := firstChannel(td.Channels, "Gear")
	lat := firstChannel(td.Channels, "GPS Latitude", "GPS_Latitude", "GPS_Lat", "Latitude", "gLat")
	lon := firstChannel(td.Channels, "GPS Longitude", "GPS_Longitude", "GPS_Lon", "Longitude", "gLon")
	lat, lon = cleanGPSPair(lat, lon)

	safeGet := func(s []float64, i int) float64 {
		if i < len(s) {
			return s[i]
		}
		return 0
	}

	out := make([]TelemetrySample, 0, n/step+1)
	for i := 0; i < n; i += step {
		s := TelemetrySample{
			T:    safeGet(timeData, i),
			Spd:  safeGet(speed, i),
			Thr:  safeGet(throttle, i),
			Brk:  safeGet(brake, i),
			RPM:  safeGet(rpm, i),
			Gear: safeGet(gear, i),
			Lat:  safeGet(lat, i),
			Lon:  safeGet(lon, i),
		}
		if i < len(lapData) {
			s.Lap = int(lapData[i])
		}
		out = append(out, s)
	}
	return out
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

	lapTimeData := firstChannel(td.Channels, "Lap_Time", "Lap Time", "LapTime")

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
	best := 0.0
	totalDur := 0.0
	hasValidLap := false

	for lapNum, times := range lapTimes {
		if len(times) < 2 {
			continue
		}
		duration := 0.0
		if lapTimeData != nil {
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
			if startIdx >= 0 && endIdx >= startIdx {
				maxLapTime := 0.0
				for i := startIdx; i <= endIdx && i < len(lapTimeData); i++ {
					v := lapTimeData[i]
					if v > maxLapTime {
						maxLapTime = v
					}
				}
				if maxLapTime > 0 {
					duration = maxLapTime
				}
			}
		}

		if duration <= 0 {
			duration = times[len(times)-1] - times[0]
		}
		if duration <= 0 {
			continue
		}

		ls := LapStats{Lap: lapNum, Duration: duration}

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
		if !hasValidLap || duration < best {
			best = duration
			hasValidLap = true
		}
	}

	if len(laps) == 0 {
		return SessionStats{}
	}

	avgLap := totalDur / float64(len(laps))

	return SessionStats{
		TotalLaps:   len(laps),
		BestLapTime: best,
		AvgLapTime:  avgLap,
		Laps:        laps,
	}
}

func firstChannel(channels map[string][]float64, names ...string) []float64 {
	for _, name := range names {
		if data, ok := channels[name]; ok {
			return data
		}
	}
	return nil
}

func cleanGPSPair(latData, lonData []float64) ([]float64, []float64) {
	if latData == nil || lonData == nil {
		return latData, lonData
	}
	n := len(latData)
	if len(lonData) < n {
		n = len(lonData)
	}
	if n < 3 {
		return latData, lonData
	}

	cleanLat := make([]float64, len(latData))
	copy(cleanLat, latData)
	cleanLon := make([]float64, len(lonData))
	copy(cleanLon, lonData)

	isValid := func(lat, lon float64) bool {
		return (lat != 0 || lon != 0) &&
			!math.IsNaN(lat) && !math.IsNaN(lon) &&
			!math.IsInf(lat, 0) && !math.IsInf(lon, 0) &&
			lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180
	}

	lastValid := -1
	for i := 0; i < n; i++ {
		if !isValid(cleanLat[i], cleanLon[i]) {
			if lastValid >= 0 {
				cleanLat[i] = cleanLat[lastValid]
				cleanLon[i] = cleanLon[lastValid]
			} else {
				cleanLat[i] = 0
				cleanLon[i] = 0
			}
			continue
		}
		if lastValid == -1 {
			lastValid = i
			continue
		}
		lastValid = i
	}

	return cleanLat, cleanLon
}

// ExtractGPS returns GPS points from telemetry lat/lon channels.
func (td *TelemetryData) ExtractGPS() []GPSPoint {
	latKeys := []string{"GPS Latitude", "GPS_Latitude", "Latitude", "gLat", "CG_PosY"}
	lonKeys := []string{"GPS Longitude", "GPS_Longitude", "Longitude", "gLon", "CG_PosX"}

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
	latData, lonData = cleanGPSPair(latData, lonData)

	n := len(latData)
	if len(lonData) < n {
		n = len(lonData)
	}

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
