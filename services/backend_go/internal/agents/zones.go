package agents

import (
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

// Zone type constants (Spanish labels for prompts).
const (
	zoneTypeBraking  = "FRENADA"
	zoneTypeCorner   = "CURVA"
	zoneTypeTraction = "TRACCIÓN"
	zoneTypeStraight = "RECTA"
)

// zone represents a detected driving zone within a lap.
type zone struct {
	Type     string
	StartIdx int
	EndIdx   int
}

// channelResolver provides unified access to telemetry channels regardless of naming conventions.
type channelResolver struct {
	td *domain.TelemetryData
}

func newChannelResolver(td *domain.TelemetryData) *channelResolver {
	return &channelResolver{td: td}
}

func (r *channelResolver) get(names ...string) []float64 {
	for _, name := range names {
		if data, ok := r.td.Channels[name]; ok {
			return data
		}
	}
	return nil
}

func (r *channelResolver) time() []float64     { return r.td.Channels[r.td.TimeCol] }
func (r *channelResolver) lap() []float64      { return r.td.Channels[r.td.LapCol] }
func (r *channelResolver) speed() []float64    { return r.get("Speed", "Ground_Speed") }
func (r *channelResolver) throttle() []float64 { return r.get("Throttle", "Throttle_Pos") }
func (r *channelResolver) brake() []float64    { return r.get("Brake", "Brake_Pos") }
func (r *channelResolver) steering() []float64 { return r.get("Steering") }
func (r *channelResolver) latG() []float64 {
	return r.get("G_Force_Lat", "LateralAcceleration")
}
func (r *channelResolver) longG() []float64 {
	return r.get("G_Force_Long", "LongitudinalAcceleration")
}
func (r *channelResolver) brakeTempFL() []float64 { return r.get("Brake_Temp_FL") }
func (r *channelResolver) brakeTempFR() []float64 { return r.get("Brake_Temp_FR") }
func (r *channelResolver) brakeTempRL() []float64 { return r.get("Brake_Temp_RL") }
func (r *channelResolver) brakeTempRR() []float64 { return r.get("Brake_Temp_RR") }
func (r *channelResolver) rideHFL() []float64     { return r.get("Ride_Height_FL") }
func (r *channelResolver) rideHFR() []float64     { return r.get("Ride_Height_FR") }
func (r *channelResolver) rideHRL() []float64     { return r.get("Ride_Height_RL") }
func (r *channelResolver) rideHRR() []float64     { return r.get("Ride_Height_RR") }
func (r *channelResolver) tyreTempFL() []float64   { return r.get("Tyre_Temp_FL_Centre") }
func (r *channelResolver) tyreTempFR() []float64   { return r.get("Tyre_Temp_FR_Centre") }
func (r *channelResolver) tyreTempRL() []float64   { return r.get("Tyre_Temp_RL_Centre") }
func (r *channelResolver) tyreTempRR() []float64   { return r.get("Tyre_Temp_RR_Centre") }
func (r *channelResolver) gripFL() []float64       { return r.get("Grip_Fract_FL") }
func (r *channelResolver) gripFR() []float64       { return r.get("Grip_Fract_FR") }
func (r *channelResolver) gripRL() []float64       { return r.get("Grip_Fract_RL") }
func (r *channelResolver) gripRR() []float64       { return r.get("Grip_Fract_RR") }
func (r *channelResolver) brakeBias() []float64    { return r.get("Brake_Bias_Rear") }

// BuildEnhancedTelemetrySummary creates a zone-segmented telemetry summary
// that provides AI agents with detailed per-zone context instead of just aggregates.
func BuildEnhancedTelemetrySummary(td *domain.TelemetryData) string {
	if td == nil || len(td.Channels) == 0 {
		return "No hay datos de telemetría disponibles."
	}

	var sb strings.Builder
	r := newChannelResolver(td)

	writeOverview(&sb, td, r)
	writeLapTable(&sb, td)
	writeAllLapsZoneAnalysis(&sb, td, r)
	writeCrossLapComparison(&sb, td, r)

	return sb.String()
}

// --- Section writers ---

func writeOverview(sb *strings.Builder, td *domain.TelemetryData, r *channelResolver) {
	sb.WriteString("=== RESUMEN DE TELEMETRÍA ===\n")
	sb.WriteString(fmt.Sprintf("Canales disponibles: %d\n", len(td.Channels)))

	stats := td.SessionStats()
	sb.WriteString(fmt.Sprintf("Total vueltas: %d\n", stats.TotalLaps))
	sb.WriteString(fmt.Sprintf("Mejor vuelta: %.3f s\n", stats.BestLapTime))
	sb.WriteString(fmt.Sprintf("Media de vueltas: %.3f s\n\n", stats.AvgLapTime))

	channels := []struct {
		name string
		data []float64
	}{
		{"Velocidad (km/h)", r.speed()},
		{"Acelerador (0-1)", r.throttle()},
		{"Freno (0-1)", r.brake()},
		{"Dirección (°)", r.steering()},
		{"RPM", r.get("RPM", "Engine_RPM")},
		{"G Lateral", r.latG()},
		{"G Longitudinal", r.longG()},
	}

	for _, ch := range channels {
		if ch.data == nil {
			continue
		}
		mn, mx, avg := sliceStats(ch.data)
		sb.WriteString(fmt.Sprintf("%s: min=%.1f max=%.1f avg=%.1f\n", ch.name, mn, mx, avg))
	}
	sb.WriteString("\n")
}

func writeLapTable(sb *strings.Builder, td *domain.TelemetryData) {
	stats := td.SessionStats()
	if len(stats.Laps) == 0 {
		return
	}

	laps := make([]domain.LapStats, len(stats.Laps))
	copy(laps, stats.Laps)
	sort.Slice(laps, func(i, j int) bool { return laps[i].Lap < laps[j].Lap })

	sb.WriteString("=== COMPARACIÓN POR VUELTAS ===\n")
	sb.WriteString(fmt.Sprintf("%-8s %-10s %-10s %-10s %-12s %-12s\n",
		"Vuelta", "Tiempo", "V.Media", "V.Máx", "Acel.Media", "Freno.Media"))

	for _, ls := range laps {
		sb.WriteString(fmt.Sprintf("%-8d %-10.3f %-10.1f %-10.1f %-12.1f%% %-12.1f%%\n",
			ls.Lap, ls.Duration, ls.AvgSpeed, ls.MaxSpeed,
			ls.AvgThrottle*100, ls.AvgBrake*100))
	}
	sb.WriteString("\n")
}

// maxAnalysisLaps limits detailed per-zone analysis to avoid token explosion.
const maxAnalysisLaps = 6

// writeAllLapsZoneAnalysis writes zone-by-zone analysis for every valid lap (capped).
func writeAllLapsZoneAnalysis(sb *strings.Builder, td *domain.TelemetryData, r *channelResolver) {
	lapData := r.lap()
	timeData := r.time()
	if lapData == nil || timeData == nil {
		return
	}

	laps := findValidLaps(lapData)
	if len(laps) == 0 {
		return
	}

	bestLap := findBestLap(td)

	// Cap: if more laps than maxAnalysisLaps, keep first, best, last, and fill around best
	analysisLaps := selectRepresentativeLaps(laps, bestLap, maxAnalysisLaps)

	for _, lapNum := range analysisLaps {
		start, end := lapRange(lapData, lapNum)
		if start < 0 || end <= start {
			continue
		}
		zones := detectZones(r, start, end)
		if len(zones) == 0 {
			continue
		}

		label := fmt.Sprintf("Vuelta %d", lapNum)
		if lapNum == bestLap {
			label += " ★ MEJOR"
		}
		sb.WriteString(fmt.Sprintf("=== ANÁLISIS POR ZONAS — %s ===\n\n", label))

		brakingNum := 0
		cornerNum := 0

		for _, z := range zones {
			switch z.Type {
			case zoneTypeBraking:
				brakingNum++
				writeBrakingZone(sb, r, z, brakingNum)
			case zoneTypeCorner:
				cornerNum++
				writeCornerZone(sb, r, z, cornerNum)
			case zoneTypeTraction:
				writeTractionZone(sb, r, z)
			case zoneTypeStraight:
				writeStraightZone(sb, r, z)
			}
		}
	}
}

// selectRepresentativeLaps picks at most maxN laps, ensuring best + first + last are included
// and the rest are evenly distributed.
func selectRepresentativeLaps(laps []int, bestLap, maxN int) []int {
	if len(laps) <= maxN {
		return laps
	}

	chosen := make(map[int]bool)
	chosen[laps[0]] = true
	chosen[laps[len(laps)-1]] = true
	if bestLap > 0 {
		chosen[bestLap] = true
	}

	// Fill remaining slots evenly across the list
	remaining := maxN - len(chosen)
	if remaining > 0 {
		step := float64(len(laps)-1) / float64(remaining+1)
		for i := 1; i <= remaining; i++ {
			idx := int(math.Round(float64(i) * step))
			if idx >= len(laps) {
				idx = len(laps) - 1
			}
			chosen[laps[idx]] = true
		}
	}

	var result []int
	for _, l := range laps {
		if chosen[l] {
			result = append(result, l)
		}
	}
	return result
}

// --- Cross-lap comparison (zone-by-zone patterns) ---

// zoneSummary holds aggregate metrics for a single zone, used for cross-lap comparison.
type zoneSummary struct {
	Lap       int
	ZoneIdx   int // sequential index within the zone type (e.g., braking #1, #2)
	SpeedIn   float64
	SpeedOut  float64
	SpeedMin  float64
	SpeedMax  float64
	BrkAvg    float64
	BrkPeak   float64
	ThrAvg    float64
	LatGPeak  float64
	LongGPeak float64
	Duration  float64
	GripFront float64
	GripRear  float64
}

// lapZones holds detected braking and cornering zones for a single lap.
type lapZones struct {
	Lap       int
	Braking   []zoneSummary
	Cornering []zoneSummary
}

func writeCrossLapComparison(sb *strings.Builder, td *domain.TelemetryData, r *channelResolver) {
	lapData := r.lap()
	if lapData == nil {
		return
	}

	laps := findValidLaps(lapData)
	if len(laps) < 2 {
		return
	}

	// Use same representative laps
	bestLap := findBestLap(td)
	analysisLaps := selectRepresentativeLaps(laps, bestLap, maxAnalysisLaps)

	// Build per-lap zone summaries
	var allLapZones []lapZones
	for _, lapNum := range analysisLaps {
		start, end := lapRange(lapData, lapNum)
		if start < 0 || end <= start {
			continue
		}
		zones := detectZones(r, start, end)
		lz := lapZones{Lap: lapNum}
		bIdx, cIdx := 0, 0
		for _, z := range zones {
			switch z.Type {
			case zoneTypeBraking:
				bIdx++
				lz.Braking = append(lz.Braking, buildZoneSummary(r, z, lapNum, bIdx))
			case zoneTypeCorner:
				cIdx++
				lz.Cornering = append(lz.Cornering, buildZoneSummary(r, z, lapNum, cIdx))
			}
		}
		allLapZones = append(allLapZones, lz)
	}

	if len(allLapZones) < 2 {
		return
	}

	// Find common zone count (minimum across laps)
	minBraking := len(allLapZones[0].Braking)
	minCornering := len(allLapZones[0].Cornering)
	for _, lz := range allLapZones[1:] {
		if len(lz.Braking) < minBraking {
			minBraking = len(lz.Braking)
		}
		if len(lz.Cornering) < minCornering {
			minCornering = len(lz.Cornering)
		}
	}

	sb.WriteString("=== COMPARACIÓN ENTRE VUELTAS POR ZONA ===\n\n")
	sb.WriteString("(Compara la misma zona en distintas vueltas para detectar patrones)\n\n")

	// Compare braking zones
	for zIdx := 0; zIdx < minBraking; zIdx++ {
		sb.WriteString(fmt.Sprintf("--- Frenada %d ---\n", zIdx+1))
		sb.WriteString(fmt.Sprintf("  %-8s %-14s %-12s %-10s %-10s %-10s\n",
			"Vuelta", "Vel entrada→sal", "Freno pico", "G long pk", "Duración", "Trail brk"))

		for _, lz := range allLapZones {
			if zIdx >= len(lz.Braking) {
				continue
			}
			zs := lz.Braking[zIdx]
			trailStr := "-"
			if zs.LatGPeak > 0.3 {
				trailStr = fmt.Sprintf("%.2fg", zs.LatGPeak)
			}
			bestMark := ""
			if lz.Lap == bestLap {
				bestMark = " ★"
			}
			sb.WriteString(fmt.Sprintf("  %-8s %-14s %-12s %-10s %-10s %-10s\n",
				fmt.Sprintf("%d%s", lz.Lap, bestMark),
				fmt.Sprintf("%.0f→%.0f", zs.SpeedIn, zs.SpeedOut),
				fmt.Sprintf("%.0f%%", zs.BrkPeak*100),
				fmt.Sprintf("%.2fg", zs.LongGPeak),
				fmt.Sprintf("%.2fs", zs.Duration),
				trailStr))
		}

		// Variance analysis
		writeBrakingVariance(sb, allLapZones, zIdx, bestLap)
		sb.WriteString("\n")
	}

	// Compare cornering zones
	for zIdx := 0; zIdx < minCornering; zIdx++ {
		sb.WriteString(fmt.Sprintf("--- Curva %d ---\n", zIdx+1))
		sb.WriteString(fmt.Sprintf("  %-8s %-10s %-10s %-10s %-12s %-12s\n",
			"Vuelta", "V.Mín", "V.Media", "G lat pk", "Grip del.", "Grip tras."))

		for _, lz := range allLapZones {
			if zIdx >= len(lz.Cornering) {
				continue
			}
			zs := lz.Cornering[zIdx]
			bestMark := ""
			if lz.Lap == bestLap {
				bestMark = " ★"
			}
			sb.WriteString(fmt.Sprintf("  %-8s %-10s %-10s %-10s %-12s %-12s\n",
				fmt.Sprintf("%d%s", lz.Lap, bestMark),
				fmt.Sprintf("%.0f", zs.SpeedMin),
				fmt.Sprintf("%.0f", (zs.SpeedIn+zs.SpeedOut)/2),
				fmt.Sprintf("%.2fg", zs.LatGPeak),
				fmt.Sprintf("%.2f", zs.GripFront),
				fmt.Sprintf("%.2f", zs.GripRear)))
		}

		// Balance pattern
		writeCorneringVariance(sb, allLapZones, zIdx, bestLap)
		sb.WriteString("\n")
	}

	// Global pattern summary
	writePatternSummary(sb, allLapZones, bestLap)
}

func buildZoneSummary(r *channelResolver, z zone, lapNum, idx int) zoneSummary {
	timeData := r.time()
	duration := safeIdx(timeData, z.EndIdx) - safeIdx(timeData, z.StartIdx)

	gripFlAvg := avgRange(r.gripFL(), z.StartIdx, z.EndIdx)
	gripFrAvg := avgRange(r.gripFR(), z.StartIdx, z.EndIdx)
	gripRlAvg := avgRange(r.gripRL(), z.StartIdx, z.EndIdx)
	gripRrAvg := avgRange(r.gripRR(), z.StartIdx, z.EndIdx)

	return zoneSummary{
		Lap:       lapNum,
		ZoneIdx:   idx,
		SpeedIn:   safeIdx(r.speed(), z.StartIdx),
		SpeedOut:  safeIdx(r.speed(), z.EndIdx),
		SpeedMin:  minRange(r.speed(), z.StartIdx, z.EndIdx),
		SpeedMax:  maxRange(r.speed(), z.StartIdx, z.EndIdx),
		BrkAvg:    avgRange(r.brake(), z.StartIdx, z.EndIdx),
		BrkPeak:   maxRange(r.brake(), z.StartIdx, z.EndIdx),
		ThrAvg:    avgRange(r.throttle(), z.StartIdx, z.EndIdx),
		LatGPeak:  maxAbsRange(r.latG(), z.StartIdx, z.EndIdx),
		LongGPeak: math.Abs(minRange(r.longG(), z.StartIdx, z.EndIdx)),
		Duration:  duration,
		GripFront: (gripFlAvg + gripFrAvg) / 2,
		GripRear:  (gripRlAvg + gripRrAvg) / 2,
	}
}

func writeBrakingVariance(sb *strings.Builder, allLapZones []lapZones, zIdx, bestLap int) {
	var speeds, durations []float64
	var bestSpeed, bestDuration float64
	for _, lz := range allLapZones {
		if zIdx >= len(lz.Braking) {
			continue
		}
		zs := lz.Braking[zIdx]
		speeds = append(speeds, zs.SpeedOut)
		durations = append(durations, zs.Duration)
		if lz.Lap == bestLap {
			bestSpeed = zs.SpeedOut
			bestDuration = zs.Duration
		}
	}

	if len(speeds) < 2 {
		return
	}

	speedStd := stddev(speeds)
	durationStd := stddev(durations)

	if speedStd > 5 {
		sb.WriteString(fmt.Sprintf("  ⚠ INCONSISTENCIA: velocidad de salida varía σ=%.1f km/h entre vueltas\n", speedStd))
	}
	if durationStd > 0.15 {
		sb.WriteString(fmt.Sprintf("  ⚠ INCONSISTENCIA: duración de frenada varía σ=%.2fs entre vueltas\n", durationStd))
	}

	if bestSpeed > 0 {
		avgSpd := mean(speeds)
		if math.Abs(bestSpeed-avgSpd) > 3 {
			sb.WriteString(fmt.Sprintf("  → En la mejor vuelta la salida fue a %.0f km/h vs media %.0f km/h\n", bestSpeed, avgSpd))
		}
	}
	if bestDuration > 0 {
		avgDur := mean(durations)
		if math.Abs(bestDuration-avgDur) > 0.1 {
			sb.WriteString(fmt.Sprintf("  → En la mejor vuelta la frenada duró %.2fs vs media %.2fs\n", bestDuration, avgDur))
		}
	}
}

func writeCorneringVariance(sb *strings.Builder, allLapZones []lapZones, zIdx, bestLap int) {
	var minSpeeds, latGs, gripFronts, gripRears []float64
	for _, lz := range allLapZones {
		if zIdx >= len(lz.Cornering) {
			continue
		}
		zs := lz.Cornering[zIdx]
		minSpeeds = append(minSpeeds, zs.SpeedMin)
		latGs = append(latGs, zs.LatGPeak)
		gripFronts = append(gripFronts, zs.GripFront)
		gripRears = append(gripRears, zs.GripRear)
	}

	if len(minSpeeds) < 2 {
		return
	}

	speedStd := stddev(minSpeeds)
	if speedStd > 4 {
		sb.WriteString(fmt.Sprintf("  ⚠ INCONSISTENCIA: velocidad mínima varía σ=%.1f km/h\n", speedStd))
	}

	// Check for consistent under/oversteer pattern across laps
	understeerCount, oversteerCount := 0, 0
	for i := range gripFronts {
		if gripFronts[i] > 0 && gripRears[i] > 0 {
			if gripFronts[i] < gripRears[i]-0.03 {
				understeerCount++
			} else if gripRears[i] < gripFronts[i]-0.03 {
				oversteerCount++
			}
		}
	}
	total := len(gripFronts)
	if understeerCount > total/2 {
		sb.WriteString(fmt.Sprintf("  ⚠ PATRÓN: subviraje consistente en %d/%d vueltas → problema de setup\n", understeerCount, total))
	}
	if oversteerCount > total/2 {
		sb.WriteString(fmt.Sprintf("  ⚠ PATRÓN: sobreviraje consistente en %d/%d vueltas → problema de setup\n", oversteerCount, total))
	}
}

func writePatternSummary(sb *strings.Builder, allLapZones []lapZones, bestLap int) {
	if len(allLapZones) < 2 {
		return
	}

	sb.WriteString("=== PATRONES GLOBALES DETECTADOS ===\n\n")

	// Aggregate cross-lap under/oversteer
	totalCornerZones := 0
	understeerZones := 0
	oversteerZones := 0
	for _, lz := range allLapZones {
		for _, zs := range lz.Cornering {
			totalCornerZones++
			if zs.GripFront > 0 && zs.GripRear > 0 {
				if zs.GripFront < zs.GripRear-0.03 {
					understeerZones++
				} else if zs.GripRear < zs.GripFront-0.03 {
					oversteerZones++
				}
			}
		}
	}

	if totalCornerZones > 0 {
		if understeerZones > totalCornerZones/3 {
			sb.WriteString(fmt.Sprintf("• SUBVIRAJE recurrente en %d/%d zonas de curva (%.0f%%) → ajustar balance mecánico/aerodinámico\n",
				understeerZones, totalCornerZones, float64(understeerZones)/float64(totalCornerZones)*100))
		}
		if oversteerZones > totalCornerZones/3 {
			sb.WriteString(fmt.Sprintf("• SOBREVIRAJE recurrente en %d/%d zonas de curva (%.0f%%) → ajustar balance mecánico/aerodinámico\n",
				oversteerZones, totalCornerZones, float64(oversteerZones)/float64(totalCornerZones)*100))
		}
	}

	// Braking consistency across all laps
	totalBrakingZones := 0
	var allBrkPeaks []float64
	for _, lz := range allLapZones {
		for _, zs := range lz.Braking {
			totalBrakingZones++
			allBrkPeaks = append(allBrkPeaks, zs.BrkPeak)
		}
	}

	if len(allBrkPeaks) > 2 {
		brkStd := stddev(allBrkPeaks)
		if brkStd > 0.1 {
			sb.WriteString(fmt.Sprintf("• Picos de freno inconsistentes entre zonas/vueltas (σ=%.0f%%) → el piloto varía la presión de frenado\n", brkStd*100))
		}
	}

	// Best lap delta analysis
	if bestLap > 0 {
		var bestBrakingDur, otherBrakingDur []float64
		var bestCornerSpd, otherCornerSpd []float64
		for _, lz := range allLapZones {
			if lz.Lap == bestLap {
				for _, zs := range lz.Braking {
					bestBrakingDur = append(bestBrakingDur, zs.Duration)
				}
				for _, zs := range lz.Cornering {
					bestCornerSpd = append(bestCornerSpd, zs.SpeedMin)
				}
			} else {
				for _, zs := range lz.Braking {
					otherBrakingDur = append(otherBrakingDur, zs.Duration)
				}
				for _, zs := range lz.Cornering {
					otherCornerSpd = append(otherCornerSpd, zs.SpeedMin)
				}
			}
		}

		if len(bestBrakingDur) > 0 && len(otherBrakingDur) > 0 {
			bestAvgBrk := mean(bestBrakingDur)
			otherAvgBrk := mean(otherBrakingDur)
			if math.Abs(bestAvgBrk-otherAvgBrk) > 0.08 {
				sign := "más cortas"
				if bestAvgBrk > otherAvgBrk {
					sign = "más largas"
				}
				sb.WriteString(fmt.Sprintf("• En la mejor vuelta las frenadas son %s (%.2fs vs %.2fs media)\n",
					sign, bestAvgBrk, otherAvgBrk))
			}
		}

		if len(bestCornerSpd) > 0 && len(otherCornerSpd) > 0 {
			bestAvgSpd := mean(bestCornerSpd)
			otherAvgSpd := mean(otherCornerSpd)
			if bestAvgSpd-otherAvgSpd > 2 {
				sb.WriteString(fmt.Sprintf("• En la mejor vuelta la velocidad mínima en curvas es mayor (+%.0f km/h de media)\n",
					bestAvgSpd-otherAvgSpd))
			}
		}
	}

	sb.WriteString("\n")
}

// --- Statistics helpers ---

func mean(data []float64) float64 {
	if len(data) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range data {
		sum += v
	}
	return sum / float64(len(data))
}

func stddev(data []float64) float64 {
	if len(data) < 2 {
		return 0
	}
	m := mean(data)
	sum := 0.0
	for _, v := range data {
		d := v - m
		sum += d * d
	}
	return math.Sqrt(sum / float64(len(data)))
}

func writeBrakingZone(sb *strings.Builder, r *channelResolver, z zone, num int) {
	timeData := r.time()
	tStart := safeIdx(timeData, z.StartIdx)
	tEnd := safeIdx(timeData, z.EndIdx)
	duration := tEnd - tStart

	speedEntry := safeIdx(r.speed(), z.StartIdx)
	speedExit := safeIdx(r.speed(), z.EndIdx)

	sb.WriteString(fmt.Sprintf("FRENADA %d (T=%.1fs → T=%.1fs, %.2fs):\n", num, tStart, tEnd, duration))
	sb.WriteString(fmt.Sprintf("  Velocidad: %.0f → %.0f km/h (Δ %.0f km/h)\n",
		speedEntry, speedExit, speedExit-speedEntry))
	sb.WriteString(fmt.Sprintf("  Freno: media=%.0f%% pico=%.0f%%\n",
		avgRange(r.brake(), z.StartIdx, z.EndIdx)*100,
		maxRange(r.brake(), z.StartIdx, z.EndIdx)*100))

	if longG := r.longG(); longG != nil {
		sb.WriteString(fmt.Sprintf("  G Longitudinal: media=%.2fg pico=%.2fg\n",
			avgRange(longG, z.StartIdx, z.EndIdx),
			minRange(longG, z.StartIdx, z.EndIdx)))
	}

	if latG := r.latG(); latG != nil {
		peakLat := maxAbsRange(latG, z.StartIdx, z.EndIdx)
		if peakLat > 0.3 {
			sb.WriteString(fmt.Sprintf("  Trail braking detectado: G lateral pico=%.2fg\n", peakLat))
		}
	}

	writeBrakeTemps(sb, r, z)
	sb.WriteString("\n")
}

func writeCornerZone(sb *strings.Builder, r *channelResolver, z zone, num int) {
	timeData := r.time()
	tStart := safeIdx(timeData, z.StartIdx)
	tEnd := safeIdx(timeData, z.EndIdx)
	duration := tEnd - tStart

	steering := r.steering()
	avgSteer := avgRange(steering, z.StartIdx, z.EndIdx)
	direction := "Derecha"
	if avgSteer < 0 {
		direction = "Izquierda"
	}

	sb.WriteString(fmt.Sprintf("CURVA %d — %s (T=%.1fs → T=%.1fs, %.2fs):\n",
		num, direction, tStart, tEnd, duration))
	sb.WriteString(fmt.Sprintf("  Velocidad: min=%.0f media=%.0f máx=%.0f km/h\n",
		minRange(r.speed(), z.StartIdx, z.EndIdx),
		avgRange(r.speed(), z.StartIdx, z.EndIdx),
		maxRange(r.speed(), z.StartIdx, z.EndIdx)))

	sb.WriteString(fmt.Sprintf("  Dirección: media=%.1f° pico=%.1f°\n",
		avgSteer, maxAbsRange(steering, z.StartIdx, z.EndIdx)))

	if latG := r.latG(); latG != nil {
		sb.WriteString(fmt.Sprintf("  G Lateral: media=%.2fg pico=%.2fg\n",
			avgRange(latG, z.StartIdx, z.EndIdx),
			maxAbsRange(latG, z.StartIdx, z.EndIdx)))
	}

	writeRideHeights(sb, r, z)
	writeTyreTemps(sb, r, z)
	writeGripAnalysis(sb, r, z)

	// Throttle at corner exit (last quarter)
	exitStart := z.EndIdx - (z.EndIdx-z.StartIdx)/4
	if exitStart < z.StartIdx {
		exitStart = z.StartIdx
	}
	exitThrottle := avgRange(r.throttle(), exitStart, z.EndIdx)
	sb.WriteString(fmt.Sprintf("  Acelerador en salida: %.0f%%\n", exitThrottle*100))

	sb.WriteString("\n")
}

func writeTractionZone(sb *strings.Builder, r *channelResolver, z zone) {
	timeData := r.time()
	tStart := safeIdx(timeData, z.StartIdx)
	tEnd := safeIdx(timeData, z.EndIdx)

	speedEntry := safeIdx(r.speed(), z.StartIdx)
	speedExit := safeIdx(r.speed(), z.EndIdx)

	sb.WriteString(fmt.Sprintf("TRACCIÓN (T=%.1fs → T=%.1fs):\n", tStart, tEnd))
	sb.WriteString(fmt.Sprintf("  Velocidad: %.0f → %.0f km/h\n", speedEntry, speedExit))
	sb.WriteString(fmt.Sprintf("  Acelerador: media=%.0f%%\n",
		avgRange(r.throttle(), z.StartIdx, z.EndIdx)*100))

	if longG := r.longG(); longG != nil {
		sb.WriteString(fmt.Sprintf("  G Longitudinal: media=%.2fg\n",
			avgRange(longG, z.StartIdx, z.EndIdx)))
	}

	writeGripAnalysis(sb, r, z)
	sb.WriteString("\n")
}

func writeStraightZone(sb *strings.Builder, r *channelResolver, z zone) {
	duration := safeIdx(r.time(), z.EndIdx) - safeIdx(r.time(), z.StartIdx)
	if duration < 2.0 {
		return // skip short straights
	}

	tStart := safeIdx(r.time(), z.StartIdx)
	tEnd := safeIdx(r.time(), z.EndIdx)
	maxSpd := maxRange(r.speed(), z.StartIdx, z.EndIdx)

	sb.WriteString(fmt.Sprintf("RECTA (T=%.1fs → T=%.1fs, %.1fs):\n", tStart, tEnd, duration))
	sb.WriteString(fmt.Sprintf("  Velocidad máxima: %.0f km/h\n", maxSpd))
	sb.WriteString("\n")
}

// --- Detail writers ---

func writeBrakeTemps(sb *strings.Builder, r *channelResolver, z zone) {
	btFL := r.brakeTempFL()
	btFR := r.brakeTempFR()
	if btFL == nil && btFR == nil {
		return
	}

	avgFL := avgRange(btFL, z.StartIdx, z.EndIdx)
	avgFR := avgRange(btFR, z.StartIdx, z.EndIdx)
	avgRL := avgRange(r.brakeTempRL(), z.StartIdx, z.EndIdx)
	avgRR := avgRange(r.brakeTempRR(), z.StartIdx, z.EndIdx)

	sb.WriteString(fmt.Sprintf("  Temp frenos: FL=%.0f°C FR=%.0f°C RL=%.0f°C RR=%.0f°C\n",
		avgFL, avgFR, avgRL, avgRR))

	frontAvg := (avgFL + avgFR) / 2
	rearAvg := (avgRL + avgRR) / 2
	if frontAvg > 0 && rearAvg > 0 {
		sb.WriteString(fmt.Sprintf("  Balance temp frenos: delantero=%.0f°C trasero=%.0f°C (Δ=%.0f°C)\n",
			frontAvg, rearAvg, frontAvg-rearAvg))
	}
}

func writeRideHeights(sb *strings.Builder, r *channelResolver, z zone) {
	rhFL := r.rideHFL()
	rhFR := r.rideHFR()
	if rhFL == nil && rhFR == nil {
		return
	}

	fl := avgRange(rhFL, z.StartIdx, z.EndIdx)
	fr := avgRange(rhFR, z.StartIdx, z.EndIdx)
	rl := avgRange(r.rideHRL(), z.StartIdx, z.EndIdx)
	rr := avgRange(r.rideHRR(), z.StartIdx, z.EndIdx)

	sb.WriteString(fmt.Sprintf("  Alturas: FL=%.1fmm FR=%.1fmm RL=%.1fmm RR=%.1fmm\n", fl, fr, rl, rr))

	leftRight := math.Abs(fl-fr) + math.Abs(rl-rr)
	if leftRight > 3.0 {
		sb.WriteString(fmt.Sprintf("  ⚠ Roll significativo detectado (Δ lateral %.1fmm)\n", leftRight/2))
	}
}

func writeTyreTemps(sb *strings.Builder, r *channelResolver, z zone) {
	ttFL := r.tyreTempFL()
	ttFR := r.tyreTempFR()
	if ttFL == nil && ttFR == nil {
		return
	}

	sb.WriteString(fmt.Sprintf("  Temp neumáticos: FL=%.0f°C FR=%.0f°C RL=%.0f°C RR=%.0f°C\n",
		avgRange(ttFL, z.StartIdx, z.EndIdx),
		avgRange(ttFR, z.StartIdx, z.EndIdx),
		avgRange(r.tyreTempRL(), z.StartIdx, z.EndIdx),
		avgRange(r.tyreTempRR(), z.StartIdx, z.EndIdx)))
}

func writeGripAnalysis(sb *strings.Builder, r *channelResolver, z zone) {
	gFL := r.gripFL()
	gFR := r.gripFR()
	if gFL == nil && gFR == nil {
		return
	}

	avgGripFL := avgRange(gFL, z.StartIdx, z.EndIdx)
	avgGripFR := avgRange(gFR, z.StartIdx, z.EndIdx)
	avgGripRL := avgRange(r.gripRL(), z.StartIdx, z.EndIdx)
	avgGripRR := avgRange(r.gripRR(), z.StartIdx, z.EndIdx)

	sb.WriteString(fmt.Sprintf("  Grip: FL=%.2f FR=%.2f RL=%.2f RR=%.2f\n",
		avgGripFL, avgGripFR, avgGripRL, avgGripRR))

	frontGrip := (avgGripFL + avgGripFR) / 2
	rearGrip := (avgGripRL + avgGripRR) / 2
	if frontGrip > 0 && rearGrip > 0 {
		if frontGrip < rearGrip-0.03 {
			sb.WriteString("  ⚠ Grip delantero inferior → tendencia a SUBVIRAJE\n")
		} else if rearGrip < frontGrip-0.03 {
			sb.WriteString("  ⚠ Grip trasero inferior → tendencia a SOBREVIRAJE\n")
		}
	}
}

// --- Zone detection ---

// detectZones classifies each sample in a lap range and groups consecutive same-type samples.
func detectZones(r *channelResolver, start, end int) []zone {
	if end-start < 10 {
		return nil
	}

	brake := r.brake()
	steering := r.steering()
	latG := r.latG()
	throttle := r.throttle()
	speed := r.speed()

	// Dynamic steering threshold: 8% of max absolute steering in this range
	steerThreshold := 5.0
	if steering != nil {
		maxSteer := maxAbsRange(steering, start, end)
		if dynamic := maxSteer * 0.08; dynamic > steerThreshold {
			steerThreshold = dynamic
		}
	}

	n := end - start + 1
	types := make([]string, n)

	for i := start; i <= end; i++ {
		idx := i - start
		brk := safeIdx(brake, i)
		str := math.Abs(safeIdx(steering, i))
		lg := math.Abs(safeIdx(latG, i))
		thr := safeIdx(throttle, i)
		spd := safeIdx(speed, i)

		switch {
		case brk > 0.05:
			types[idx] = zoneTypeBraking
		case str > steerThreshold || lg > 0.3:
			types[idx] = zoneTypeCorner
		case thr > 0.8 && spd > 50:
			types[idx] = zoneTypeStraight
		default:
			// Transition: inherit from previous zone or mark as traction
			if idx > 0 {
				prev := types[idx-1]
				if prev == zoneTypeBraking || prev == zoneTypeCorner {
					types[idx] = zoneTypeTraction
				} else {
					types[idx] = zoneTypeStraight
				}
			} else {
				types[idx] = zoneTypeStraight
			}
		}
	}

	// Group consecutive same-type samples into zones
	var zones []zone
	if n == 0 {
		return zones
	}

	current := zone{Type: types[0], StartIdx: start, EndIdx: start}
	for i := 1; i < n; i++ {
		if types[i] == current.Type {
			current.EndIdx = start + i
		} else {
			if current.EndIdx-current.StartIdx >= 5 {
				zones = append(zones, current)
			}
			current = zone{Type: types[i], StartIdx: start + i, EndIdx: start + i}
		}
	}
	if current.EndIdx-current.StartIdx >= 5 {
		zones = append(zones, current)
	}

	return zones
}

// --- Helpers ---

func safeIdx(data []float64, i int) float64 {
	if data != nil && i >= 0 && i < len(data) {
		return data[i]
	}
	return 0
}

func sliceStats(data []float64) (min, max, avg float64) {
	if len(data) == 0 {
		return 0, 0, 0
	}
	min = data[0]
	max = data[0]
	sum := 0.0
	for _, v := range data {
		if v < min {
			min = v
		}
		if v > max {
			max = v
		}
		sum += v
	}
	avg = sum / float64(len(data))
	return
}

func avgRange(data []float64, start, end int) float64 {
	if data == nil || start < 0 || end < start {
		return 0
	}
	sum := 0.0
	count := 0
	for i := start; i <= end && i < len(data); i++ {
		sum += data[i]
		count++
	}
	if count == 0 {
		return 0
	}
	return sum / float64(count)
}

func maxRange(data []float64, start, end int) float64 {
	if data == nil || start < 0 || end < start {
		return 0
	}
	m := math.Inf(-1)
	for i := start; i <= end && i < len(data); i++ {
		if data[i] > m {
			m = data[i]
		}
	}
	if math.IsInf(m, -1) {
		return 0
	}
	return m
}

func minRange(data []float64, start, end int) float64 {
	if data == nil || start < 0 || end < start {
		return 0
	}
	m := math.Inf(1)
	for i := start; i <= end && i < len(data); i++ {
		if data[i] < m {
			m = data[i]
		}
	}
	if math.IsInf(m, 1) {
		return 0
	}
	return m
}

func maxAbsRange(data []float64, start, end int) float64 {
	if data == nil || start < 0 || end < start {
		return 0
	}
	m := 0.0
	for i := start; i <= end && i < len(data); i++ {
		a := math.Abs(data[i])
		if a > m {
			m = a
		}
	}
	return m
}

func lapRange(lapData []float64, lapNum int) (int, int) {
	start := -1
	end := -1
	for i, v := range lapData {
		if int(v) == lapNum {
			if start == -1 {
				start = i
			}
			end = i
		}
	}
	return start, end
}

func findValidLaps(lapData []float64) []int {
	seen := make(map[int]int)
	for _, v := range lapData {
		lap := int(v)
		if lap > 0 {
			seen[lap]++
		}
	}
	var laps []int
	for lap, count := range seen {
		if count >= 10 {
			laps = append(laps, lap)
		}
	}
	sort.Ints(laps)
	return laps
}

func findBestLap(td *domain.TelemetryData) int {
	stats := td.SessionStats()
	if len(stats.Laps) == 0 {
		return -1
	}
	best := stats.Laps[0]
	for _, ls := range stats.Laps[1:] {
		if ls.Duration > 0 && ls.Duration < best.Duration {
			best = ls
		}
	}
	return best.Lap
}
