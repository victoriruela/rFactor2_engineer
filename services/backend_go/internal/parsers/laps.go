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

// ExtractGPS extracts GPS coordinates from telemetry for circuit map display.
// Selects the single lap with the most data points to avoid multi-lap overlap.
// The data is already gently smoothed at parse time (rolling mean only).
func ExtractGPS(td *domain.TelemetryData, maxPoints int) []domain.GPSPoint {
	latCol := findChannel(td, "GPS Latitude", "GPS_Latitude", "gps latitude")
	lonCol := findChannel(td, "GPS Longitude", "GPS_Longitude", "gps longitude")
	if latCol == "" || lonCol == "" {
		return nil
	}

	allLat := td.Channels[latCol]
	allLon := td.Channels[lonCol]
	n := len(allLat)
	if len(allLon) < n {
		n = len(allLon)
	}
	if n == 0 {
		return nil
	}

	// Select only the single best lap to avoid multi-lap overlap artifacts.
	lat, lon := bestLapGPS(td, allLat[:n], allLon[:n])
	if len(lat) == 0 {
		return nil
	}

	// Filter out invalid coordinates and consecutive duplicates (stationary car).
	type pair struct{ lat, lon float64 }
	valid := make([]pair, 0, len(lat))
	var prevLat, prevLon float64
	for i := range lat {
		la, lo := lat[i], lon[i]
		if math.IsNaN(la) || math.IsNaN(lo) || math.IsInf(la, 0) || math.IsInf(lo, 0) {
			continue
		}
		if la == prevLat && lo == prevLon {
			continue // skip stationary / duplicate samples
		}
		valid = append(valid, pair{la, lo})
		prevLat, prevLon = la, lo
	}
	if len(valid) == 0 {
		return nil
	}

	// Subsample evenly to maxPoints.
	rawN := len(valid)
	if maxPoints <= 0 || maxPoints >= rawN {
		out := make([]domain.GPSPoint, rawN)
		for i, p := range valid {
			out[i] = domain.GPSPoint{Lat: p.lat, Lon: p.lon}
		}
		return out
	}

	step := float64(rawN) / float64(maxPoints)
	out := make([]domain.GPSPoint, maxPoints)
	for i := 0; i < maxPoints; i++ {
		idx := int(math.Round(float64(i) * step))
		if idx >= rawN {
			idx = rawN - 1
		}
		out[i] = domain.GPSPoint{Lat: valid[idx].lat, Lon: valid[idx].lon}
	}
	return out
}

// bestLapGPS picks the single lap with the most GPS samples.
// Falls back to the full data if no lap column is available.
func bestLapGPS(td *domain.TelemetryData, lat, lon []float64) ([]float64, []float64) {
	if td.LapCol == "" {
		return lat, lon
	}
	lapData, ok := td.Channels[td.LapCol]
	if !ok || len(lapData) == 0 {
		return lat, lon
	}

	n := len(lat)
	if len(lapData) < n {
		n = len(lapData)
	}

	// Count samples per lap.
	lapCounts := make(map[int]int)
	for i := 0; i < n; i++ {
		lap := int(lapData[i])
		if lap > 0 {
			lapCounts[lap]++
		}
	}
	if len(lapCounts) == 0 {
		return lat, lon
	}

	// Find the lap with the most data points.
	bestLap := 0
	bestCount := 0
	for lap, count := range lapCounts {
		if count > bestCount {
			bestCount = count
			bestLap = lap
		}
	}

	// Extract GPS data for the best lap only.
	bestLat := make([]float64, 0, bestCount)
	bestLon := make([]float64, 0, bestCount)
	for i := 0; i < n; i++ {
		if int(lapData[i]) == bestLap {
			bestLat = append(bestLat, lat[i])
			bestLon = append(bestLon, lon[i])
		}
	}

	return bestLat, bestLon
}

func findChannel(td *domain.TelemetryData, names ...string) string {
	for _, name := range names {
		if _, ok := td.Channels[name]; ok {
			return name
		}
	}
	return ""
}
