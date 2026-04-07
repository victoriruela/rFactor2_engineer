package parsers

import (
	"math"
	"sort"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

// FilterIncompleteLaps removes incomplete and anomalous laps from telemetry data.
// Excludes lap 0 (out-lap) and laps with duration outside the 90%-110% median window.
func FilterIncompleteLaps(td *domain.TelemetryData) {
	if td.LapCol == "" {
		return
	}

	lapData, ok := td.Channels[td.LapCol]
	if !ok || len(lapData) == 0 {
		return
	}

	// Find unique laps > 0
	lapSet := make(map[int]bool)
	for _, v := range lapData {
		lap := int(v)
		if lap > 0 {
			lapSet[lap] = true
		}
	}

	laps := make([]int, 0, len(lapSet))
	for l := range lapSet {
		laps = append(laps, l)
	}
	sort.Ints(laps)

	if len(laps) <= 1 {
		// Keep all data with lap > 0
		filterByLaps(td, laps)
		return
	}

	// Filter by duration: exclude laps outside the median window.
	completeLaps := filterByDuration(td, laps)
	if len(completeLaps) == 0 {
		completeLaps = laps
	}

	filterByLaps(td, completeLaps)
}

func filterByDuration(td *domain.TelemetryData, laps []int) []int {
	if td.TimeCol == "" {
		return laps
	}

	timeData, ok := td.Channels[td.TimeCol]
	if !ok || len(timeData) == 0 {
		return laps
	}

	lapData := td.Channels[td.LapCol]

	// Compute duration per lap
	lapDurations := make(map[int]float64)
	for _, lap := range laps {
		var minT, maxT float64
		first := true
		for i, v := range lapData {
			if int(v) != lap {
				continue
			}
			if i < len(timeData) {
				t := timeData[i]
				if first {
					minT = t
					maxT = t
					first = false
				} else {
					if t < minT {
						minT = t
					}
					if t > maxT {
						maxT = t
					}
				}
			}
		}
		if !first {
			lapDurations[lap] = maxT - minT
		}
	}

	if len(laps) <= 2 {
		return laps
	}

	// Median of middle laps (exclude first and last)
	middleLaps := laps[1 : len(laps)-1]
	durations := make([]float64, 0, len(middleLaps))
	for _, l := range middleLaps {
		if d, ok := lapDurations[l]; ok && d > 0 {
			durations = append(durations, d)
		}
	}

	if len(durations) == 0 {
		return laps
	}

	sort.Float64s(durations)
	medianDur := durations[len(durations)/2]
	minThreshold := medianDur * 0.90
	maxThreshold := medianDur * 1.10

	result := make([]int, 0, len(laps))
	for _, l := range laps {
		if d, ok := lapDurations[l]; ok && d >= minThreshold && d <= maxThreshold {
			result = append(result, l)
		}
	}

	return result
}

func filterByLaps(td *domain.TelemetryData, keepLaps []int) {
	if len(keepLaps) == 0 {
		return
	}

	lapData := td.Channels[td.LapCol]
	if len(lapData) == 0 {
		return
	}

	keepSet := make(map[int]bool)
	for _, l := range keepLaps {
		keepSet[l] = true
	}

	// Build index mask
	mask := make([]bool, len(lapData))
	keepCount := 0
	for i, v := range lapData {
		if keepSet[int(v)] {
			mask[i] = true
			keepCount++
		}
	}

	if keepCount == len(lapData) {
		return // Nothing to filter
	}

	// Apply mask to all channels
	for name, data := range td.Channels {
		if len(data) != len(mask) {
			continue
		}
		filtered := make([]float64, 0, keepCount)
		for i, keep := range mask {
			if keep {
				filtered = append(filtered, data[i])
			}
		}
		td.Channels[name] = filtered
	}
}

// ExtractGPS extracts GPS coordinates from telemetry, applying smoothing.
// Subsamples to maxPoints for circuit map display.
func ExtractGPS(td *domain.TelemetryData, maxPoints int) []domain.GPSPoint {
	latCol := findChannel(td, "GPS Latitude", "GPS_Latitude", "gps latitude")
	lonCol := findChannel(td, "GPS Longitude", "GPS_Longitude", "gps longitude")

	if latCol == "" || lonCol == "" {
		return nil
	}

	lat := SmoothGPS(td.Channels[latCol])
	lon := SmoothGPS(td.Channels[lonCol])

	n := len(lat)
	if len(lon) < n {
		n = len(lon)
	}

	if maxPoints <= 0 || maxPoints >= n {
		points := make([]domain.GPSPoint, n)
		for i := 0; i < n; i++ {
			points[i] = domain.GPSPoint{Lat: lat[i], Lon: lon[i]}
		}
		return points
	}

	// Subsample
	step := float64(n) / float64(maxPoints)
	points := make([]domain.GPSPoint, maxPoints)
	for i := 0; i < maxPoints; i++ {
		idx := int(math.Round(float64(i) * step))
		if idx >= n {
			idx = n - 1
		}
		points[i] = domain.GPSPoint{Lat: lat[idx], Lon: lon[idx]}
	}

	return points
}

func findChannel(td *domain.TelemetryData, names ...string) string {
	for _, name := range names {
		if _, ok := td.Channels[name]; ok {
			return name
		}
	}
	return ""
}
